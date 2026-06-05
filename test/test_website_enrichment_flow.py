import json
import sqlite3

from jlcparts.compact_query import CompactQueryService
from test_compact_index import build_compact_index_fixture


def test_exact_website_detail_lookup_updates_only_requested_component(tmp_path):
    index_path = build_compact_index_fixture(tmp_path)

    def fake_lookup(lcsc):
        assert lcsc == "C1001"
        return {
            "websiteComponentId": 1001,
            "assemblyProcess": "SMT",
            "assemblyMode": "smtWeld",
            "lossNumber": 2,
            "leastNumber": 5,
        }

    with CompactQueryService(index_path, read_only=False) as service:
        result = service.lookup_component_website_detail("C1001", lookup_func=fake_lookup)

    conn = sqlite3.connect(index_path)
    try:
        detail_rows = conn.execute(
            "SELECT lcsc, website_json FROM website_component_details"
        ).fetchall()
        rows = conn.execute(
            "SELECT lcsc, website_checked_at FROM components ORDER BY lcsc"
        ).fetchall()
    finally:
        conn.close()

    assert result["found"] is True
    assert detail_rows == [
        (
            "C1001",
            json.dumps(result["website_detail"], separators=(",", ":")),
        )
    ]
    assert [(lcsc, checked_at is not None) for lcsc, checked_at in rows] == [
        ("C1001", True),
        ("C1002", False),
        ("C1003", False),
    ]


def test_exact_website_detail_failure_is_actionable_and_does_not_mark_component(tmp_path):
    index_path = build_compact_index_fixture(tmp_path)

    with CompactQueryService(index_path, read_only=False) as service:
        result = service.lookup_component_website_detail(
            "C1001",
            lookup_func=lambda lcsc: (_ for _ in ()).throw(RuntimeError("website down")),
        )

    conn = sqlite3.connect(index_path)
    try:
        detail_count = conn.execute(
            "SELECT COUNT(*) FROM website_component_details"
        ).fetchone()[0]
        checked_at = conn.execute(
            "SELECT website_checked_at FROM components WHERE lcsc = 'C1001'"
        ).fetchone()[0]
    finally:
        conn.close()

    assert result["found"] is False
    assert "website down" in result["error"]
    assert "public website" in result["note"]
    assert detail_count == 0
    assert checked_at is None
