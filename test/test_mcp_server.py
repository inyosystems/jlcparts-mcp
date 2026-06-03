import asyncio
import json
import sqlite3
import time
from unittest.mock import Mock

import pytest

from jlcparts.mcp_server import (
    CacheManager,
    build_arg_parser,
    build_config,
    create_mcp_server,
)
from jlcparts.query_cache import build_query_cache
from jlcparts.sourceDb import SourceDb
from test_query_service import _build_source_fixture, _parameters, _payload, _price_ranges


def _config(tmp_path, credentials=None, max_cache_age_hours=24):
    args = build_arg_parser().parse_args([
        "--cache", str(tmp_path / "cache.sqlite3"),
        "--query-cache", str(tmp_path / "query.sqlite3"),
        "--max-cache-age-hours", str(max_cache_age_hours),
    ])
    config = build_config(args)
    if credentials is not None:
        config.credentials = credentials
    return config


def _fresh_cache(tmp_path):
    config = _config(tmp_path)
    _build_source_fixture(config.cache_path)
    db = SourceDb(config.cache_path)
    db.setMeta("last_successful_refresh", str(int(time.time())))
    db.setMeta("last_refresh_error", "")
    db.close()
    build_query_cache(config.cache_path, config.query_cache_path)
    return config


def test_cli_credentials_override_env_without_persisting(monkeypatch, tmp_path):
    monkeypatch.setenv("JLCPCB_APP_ID", "env-app")
    monkeypatch.setenv("JLCPCB_ACCESS_KEY", "env-access")
    monkeypatch.setenv("JLCPCB_SECRET_KEY", "env-secret")
    args = build_arg_parser().parse_args([
        "--cache", str(tmp_path / "cache.sqlite3"),
        "--jlcpcb-app-id", "flag-app",
        "--jlcpcb-access-key", "flag-access",
        "--jlcpcb-secret-key", "flag-secret",
    ])

    config = build_config(args)

    assert config.credentials.app_id == "flag-app"
    assert config.credentials.access_key == "flag-access"
    assert config.credentials.secret_key == "flag-secret"
    assert config.cache_path.endswith("cache.sqlite3")
    assert config.query_cache_path.endswith("query-cache.sqlite3")
    assert "flag-app" not in config.cache_path


def test_cli_credentials_fall_back_to_env(monkeypatch, tmp_path):
    monkeypatch.setenv("JLCPCB_APP_ID", "env-app")
    monkeypatch.setenv("JLCPCB_ACCESS_KEY", "env-access")
    monkeypatch.setenv("JLCPCB_SECRET_KEY", "env-secret")
    args = build_arg_parser().parse_args(["--cache", str(tmp_path / "cache.sqlite3")])

    config = build_config(args)

    assert config.credentials.app_id == "env-app"
    assert config.credentials.access_key == "env-access"
    assert config.credentials.secret_key == "env-secret"


def test_missing_cache_blocks_read_and_returns_actionable_refresh_error(tmp_path):
    config = _config(tmp_path)
    refresh = Mock(side_effect=RuntimeError("missing credential"))
    manager = CacheManager(config, refresh_func=refresh)

    with pytest.raises(RuntimeError, match="Run refresh_cache"):
        manager.ensure_ready()

    refresh.assert_not_called()


def test_fresh_cache_does_not_refresh_before_query(tmp_path):
    config = _fresh_cache(tmp_path)
    refresh = Mock(side_effect=AssertionError("fresh cache should not refresh"))
    manager = CacheManager(config, refresh_func=refresh)

    with manager.query_service() as service:
        results = service.search_components(text_query="resistor", limit=1)

    assert results["total"] == 3
    refresh.assert_not_called()


def test_old_completed_cache_remains_readable_without_age_refresh(tmp_path):
    config = _fresh_cache(tmp_path)
    old = int(time.time()) - 365 * 24 * 3600
    db = SourceDb(config.cache_path)
    db.setMeta("last_successful_refresh", str(old))
    db.close()
    refresh = Mock(side_effect=AssertionError("old completed cache should not auto-refresh"))
    manager = CacheManager(config, refresh_func=refresh)

    status = manager.cache_status()
    with manager.query_service() as service:
        results = service.search_components(text_query="resistor", limit=1)

    assert status["source_stale"] is False
    assert status["last_full_api_refresh"] == old
    assert status["last_full_api_refresh_age_seconds"] >= 365 * 24 * 3600
    assert results["total"] == 3
    refresh.assert_not_called()


def test_explicit_refresh_runs_full_refresh_and_rebuilds_query_cache(tmp_path):
    config = _fresh_cache(tmp_path)
    refresh = Mock(return_value={"done": True, "count": 3})
    build_query = Mock(side_effect=build_query_cache)
    manager = CacheManager(
        config,
        refresh_func=refresh,
        build_query_func=build_query,
    )

    status = manager.refresh_cache(force=True, max_seconds=60)

    assert status["refreshed"] is True
    assert status["rebuilt_query_cache"] is True
    refresh.assert_called_once_with(
        config.cache_path,
        checkpoint=config.checkpoint_path,
        credentials=config.credentials,
        max_seconds=60,
    )
    build_query.assert_called_once_with(config.cache_path, config.query_cache_path)


def test_missing_query_built_at_is_stale_and_rebuilt_without_source_refresh(tmp_path):
    config = _fresh_cache(tmp_path)
    conn = sqlite3.connect(config.query_cache_path)
    try:
        conn.execute("DELETE FROM metadata WHERE key = 'built_at'")
        conn.commit()
    finally:
        conn.close()
    refresh = Mock(side_effect=AssertionError("fresh source should not refresh"))
    build_query = Mock(side_effect=build_query_cache)
    manager = CacheManager(
        config,
        refresh_func=refresh,
        build_query_func=build_query,
    )

    status = manager.cache_status()
    refreshed = manager.refresh_cache(force=False)

    assert status["source_stale"] is False
    assert status["query_stale"] is True
    assert refreshed["refreshed"] is False
    assert refreshed["rebuilt_query_cache"] is True
    refresh.assert_not_called()
    build_query.assert_called_once_with(config.cache_path, config.query_cache_path)


def test_checkpointed_explicit_refresh_does_not_rebuild_query_cache(tmp_path):
    config = _fresh_cache(tmp_path)
    refresh = Mock(return_value={"done": False, "count": 1000, "checkpointed": True})
    build_query = Mock(side_effect=AssertionError("checkpointed refresh should not rebuild index"))
    manager = CacheManager(
        config,
        refresh_func=refresh,
        build_query_func=build_query,
    )

    status = manager.refresh_cache(force=True, max_seconds=1)

    assert status["refreshed"] is True
    assert status["rebuilt_query_cache"] is False
    assert status["refresh_result"]["checkpointed"] is True
    build_query.assert_not_called()


def test_live_lookup_updates_existing_cached_component_and_rebuilds_query_cache(tmp_path):
    config = _fresh_cache(tmp_path)
    live_payload = _payload(
        "C1001",
        "Resistors",
        "Chip Resistor - Surface Mount",
        "R0603-10K-LIVE",
        "0603",
        "Live Manufacturer",
        "Basic",
        42,
        _price_ranges((1, 99, 0.02), (100, None, 0.01)),
        _parameters(Resistance="10kΩ", Package="0603"),
        "Live updated resistor",
    )
    website_detail = {
        "websiteComponentId": 123,
        "assemblyProcess": "SMT",
        "assemblyMode": "smtWeld",
        "lossNumber": 4,
        "leastNumber": 10,
    }
    live_lookup = Mock(return_value={
        "lcsc": "C1001",
        "official_payload": live_payload,
        "website_detail": website_detail,
        "normalized_component": {},
    })
    manager = CacheManager(config, live_lookup_func=live_lookup)

    result = manager.live_lookup_and_update_cache("C1001")

    with manager.query_service() as service:
        component = service.get_component("C1001")

    assert result["cache_update"]["updated"] is True
    assert component["mfr"] == "R0603-10K-LIVE"
    assert component["stock"] == 42
    assert component["website_component_id"] == "123"
    assert component["assembly_process"] == "SMT"
    assert component["attrition"]["lossNumber"] == 4
    assert component["attributes"]["Attrition"]["values"]["count"] == [4, "count"]


def test_fastmcp_lists_and_calls_tools_with_fresh_cache(tmp_path):
    config = _fresh_cache(tmp_path)
    mcp = create_mcp_server(config)

    async def exercise():
        tools = await mcp.list_tools()
        names = {tool.name for tool in tools}
        assert {
            "cache_status",
            "refresh_cache",
            "live_lookup_component",
            "list_categories",
            "list_attributes",
            "list_attribute_values",
            "search_components",
            "get_component",
            "compare_components",
            "search",
            "fetch",
        }.issubset(names)

        status = _tool_json(await mcp.call_tool("cache_status", {}))
        assert status["source_exists"] is True
        result = _tool_json(await mcp.call_tool("search", {"query": "resistor"}))
        assert result["total"] == 3
        component = _tool_json(await mcp.call_tool("fetch", {"id": "component:C1001"}))
        assert component["lcsc"] == "C1001"

    asyncio.run(exercise())


def test_fastmcp_tool_descriptions_explain_agent_workflow_and_filter_shapes(tmp_path):
    config = _fresh_cache(tmp_path)
    mcp = create_mcp_server(config)

    async def exercise():
        tools = {tool.name: tool for tool in await mcp.list_tools()}
        search_tool = tools["search_components"]
        search_schema = search_tool.inputSchema["properties"]

        assert "cache-only research/design tool" in search_tool.description
        assert "does not contact JLCPCB" in search_tool.description
        assert "final current confirmation" in search_tool.description
        assert "required_attributes" in search_schema
        assert "sort_direction" in search_schema
        assert "exact_filters accepts" in search_tool.description
        assert "numeric_filters accepts" in search_tool.description
        assert "library_types may include basic, extended, preferred" in search_tool.description
        assert "Required checkbox" in search_tool.description

        values_description = tools["list_attribute_values"].description
        assert "Cache-only research tool" in values_description
        assert "Pass values[].value directly" in values_description
        assert "numeric.ranges[].unit" in values_description

        live_description = tools["live_lookup_component"].description
        assert "after cache-based research/design" in live_description
        assert "Do not use this for broad search" in live_description
        assert "website assembly/detail enrichment" in live_description

        compare_tool = tools["compare_components"]
        compare_schema = compare_tool.inputSchema["properties"]
        assert "keep_order" in compare_schema
        assert "in_stock" in compare_schema
        assert "stock >= quantity" in compare_tool.description
        assert "does not contact JLCPCB" in compare_tool.description

        assert "Prefer search_components" in tools["search"].description
        assert "Cache-only compatibility wrapper" in tools["search"].description
        assert "Prefer get_component" in tools["fetch"].description
        assert "Cache-only compatibility wrapper" in tools["fetch"].description
        assert "image URLs" in tools["get_component"].description
        assert "Cache-only by default" in tools["get_component"].description
        assert "live_verify=true only after cache-based research is done" in tools["get_component"].description

    asyncio.run(exercise())


def _tool_json(result):
    return json.loads(result[0].text)
