import gzip
import json
import sqlite3

from jlcparts.compact_index import CompactIndexBuilder


def _write_json_gz(path, data):
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))


def _write_jsonl_gz(path, rows):
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for row in rows:
            json.dump(row, f, separators=(",", ":"))
            f.write("\n")


def build_upstream_catalog_fixture(path):
    path.mkdir(parents=True, exist_ok=True)
    attributes = [
        ["Resistance", {"format": "${resistance}", "primary": "resistance", "values": {"resistance": [10000.0, "resistance"]}}],
        ["Resistance", {"format": "${resistance}", "primary": "resistance", "values": {"resistance": [1000.0, "resistance"]}}],
        ["Capacitance", {"format": "${capacitance}", "primary": "capacitance", "values": {"capacitance": [1e-7, "capacitance"]}}],
        ["Package", {"format": "${identifier}", "primary": "identifier", "values": {"identifier": ["0603", "identifier"]}}],
        ["Package", {"format": "${identifier}", "primary": "identifier", "values": {"identifier": ["0402", "identifier"]}}],
        ["Manufacturer", {"format": "${identifier}", "primary": "identifier", "values": {"identifier": ["Acme", "identifier"]}}],
        ["Manufacturer", {"format": "${identifier}", "primary": "identifier", "values": {"identifier": ["CapCo", "identifier"]}}],
        ["Basic/Extended", {"format": "${catalog class 1}", "primary": "catalog class 1", "values": {"catalog class 1": ["Basic", "identifier"]}}],
        ["Basic/Extended", {"format": "${catalog class 1}", "primary": "catalog class 1", "values": {"catalog class 1": ["Extended", "identifier"]}}],
        ["Basic/Extended", {"format": "${catalog class 1}", "primary": "catalog class 1", "values": {"catalog class 1": ["Preferred", "identifier"]}}],
        ["Status", {"format": "${default}", "primary": "default", "values": {"default": ["Active", "string"]}}],
        ["RoHS", {"format": "${default}", "primary": "default", "values": {"default": ["Yes", "string"]}}],
        ["ECCN", {"format": "${default}", "primary": "default", "values": {"default": ["EAR99", "string"]}}],
        ["Assembly Process", {"format": "${default}", "primary": "default", "values": {"default": ["SMT", "string"]}}],
    ]
    _write_json_gz(path / "attributes-lut.json.gz", attributes)

    schema = {
        "lcsc": 0,
        "mfr": 1,
        "joints": 2,
        "description": 3,
        "datasheet": 4,
        "price": 5,
        "img": 6,
        "url": 7,
        "attributes": 8,
        "stock": 9,
        "subcategory": 10,
    }
    resistor_rows = [
        schema,
        [
            "C1001", "R0603-10K", 2, "10K 1% 0603 resistor ROHS",
            "https://datasheet.example/C1001.pdf",
            [{"qFrom": 1, "qTo": 99, "price": 0.01}, {"qFrom": 100, "qTo": None, "price": 0.005}],
            "R0603_C1001_front.jpg", "Chip-Resistor-Acme-R0603-10K", [0, 3, 5, 7, 10, 11, 12, 13], 1000, 1,
        ],
        [
            "C1002", "R0603-1K", 2, "1K 1% 0603 resistor ROHS",
            "https://datasheet.example/C1002.pdf",
            [{"qFrom": 1, "qTo": None, "price": 0.02}],
            None, None, [1, 3, 5, 8, 10, 11, 12, 13], 3, 1,
        ],
    ]
    cap_rows = [
        schema,
        [
            "C1003", "C0402-100N", 2, "100nF 0402 capacitor ROHS",
            "https://datasheet.example/C1003.pdf",
            [{"qFrom": 1, "qTo": None, "price": 0.03}],
            None, "Ceramic-Capacitor-CapCo-C0402-100N", [2, 4, 6, 9, 10, 11, 12], 500, 2,
        ],
    ]
    _write_jsonl_gz(path / "components-resistors-001.jsonl.gz", resistor_rows)
    _write_jsonl_gz(path / "components-capacitors-001.jsonl.gz", cap_rows)

    manifest = {
        "version": 4,
        "created": "2026-06-04T00:00:00+00:00",
        "totalComponents": 3,
        "attributesLut": "attributes-lut.json.gz",
        "categories": [
            {
                "id": 1,
                "category": "Resistors",
                "subcategory": "Chip Resistor - Surface Mount",
                "componentCount": 2,
                "shards": ["components-resistors-001.jsonl.gz"],
                "browseShards": ["components-resistors-001.jsonl.gz"],
                "rawCategories": [],
            },
            {
                "id": 2,
                "category": "Capacitors",
                "subcategory": "Multilayer Ceramic Capacitors MLCC - SMD/SMT",
                "componentCount": 1,
                "shards": ["components-capacitors-001.jsonl.gz"],
                "browseShards": ["components-capacitors-001.jsonl.gz"],
                "rawCategories": [],
            },
        ],
        "files": {
            "attributes-lut.json.gz": {"name": "attributes-lut.json.gz", "kind": "attributes-lut"},
            "components-resistors-001.jsonl.gz": {"name": "components-resistors-001.jsonl.gz", "kind": "components", "componentCount": 2, "subcategoryId": 1},
            "components-capacitors-001.jsonl.gz": {"name": "components-capacitors-001.jsonl.gz", "kind": "components", "componentCount": 1, "subcategoryId": 2},
        },
    }
    (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (path / "catalog-metadata.json").write_text(json.dumps({
        "catalog_source": "yaqwsx",
        "source_url": "https://example.test/data",
        "downloaded_at": "2026-06-04T00:00:00+00:00",
        "etag": "test-etag",
        "last_modified": "Thu, 04 Jun 2026 00:00:00 GMT",
        "sha256": "abc123",
        "component_count": 3,
        "schema_version": 4,
    }), encoding="utf-8")
    return path


def build_compact_index_fixture(tmp_path):
    catalog_path = build_upstream_catalog_fixture(tmp_path / "catalog")
    index_path = tmp_path / "mcp-index.sqlite3"
    CompactIndexBuilder(catalog_path, index_path).build(force=True)
    return index_path


def test_compact_index_builder_creates_normalized_schema(tmp_path):
    catalog_path = build_upstream_catalog_fixture(tmp_path / "catalog")
    index_path = tmp_path / "mcp-index.sqlite3"

    result = CompactIndexBuilder(catalog_path, index_path).build(force=True)

    assert result.component_count == 3
    conn = sqlite3.connect(index_path)
    try:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'virtual table')")
        }
        assert {
            "metadata",
            "categories",
            "manufacturers",
            "packages",
            "components",
            "attribute_keys",
            "attribute_values",
            "component_attributes",
            "numeric_attribute_values",
            "price_tiers",
            "website_component_details",
            "components_fts",
        }.issubset(tables)
        component_columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(components)")
        }
        link_columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(component_attributes)")
        }
        assert "attributes_json" not in component_columns
        assert "extra_json" not in component_columns
        assert "jlc_extra_json" not in component_columns
        assert "attribute_json" not in link_columns
        assert conn.execute("SELECT COUNT(*) FROM component_attributes").fetchone()[0] > conn.execute("SELECT COUNT(*) FROM attribute_values").fetchone()[0]
        assert conn.execute("SELECT value FROM metadata WHERE key = 'schema_version'").fetchone()[0] == "1"
        assert conn.execute("SELECT value FROM metadata WHERE key = 'source_kind'").fetchone()[0] == "yaqwsx-generated-catalog"
    finally:
        conn.close()
