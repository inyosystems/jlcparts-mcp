# JLCParts MCP

[![CI](https://github.com/inyosystems/jlcparts-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/inyosystems/jlcparts-mcp/actions/workflows/ci.yml)

A local, cache-first MCP server and command-line toolkit for searching JLCPCB
SMT assembly components.

This project is derived from the great work in
[yaqwsx/jlcparts](https://github.com/yaqwsx/jlcparts). The original project
made the JLCPCB component catalog practical to browse and search. This fork
builds on that foundation by using the public generated catalog as the source
data, building a compact local SQLite index, and exposing fast component
research tools through MCP.

## Features

- Download the public generated `yaqwsx` component catalog.
- Build a compact SQLite index for local component search.
- Search by category, text, package, manufacturer, stock, lifecycle, and
  numeric attributes.
- Compare exact LCSC parts by package, stock, price, and attributes.
- Optionally fetch public website detail for one exact LCSC code at a time.
- Run as a local MCP server over stdio or streamable HTTP.

No JLCPCB credentials are required for catalog download, index building, cached
searches, or exact public website detail lookup.

## Requirements

- Python 3.10-3.12
- [uv](https://docs.astral.sh/uv/) for the recommended local workflow

## Quick Start

From a checkout of this repository:

```sh
uv sync
uv run jlcparts download-catalog
uv run jlcparts build-index
uv run jlcparts-mcp
```

Defaults:

- upstream generated catalog: `~/.cache/jlcparts/catalog`
- compact MCP index: `~/.cache/jlcparts/mcp-index.sqlite3`
- MCP transport: stdio

To refresh the source catalog and rebuild the index:

```sh
uv run jlcparts download-catalog --force
uv run jlcparts build-index --force
```

## MCP Client Configuration

Most MCP clients support a JSON configuration shaped like this:

```json
{
  "mcpServers": {
    "jlcparts": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/jlcparts-mcp",
        "run",
        "jlcparts-mcp"
      ]
    }
  }
}
```

The example uses the default stdio transport and default index path. If you keep
the index somewhere else, pass it to the server:

```json
{
  "mcpServers": {
    "jlcparts": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/jlcparts-mcp",
        "run",
        "jlcparts-mcp",
        "--index",
        "/path/to/mcp-index.sqlite3"
      ]
    }
  }
}
```

For HTTP transport:

```sh
uv run jlcparts-mcp --transport http --host 127.0.0.1 --port 8765
```

## MCP Tools

The server exposes these tools:

- `cache_status`
- `list_categories`
- `list_attributes`
- `list_attribute_values`
- `search_components`
- `get_component`
- `lookup_component_website_detail`
- `compare_components`
- `search`
- `fetch`

Cached research tools read only from the local SQLite index. Website detail
lookup is intentionally scoped to a single exact LCSC code.

## CLI Commands

```sh
uv run jlcparts download-catalog
uv run jlcparts build-index
uv run jlcparts-mcp
```

The package also exposes direct console scripts:

- `jlcparts-download-catalog`
- `jlcparts-build-index`
- `jlcparts-mcp`

## Example Requests

Use these with an MCP-capable client after the server is configured:

- "Find in-stock basic 0603 10 kOhm resistors, sorted by price at quantity 100."
- "Compare C25804, C21190, and C23162 for package, stock, price, and voltage."
- "Fetch public website detail for C25804 and compare it with the cached data."

## Catalog Scope

The upstream generated `yaqwsx` catalog is optimized for practical PCBA design
search. It is not intended to mirror every reference shown on the live JLCPCB
parts website, and live category totals can be larger than the generated
catalog. Cached searches should be treated as design research against the local
catalog snapshot. Use exact website detail lookup when you need to verify one
specific LCSC code against the public website.

## Why?

JLCPCB SMT assembly is useful for fast and affordable PCBA manufacturing, but
part selection often needs more than broad category browsing or text search.
Design work benefits from local parametric search, stock filtering, price
comparison, and repeatable part comparisons.

This project keeps that workflow local and agent-friendly: bulk data is
downloaded from the public generated catalog, indexed once, and then queried
quickly without remote calls during normal searches.

## Development

Install dependencies:

```sh
uv sync
```

Run the test suite:

```sh
uv run pytest -q
```

Focused attribute normalization tests are useful when changing parsing rules:

```sh
uv run pytest -q test/test_attribute_section_scan.py \
  --attribute-section 'Peak Forward Surge Current'
```

If `cache-v2.sqlite3` is present in the repository root, this command reads raw
values for only that selected section directly from the compact source database.
It does not rebuild the frontend datatables.

Pass `--attribute-section` multiple times to test a small batch. To test raw
values before rebuilding datatables, pass them directly:

```sh
uv run pytest -q test/test_attribute_section_scan.py \
  --attribute-section 'Vbo (Range Value)' \
  --attribute-value '35V~45V'
```

To test one section against a non-default compact source database path, point
the same test at it explicitly:

```sh
uv run pytest -q test/test_attribute_section_scan.py \
  --attribute-section 'Peak Forward Surge Current' \
  --attribute-source-db cache-v2.sqlite3
```

The legacy `cache.sqlite3` format is also supported with `--attribute-sqlite`,
but it is slower because raw attributes are stored inside larger JSON blobs.

For textual sections whose values do not contain numbers, include all generated
strings explicitly:

```sh
uv run pytest -q test/test_attribute_section_scan.py \
  --attribute-section 'Features' \
  --attribute-all-strings
```

## Project Documents

- [Changelog](https://github.com/inyosystems/jlcparts-mcp/blob/master/CHANGELOG.md)
- [Contributing](https://github.com/inyosystems/jlcparts-mcp/blob/master/CONTRIBUTING.md)
- [Security policy](https://github.com/inyosystems/jlcparts-mcp/blob/master/SECURITY.md)

## Attribution

This repository is derived from
[yaqwsx/jlcparts](https://github.com/yaqwsx/jlcparts). The original project and
generated catalog work made this MCP-focused workflow possible.

## License

MIT. See [LICENSE](LICENSE).
