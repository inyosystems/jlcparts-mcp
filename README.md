![Logo](web/public/favicon.svg)

# JLC PCB SMD Assembly Component Catalogue

A better tool to browse the components offered by the [JLC PCB SMT Assembly
Service](https://jlcpcb.com/smt-assembly).

## How To Use It?

Just visit: [https://yaqwsx.github.io/jlcparts/](https://yaqwsx.github.io/jlcparts/)

## MCP Server

This repository can also run as a local MCP server for agents such as Codex.
The server helps an agent search the JLCPCB PCBA component database while
designing boards: broad searches, parametric filters, category and attribute
facets, exact component fetches, price/stock checks, and component comparisons
all run against a local SQLite cache. Exact freshness checks can use live
JLCPCB calls.

Install the Python package with uv:

```
$ uv sync
```

Run the MCP server over stdio, which is the default transport for local agents:

```
$ uv run jlcparts-mcp \
    --cache ~/.cache/jlcparts/cache.sqlite3 \
    --jlcpcb-app-id "$JLCPCB_APP_ID" \
    --jlcpcb-access-key "$JLCPCB_ACCESS_KEY" \
    --jlcpcb-secret-key "$JLCPCB_SECRET_KEY"
```

The same credentials can be provided through environment variables:

```
$ export JLCPCB_APP_ID=...
$ export JLCPCB_ACCESS_KEY=...
$ export JLCPCB_SECRET_KEY=...
$ uv run jlcparts-mcp --cache ~/.cache/jlcparts/cache.sqlite3
```

Command-line credentials override `JLCPCB_APP_ID`, `JLCPCB_ACCESS_KEY`, and
`JLCPCB_SECRET_KEY`. They are used only by the running process and are not saved
to disk. Credentials are needed for full cache refreshes and
`live_lookup_component`; read-only cached searches can run without them after a
full cache has been populated.

Optional streamable HTTP mode:

```
$ uv run jlcparts-mcp --transport http --host 127.0.0.1 --port 8765
```

### Codex Setup

Populate the source cache and query index once before doing normal cached
research. Full refresh is intentionally a command-line operation because it can
run longer than MCP client tool-call timeouts. MCP read tools do not start a
full remote catalog download implicitly:

```
$ export JLCPCB_APP_ID=...
$ export JLCPCB_ACCESS_KEY=...
$ export JLCPCB_SECRET_KEY=...
$ uv run jlcparts refresh-cache --verbose
```

Then add the MCP server to your Codex MCP configuration. Use the same JSON shape
your Codex installation uses for other MCP servers, commonly an `mcpServers`
object in the Codex config file. Point `--directory` at this repository so uv
can run the local package:

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

The example above relies on the MCP server defaults:

- `--cache`: `~/.cache/jlcparts/cache.sqlite3`
- `--query-cache`: `query-cache.sqlite3` next to the source cache
- refresh checkpoint: `refresh-checkpoint.json` next to the source cache
- `--transport`: `stdio`
- `--host`: `127.0.0.1` for HTTP mode
- `--port`: `8765` for HTTP mode

Optional arguments to add only when needed:

- `--cache /path/to/cache.sqlite3`
- `--query-cache /path/to/query-cache.sqlite3`
- `--transport http --host 127.0.0.1 --port 8765`
- `--jlcpcb-app-id ... --jlcpcb-access-key ... --jlcpcb-secret-key ...`

Credentials should usually be supplied through the Codex process environment,
not as literal JSON argv strings. Do not put values such as `"$JLCPCB_APP_ID"`
in JSON `args` unless your MCP client explicitly expands them. Most clients pass
argv arrays directly, and command-line credentials intentionally override
environment variables.

With the defaults above, the files live here:

- source cache: `~/.cache/jlcparts/cache.sqlite3`
- query index: `~/.cache/jlcparts/query-cache.sqlite3`
- refresh checkpoint: `~/.cache/jlcparts/refresh-checkpoint.json`

After Codex starts the server, ask it to call `cache_status()` first. For fast
research/design it should use the cached tools such as `search_components`,
`get_component`, and `compare_components`. After narrowing to exact LCSC codes,
it should use `live_lookup_component` or `get_component(live_verify=true)` to
confirm current JLCPCB data.

If you do not use uv, the package still supports the standard editable install:

```
$ python3 -m venv venv
$ source venv/bin/activate
$ pip install -e .
$ jlcparts-mcp --cache ~/.cache/jlcparts/cache.sqlite3
```

The cache is useful even with JLCPCB API credentials because it gives agents a
normalized, local, read-optimized search index. The server can filter and sort
by normalized attributes, price tiers, stock, Basic/Extended/Preferred status,
RoHS, ECCN, assembly fields, attrition metadata, categories, and hidden website
detail fields without repeatedly issuing broad remote queries. Cache age is
reported by `cache_status()` as `last_full_api_refresh` and
`last_full_api_refresh_age_seconds`; there is no arbitrary 24-hour freshness
cutoff. Read tools require a completed full source refresh and a valid query
index, but they do not automatically start a full remote catalog download.
Use the standalone refresh command when you want to run a full refresh.

Run or resume a full official JLCPCB OpenAPI refresh outside the MCP server:

```
$ uv run jlcparts refresh-cache \
    --cache ~/.cache/jlcparts/cache.sqlite3 \
    --query-cache ~/.cache/jlcparts/query-cache.sqlite3 \
    --jlcpcb-app-id "$JLCPCB_APP_ID" \
    --jlcpcb-access-key "$JLCPCB_ACCESS_KEY" \
    --jlcpcb-secret-key "$JLCPCB_SECRET_KEY" \
    --verbose
```

Equivalent direct console command:

```
$ uv run jlcparts-refresh-cache --cache ~/.cache/jlcparts/cache.sqlite3
```

The JLCPCB API does not currently expose a delta feed, so full refresh walks the
whole PCBA component catalog. Use `--max-seconds N` for a bounded run; the
command writes a checkpoint and can be rerun with the same cache/checkpoint
paths to resume. `cache_status()` reports `refresh_checkpoint`, so an agent can
inspect whether a command-line refresh is currently checkpointed or incomplete.

Command-line cache refresh uses the official JLCPCB OpenAPI only by default.
The slower, best-effort website enrichment pass is intentionally separate so an
agent does not block for hours while hidden website fields are fetched one
component at a time. Run it as a maintenance job when you want fields such as
website component IDs, assembly mode/process corrections, attrition, and minimum
purchase or placement quantities:

```
$ uv run jlcparts enrich-website ~/.cache/jlcparts/cache.sqlite3 \
    --query-cache ~/.cache/jlcparts/query-cache.sqlite3 \
    --workers 8
```

Equivalent direct console command:

```
$ uv run jlcparts-enrich-website ~/.cache/jlcparts/cache.sqlite3 \
    --query-cache ~/.cache/jlcparts/query-cache.sqlite3
```

By default `enrich-website` processes only components missing website detail.
Use `--all` to refresh already enriched rows, `--limit N` for a bounded run, and
`--workers N` to tune concurrency. If `--query-cache` is omitted, MCP will notice
that the source cache changed and rebuild the query index before the next read.
The legacy/maintenance `jlcparts fetch-db` command also accepts
`--enrich-website`, but normal MCP refreshes do not enable it.

Live lookups always request website enrichment by default. When the live LCSC
part already exists in the source cache, the MCP server opportunistically writes
the fresh official payload plus website enrichment back to the cache and
rebuilds the query index, so subsequent cached searches see the updated part.

Available MCP tools:

- `cache_status()`
- `live_lookup_component(lcsc, include_website_detail=True)`
- `list_categories(search=None)`
- `list_attributes(category_ids=None, text_query=None, limit=100)`
- `list_attribute_values(attribute, category_ids=None, text_query=None, limit=100)`
- `search_components(...)`
- `get_component(lcsc, live_verify=False)`
- `compare_components(lcsc_codes, quantity=1, attributes=None, only_differences=False)`
- `search(query)` and `fetch(id)` compatibility wrappers

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
