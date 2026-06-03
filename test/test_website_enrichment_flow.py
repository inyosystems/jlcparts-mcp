import sqlite3
import time
from unittest.mock import Mock

from jlcparts.mcp_server import CacheManager
from jlcparts.query_cache import build_query_cache
from jlcparts.sourceDb import SourceDb
from jlcparts.ui import enrichWebsiteDetails, refreshSourceDb
from test_mcp_server import _config
from test_query_service import _parameters, _payload, _price_ranges


def _official_payload(lcsc="C9001"):
    payload = _payload(
        lcsc,
        "Resistors",
        "Chip Resistor - Surface Mount",
        "R0603-10K",
        "0603",
        "Acme",
        "Basic",
        100,
        _price_ranges((1, None, 0.01)),
        _parameters(Resistance="10kΩ", Package="0603"),
        "10k resistor",
    )
    payload["assemblyProcess"] = None
    payload["assemblyMode"] = None
    payload["websiteComponentId"] = None
    payload.pop("lossNumber", None)
    payload.pop("leastNumber", None)
    return payload


class _OnePageInterface:
    def __init__(self, page):
        self.page = page
        self.calls = 0
        self.lastPage = None

    def getPage(self):
        self.calls += 1
        if self.calls == 1:
            self.lastPage = "cursor-1"
            return list(self.page)
        self.lastPage = None
        return None


def test_refresh_source_db_skips_website_enrichment_by_default(monkeypatch, tmp_path):
    interface = _OnePageInterface([_official_payload()])
    enrich = Mock(side_effect=AssertionError("website enrichment should be opt-in"))
    monkeypatch.setattr(
        "jlcparts.jlcpcb.createComponentInterface",
        lambda lastKey=None, credentials=None: interface,
    )
    monkeypatch.setattr("jlcparts.jlcpcb.enrichComponentsFromWebsite", enrich)

    result = refreshSourceDb(str(tmp_path / "cache.sqlite3"), limit=0)

    assert result["done"] is True
    assert result["count"] == 1
    assert result["website_enrichment"] is False
    enrich.assert_not_called()


def test_refresh_source_db_can_opt_into_website_enrichment(monkeypatch, tmp_path):
    interface = _OnePageInterface([_official_payload()])

    def enrich(page):
        enriched = list(page)
        enriched[0] = {
            **enriched[0],
            "websiteComponentId": 42,
            "assemblyProcess": "SMT",
            "assemblyMode": "smtWeld",
            "lossNumber": 1,
        }
        return enriched

    monkeypatch.setattr(
        "jlcparts.jlcpcb.createComponentInterface",
        lambda lastKey=None, credentials=None: interface,
    )
    monkeypatch.setattr("jlcparts.jlcpcb.enrichComponentsFromWebsite", Mock(side_effect=enrich))

    result = refreshSourceDb(
        str(tmp_path / "cache.sqlite3"),
        limit=0,
        enrich_website=True,
    )

    db = SourceDb(str(tmp_path / "cache.sqlite3"), create=False)
    try:
        row = db.conn.execute(
            "SELECT website_component_id, assembly_process, assembly_mode, attrition "
            "FROM jlc_components WHERE lcsc = 9001"
        ).fetchone()
    finally:
        db.close()

    assert result["website_enrichment"] is True
    assert row["website_component_id"] == "42"
    assert row["assembly_process"] == "SMT"
    assert row["assembly_mode"] == "smtWeld"
    assert '"lossNumber":1' in row["attrition"]


def test_standalone_website_enrichment_updates_source_and_marks_query_stale(monkeypatch, tmp_path):
    source_path = str(tmp_path / "cache.sqlite3")
    query_path = str(tmp_path / "query.sqlite3")
    source = SourceDb(source_path)
    source.updateJlcPayload(_official_payload())
    source.setMeta("last_successful_refresh", str(int(time.time()) - 10))
    source.close()
    build_query_cache(source_path, query_path)
    with sqlite3.connect(query_path) as conn:
        conn.execute("UPDATE metadata SET value = '1' WHERE key = 'built_at'")
        conn.commit()

    monkeypatch.setattr(
        "jlcparts.jlcpcb._website_component_enrichment",
        lambda lcsc: {
            "websiteComponentId": 100,
            "assemblyProcess": "SMT",
            "assemblyMode": "smtWeld",
            "lossNumber": 2,
            "leastNumber": 5,
        },
    )

    result = enrichWebsiteDetails(source_path, workers=1)

    db = SourceDb(source_path, create=False)
    try:
        row = db.conn.execute(
            "SELECT website_component_id, assembly_process, assembly_mode, attrition "
            "FROM jlc_components WHERE lcsc = 9001"
        ).fetchone()
        meta = db.metaDict()
    finally:
        db.close()
    config = _config(tmp_path)
    manager = CacheManager(config, refresh_func=Mock())
    status = manager.cache_status()

    assert result["candidate_count"] == 1
    assert result["enriched"] == 1
    assert result["failed"] == 0
    assert row["website_component_id"] == "100"
    assert row["assembly_process"] == "SMT"
    assert row["assembly_mode"] == "smtWeld"
    assert '"lossNumber":2' in row["attrition"]
    assert '"leastNumber":5' in row["attrition"]
    assert meta["last_successful_website_enrichment"]
    assert status["source_stale"] is False
    assert status["query_stale"] is True
