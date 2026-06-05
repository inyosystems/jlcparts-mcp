# Contributing

Thanks for helping improve JLCParts MCP.

## Development Setup

Install dependencies with uv:

```sh
uv sync
```

Run the test suite:

```sh
uv run pytest -q
```

Build the package locally:

```sh
uv build
```

## Contribution Guidelines

- Keep normal search and comparison tools cache-first. They should not contact
  JLCPCB or LCSC during broad research queries.
- Keep exact website lookups scoped to a single LCSC code.
- Prefer small, focused changes with tests for parser, index, query, or MCP
  behavior changes.
- Update README or changelog entries when changing public commands, MCP tools,
  configuration, or user-visible behavior.
- Preserve attribution to [yaqwsx/jlcparts](https://github.com/yaqwsx/jlcparts)
  when changing catalog-related workflows.

## Pull Request Checklist

- `uv run pytest -q`
- `uv run python scripts/check_readme_links.py README.md`
- `uv build`
- Documentation updated when public behavior changes
