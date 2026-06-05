from jlcparts.compact_query import CompactQueryService
from test_compact_index import build_compact_index_fixture


def test_compact_query_search_filters_and_sorts(tmp_path):
    index_path = build_compact_index_fixture(tmp_path)

    with CompactQueryService(index_path) as service:
        categories = service.list_categories(search="resistor")
        package_values = service.list_attribute_values("Package", limit=10)
        package_0603 = next(
            item["value"]
            for item in package_values["values"]
            if item["display"] == "0603"
        )
        results = service.search_components(
            text_query="resistor",
            category_ids=[categories[0]["category_id"]],
            exact_filters={"Package": package_0603},
            numeric_filters=[{"name": "Resistance", "unit": "resistance", "min": 9000, "max": 11000}],
            quantity=100,
            in_stock=True,
            library_types=["basic"],
            sort="price",
            limit=10,
            include_attributes=["Resistance", "Package", "Basic/Extended"],
        )

    assert categories[0]["path"] == "Resistors / Chip Resistor - Surface Mount"
    assert results["total"] == 1
    component = results["components"][0]
    assert component["lcsc"] == "C1001"
    assert component["manufacturer"] == "Acme"
    assert component["package"] == "0603"
    assert component["selected_price"] == 0.005
    assert set(component["attributes"]) == {"Resistance", "Package", "Basic/Extended"}


def test_compact_query_facets_pagination_and_exact_lcsc(tmp_path):
    index_path = build_compact_index_fixture(tmp_path)

    with CompactQueryService(index_path) as service:
        attributes = service.list_attributes(text_query="resistor")
        resistance_values = service.list_attribute_values("Resistance", text_query="resistor")
        exact = service.search_components(text_query="C1003", limit=10)
        page = service.search_components(sort="stock", sort_direction="desc", offset=1, limit=1)

    assert {item["name"] for item in attributes} >= {"Resistance", "Package", "Manufacturer"}
    assert resistance_values["numeric"]["ranges"] == [
        {"unit": "resistance", "min": 1000.0, "max": 10000.0}
    ]
    assert [component["lcsc"] for component in exact["components"]] == ["C1003"]
    assert page["total"] == 3
    assert [component["lcsc"] for component in page["components"]] == ["C1003"]


def test_compact_query_get_and_compare(tmp_path):
    index_path = build_compact_index_fixture(tmp_path)

    with CompactQueryService(index_path) as service:
        component = service.get_component("1001")
        comparison = service.compare_components(
            ["C1002", "C9999", "C1001"],
            quantity=100,
            attributes=["Resistance", "Package", "Basic/Extended"],
            only_differences=True,
        )

    assert component["lcsc"] == "C1001"
    assert component["lcsc_url"] == "https://lcsc.com/product-detail/Chip-Resistor-Acme-R0603-10K_C1001.html"
    assert component["image_urls"]["small"].endswith("/R0603_C1001_front.jpg")
    assert component["source"] == "upstream_catalog"
    assert comparison["missing_lcsc"] == ["C9999"]
    assert [component["lcsc"] for component in comparison["components"]] == ["C1002", "C1001"]
    assert set(comparison["differing_attributes"]) == {"Basic/Extended", "Resistance"}
    assert all("Package" not in component["attributes"] for component in comparison["components"])


def test_compact_query_connections_are_configured_for_concurrent_mcp_clients(tmp_path):
    index_path = build_compact_index_fixture(tmp_path)

    with CompactQueryService(index_path, read_only=False) as writer:
        journal_mode = writer.conn.execute("PRAGMA journal_mode").fetchone()[0]
        writer_busy_timeout_ms = writer.conn.execute("PRAGMA busy_timeout").fetchone()[0]

    with CompactQueryService(index_path) as reader:
        reader_busy_timeout_ms = reader.conn.execute("PRAGMA busy_timeout").fetchone()[0]
        query_only = reader.conn.execute("PRAGMA query_only").fetchone()[0]
        result = reader.search_components(text_query="resistor", limit=1)

    assert journal_mode.lower() == "wal"
    assert writer_busy_timeout_ms >= 30000
    assert reader_busy_timeout_ms >= 30000
    assert query_only == 1
    assert result["total"] == 2


def test_website_detail_lookup_rejects_invalid_lcsc_without_remote_call(tmp_path):
    index_path = build_compact_index_fixture(tmp_path)
    calls = []

    def lookup_func(lcsc):
        calls.append(lcsc)
        return {"websiteComponentId": 123}

    with CompactQueryService(index_path) as service:
        result = service.lookup_component_website_detail("resistor 10k", lookup_func=lookup_func)

    assert result["found"] is False
    assert result["error"] == "invalid_lcsc"
    assert calls == []


def test_website_detail_lookup_rejects_non_cached_lcsc_without_remote_call(tmp_path):
    index_path = build_compact_index_fixture(tmp_path)
    calls = []

    def lookup_func(lcsc):
        calls.append(lcsc)
        return {"websiteComponentId": 123}

    with CompactQueryService(index_path) as service:
        result = service.lookup_component_website_detail("C9999", lookup_func=lookup_func)

    assert result["found"] is False
    assert result["error"] == "not_in_cache"
    assert calls == []


def test_website_detail_lookup_allows_cached_exact_lcsc(tmp_path):
    index_path = build_compact_index_fixture(tmp_path)
    calls = []

    def lookup_func(lcsc):
        calls.append(lcsc)
        return {"websiteComponentId": 123}

    with CompactQueryService(index_path) as service:
        result = service.lookup_component_website_detail("1001", lookup_func=lookup_func)

    assert result["found"] is True
    assert result["website_detail"] == {"websiteComponentId": 123}
    assert calls == ["C1001"]
