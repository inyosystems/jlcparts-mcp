import asyncio
import json
import time

from jlcparts.mcp_server import (
    CompactCacheManager,
    build_arg_parser,
    build_config,
    create_mcp_server,
    validate_bind_args,
)
from test_compact_index import build_compact_index_fixture


def test_mcp_config_defaults_to_compact_index_without_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("JLCPCB_APP_ID", "ignored")
    args = build_arg_parser().parse_args(["--index", str(tmp_path / "mcp-index.sqlite3")])

    config = build_config(args)

    assert config.index_path.endswith("mcp-index.sqlite3")
    assert not hasattr(config, "credentials")


def test_http_transport_rejects_non_loopback_host_without_explicit_opt_in():
    args = build_arg_parser().parse_args(["--transport", "http", "--host", "0.0.0.0"])

    assert validate_bind_args(args) == (
        "--transport http only binds to loopback hosts by default; "
        "pass --allow-remote-http to bind 0.0.0.0"
    )


def test_http_transport_allows_non_loopback_host_with_explicit_opt_in():
    args = build_arg_parser().parse_args([
        "--transport",
        "http",
        "--host",
        "0.0.0.0",
        "--allow-remote-http",
    ])

    assert validate_bind_args(args) is None


def test_fastmcp_lists_compact_cache_first_tools(tmp_path):
    index_path = build_compact_index_fixture(tmp_path)
    config = build_config(build_arg_parser().parse_args(["--index", str(index_path)]))
    mcp = create_mcp_server(config)

    async def exercise():
        tools = await mcp.list_tools()
        by_name = {tool.name: tool for tool in tools}
        assert {
            "cache_status",
            "list_categories",
            "list_attributes",
            "list_attribute_values",
            "search_components",
            "get_component",
            "lookup_component_website_detail",
            "compare_components",
            "search",
            "fetch",
        }.issubset(by_name)
        assert "refresh_cache" not in by_name
        assert "live_lookup_component" not in by_name
        descriptions = "\n".join(tool.description or "" for tool in tools)
        assert "cache-only" in descriptions
        assert "does not contact JLCPCB" in descriptions
        assert "after narrowing" in descriptions
        assert "public website" in descriptions

        status = _tool_json(await mcp.call_tool("cache_status", {}))
        assert status["ready"] is True
        assert status["remote_queries_for_cache_reads"] is False
        result = _tool_json(await mcp.call_tool("search", {"query": "resistor"}))
        assert result["total"] == 2
        component = _tool_json(await mcp.call_tool("fetch", {"id": "component:C1001"}))
        assert component["lcsc"] == "C1001"

    asyncio.run(exercise())


def test_mcp_get_component_without_website_detail_uses_read_only_connection(tmp_path, monkeypatch):
    index_path = build_compact_index_fixture(tmp_path)
    config = build_config(build_arg_parser().parse_args(["--index", str(index_path)]))
    writable_calls = []
    original_writable_query_service = CompactCacheManager.writable_query_service

    def track_writable_query_service(self):
        writable_calls.append(True)
        return original_writable_query_service(self)

    monkeypatch.setattr(CompactCacheManager, "writable_query_service", track_writable_query_service)
    mcp = create_mcp_server(config)

    async def exercise():
        component = _tool_json(await mcp.call_tool("get_component", {"lcsc": "C1001"}))
        assert component["lcsc"] == "C1001"

    asyncio.run(exercise())

    assert writable_calls == []


def test_mcp_tool_calls_can_overlap_for_multiple_clients(tmp_path, monkeypatch):
    index_path = build_compact_index_fixture(tmp_path)
    config = build_config(build_arg_parser().parse_args(["--index", str(index_path)]))
    original_query_service = CompactCacheManager.query_service

    class SlowQueryService:
        def __init__(self, wrapped):
            self.wrapped = wrapped

        def __enter__(self):
            self.service = self.wrapped.__enter__()
            return self

        def __exit__(self, exc_type, exc, traceback):
            return self.wrapped.__exit__(exc_type, exc, traceback)

        def search_components(self, *args, **kwargs):
            time.sleep(0.25)
            return self.service.search_components(*args, **kwargs)

    def slow_query_service(self):
        return SlowQueryService(original_query_service(self))

    monkeypatch.setattr(CompactCacheManager, "query_service", slow_query_service)
    mcp = create_mcp_server(config)

    async def exercise():
        start = time.perf_counter()
        results = await asyncio.gather(
            mcp.call_tool("search", {"query": "resistor"}),
            mcp.call_tool("search", {"query": "capacitor"}),
        )
        elapsed = time.perf_counter() - start
        return results, elapsed

    results, elapsed = asyncio.run(exercise())

    assert [_tool_json(result)["total"] for result in results] == [2, 1]
    assert elapsed < 0.45


def _tool_json(result):
    text = result[0].text if isinstance(result, list) else result.content[0].text
    return json.loads(text)
