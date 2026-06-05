import argparse
import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .compact_index import DEFAULT_INDEX_NAME
from .compact_query import CompactQueryService


DEFAULT_INDEX_PATH = f"~/.cache/jlcparts/{DEFAULT_INDEX_NAME}"


@dataclass
class McpServerConfig:
    index_path: str
    host: str = "127.0.0.1"
    port: int = 8765


class CompactCacheManager:
    def __init__(self, config):
        self.config = config

    def cache_status(self):
        if not os.path.exists(self.config.index_path):
            return {
                "index_path": self.config.index_path,
                "index_exists": False,
                "ready": False,
                "remote_queries_for_cache_reads": False,
                "error": (
                    "Compact MCP index is missing. Run `jlcparts download-catalog` "
                    "and `jlcparts build-index` before using cache research tools."
                ),
            }
        with self.query_service() as service:
            return service.cache_status()

    def query_service(self):
        if not os.path.exists(self.config.index_path):
            raise RuntimeError(
                "Compact MCP index is missing. Run `jlcparts download-catalog` "
                "and `jlcparts build-index` first. Normal MCP read tools do not "
                "start bulk catalog downloads or index builds."
            )
        return CompactQueryService(self.config.index_path)

    def writable_query_service(self):
        if not os.path.exists(self.config.index_path):
            raise RuntimeError(
                "Compact MCP index is missing. Run `jlcparts download-catalog` "
                "and `jlcparts build-index` first."
            )
        return CompactQueryService(self.config.index_path, read_only=False)


def create_mcp_server(config):
    manager = CompactCacheManager(config)
    mcp = FastMCP(
        "JLCParts MCP",
        instructions=(
            "JLCParts is cache-first for electronic design research. Use the "
            "local compact SQLite index for fast part discovery, parametric "
            "filtering, stock/price comparison, and board-design iteration. "
            "The cache tools do not contact JLCPCB. After research has narrowed "
            "to exact LCSC candidates, use lookup_component_website_detail or "
            "get_component(include_website_detail=true) for a public website "
            "detail check on one part at a time. The upstream generated catalog "
            "is a recently-stocked PCBA design dataset, not a full mirror of "
            "every reference shown on live JLCPCB category pages. Bulk catalog download and "
            "index build are CLI operations: `jlcparts download-catalog` and "
            "`jlcparts build-index`."
        ),
        host=config.host,
        port=config.port,
    )

    async def run_blocking(func):
        return await asyncio.to_thread(func)

    @mcp.tool()
    async def cache_status():
        """Return compact index readiness and upstream catalog metadata.

        Cache-only status tool; does not contact JLCPCB. Use this before
        research to confirm the local compact MCP index exists and to inspect
        upstream catalog source URL, source timestamp, build timestamp, schema
        version, and component count.
        """
        return await run_blocking(manager.cache_status)

    @mcp.tool()
    async def list_categories(search: str | None = None, limit: int = 200):
        """List JLCPCB component categories available in the local index.

        Cache-only research tool; does not contact JLCPCB. Use this to obtain
        category_id values for search_components. The optional search text
        filters category paths such as resistor, capacitor, connector, or
        voltage regulator.
        """
        def query():
            with manager.query_service() as service:
                return service.list_categories(search=search, limit=limit)

        return await run_blocking(query)

    @mcp.tool()
    async def list_attributes(
        category_ids: list[int] | None = None,
        text_query: str | None = None,
        limit: int = 100,
    ):
        """List normalized attributes present in a local candidate set.

        Cache-only research tool; does not contact JLCPCB. Use after selecting
        category_ids or text_query to discover attribute names for exact_filters,
        numeric_filters, required_attributes, sort_attribute, include_attributes,
        and compare_components. Returns each attribute name, matching component
        count, and normalized quantity types such as resistance, voltage,
        capacitance, current, temperature, count, identifier, and string.
        """
        def query():
            with manager.query_service() as service:
                return service.list_attributes(category_ids, text_query, limit)

        return await run_blocking(query)

    @mcp.tool()
    async def list_attribute_values(
        attribute: str,
        category_ids: list[int] | None = None,
        text_query: str | None = None,
        limit: int = 100,
    ):
        """List exact values and numeric ranges for one local attribute.

        Cache-only research tool; does not contact JLCPCB. Pass attribute names
        returned by list_attributes. Copy a values[].value object directly into
        search_components exact_filters. Use numeric.ranges[].unit with
        numeric_filters for range searches.
        """
        def query():
            with manager.query_service() as service:
                return service.list_attribute_values(attribute, category_ids, text_query, limit)

        return await run_blocking(query)

    @mcp.tool()
    async def search_components(
        category_ids: list[int] | None = None,
        text_query: str = "",
        exact_filters: dict | list | None = None,
        numeric_filters: list[dict] | None = None,
        required_attributes: list[str] | None = None,
        quantity: int = 1,
        in_stock: bool = False,
        library_types: list[str] | None = None,
        rohs: bool | None = None,
        eccn: str | None = None,
        assembly: bool | None = None,
        assembly_process: str | None = None,
        assembly_mode: str | None = None,
        has_website_detail: bool | None = None,
        category_path: str | None = None,
        manufacturers: list[str] | None = None,
        packages: list[str] | None = None,
        stock_min: int | None = None,
        basic: bool | None = None,
        preferred: bool | None = None,
        discontinued: bool | None = None,
        sort: str = "relevance",
        sort_direction: str = "asc",
        sort_attribute: str | None = None,
        offset: int = 0,
        limit: int = 25,
        include_attributes: list[str] | None = None,
    ):
        """Search JLCPCB PCBA components in the local compact index.

        Primary cache-only research/design tool; does not contact JLCPCB. Use
        it for broad search, parametric exploration, category narrowing,
        stock/price filtering, and candidate selection. After narrowing to exact
        LCSC codes, use lookup_component_website_detail for a public website
        detail check. text_query searches LCSC, MFR part, description,
        manufacturer, package, and category path. exact_filters accepts
        {attribute_name: value_or_values}; copy value objects from
        list_attribute_values. numeric_filters accepts objects such as
        {name: "Resistance", unit: "resistance", min: 9000, max: 11000}.
        quantity controls selected_price and in_stock. library_types may include
        basic, extended, preferred. sort supports relevance, lcsc, mfr,
        manufacturer, description, category, stock, price, library_type, or use
        sort_attribute for an attribute column.
        """
        def query():
            with manager.query_service() as service:
                return service.search_components(
                    category_ids=category_ids,
                    text_query=text_query,
                    exact_filters=exact_filters,
                    numeric_filters=numeric_filters,
                    required_attributes=required_attributes,
                    quantity=quantity,
                    in_stock=in_stock,
                    library_types=library_types,
                    rohs=rohs,
                    eccn=eccn,
                    assembly=assembly,
                    assembly_process=assembly_process,
                    assembly_mode=assembly_mode,
                    has_website_detail=has_website_detail,
                    category_path=category_path,
                    manufacturers=manufacturers,
                    packages=packages,
                    stock_min=stock_min,
                    basic=basic,
                    preferred=preferred,
                    discontinued=discontinued,
                    sort=sort,
                    sort_direction=sort_direction,
                    sort_attribute=sort_attribute,
                    offset=offset,
                    limit=limit,
                    include_attributes=include_attributes,
                )

        return await run_blocking(query)

    @mcp.tool()
    async def get_component(lcsc: str, include_website_detail: bool = False):
        """Return full local detail for one LCSC component code.

        Cache-only by default; does not contact JLCPCB unless
        include_website_detail=true. Use during research/design to inspect one
        cached candidate. Set include_website_detail only after narrowing to a
        candidate LCSC part; that path may fetch the public JLCPCB website for
        that exact code and returns website data separately from upstream
        catalog fields.
        """
        def query():
            if not include_website_detail:
                with manager.query_service() as service:
                    return service.get_component(lcsc)

            with manager.writable_query_service() as service:
                component = service.get_component(lcsc)
                if component is None:
                    return None
                return {
                    **component,
                    "website_detail_lookup": service.lookup_component_website_detail(lcsc),
                    "field_sources": {
                        "catalog": "upstream generated yaqwsx catalog",
                        "website_detail_lookup": "public JLCPCB website exact lookup",
                    },
                }

        return await run_blocking(query)

    @mcp.tool()
    async def lookup_component_website_detail(lcsc: str):
        """Fetch public website detail for one exact LCSC candidate.

        Use only after cache-based research/design has narrowed to a specific
        LCSC code such as C25804. This is not a broad search API. It may contact
        the public JLCPCB/LCSC website for this one component and returns
        best-effort detail or an actionable failure message. No JLCPCB
        credentials are used.
        """
        def query():
            with manager.writable_query_service() as service:
                return service.lookup_component_website_detail(lcsc)

        return await run_blocking(query)

    @mcp.tool()
    async def compare_components(
        lcsc_codes: list[str],
        quantity: int = 1,
        attributes: list[str] | None = None,
        only_differences: bool = False,
        keep_order: bool = True,
        in_stock: bool = False,
    ):
        """Compare known LCSC components for board-design part selection.

        Cache-only research/design tool; does not contact JLCPCB. Use this to
        compare local candidate parts before exact public website detail checks.
        quantity selects price tiers and, when in_stock is true, filters
        returned components to stock >= quantity. attributes limits compared
        normalized attributes. only_differences returns only attributes whose
        normalized values differ across found components.
        """
        def query():
            with manager.query_service() as service:
                return service.compare_components(
                    lcsc_codes,
                    quantity=quantity,
                    attributes=attributes,
                    only_differences=only_differences,
                    keep_order=keep_order,
                    in_stock=in_stock,
                )

        return await run_blocking(query)

    @mcp.tool()
    async def search(query: str):
        """Generic MCP search wrapper for JLCPCB/LCSC components.

        Cache-only compatibility wrapper; does not contact JLCPCB. Use for
        simple text lookup when an MCP client expects search(query). Prefer
        search_components for category, stock, price, Basic/Extended/Preferred,
        exact attribute, or numeric parametric filtering.
        """
        def search_query():
            with manager.query_service() as service:
                return service.search_components(text_query=query, limit=10)

        return await run_blocking(search_query)

    @mcp.tool()
    async def fetch(id: str):
        """Generic MCP fetch wrapper for one cached component.

        Cache-only compatibility wrapper; does not contact JLCPCB. id may be a
        plain LCSC code such as C25804 or a prefixed id such as component:C25804.
        Returns the same local component detail as get_component with
        include_website_detail=false.
        """
        def query():
            lcsc = str(id).split(":", 1)[-1]
            with manager.query_service() as service:
                return service.get_component(lcsc)

        return await run_blocking(query)

    return mcp


def build_config(args):
    return McpServerConfig(
        index_path=os.path.abspath(os.path.expanduser(args.index)),
        host=args.host,
        port=args.port,
    )


def build_arg_parser():
    parser = argparse.ArgumentParser(
        prog="jlcparts-mcp",
        description="Run a local cache-first JLCPCB PCBA component search MCP server.",
    )
    parser.add_argument("--index", default=DEFAULT_INDEX_PATH, help="Compact MCP index SQLite path")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="MCP transport; http maps to streamable HTTP",
    )
    parser.add_argument("--host", default="127.0.0.1", help="HTTP bind host")
    parser.add_argument("--port", type=int, default=8765, help="HTTP bind port")
    return parser


def main(argv=None):
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    config = build_config(args)
    mcp = create_mcp_server(config)
    transport = "streamable-http" if args.transport == "http" else "stdio"
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
