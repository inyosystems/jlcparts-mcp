import asyncio
import json

from jlcparts.mcp_server import build_arg_parser, build_config, create_mcp_server
from test_compact_index import build_compact_index_fixture


def test_mcp_config_defaults_to_compact_index_without_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("JLCPCB_APP_ID", "ignored")
    args = build_arg_parser().parse_args(["--index", str(tmp_path / "mcp-index.sqlite3")])

    config = build_config(args)

    assert config.index_path.endswith("mcp-index.sqlite3")
    assert not hasattr(config, "credentials")


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


def _tool_json(result):
    text = result[0].text if isinstance(result, list) else result.content[0].text
    return json.loads(text)
