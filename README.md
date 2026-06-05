![Logo](web/public/favicon.svg)

# JLC PCB SMD Assembly Component Catalogue

A better tool to browse the components offered by the [JLC PCB SMT Assembly
Service](https://jlcpcb.com/smt-assembly).

## How To Use It?

Just visit: [https://yaqwsx.github.io/jlcparts/](https://yaqwsx.github.io/jlcparts/)

## MCP Server

This repository can also run as a local MCP server for agents such as Codex. It
uses a cache-first workflow: download the upstream generated `yaqwsx` catalog,
build a compact local SQLite MCP index, and let the server answer normal
component research queries from that index.

No JLCPCB credentials are needed. Bulk data comes from the public generated
catalog, cached searches do not query JLCPCB, and exact website detail lookup
may fetch the public JLCPCB page for one LCSC code at a time.

Catalog scope note: the upstream generated `yaqwsx` catalog is optimized for
practical PCBA design search, not for mirroring every reference shown on the
live JLCPCB parts website. The upstream generation currently builds with
`--ignoreoldstock 120`, so it excludes parts that have not been observed in
stock in roughly the last 120 days. Live JLCPCB category pages can therefore
show much larger totals, especially in broad categories such as surface-mount
resistors.

Install the Python package:

```
$ uv sync
```

Prepare the local cache:

```
$ uv run jlcparts download-catalog
$ uv run jlcparts build-index
```

Defaults:

- upstream generated catalog: `~/.cache/jlcparts/catalog`
- compact MCP index: `~/.cache/jlcparts/mcp-index.sqlite3`

If an old `query-cache.sqlite3.tmp` file exists from the previous query-cache
implementation, it is no longer used and can be deleted.

Run the MCP server over stdio, which is the default transport for local agents:

```
$ uv run jlcparts-mcp
```

Useful CLI commands:

- `uv run jlcparts download-catalog`: download/update the upstream generated catalog
- `uv run jlcparts build-index`: build the compact MCP index from the catalog
- `uv run jlcparts-mcp`: run the MCP server
- `uv run jlcparts enrich-cache`: optional exact public website detail enrichment

The package also exposes direct console scripts:

- `jlcparts-download-catalog`
- `jlcparts-build-index`
- `jlcparts-enrich-cache`
- `jlcparts-mcp`

### Codex Setup

After running `download-catalog` and `build-index`, add the MCP server to your
Codex MCP configuration. Use the same JSON shape your Codex installation uses
for other MCP servers, commonly an `mcpServers` object. Point `--directory` at
this repository so uv can run the local package:

```
{
  "mcpServers": {
    "jlcparts": {
      "command": "uv",
      "args": [
        "--directory", "/path/to/jlcparts",
        "run", "jlcparts-mcp"
      ]
    }
  }
}
```

The example relies on the defaults: stdio transport, catalog at
`~/.cache/jlcparts/catalog`, and index at
`~/.cache/jlcparts/mcp-index.sqlite3`. Add optional arguments only when you need
non-default paths or HTTP transport, for example `--index /path/to/index.sqlite3`
or `--transport http --host 127.0.0.1 --port 8765`.

After Codex starts the server, ask it to call `cache_status()` first. For fast
research/design it should use the cached tools such as `search_components`,
`get_component`, and `compare_components`; those searches stay local. After
narrowing to exact LCSC codes, it can request exact website detail for the
specific parts it needs.

If you do not use uv, the package still supports the standard editable install:

```
$ python3 -m venv venv
$ source venv/bin/activate
$ pip install -e .
$ jlcparts download-catalog
$ jlcparts build-index
$ jlcparts-mcp
```

Example prompts for an agent:

- "Find in-stock basic 0603 10 kOhm resistors, sorted by price at quantity 100."
- "Compare C25804, C21190, and C23162 for package, stock, price, and voltage."
- "Live-verify C25804 right now and tell me whether assembly metadata changed."

## Why?

Probably all of us love JLC PCB SMT assembly service. It is easy to use, cheap
and fast. However, you can use only components from [their
catalogue](https://jlcpcb.com/parts). This is not as bad, since the library is
quite broad. However, the library UI sucks. You can only browse the categories,
do full-text search. You cannot do parametric search nor sort by property.
That's why I created a simple page which presents the catalogue in much nicer
form. You can:
- do full-text search
- browse categories
- parametric search
- sort by any component attribute
- sort by price based on quantity
- easily access datasheet and LCSC product page.

## Do You Enjoy It? Does It Make Your Life Easier?

[![ko-fi](https://www.ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/E1E2181LU)

Support on Ko-Fi allows me to develop such tools as this one and perform
hardware-related experiments.

## How Does It Look Like?

Title page

![Preview 1](https://user-images.githubusercontent.com/1590880/93708766-32ab0d80-fb39-11ea-8365-da2ca1b13d8b.jpg)

Property filter

![Preview 2](https://user-images.githubusercontent.com/1590880/93708599-e01d2180-fb37-11ea-96b6-5d5eb4e0f285.jpg)

Component detail

![Preview 3](https://user-images.githubusercontent.com/1590880/93708601-e0b5b800-fb37-11ea-84ed-6ba73f07911d.jpg)


## How Does It Work?

The page has no backend so it can be easily hosted on GitHub Pages. Therefore,
Travis CI download XLS spreadsheet from the JLC PCB page, a Python script
process it and it generates per-category JSON file with components.

The frontend uses IndexedDB in the browser to store the component library and
perform queries on it. Therefore, before the first use, you have to download the
component library and it can take a while. Then, all the queries are performed
locally.

## Development

To get started with developing the frontend, you will need NodeJS & Python 3.

Set up the Python portion of the program by running:

```
$ uv sync
```

The checked-in `uv.lock` gives agents and CI a reproducible Python environment.
For legacy environments, `python3 -m venv venv && source venv/bin/activate &&
pip install -e .` is still supported.

Download the cached parts database as shown in the [GitHub Actions workflow](https://github.com/yaqwsx/jlcparts/blob/master/.github/workflows/update_components.yaml),
then process it:

```
$ mkdir -p web/public/data/
$ uv run jlcparts buildtables --jobs 0 --ignoreoldstock 30 cache.sqlite3 web/public/data
```

To launch the frontend web server, run:

```
$ cd web
$ npm install
$ npm start
```

### Attribute Normalization Tests

When changing one attribute normalization rule, use the focused section scan
instead of rebuilding the whole generated database:

```
$ uv run pytest -q test/test_attribute_section_scan.py --attribute-section 'Peak Forward Surge Current'
```

Pass `--attribute-section` multiple times to test a small batch. To test raw
values before rebuilding datatables, pass them directly:

```
$ uv run pytest -q test/test_attribute_section_scan.py \
    --attribute-section 'Vbo (Range Value)' \
    --attribute-value '35V~45V'
```

To test one section against the SQLite cache without rebuilding generated
tables, point the same test at the local database:

```
$ uv run pytest -q test/test_attribute_section_scan.py \
    --attribute-section 'Peak Forward Surge Current' \
    --attribute-sqlite cache.sqlite3
```

For textual sections whose values do not contain numbers, include all generated
strings explicitly:

```
$ uv run pytest -q test/test_attribute_section_scan.py \
    --attribute-section 'Features' \
    --attribute-all-strings
```

## The Page Is Broken!

Feel free to open an issue on GitHub.

## You Might Also Be Interested

- [KiKit](https://github.com/yaqwsx/KiKit): a tool for automatic panelization of
  KiCAD PCBs. It can also perform fully automatic export of manufacturing data
  for JLC PCB assembly - read [the
  documentation](https://github.com/yaqwsx/KiKit/blob/master/doc/fabrication/jlcpcb.md)
  or produce a solder-paste stencil for populating components missing at JLC PCB - read [the
  documentation](https://github.com/yaqwsx/KiKit/blob/master/doc/stencil.md).
- [PcbDraw](https://github.com/yaqwsx/PcbDraw): a tool for making nice schematic
  drawings of your boards and population manuals.
