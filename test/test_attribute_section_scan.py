import gzip
import json
import os
import re
import sqlite3
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


def _is_numeric_string(value):
    return isinstance(value, str) and re.search(r"\d", value)


def _attribute_values_from_extra(extra):
    if not isinstance(extra, dict):
        return {}
    attributes = extra.get("attributes", extra)
    if isinstance(attributes, list):
        return {}
    return attributes or {}


def _attribute_values_from_jlc_extra(jlc_extra):
    if not isinstance(jlc_extra, dict):
        return {}
    attributes = jlc_extra.get("attributes", {})
    if isinstance(attributes, list):
        return {}
    return attributes or {}


def _string_values_for_section_from_sqlite(
    db_path, section, value_pattern=None, max_values=None
):
    pattern = re.compile(value_pattern) if value_pattern else None
    values = []

    conn = sqlite3.connect(db_path)
    try:
        query = """
            SELECT extra, jlc_extra
            FROM components
            WHERE extra LIKE ? OR jlc_extra LIKE ?
        """
        params = [f'%"{section}"%', f'%"{section}"%']
        if max_values:
            query += " LIMIT ?"
            params.append(max_values)
        cursor = conn.execute(query, params)
        for extra_json, jlc_extra_json in cursor:
            for source, extractor in [
                (extra_json, _attribute_values_from_extra),
                (jlc_extra_json, _attribute_values_from_jlc_extra),
            ]:
                try:
                    attributes = extractor(json.loads(source or "{}"))
                except json.JSONDecodeError:
                    continue
                value = attributes.get(section)
                if not _is_numeric_string(value):
                    continue
                if pattern and not pattern.search(value):
                    continue
                values.append(value)
                if max_values and len(values) >= max_values:
                    return list(dict.fromkeys(values))
    finally:
        conn.close()

    return list(dict.fromkeys(values))


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
                if not _is_numeric_string(value[0]):
                    continue
                if pattern and not pattern.search(value[0]):
                    continue
                values.append(value[0])
    return list(dict.fromkeys(values))


def _values_for_focused_section(
    section,
    direct_values=None,
    value_file=None,
    sqlite_path=None,
    value_pattern=None,
    limit=None,
):
    values = list(direct_values or [])
    values.extend(_values_from_file(value_file))

    if values:
        pass
    elif sqlite_path:
        values = _string_values_for_section_from_sqlite(
            sqlite_path, section, value_pattern, limit
        )
    else:
        if not LUT_PATH.exists():
            pytest.skip("generated attribute LUT is not available")
        values = _string_values_for_section(section, value_pattern)

    if limit:
        return values[:limit]
    return values


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
    sqlite_path = pytestconfig.getoption("--attribute-sqlite") or os.environ.get(
        "JLC_ATTRIBUTE_SQLITE"
    )

    for section in sections:
        values = _values_for_focused_section(
            section,
            direct_values=direct_values,
            value_file=value_file,
            sqlite_path=sqlite_path,
            value_pattern=value_pattern,
            limit=limit,
        )
        assert values, f"no generated numeric string values found for {section!r}"

        for raw_value in values:
            _assert_normalized(section, raw_value, capsys)


def test_attribute_section_scan_uses_direct_values_without_generated_lut(monkeypatch):
    monkeypatch.setattr(
        "test_attribute_section_scan.LUT_PATH",
        Path("missing-attributes-lut.json.gz"),
    )

    assert _values_for_focused_section(
        "Peak Forward Surge Current",
        direct_values=["1A", "2A"],
    ) == ["1A", "2A"]


def test_attribute_section_scan_reads_value_file_without_generated_lut(
    tmp_path, monkeypatch
):
    value_file = tmp_path / "values.txt"
    value_file.write_text("1A\n\n2A\n", encoding="utf-8")
    monkeypatch.setattr(
        "test_attribute_section_scan.LUT_PATH",
        Path("missing-attributes-lut.json.gz"),
    )

    assert _values_for_focused_section(
        "Peak Forward Surge Current",
        value_file=value_file,
        limit=1,
    ) == ["1A"]


def test_attribute_section_sqlite_loader_reads_only_selected_section(tmp_path):
    db_path = tmp_path / "cache.sqlite3"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE components(extra TEXT, jlc_extra TEXT)")
        conn.execute(
            "INSERT INTO components(extra, jlc_extra) VALUES (?, ?)",
            (
                json.dumps({"attributes": {"Switching Current": "500mA"}}),
                json.dumps({"attributes": {"Switching Voltage": "180V"}}),
            ),
        )
        conn.execute(
            "INSERT INTO components(extra, jlc_extra) VALUES (?, ?)",
            (
                json.dumps({"attributes": {"Other": "123"}}),
                json.dumps({"attributes": {"Switching Current": "1A"}}),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    assert _string_values_for_section_from_sqlite(
        db_path, "Switching Current"
    ) == ["500mA", "1A"]
    assert _string_values_for_section_from_sqlite(
        db_path, "Switching Current", r"mA$"
    ) == ["500mA"]
