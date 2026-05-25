import gzip
import json
import os
import re
from pathlib import Path

import pytest

from jlcparts.datatables import normalizeAttribute


LUT_PATH = Path("web/public/data/attributes-lut.json.gz")
SECTION_SEPARATOR = "||"


def _string_values_for_section(section, value_pattern=None):
    with gzip.open(LUT_PATH, "rt", encoding="utf-8") as lut_file:
        attributes = json.load(lut_file)

    values = []
    pattern = re.compile(value_pattern) if value_pattern else None
    for name, payload in attributes:
        if name != section:
            continue
        for value in payload.get("values", {}).values():
            if isinstance(value, list) and len(value) > 1 and value[1] == "string":
                if not re.search(r"\d", value[0]):
                    continue
                if pattern and not pattern.search(value[0]):
                    continue
                values.append(value[0])
    return list(dict.fromkeys(values))


def _assert_normalized(section, raw_value, capsys):
    normalized_name, normalized = normalizeAttribute(section, raw_value)
    captured = capsys.readouterr()

    assert "Could not process key" not in captured.out, (
        f"{section!r} value {raw_value!r} was not handled:\n{captured.out}"
    )
    assert normalized_name == section, f"{section!r} was renamed to {normalized_name!r}"
    assert normalized["values"], f"{section!r} value {raw_value!r} normalized to no values"

    string_values = {
        name: value
        for name, value in normalized["values"].items()
        if isinstance(value, list) and len(value) > 1 and value[1] == "string"
    }
    assert not string_values, (
        f"{section!r} value {raw_value!r} still has string-normalized fields: "
        f"{string_values!r}"
    )


def _selected_sections():
    sections = os.environ.get("JLC_ATTRIBUTE_SECTION")
    if not sections:
        return []
    return [
        section.strip()
        for section in sections.split(SECTION_SEPARATOR)
        if section.strip()
    ]


@pytest.mark.skipif(
    not LUT_PATH.exists(),
    reason="generated attribute LUT is not available",
)
def test_selected_attribute_section_normalizes_generated_values(capsys):
    sections = _selected_sections()
    if not sections:
        pytest.skip(
            "set JLC_ATTRIBUTE_SECTION to scan one generated attribute section; "
            f"use {SECTION_SEPARATOR!r} to scan a small set of sections"
        )

    limit = (
        int(os.environ["JLC_ATTRIBUTE_SECTION_LIMIT"])
        if os.environ.get("JLC_ATTRIBUTE_SECTION_LIMIT")
        else None
    )
    value_pattern = os.environ.get("JLC_ATTRIBUTE_VALUE_RE")

    for section in sections:
        values = _string_values_for_section(section, value_pattern)
        assert values, f"no generated numeric string values found for {section!r}"

        if limit:
            values = values[:limit]

        for raw_value in values:
            _assert_normalized(section, raw_value, capsys)
