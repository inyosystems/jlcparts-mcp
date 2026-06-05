#!/usr/bin/env python3
"""Validate local Markdown links in README-style files."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse


MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]]*]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
REFERENCE_LINK_RE = re.compile(r"^\s*\[[^\]]+]:\s+(\S+)", re.MULTILINE)
SKIP_SCHEMES = {"http", "https", "mailto"}


def iter_link_targets(text: str):
    for match in MARKDOWN_LINK_RE.finditer(text):
        yield match.group(1)
    for match in REFERENCE_LINK_RE.finditer(text):
        yield match.group(1)


def is_local_link(target: str) -> bool:
    parsed = urlparse(target)
    return parsed.scheme not in SKIP_SCHEMES and not target.startswith("#")


def target_path(markdown_path: Path, target: str) -> Path:
    parsed = urlparse(target)
    raw_path = unquote(parsed.path)
    if not raw_path:
        return markdown_path
    return (markdown_path.parent / raw_path).resolve()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("markdown", type=Path)
    args = parser.parse_args(argv)

    markdown_path = args.markdown.resolve()
    text = markdown_path.read_text(encoding="utf-8")
    missing = []

    for target in iter_link_targets(text):
        if not is_local_link(target):
            continue
        path = target_path(markdown_path, target)
        if not path.exists():
            missing.append(f"{target} -> {path}")

    if missing:
        print("Missing local README links:", file=sys.stderr)
        for item in missing:
            print(f"- {item}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
