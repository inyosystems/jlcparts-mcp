import gzip
import json
import os
from pathlib import Path

import pytest

from jlcparts.datatables import normalizeAttribute


LUT_PATH = Path("web/public/data/attributes-lut.json.gz")


def _string_values_for_section(section):
    with gzip.open(LUT_PATH, "rt", encoding="utf-8") as lut_file:
        attributes = json.load(lut_file)

    values = []
    for name, payload in attributes:
        if name != section:
            continue
        for value in payload.get("values", {}).values():
            if isinstance(value, list) and len(value) > 1 and value[1] == "string":
                values.append(value[0])
    return list(dict.fromkeys(values))


def _assert_normalized(section, raw_value, capsys):
    normalized_name, normalized = normalizeAttribute(section, raw_value)
    captured = capsys.readouterr()

    assert "Could not process key" not in captured.out
    assert normalized_name == section
    assert normalized["values"]
    assert all(value[1] != "string" for value in normalized["values"].values())


@pytest.mark.skipif(
    not LUT_PATH.exists(),
    reason="generated attribute LUT is not available",
)
def test_selected_attribute_section_normalizes_generated_values(capsys):
    section = os.environ.get("JLC_ATTRIBUTE_SECTION")
    if not section:
        pytest.skip("set JLC_ATTRIBUTE_SECTION to scan one generated attribute section")

    values = _string_values_for_section(section)
    assert values, f"no generated string values found for {section!r}"

    limit = os.environ.get("JLC_ATTRIBUTE_SECTION_LIMIT")
    if limit:
        values = values[: int(limit)]

    for raw_value in values:
        _assert_normalized(section, raw_value, capsys)
