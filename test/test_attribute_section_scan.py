import gzip
import json
import os
import re
from pathlib import Path

import pytest

from jlcparts.datatables import normalizeAttribute


LUT_PATH = Path("web/public/data/attributes-lut.json.gz")
SECTION_SEPARATOR = "||"


def _values_from_env():
    values = os.environ.get("JLC_ATTRIBUTE_VALUE")
    if not values:
        return []
    return [
        value.strip()
        for value in values.split(SECTION_SEPARATOR)
        if value.strip()
    ]


def _values_from_file(path):
    if not path:
        return []
    return [
        value.strip()
        for value in Path(path).read_text(encoding="utf-8").splitlines()
        if value.strip()
    ]


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


def _sections_from_env():
    sections = os.environ.get("JLC_ATTRIBUTE_SECTION")
    if not sections:
        return []
    return [
        section.strip()
        for section in sections.split(SECTION_SEPARATOR)
        if section.strip()
    ]


@pytest.mark.attribute_section
def test_selected_attribute_section_normalizes_generated_values(pytestconfig, capsys):
    sections = pytestconfig.getoption("--attribute-section") or _sections_from_env()
    if not sections:
        pytest.skip(
            "set JLC_ATTRIBUTE_SECTION or pass --attribute-section to scan one "
            f"generated attribute section; use {SECTION_SEPARATOR!r} in the "
            "environment variable or pass --attribute-section multiple times to "
            "scan a small set of sections"
        )

    limit = pytestconfig.getoption("--attribute-section-limit")
    if limit is None and os.environ.get("JLC_ATTRIBUTE_SECTION_LIMIT"):
        limit = int(os.environ["JLC_ATTRIBUTE_SECTION_LIMIT"])
    value_pattern = (
        pytestconfig.getoption("--attribute-value-re")
        or os.environ.get("JLC_ATTRIBUTE_VALUE_RE")
    )
    direct_values = pytestconfig.getoption("--attribute-value") or _values_from_env()
    value_file = pytestconfig.getoption("--attribute-value-file") or os.environ.get(
        "JLC_ATTRIBUTE_VALUE_FILE"
    )
    direct_values.extend(_values_from_file(value_file))

    for section in sections:
        if direct_values:
            values = direct_values
        else:
            if not LUT_PATH.exists():
                pytest.skip("generated attribute LUT is not available")
            values = _string_values_for_section(section, value_pattern)
        assert values, f"no generated numeric string values found for {section!r}"

        if limit:
            values = values[:limit]

        for raw_value in values:
            _assert_normalized(section, raw_value, capsys)
