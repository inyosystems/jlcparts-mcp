# Compact MCP Catalog Index Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current unusably large MCP query cache with a compact SQLite index built from the upstream generated `jlcparts` catalog. The MCP server should support fast JLCPCB PCBA research workflows, keep normal MCP searches fully local, and avoid any need for JLCPCB API credentials.

**Architecture:** Use the canonical upstream generated catalog from `yaqwsx/jlcparts` as the bulk data source. Download its manifest and referenced shards, validate the schema, and build a separate read-optimized SQLite MCP index from it. The index stays close to `yaqwsx` data shapes so future upstream updates are easy to adopt, while using the useful idea observed in `dougy83/jlcparts`: component rows point to shared lookup-table values instead of duplicating JSON per component. MCP tools query only the compact local index for research and design work. Exact component confirmation uses the local index plus optional public website detail fetching when available, with no JLCPCB API keys.

**Tech Stack:** Python, SQLite/FTS5, pytest, FastMCP, existing `jlcparts` CLI packaging.

---

## Design Decisions

- [ ] Treat the current `jlcparts/query_cache.py` implementation as deprecated for MCP use because it duplicates component JSON, attribute JSON, attribute value JSON, text-search blobs, numeric rows, price rows, and multiple secondary indexes.
- [ ] Use upstream generated catalog artifacts as the only bulk source instead of crawling the full JLCPCB API.
- [ ] Support only the canonical `yaqwsx` generated catalog format so this repo benefits directly from upstream updates.
- [ ] Use `dougy83/jlcparts` only as design inspiration for compact lookup-table storage, not as a runtime data source.
- [ ] Reuse the compact direction already present in `jlcparts/webdb.py`: integer component IDs, lookup tables, normalized component-attribute links, and narrow FTS.
- [ ] Do not automatically start a full catalog download or full index build from normal MCP read tools.
- [ ] Keep all normal cache research tools offline: `search_components`, `list_categories`, `list_attributes`, `list_attribute_values`, `get_component(include_website_detail=False)`, `compare_components`, `search`, and `fetch`.
- [ ] Keep exact website confirmation explicit: `lookup_component_website_detail` and `get_component(include_website_detail=True)` may fetch public JLCPCB/LCSC website detail for the requested LCSC part only.
- [ ] Use discrete CLI commands for upstream catalog download, compact index build, and optional website enrichment.

---

## Data Source Strategy

- [ ] Add a default upstream-catalog path:
  - download `https://yaqwsx.github.io/jlcparts/data/manifest.json` plus referenced shards
  - validate schema lines and required columns before building the index
  - persist source metadata locally so `cache_status()` can report upstream URL, download time, manifest version/hash if available, and component count
- [ ] Remove direct JLCPCB OpenAPI crawling from this MCP server design.
- [ ] Remove JLCPCB credential handling from the MCP CLI and docs.
- [ ] Use exact website detail fetching only for:
  - `lookup_component_website_detail(lcsc)`
  - `get_component(include_website_detail=True)`
  - opportunistic exact-component overlay updates after a successful website detail fetch
- [ ] Do not require credentials for catalog download, index build, cache-only MCP searches, or exact website detail fetching.

---

## Target Data Model

- [ ] Create a compact MCP index schema with these tables:
  - `metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL)`
  - `categories(category_id INTEGER PRIMARY KEY, path TEXT NOT NULL, name TEXT NOT NULL, parent_path TEXT, source_name TEXT)`
  - `manufacturers(manufacturer_id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE)`
  - `packages(package_id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE)`
  - `components(component_id INTEGER PRIMARY KEY, lcsc TEXT NOT NULL UNIQUE, category_id INTEGER, manufacturer_id INTEGER, package_id INTEGER, mfr TEXT, description TEXT, stock INTEGER, basic INTEGER, preferred INTEGER, discontinued INTEGER, rohs TEXT, eccn TEXT, assembly TEXT, assembly_process TEXT, assembly_mode TEXT, joints INTEGER, datasheet TEXT, price_json TEXT, img TEXT, url TEXT, source_updated_at TEXT, website_checked_at TEXT)`
  - `attribute_keys(attribute_key_id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE)`
  - `attribute_values(attribute_value_id INTEGER PRIMARY KEY, value_key TEXT NOT NULL UNIQUE, display TEXT NOT NULL, value_json TEXT NOT NULL)`
  - `component_attributes(component_id INTEGER NOT NULL, attribute_key_id INTEGER NOT NULL, attribute_value_id INTEGER NOT NULL, PRIMARY KEY(component_id, attribute_key_id, attribute_value_id)) WITHOUT ROWID`
  - `numeric_attribute_values(component_id INTEGER NOT NULL, attribute_key_id INTEGER NOT NULL, quantity_type TEXT NOT NULL, value REAL NOT NULL, unit TEXT)`
  - `price_tiers(component_id INTEGER NOT NULL, quantity INTEGER NOT NULL, price REAL NOT NULL, currency TEXT, PRIMARY KEY(component_id, quantity)) WITHOUT ROWID`
  - `website_component_details(lcsc TEXT PRIMARY KEY, checked_at TEXT NOT NULL, website_json TEXT)` for exact website detail lookups only
  - `components_fts` as FTS5 over only `lcsc`, `mfr`, `description`, manufacturer name, package name, and category path.
- [ ] Avoid these heavy duplicate fields in the compact index:
  - no per-component `extra_json`
  - no per-component `jlc_extra_json`
  - no per-component `attributes_json`
  - no per-link `attribute_json`
  - no FTS document containing every attribute and every value
- [ ] Store one normalized JSON representation per distinct attribute value in `attribute_values.value_json`; all component links reference it by integer ID.
- [ ] Store price tiers as rows so sorting by `quantity` is cheap and does not require parsing JSON during queries.
- [ ] Store numeric attribute rows only for values that parse into a numeric quantity.
- [ ] Store upstream catalog source metadata in `metadata`, not a copy of the entire raw upstream shard content.
- [ ] Do not require or build the existing official API `SourceDb` for MCP operation.
- [ ] Store website detail JSON only in `website_component_details`, which should stay small because it contains only exact parts the user explicitly verified.

---

## Implementation Tasks

### 1. Baseline Cleanup

- [ ] Inspect the current changed files before editing:
  - `git status --short`
  - `git diff -- README.md pyproject.toml jlcparts/query_cache.py jlcparts/ui.py`
- [ ] Decide whether to delete `jlcparts/query_cache.py` or keep it as a deprecated compatibility module. Prefer deleting only if no tests/imports require it.
- [ ] Remove or rename the current `build-query-cache` CLI entry point so it cannot accidentally recreate the 40 GB temporary database.
- [ ] Add a README warning that any old `query-cache.sqlite3.tmp` file can be deleted because the new design replaces it.

### 2. Add Upstream Catalog Downloader

- [ ] Add `jlcparts/upstream_catalog.py`.
- [ ] Implement constants:
  - `DEFAULT_UPSTREAM_DATA_URL = "https://yaqwsx.github.io/jlcparts/data"`
  - `DEFAULT_CATALOG_NAME = "catalog"`
- [ ] Implement `UpstreamCatalogDownloader` with:
  - `download_manifest_source(output_dir: Path, data_url: str, force: bool = False) -> CatalogDownloadResult`
  - atomic writes through temporary files
  - conditional HTTP support with `If-Modified-Since` or `ETag` when available
  - SHA-256 hashing of downloaded files
  - explicit timeout and retry settings
- [ ] Persist a small local catalog metadata file:
  - `catalog_source`
  - `source_url`
  - `downloaded_at`
  - `etag`
  - `last_modified`
  - `sha256`
  - `component_count`
  - `schema_version`
- [ ] Do not require JLCPCB credentials for this downloader.
- [ ] Add fixtures for the canonical upstream manifest plus shard shape.

### 3. Add Compact Index Module

- [ ] Add `jlcparts/compact_index.py`.
- [ ] Implement constants:
  - `COMPACT_INDEX_SCHEMA_VERSION = 1`
  - `DEFAULT_INDEX_NAME = "mcp-index.sqlite3"`
- [ ] Implement `CompactIndexBuilder` with:
  - `__init__(catalog_path: Path, index_path: Path)`
  - `build(force: bool = False) -> CompactIndexBuildResult`
  - atomic build via `index_path.with_suffix(".sqlite3.tmp")`, then `os.replace`
  - SQLite pragmas for bulk build: `journal_mode=OFF`, `synchronous=OFF`, `temp_store=MEMORY`, `locking_mode=EXCLUSIVE`
  - indexes created after data insertion
- [ ] Reuse existing parsing helpers from `jlcparts.webdb` where possible instead of inventing a second normalization path.
- [ ] Add a parser for upstream manifest plus gzipped shards.
- [ ] Ensure the builder never calls remote JLCPCB APIs. It reads only a local downloaded upstream catalog.
- [ ] Populate metadata:
  - `schema_version`
  - `source_kind`
  - `source_path`
  - `source_url`
  - `source_downloaded_at`
  - `source_last_modified`
  - `source_etag`
  - `source_sha256`
  - `built_at`
  - `component_count`
  - `category_count`
  - `attribute_key_count`
  - `attribute_value_count`
  - `source_component_count`
- [ ] Add build progress logging every fixed component interval without printing per-component output.

### 4. Add Compact Query Service

- [ ] Add `jlcparts/compact_query.py`.
- [ ] Implement `CompactQueryService` with:
  - `cache_status()`
  - `list_categories(search: str | None = None, limit: int = 200)`
  - `list_attributes(category_ids: list[int] | None = None, text_query: str | None = None, limit: int = 100)`
  - `list_attribute_values(attribute: str, category_ids: list[int] | None = None, text_query: str | None = None, limit: int = 100)`
  - `search_components(...)`
  - `get_component(lcsc: str)`
  - `lookup_component_website_detail(lcsc: str)`
  - `compare_components(lcsc_codes: list[str], quantity: int = 1, attributes: list[str] | None = None, only_differences: bool = False)`
- [ ] Implement `search_components` with these filter groups:
  - free text query via FTS first, with fallback to `LIKE` for exact LCSC-like terms if needed
  - category IDs or category path text
  - manufacturer names
  - package names
  - stock minimum
  - basic, extended, preferred, discontinued
  - RoHS, ECCN, assembly/process/mode where present
  - exact attribute key/value filters
  - numeric attribute filters with operators `=`, `>`, `>=`, `<`, `<=`, and range
  - sort by relevance, stock, price at requested quantity, manufacturer part number, or category
  - pagination by `limit` and `offset`
- [ ] Reconstruct component attributes through joins from `component_attributes`, `attribute_keys`, and `attribute_values`.
- [ ] Return compact summaries from `search_components`; include full attribute detail only from `get_component` and `compare_components`.
- [ ] Keep query execution read-only with `mode=ro` SQLite connections where possible.

### 5. Wire MCP Tools To Compact Query Service

- [ ] Update `jlcparts/mcp_server.py` to use `CompactQueryService` for local read tools.
- [ ] Keep these MCP tools local-only unless explicitly requesting website detail:
  - `cache_status`
  - `list_categories`
  - `list_attributes`
  - `list_attribute_values`
  - `search_components`
  - `get_component(include_website_detail=False)`
  - `compare_components`
  - `search`
  - `fetch`
- [ ] Remove `refresh_cache` from the MCP tool surface if it still exists.
- [ ] Replace `live_lookup_component` with `lookup_component_website_detail(lcsc)` to avoid implying credentialed API access.
- [ ] For `get_component(include_website_detail=True)`, call the website detail path and clearly mark which fields came from the upstream catalog versus the website overlay.
- [ ] Opportunistically update `website_component_details` and the compact index row for the requested LCSC after successful website detail fetch. Keep this scoped to the exact component only.
- [ ] Improve tool descriptions so agents understand the workflow:
  - use cache tools for fast research/design exploration
  - use website detail only after narrowing to candidate LCSC parts
  - normal cache searches do not contact JLCPCB
  - upstream catalog download and index build are CLI operations because they can be long

### 6. CLI Commands

- [ ] Update `jlcparts/ui.py`.
- [ ] Add or replace with:
  - `jlcparts download-catalog`
  - `jlcparts build-index`
  - `jlcparts enrich-cache`
  - `jlcparts mcp`
- [ ] Make `download-catalog` the default bulk update path:
  - `jlcparts download-catalog`
  - `jlcparts download-catalog --data-url https://yaqwsx.github.io/jlcparts/data`
- [ ] Remove or deprecate the old official API crawl command from the user-facing CLI.
- [ ] Keep website enrichment separate:
  - `jlcparts enrich-cache --index ~/.cache/jlcparts/mcp-index.sqlite3 --limit 0`
  - `--limit 0` means no artificial limit, not skip all records
- [ ] Add `build-index` options:
  - `--catalog PATH`, default `~/.cache/jlcparts/catalog`
  - `--index PATH`, default `~/.cache/jlcparts/mcp-index.sqlite3`
  - `--force`
  - `--progress-interval`
- [ ] Add `mcp` options:
  - `--index PATH`, default `~/.cache/jlcparts/mcp-index.sqlite3`
  - transport options already implemented
- [ ] Update `pyproject.toml` console scripts:
  - keep `jlcparts-mcp`
  - add `jlcparts-download-catalog`
  - add `jlcparts-build-index`
  - remove or deprecate `jlcparts-build-query-cache`

### 7. README Update

- [ ] Rewrite the MCP storage section to describe the default local files:
  - upstream generated catalog: `~/.cache/jlcparts/catalog`
  - compact MCP index: `~/.cache/jlcparts/mcp-index.sqlite3`
- [ ] Explain that cache research tools do not query JLCPCB servers.
- [ ] Explain that exact website detail lookups may fetch public JLCPCB/LCSC pages for one LCSC code at a time.
- [ ] Explain that bulk updates use the upstream generated catalog and do not need JLCPCB credentials.
- [ ] Explain that upstream catalog download and compact index build are command-line operations.
- [ ] Update Codex setup with only non-default arguments in JSON:
  - `command`
- [ ] Document optional defaults in prose:
  - cache path
  - index path
  - stdio transport
  - host and port for HTTP mode
- [ ] Add examples:
  - upstream catalog download command without credentials
  - compact index build command
  - MCP run command
  - exact website detail command/tool prompt

### 8. Tests

- [ ] Add `tests/test_compact_index.py`.
- [ ] Create tiny upstream catalog fixtures with:
  - at least two categories
  - at least three components
  - compressed `components-*` data
  - `attributes-lut`
  - `subcategories`
  - repeated attribute values shared across components
  - numeric attributes
  - price tiers
  - basic, extended, preferred, stock, RoHS, ECCN, and assembly fields
- [ ] Assert compact schema avoids heavy duplicate columns:
  - no `attributes_json` column in `components`
  - no `attribute_json` column in `component_attributes`
  - no `extra_json` column in `components`
  - no `jlc_extra_json` column in `components`
- [ ] Assert repeated attribute values are deduplicated in `attribute_values`.
- [ ] Add `tests/test_compact_query.py`.
- [ ] Test:
  - free text search
  - exact LCSC search
  - category filters
  - manufacturer and package filters
  - stock minimum
  - basic/preferred filters
  - exact attribute filters
  - numeric range filters
  - price sorting at quantity
  - pagination
  - compare output with and without `only_differences`
- [ ] Update MCP tests to assert tool listing and descriptions include:
  - cache-first research wording
  - exact website detail wording
  - no long refresh tool
- [ ] Update CLI tests for:
  - `download-catalog`
  - `build-index`
  - no remote calls during compact index build
- [ ] Add downloader tests that mock HTTP and assert:
  - credentials are not required
  - manifest/shard downloads validate required schema
  - ETag or `Last-Modified` metadata is preserved when present

### 9. Real-Catalog Validation

- [ ] Run focused tests:
  - `python3 -m pytest -q tests/test_compact_index.py tests/test_compact_query.py`
- [ ] Run full tests:
  - `python3 -m pytest -q`
- [ ] Download the real upstream generated catalog:
  - `python3 -m jlcparts.ui download-catalog --catalog ~/.cache/jlcparts/catalog --force`
- [ ] Build the compact index from the real upstream catalog:
  - `python3 -m jlcparts.ui build-index --catalog ~/.cache/jlcparts/catalog --index ~/.cache/jlcparts/mcp-index.sqlite3 --force`
- [ ] Measure the resulting index:
  - `du -h ~/.cache/jlcparts/mcp-index.sqlite3`
  - `sqlite3 ~/.cache/jlcparts/mcp-index.sqlite3 'pragma page_count; pragma page_size; select key,value from metadata order by key;'`
- [ ] Confirm the compact index is the same order of magnitude as the upstream catalog and not tens of GiB.
- [ ] If the compact index exceeds 5x the compressed upstream catalog size or reaches multiple GiB unexpectedly, stop and optimize before committing.
- [ ] Smoke-test MCP read tools against the real compact index without credentials to confirm no remote calls are required for cache research.
- [ ] Smoke-test one `lookup_component_website_detail` without credentials to confirm exact website detail works or returns an actionable no-detail response.

### 10. Commit Strategy

- [ ] Commit 1: upstream catalog downloader and fixtures with tests.
- [ ] Commit 2: compact index schema and builder with tests.
- [ ] Commit 3: compact query service and query tests.
- [ ] Commit 4: MCP/CLI wiring and MCP tests.
- [ ] Commit 5: README update and cleanup of deprecated query-cache path.

---

## Expected Outcome

- The MCP server becomes usable for agents because normal search/filter/compare workflows are fast and local.
- The compact index avoids the current 40 GB failure mode by deduplicating attributes and values.
- Bulk catalog update no longer requires JLCPCB credentials or an overnight official API crawl.
- Website enrichment is no longer part of the default catalog update path.
- Exact website detail remains available for the selected LCSC part without API credentials when public pages provide the needed fields.
- The README clearly explains the workflow: cache for research, website detail for final confirmation.
