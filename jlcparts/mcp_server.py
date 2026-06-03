import argparse
import json
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .jlcpcb import JlcPcbCredentials, live_lookup_component as jlc_live_lookup_component
from .query_cache import QUERY_CACHE_FORMAT, build_query_cache
from .query_service import CachedComponentQueryService
from .sourceDb import SOURCE_DB_FORMAT, SourceDb, detectSourceDb
from .ui import refreshSourceDb


DEFAULT_CACHE_PATH = "~/.cache/jlcparts/cache.sqlite3"
DEFAULT_QUERY_CACHE_NAME = "query-cache.sqlite3"


@dataclass
class McpServerConfig:
    cache_path: str
    query_cache_path: str
    checkpoint_path: str
    credentials: JlcPcbCredentials
    host: str = "127.0.0.1"
    port: int = 8765


class CacheManager:
    def __init__(
        self,
        config,
        refresh_func=refreshSourceDb,
        build_query_func=build_query_cache,
        live_lookup_func=jlc_live_lookup_component,
    ):
        self.config = config
        self.refresh_func = refresh_func
        self.build_query_func = build_query_func
        self.live_lookup_func = live_lookup_func

    def cache_status(self):
        source_path = self.config.cache_path
        query_path = self.config.query_cache_path
        now = int(time.time())
        source_exists = os.path.exists(source_path)
        source_format = detectSourceDb(source_path) if source_exists else None
        source_meta = self._source_meta(source_path, source_format)
        last_success = _int_or_none(source_meta.get("last_successful_refresh"))
        last_component_fetch = self._latest_component_fetch(source_path, source_format)
        last_website_enrichment = _int_or_none(
            source_meta.get("last_successful_website_enrichment")
        )
        last_live_component_update = _int_or_none(
            source_meta.get("last_live_component_update")
        )
        latest_source_change = max(
            value for value in [last_success, last_website_enrichment, last_live_component_update]
            if value is not None
        ) if any(value is not None for value in [last_success, last_website_enrichment, last_live_component_update]) else None
        age_seconds = None if last_success is None else max(0, now - last_success)
        source_stale = (
            not source_exists
            or source_format != SOURCE_DB_FORMAT
            or last_success is None
        )

        query_meta = self._query_meta(query_path)
        query_exists = os.path.exists(query_path)
        query_format = query_meta.get("format") if query_exists else None
        query_built_at = _int_or_none(query_meta.get("built_at"))
        query_stale = (
            not query_exists
            or query_format != QUERY_CACHE_FORMAT
            or query_built_at is None
            or (
                latest_source_change is not None
                and query_built_at is not None
                and query_built_at < latest_source_change
            )
        )

        component_count = _int_or_none(source_meta.get("component_count"))
        if component_count is None:
            component_count = self._component_count(source_path, source_format)

        return {
            "cache_path": source_path,
            "query_cache_path": query_path,
            "checkpoint_path": self.config.checkpoint_path,
            "source_exists": source_exists,
            "source_format": source_format,
            "query_exists": query_exists,
            "query_format": query_format,
            "last_successful_refresh": last_success,
            "last_full_api_refresh": last_success,
            "last_component_fetch": last_component_fetch,
            "last_successful_website_enrichment": last_website_enrichment,
            "last_live_component_update": last_live_component_update,
            "last_full_api_refresh_age_seconds": age_seconds,
            "freshness_age_seconds": age_seconds,
            "stale": source_stale or query_stale,
            "source_stale": source_stale,
            "query_stale": query_stale,
            "source_ready": not source_stale,
            "refresh_checkpoint": self._checkpoint_status(self.config.checkpoint_path),
            "component_count": component_count,
            "source_schema_version": source_meta.get("format"),
            "query_schema_version": query_meta.get("format"),
            "index_version": query_meta.get("format"),
            "credential_available": _credentials_available(self.config.credentials),
            "last_refresh_error": source_meta.get("last_refresh_error") or None,
            "last_website_enrichment_error": source_meta.get("last_website_enrichment_error") or None,
        }

    def refresh_cache(self, force=False, max_seconds=None):
        status = self.cache_status()
        if not force and not status["stale"]:
            return {"refreshed": False, **status}

        Path(self.config.cache_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        Path(self.config.query_cache_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        refresh_result = None
        if force or status["source_stale"]:
            refresh_result = self.refresh_func(
                self.config.cache_path,
                checkpoint=self.config.checkpoint_path,
                credentials=self.config.credentials,
                max_seconds=max_seconds,
            )
        rebuilt_query_cache = False
        if refresh_result is None or refresh_result.get("done"):
            self.build_query_func(self.config.cache_path, self.config.query_cache_path)
            rebuilt_query_cache = True
        return {
            "refreshed": refresh_result is not None,
            "rebuilt_query_cache": rebuilt_query_cache,
            "refresh_result": refresh_result,
            "monitoring": (
                "Full catalog refresh can take minutes or longer. If refresh_result.checkpointed "
                "is true, call cache_status to monitor refresh_checkpoint and call refresh_cache "
                "again to resume."
            ),
            **self.cache_status(),
        }

    def ensure_ready(self):
        status = self.cache_status()
        if status["source_stale"]:
            raise RuntimeError(
                "JLCParts source cache is missing, invalid, or has no completed full "
                "JLCPCB OpenAPI refresh. Run `jlcparts refresh-cache --cache ...` "
                "from the command line before using read tools. "
                "A full catalog refresh can take minutes or longer and should be "
                "monitored from the command line."
            )
        if status["query_stale"]:
            try:
                self.build_query_func(self.config.cache_path, self.config.query_cache_path)
            except Exception as e:
                raise RuntimeError(
                    f"JLCParts query cache could not be rebuilt: {type(e).__name__}: {e}"
                ) from None
        return self.cache_status()

    def query_service(self):
        self.ensure_ready()
        return CachedComponentQueryService(self.config.query_cache_path)

    def live_lookup_component(self, lcsc, include_website_detail=True):
        return self.live_lookup_func(
            lcsc=lcsc,
            credentials=self.config.credentials,
            include_website_detail=include_website_detail,
        )

    def live_lookup_and_update_cache(self, lcsc, include_website_detail=True):
        result = self.live_lookup_component(lcsc, include_website_detail)
        result["cache_update"] = self._update_cached_component_from_live_result(result)
        return result

    def _update_cached_component_from_live_result(self, result):
        status = self.cache_status()
        if not status["source_exists"] or status["source_format"] != SOURCE_DB_FORMAT:
            return {"updated": False, "reason": "source cache is not available"}

        lcsc = result.get("lcsc")
        official_payload = result.get("official_payload")
        if not lcsc or not official_payload:
            return {"updated": False, "reason": "live result has no official payload"}

        db = SourceDb(self.config.cache_path)
        try:
            if not db.exists(lcsc):
                return {"updated": False, "reason": "component is not present in the cache"}
            payload = official_payload
            website_detail = result.get("website_detail")
            if isinstance(website_detail, dict):
                payload = {**official_payload, **website_detail}
            db.updateJlcPayload(payload, flag=1)
            db.setMeta("last_live_component_update", str(int(time.time())))
        finally:
            db.close()

        try:
            self.build_query_func(self.config.cache_path, self.config.query_cache_path)
            return {"updated": True, "rebuilt_query_cache": True}
        except Exception as e:
            return {
                "updated": True,
                "rebuilt_query_cache": False,
                "query_cache_error": f"{type(e).__name__}: {e}",
            }

    def _source_meta(self, source_path, source_format):
        if source_format != SOURCE_DB_FORMAT:
            return {}
        db = SourceDb(source_path, create=False)
        try:
            return db.metaDict()
        finally:
            db.close()

    def _query_meta(self, query_path):
        if not os.path.exists(query_path):
            return {}
        conn = sqlite3.connect(query_path)
        try:
            return {
                row[0]: row[1]
                for row in conn.execute("SELECT key, value FROM metadata")
            }
        except sqlite3.Error:
            return {}
        finally:
            conn.close()

    def _component_count(self, source_path, source_format):
        if source_format != SOURCE_DB_FORMAT:
            return None
        db = SourceDb(source_path, create=False)
        try:
            return db.componentCount()
        finally:
            db.close()

    def _latest_component_fetch(self, source_path, source_format):
        if source_format != SOURCE_DB_FORMAT:
            return None
        db = SourceDb(source_path, create=False)
        try:
            row = db.conn.execute(
                "SELECT MAX(fetched_at) FROM jlc_components WHERE present = 1"
            ).fetchone()
            return None if row is None or row[0] is None else int(row[0])
        finally:
            db.close()

    def _checkpoint_status(self, checkpoint_path):
        if not checkpoint_path or not os.path.exists(checkpoint_path):
            return None
        try:
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}


def create_mcp_server(config):
    manager = CacheManager(config)
    mcp = FastMCP(
        "JLCParts MCP",
        instructions=(
            "JLCParts is cache-first for electronic design research. Use the "
            "local SQLite cache tools for fast exploration, part discovery, "
            "parametric filtering, price/stock comparison, and board-design "
            "iteration: cache_status, list_categories, list_attributes, "
            "list_attribute_values, search_components, get_component, and "
            "compare_components. These cached read tools do not contact JLCPCB. "
            "After research has narrowed the choice to specific LCSC parts, use "
            "live_lookup_component or get_component(live_verify=true) to confirm "
            "current official JLCPCB data and website enrichment for final "
            "selection. Full catalog refresh is intentionally not exposed as an "
            "MCP tool because it can exceed client tool-call timeouts; run "
            "`jlcparts refresh-cache` from the command line instead."
        ),
        host=config.host,
        port=config.port,
    )

    @mcp.tool()
    def cache_status():
        """Return cache readiness for local JLCPCB part search.

        Use this before research to inspect the local cache. The
        response reports source/query cache paths, staleness, component count,
        last full official API refresh, last successful website enrichment, and
        whether JLCPCB OpenAPI credentials are available for explicit refresh or
        final live checks. This status call does not contact JLCPCB.
        """
        return manager.cache_status()

    @mcp.tool()
    def live_lookup_component(lcsc: str, include_website_detail: bool = True):
        """Confirm one selected LCSC part against JLCPCB right now.

        Use after cache-based research/design has narrowed the choice to an
        exact part. Do not use this for broad search or parametric exploration;
        use search_components and related cache tools for that. lcsc is an LCSC
        code such as C25804. Returns official OpenAPI payload, normalized
        component summary, and best-effort website assembly/detail enrichment
        when include_website_detail is true, which is the default.
        When the component already exists in the local cache, the cached source
        row is opportunistically updated from the live official payload plus
        website enrichment and the query index is rebuilt. Requires JLCPCB
        OpenAPI credentials for the official payload.
        """
        return manager.live_lookup_and_update_cache(lcsc, include_website_detail)

    @mcp.tool()
    def list_categories(search: str | None = None):
        """List JLCPCB component categories and subcategories for search.

        Cache-only research tool; does not contact JLCPCB. Use this to obtain
        category_ids for search_components. The optional search text filters
        category/subcategory names, e.g. "resistor", "capacitor", "connector",
        or "voltage regulator".
        """
        with manager.query_service() as service:
            return service.list_categories(search=search)

    @mcp.tool()
    def list_attributes(
        category_ids: list[int] | None = None,
        text_query: str | None = None,
        limit: int = 100,
    ):
        """List normalized attributes available in a candidate result set.

        Cache-only research tool; does not contact JLCPCB. Use after choosing
        category_ids and/or text_query to discover attribute names for
        exact_filters, numeric_filters, required_attributes, sort_attribute,
        include_attributes, and compare_components attributes. Returns each
        attribute name, component count, and normalized quantity types such as
        resistance, voltage, capacitance, temperature, current, package
        identifiers, and string labels.
        """
        with manager.query_service() as service:
            return service.list_attributes(category_ids, text_query, limit)

    @mcp.tool()
    def list_attribute_values(
        attribute: str,
        category_ids: list[int] | None = None,
        text_query: str | None = None,
        limit: int = 100,
    ):
        """List legal exact-filter values and numeric ranges for one attribute.

        Cache-only research tool; does not contact JLCPCB. Use attribute names
        returned by list_attributes. Each values[] item has display text for
        humans, count, quantity_types, value, and value_json.
        Pass values[].value directly into search_components exact_filters, for
        example exact_filters={"Package": value}. If numeric is present, use
        search_components numeric_filters with shape {name, unit, value_name?,
        min?, max?}; units come from numeric.ranges[].unit.
        """
        with manager.query_service() as service:
            return service.list_attribute_values(attribute, category_ids, text_query, limit)

    @mcp.tool()
    def search_components(
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
        sort: str = "relevance",
        sort_direction: str = "asc",
        sort_attribute: str | None = None,
        offset: int = 0,
        limit: int = 25,
        include_attributes: list[str] | None = None,
    ):
        """Search JLCPCB PCBA assembly components with parametric filters.

        Primary cache-only research/design tool; does not contact JLCPCB. Use
        this for fast broad search, parametric exploration, stock/price
        filtering, and candidate selection. After selecting exact LCSC codes,
        call live_lookup_component for final current confirmation. Use
        category_ids from list_categories and attribute names/values from
        list_attributes/list_attribute_values. text_query is full-text search
        over LCSC, MFR part, manufacturer, description, category, package, and
        attributes. exact_filters accepts {attribute_name: value_or_values};
        copy value objects from list_attribute_values(...).values[].value.
        numeric_filters accepts objects like {name: "Resistance", unit:
        "resistance", min: 9000, max: 11000} or adds value_name for multi-value
        ranges such as temperature min/max. required_attributes requires an
        attribute to exist regardless of value, matching the web UI Required checkbox.
        quantity selects price tiers and controls in_stock
        (stock >= quantity). library_types may include basic, extended, preferred.
        sort supports relevance, lcsc, mfr, manufacturer,
        description, category, stock, price, library_type; sort_attribute sorts
        by a normalized attribute instead. Web UI column labels such as MFR,
        LCSC, Basic/Extended, Stock, and Price are accepted as sort aliases.
        sort_direction is asc or desc. include_attributes limits returned
        attributes; omit it for full detail.
        """
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
                sort=sort,
                sort_direction=sort_direction,
                sort_attribute=sort_attribute,
                offset=offset,
                limit=limit,
                include_attributes=include_attributes,
            )

    @mcp.tool()
    def get_component(lcsc: str, live_verify: bool = False):
        """Return full cached detail for one LCSC component code.

        Cache-only by default; does not contact JLCPCB unless live_verify=true.
        Use during research/design to inspect one cached candidate. lcsc is an
        LCSC code such as C25804. Returns MFR part, manufacturer, category,
        package, stock, price tiers, selected links, datasheet, image URLs,
        normalized attributes, RoHS/ECCN, assembly fields, and any cached
        website enrichment such as website detail IDs and attrition/minimum-order
        metadata. Set live_verify=true only after cache-based research is done
        and you need current official JLCPCB confirmation for this exact part.
        """
        with manager.query_service() as service:
            component = service.get_component(lcsc)
        if component is not None and live_verify:
            component = {
                **component,
                "live_verification": manager.live_lookup_and_update_cache(lcsc),
            }
        return component

    @mcp.tool()
    def compare_components(
        lcsc_codes: list[str],
        quantity: int = 1,
        attributes: list[str] | None = None,
        only_differences: bool = False,
        keep_order: bool = True,
        in_stock: bool = False,
    ):
        """Compare known LCSC components for board-design part selection.

        Cache-only research/design tool; does not contact JLCPCB. Use this to
        compare cached candidates before final live verification. lcsc_codes is
        a list such as ["C25804", "C21190"]. quantity selects price tiers and,
        when in_stock is true, filters returned components to stock >= quantity.
        By default components preserve input order; set keep_order false to sort
        by LCSC. attributes limits compared normalized attributes; omit it to
        consider all attributes. only_differences true returns only attributes
        whose normalized values differ across found components. Missing codes
        are reported in missing_lcsc.
        """
        with manager.query_service() as service:
            return service.compare_components(
                lcsc_codes,
                quantity=quantity,
                attributes=attributes,
                only_differences=only_differences,
                keep_order=keep_order,
                in_stock=in_stock,
            )

    @mcp.tool()
    def search(query: str):
        """Generic MCP search wrapper for JLCPCB/LCSC components.

        Cache-only compatibility wrapper; does not contact JLCPCB. Use for
        simple text lookup when the MCP client expects a generic search(query)
        tool. Returns the first cached component matches for terms like "0603
        10k resistor" or "C25804". Prefer search_components for category,
        stock, price, Basic/Extended/Preferred, exact attribute, or numeric
        parametric filtering.
        """
        with manager.query_service() as service:
            return service.search_components(text_query=query, limit=10)

    @mcp.tool()
    def fetch(id: str):
        """Generic MCP fetch wrapper for one JLCPCB/LCSC component.

        Cache-only compatibility wrapper; does not contact JLCPCB. id may be a
        plain LCSC code such as C25804 or a prefixed id such as component:C25804.
        Returns the same cached component detail as get_component without live
        verification. Prefer get_component when you need to choose live_verify
        explicitly.
        """
        lcsc = str(id).split(":", 1)[-1]
        with manager.query_service() as service:
            return service.get_component(lcsc)

    return mcp


def build_config(args):
    cache_path = os.path.abspath(os.path.expanduser(args.cache))
    query_cache = args.query_cache
    if query_cache is None:
        query_cache = os.path.join(os.path.dirname(cache_path), DEFAULT_QUERY_CACHE_NAME)
    query_cache_path = os.path.abspath(os.path.expanduser(query_cache))
    checkpoint_path = os.path.join(os.path.dirname(cache_path), "refresh-checkpoint.json")
    return McpServerConfig(
        cache_path=cache_path,
        query_cache_path=query_cache_path,
        checkpoint_path=checkpoint_path,
        credentials=JlcPcbCredentials(
            app_id=args.jlcpcb_app_id or os.environ.get("JLCPCB_APP_ID"),
            access_key=args.jlcpcb_access_key or os.environ.get("JLCPCB_ACCESS_KEY"),
            secret_key=args.jlcpcb_secret_key or os.environ.get("JLCPCB_SECRET_KEY"),
        ),
        host=args.host,
        port=args.port,
    )


def build_arg_parser():
    parser = argparse.ArgumentParser(
        prog="jlcparts-mcp",
        description="Run a JLCPCB PCBA component search MCP server.",
    )
    parser.add_argument("--cache", default=DEFAULT_CACHE_PATH, help="Source cache SQLite path")
    parser.add_argument("--query-cache", default=None, help="Query index SQLite path")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="MCP transport; http maps to streamable HTTP",
    )
    parser.add_argument("--host", default="127.0.0.1", help="HTTP bind host")
    parser.add_argument("--port", type=int, default=8765, help="HTTP bind port")
    parser.add_argument(
        "--max-cache-age-hours",
        type=float,
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--jlcpcb-app-id", default=None, help="JLCPCB OpenAPI app id")
    parser.add_argument("--jlcpcb-access-key", default=None, help="JLCPCB OpenAPI access key")
    parser.add_argument("--jlcpcb-secret-key", default=None, help="JLCPCB OpenAPI secret key")
    return parser


def _credentials_available(credentials):
    return bool(credentials.app_id and credentials.access_key and credentials.secret_key)


def _int_or_none(value):
    try:
        return None if value in [None, ""] else int(value)
    except (TypeError, ValueError):
        return None


def main(argv=None):
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    config = build_config(args)
    mcp = create_mcp_server(config)
    transport = "streamable-http" if args.transport == "http" else "stdio"
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
