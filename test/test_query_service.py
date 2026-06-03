import math
import sqlite3

from jlcparts.partLib import lcscToDb
from jlcparts.pricing import get_quantity_price
from jlcparts.query_cache import build_query_cache, numeric_attribute_values
from jlcparts.query_service import CachedComponentQueryService
from jlcparts.sourceDb import SourceDb


def _price_ranges(*ranges):
    return [
        {"startQuantity": q_from, "endQuantity": q_to, "unitPrice": price}
        for q_from, q_to, price in ranges
    ]


def _parameters(**values):
    return [
        {"parameterName": name, "parameterValue": value}
        for name, value in values.items()
    ]


def _payload(
    lcsc,
    category,
    subcategory,
    mfr,
    package,
    manufacturer,
    library_type,
    stock,
    prices,
    parameters,
    description,
):
    return {
        "componentCode": lcsc,
        "firstTypeName": category,
        "secondTypeName": subcategory,
        "componentModel": mfr,
        "componentSpecification": package,
        "solderJointCount": 2,
        "manufacturer": manufacturer,
        "libraryType": library_type,
        "description": description,
        "dataManualUrl": f"https://datasheet.example/{lcsc}.pdf",
        "stockCount": stock,
        "priceRanges": prices,
        "parameters": parameters,
        "rohsFlag": True,
        "eccnCode": "EAR99",
        "assemblyComponentFlag": True,
        "assemblyProcess": "SMT",
        "assemblyMode": "Standard",
        "websiteComponentId": lcsc[1:],
        "lossNumber": 2,
        "leastNumber": 5,
    }


def _extra(lcsc, manufacturer, attributes):
    slug = f"Example-{lcsc}"
    return {
        "manufacturer": {"en": manufacturer},
        "attributes": attributes,
        "images": [{"original": f"https://assets.example/{lcsc}_front.jpg"}],
        "url": f"https://lcsc.com/product-detail/{slug}_{lcsc}.html",
    }


def _build_source_fixture(path):
    source = SourceDb(path)
    source.updateJlcPayload(_payload(
        "C1001",
        "Resistors",
        "Chip Resistor - Surface Mount",
        "R0603-10K",
        "0603",
        "Acme Resistors",
        "Basic",
        1000,
        _price_ranges((1, 99, 0.01), (100, None, 0.005)),
        _parameters(
            Resistance="10kΩ",
            Package="0603",
            Manufacturer="Acme Resistors",
            **{"Input Resistor": "20mΩ"},
            **{"Operating Temperature": "-40℃~85℃"},
        ),
        "Chip Resistor - Surface Mount 10KOhms 1% 1/10W 0603 RoHS",
    ))
    source.updateExtra("C1001", _extra(
        "C1001",
        "Acme Resistors",
        {"Resistance": "10kΩ", "Tolerance": "±1%"},
    ))

    source.updateJlcPayload(_payload(
        "C1002",
        "Resistors",
        "Chip Resistor - Surface Mount",
        "R0603-1K",
        "0603",
        "Acme Resistors",
        "Extended",
        3,
        _price_ranges((1, 9, 0.02), (10, None, 0.01)),
        _parameters(
            Resistance="-",
            Package="0603",
            Manufacturer="Acme Resistors",
            **{"Input Resistor": "-"},
            **{"Operating Temperature": "0℃~70℃"},
        ),
        "Chip Resistor - Surface Mount 1KOhms 1% 1/10W 0603 RoHS",
    ))
    source.updateExtra("C1002", _extra(
        "C1002",
        "Acme Resistors",
        {"Resistance": "-", "Input Resistor": "-", "Tolerance": "±1%"},
    ))

    source.updateJlcPayload(_payload(
        "C1003",
        "Capacitors",
        "Multilayer Ceramic Capacitors MLCC - SMD/SMT",
        "C0603-100N",
        "0603",
        "CapCo",
        "Extended",
        500,
        _price_ranges((1, 99, 0.03), (100, None, 0.015)),
        _parameters(
            Capacitance="100nF",
            **{
                "Rated Voltage": "50V",
                "Package": "0603",
                "Manufacturer": "CapCo",
                "Forward Voltage (Vf @ If)": "1.2V@20mA",
            },
        ),
        "Multilayer Ceramic Capacitors MLCC - SMD/SMT 100nF 50V X7R 0603 RoHS",
    ))
    source.updateExtra("C1003", _extra(
        "C1003",
        "CapCo",
        {"Capacitance": "100nF", "Voltage - Rated": "50V"},
    ))

    source.updateJlcPayload(_payload(
        "C1004",
        "Capacitors",
        "Multilayer Ceramic Capacitors MLCC - SMD/SMT",
        "C0402-1U",
        "0402",
        "CapCo",
        "Basic",
        0,
        [],
        _parameters(
            Capacitance="1uF",
            **{
                "Rated Voltage": "16V",
                "Package": "0402",
                "Manufacturer": "CapCo",
                "Forward Voltage (Vf @ If)": "2.1V@30mA",
            },
        ),
        "Multilayer Ceramic Capacitors MLCC - SMD/SMT 1uF 16V X5R 0402 RoHS",
    ))
    source.updateExtra("C1004", _extra(
        "C1004",
        "CapCo",
        {"Capacitance": "1uF", "Voltage - Rated": "16V"},
    ))

    source.updateJlcPayload(_payload(
        "C1005",
        "Resistors",
        "Chip Resistor - Surface Mount",
        "R0805-10K",
        "0805",
        "NoExtra Inc",
        "Extended",
        25,
        _price_ranges((1, None, 0.04)),
        _parameters(Resistance="10kΩ", Package="0805", Manufacturer="NoExtra Inc"),
        "Chip Resistor - Surface Mount 10KOhms 5% 1/8W 0805 RoHS",
    ))

    source.updateJlcPayload(_payload(
        "C1006",
        "Capacitors",
        "Aluminum Electrolytic Capacitors",
        "E5-10U",
        "Radial",
        "Electrolytic Ltd",
        "Basic",
        8,
        _price_ranges((5, 49, 0.2), (50, None, 0.15)),
        _parameters(Capacitance="10uF", **{"Rated Voltage": "25V", "Package": "Radial", "Manufacturer": "Electrolytic Ltd"}),
        "Aluminum Electrolytic Capacitors 10uF 25V Radial RoHS",
    ))
    source.updateExtra("C1006", _extra(
        "C1006",
        "Electrolytic Ltd",
        {"Capacitance": "10uF", "Voltage - Rated": "25V"},
    ))

    source.setPreferred({"C1003"})
    source.close()


def _build_query_fixture(tmp_path):
    source_path = tmp_path / "source.sqlite3"
    query_path = tmp_path / "query.sqlite3"
    _build_source_fixture(source_path)
    build_query_cache(source_path, query_path)
    return query_path


def test_get_quantity_price_matches_frontend_tier_selection():
    prices = [
        {"qFrom": 10, "qTo": 20, "price": 1.5},
        {"qFrom": 25, "qTo": None, "price": 1.0},
    ]

    assert get_quantity_price(10, prices) == 1.5
    assert get_quantity_price(20, prices) == 1.5
    assert get_quantity_price(25, prices) == 1.0
    assert get_quantity_price(21, prices) == 1.5
    assert get_quantity_price(1, []) is None


def test_numeric_attribute_values_indexes_all_finite_non_text_units():
    attribute = {
        "values": {
            "force": [2.5, "force"],
            "pressure": [101325, "pressure"],
            "label": ["normally open", "identifier"],
            "text": ["not numeric", "string"],
        }
    }

    assert numeric_attribute_values(attribute) == [
        ("force", "force", 2.5),
        ("pressure", "pressure", 101325.0),
    ]


def test_build_query_cache_creates_expected_tables_and_category_counts(tmp_path):
    query_path = _build_query_fixture(tmp_path)

    conn = sqlite3.connect(query_path)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'virtual table')"
            )
        }
        assert {
            "metadata",
            "categories",
            "components",
            "attribute_keys",
            "attribute_values",
            "component_attributes",
            "numeric_attributes",
            "price_tiers",
        }.issubset(tables)
        assert conn.execute("SELECT COUNT(*) FROM components").fetchone()[0] == 6
        assert conn.execute(
            "SELECT value FROM metadata WHERE key = 'format'"
        ).fetchone()[0] == "query-cache-v1"
    finally:
        conn.close()

    with CachedComponentQueryService(query_path) as service:
        categories = service.list_categories()

    assert categories == [
        {
            "id": 1,
            "category": "Capacitors",
            "subcategory": "Aluminum Electrolytic Capacitors",
            "component_count": 1,
        },
        {
            "id": 2,
            "category": "Capacitors",
            "subcategory": "Multilayer Ceramic Capacitors MLCC - SMD/SMT",
            "component_count": 2,
        },
        {
            "id": 3,
            "category": "Resistors",
            "subcategory": "Chip Resistor - Surface Mount",
            "component_count": 3,
        },
    ]


def test_search_components_filters_by_text_stock_library_exact_and_numeric_values(tmp_path):
    query_path = _build_query_fixture(tmp_path)

    with CachedComponentQueryService(query_path) as service:
        package_values = service.list_attribute_values("Package", limit=10)
        package_0603 = next(
            item["value"]
            for item in package_values["values"]
            if item["display"] == "0603"
        )

        results = service.search_components(
            text_query="resistor",
            exact_filters={"Package": package_0603},
            numeric_filters=[{"name": "Resistance", "unit": "resistance", "min": 9000, "max": 11000}],
            quantity=100,
            in_stock=True,
            library_types=["basic"],
            sort="price",
            limit=10,
            include_attributes=["Resistance", "Package", "Basic/Extended"],
        )

    assert results["total"] == 1
    assert [component["lcsc"] for component in results["components"]] == ["C1001"]
    component = results["components"][0]
    assert component["selected_price"] == 0.005
    assert set(component["attributes"]) == {"Resistance", "Package", "Basic/Extended"}
    assert component["attributes"]["Basic/Extended"]["values"]["default"][0] == "Basic"


def test_search_components_filters_by_required_attributes(tmp_path):
    query_path = _build_query_fixture(tmp_path)

    with CachedComponentQueryService(query_path) as service:
        with_tolerance = service.search_components(
            text_query="resistor",
            required_attributes=["Tolerance"],
            limit=10,
        )
        unknown = service.search_components(
            required_attributes=["Not A Real Attribute"],
            limit=10,
        )

    assert [component["lcsc"] for component in with_tolerance["components"]] == [
        "C1001",
        "C1002",
    ]
    assert unknown["total"] == 0
    assert unknown["components"] == []


def test_search_components_filters_and_returns_assembly_detail_fields(tmp_path):
    query_path = _build_query_fixture(tmp_path)

    with CachedComponentQueryService(query_path) as service:
        results = service.search_components(
            rohs=True,
            eccn="EAR99",
            assembly=True,
            assembly_process="SMT",
            assembly_mode="Standard",
            has_website_detail=True,
            limit=10,
        )

    assert results["total"] == 6
    component = results["components"][0]
    assert component["rohs"] is True
    assert component["eccn"] == "EAR99"
    assert component["assembly"] is True
    assert component["assembly_process"] == "SMT"
    assert component["assembly_mode"] == "Standard"
    assert component["website_component_id"] == component["lcsc"][1:]
    assert component["attrition"] == {"leastNumber": 5, "lossNumber": 2}


def test_misspelled_numeric_attribute_returns_no_matches(tmp_path):
    query_path = _build_query_fixture(tmp_path)

    with CachedComponentQueryService(query_path) as service:
        results = service.search_components(
            numeric_filters=[{
                "name": "Resistnace",
                "unit": "resistance",
                "min": 9000,
            }],
        )

    assert results["total"] == 0


def test_text_search_uses_text_index_not_component_text_search_column(tmp_path):
    query_path = _build_query_fixture(tmp_path)
    conn = sqlite3.connect(query_path)
    try:
        conn.execute("UPDATE components SET text_search = ''")
        conn.commit()
    finally:
        conn.close()

    with CachedComponentQueryService(query_path) as service:
        results = service.search_components(text_query="resistor", limit=10)

    assert results["total"] == 3
    assert [component["lcsc"] for component in results["components"]] == [
        "C1001",
        "C1002",
        "C1005",
    ]


def test_library_filter_can_select_preferred_components(tmp_path):
    query_path = _build_query_fixture(tmp_path)

    with CachedComponentQueryService(query_path) as service:
        preferred = service.search_components(library_types=["preferred"], limit=10)
        extended = service.search_components(library_types=["extended"], limit=10)

    assert [component["lcsc"] for component in preferred["components"]] == ["C1003"]
    assert "C1003" not in {component["lcsc"] for component in extended["components"]}


def test_price_sort_paginates_in_sql_and_places_missing_prices_last(tmp_path):
    query_path = _build_query_fixture(tmp_path)

    with CachedComponentQueryService(query_path) as service:
        original = service._component_from_row
        decoded = 0

        def counted_component_from_row(row, include_attributes=None, quantity=None):
            nonlocal decoded
            decoded += 1
            return original(row, include_attributes=include_attributes, quantity=quantity)

        service._component_from_row = counted_component_from_row
        first_page = service.search_components(sort="price", quantity=1, limit=2)
        last_page = service.search_components(sort="price", quantity=1, offset=5, limit=1)

    assert first_page["total"] == 6
    assert [component["lcsc"] for component in first_page["components"]] == ["C1001", "C1002"]
    assert decoded == 3
    assert last_page["components"][0]["lcsc"] == "C1004"
    assert last_page["components"][0]["selected_price"] is None


def test_search_components_sorts_fixed_keys_with_direction(tmp_path):
    query_path = _build_query_fixture(tmp_path)

    with CachedComponentQueryService(query_path) as service:
        price_desc = service.search_components(
            sort="price",
            sort_direction="desc",
            quantity=1,
            limit=10,
        )
        stock_asc = service.search_components(
            sort="stock",
            sort_direction="asc",
            limit=10,
        )
        stock_desc = service.search_components(
            sort="stock",
            sort_direction="desc",
            limit=10,
        )
        manufacturer_desc = service.search_components(
            sort="manufacturer",
            sort_direction="desc",
            limit=10,
        )
        invalid_direction = service.search_components(
            sort="lcsc",
            sort_direction="sideways",
            limit=10,
        )
        ui_label_sort = service.search_components(
            sort="MFR",
            sort_direction="desc",
            limit=2,
        )
        ui_library_sort = service.search_components(
            sort="Basic/Extended",
            sort_direction="asc",
            limit=3,
        )

    assert [component["lcsc"] for component in price_desc["components"]] == [
        "C1006",
        "C1005",
        "C1003",
        "C1002",
        "C1001",
        "C1004",
    ]
    assert [component["lcsc"] for component in stock_asc["components"]] == [
        "C1004",
        "C1002",
        "C1006",
        "C1005",
        "C1003",
        "C1001",
    ]
    assert [component["lcsc"] for component in stock_desc["components"]] == [
        "C1001",
        "C1003",
        "C1005",
        "C1006",
        "C1002",
        "C1004",
    ]
    assert [component["lcsc"] for component in manufacturer_desc["components"]] == [
        "C1005",
        "C1006",
        "C1003",
        "C1004",
        "C1001",
        "C1002",
    ]
    assert [component["lcsc"] for component in invalid_direction["components"]] == [
        "C1001",
        "C1002",
        "C1003",
        "C1004",
        "C1005",
        "C1006",
    ]
    assert [component["lcsc"] for component in ui_label_sort["components"]] == [
        "C1005",
        "C1002",
    ]
    assert [component["library_type"] for component in ui_library_sort["components"]] == [
        "basic",
        "basic",
        "basic",
    ]


def test_attributes_and_values_can_be_scoped_by_category_and_text(tmp_path):
    query_path = _build_query_fixture(tmp_path)

    with CachedComponentQueryService(query_path) as service:
        mlcc_id = next(
            item["id"]
            for item in service.list_categories()
            if item["subcategory"].startswith("Multilayer Ceramic")
        )
        attributes = service.list_attributes(category_ids=[mlcc_id], text_query="capacitor")
        voltage_values = service.list_attribute_values(
            "Rated Voltage",
            category_ids=(category_id for category_id in [mlcc_id]),
            text_query="capacitor",
        )

    names = {item["name"]: item for item in attributes}
    assert names["Capacitance"]["count"] == 2
    assert names["Rated Voltage"]["quantity_types"] == ["voltage"]
    assert voltage_values["numeric"] == {
        "min": 16.0,
        "max": 50.0,
        "units": ["voltage"],
        "ranges": [{"unit": "voltage", "min": 16.0, "max": 50.0}],
    }
    assert {item["display"] for item in voltage_values["values"]} == {"16 V", "50 V"}


def test_default_search_paginates_before_decoding_component_json(tmp_path):
    query_path = _build_query_fixture(tmp_path)

    with CachedComponentQueryService(query_path) as service:
        original = service._component_from_row
        decoded = 0

        def counted_component_from_row(row, include_attributes=None, quantity=None):
            nonlocal decoded
            decoded += 1
            return original(row, include_attributes=include_attributes, quantity=quantity)

        service._component_from_row = counted_component_from_row
        results = service.search_components(offset=2, limit=2)

    assert results["total"] == 6
    assert [component["lcsc"] for component in results["components"]] == ["C1003", "C1004"]
    assert decoded == 2


def test_numeric_filter_can_target_specific_same_unit_value_name(tmp_path):
    query_path = _build_query_fixture(tmp_path)

    with CachedComponentQueryService(query_path) as service:
        broad = service.search_components(
            text_query="resistor",
            numeric_filters=[{
                "name": "Operating Temperature",
                "unit": "temperature",
                "min": 80,
            }],
        )
        min_filtered = service.search_components(
            text_query="resistor",
            numeric_filters=[{
                "name": "Operating Temperature",
                "unit": "temperature",
                "value_name": "temperature min",
                "min": 80,
            }],
        )
        max_filtered = service.search_components(
            text_query="resistor",
            numeric_filters=[{
                "name": "Operating Temperature",
                "unit": "temperature",
                "quantity_name": "temperature max",
                "min": 80,
            }],
        )

    assert [component["lcsc"] for component in broad["components"]] == ["C1001"]
    assert min_filtered["total"] == 0
    assert [component["lcsc"] for component in max_filtered["components"]] == ["C1001"]


def test_mixed_unit_numeric_metadata_returns_per_unit_ranges(tmp_path):
    query_path = _build_query_fixture(tmp_path)

    with CachedComponentQueryService(query_path) as service:
        values = service.list_attribute_values("Forward Voltage (Vf @ If)")

    assert values["numeric"]["ranges"] == [
        {"unit": "current", "min": 0.02, "max": 0.03},
        {"unit": "voltage", "min": 1.2, "max": 2.1},
    ]
    assert values["numeric"]["min"] is None
    assert values["numeric"]["max"] is None
    assert values["numeric"]["units"] == ["current", "voltage"]


def test_attribute_sort_handles_numeric_and_nan_values_without_crashing(tmp_path):
    query_path = _build_query_fixture(tmp_path)

    with CachedComponentQueryService(query_path) as service:
        results = service.search_components(
            text_query="resistor",
            sort_attribute="Input Resistor",
            limit=10,
        )

    assert results["total"] == 3
    assert [component["lcsc"] for component in results["components"]] == [
        "C1001",
        "C1002",
        "C1005",
    ]


def test_search_components_sorts_by_attribute_desc(tmp_path):
    query_path = _build_query_fixture(tmp_path)

    with CachedComponentQueryService(query_path) as service:
        results = service.search_components(
            text_query="capacitor",
            sort_attribute="Capacitance",
            sort_direction="desc",
            limit=10,
        )

    assert results["total"] == 3
    assert [component["lcsc"] for component in results["components"]] == [
        "C1006",
        "C1004",
        "C1003",
    ]


def test_get_component_returns_full_payload_with_missing_lcsc_extra(tmp_path):
    query_path = _build_query_fixture(tmp_path)

    with CachedComponentQueryService(query_path) as service:
        component = service.get_component("C1005")

    assert component["lcsc"] == "C1005"
    assert component["extra"] == {}
    assert component["jlc_extra"]["attributes"]["Resistance"] == "10kΩ"
    assert component["attributes"]["Resistance"]["values"]["resistance"][0] == 10000.0
    assert component["attributes"]["Manufacturer"]["values"]["identifier"][0] == "NoExtra Inc"
    assert component["image"] is None
    assert component["url"] is None


def test_component_output_includes_convenience_links_and_image_urls(tmp_path):
    query_path = _build_query_fixture(tmp_path)

    with CachedComponentQueryService(query_path) as service:
        component = service.get_component("C1001")
        missing_image = service.get_component("C1005")

    assert component["lcsc_url"] == "https://lcsc.com/product-detail/Example-C1001_C1001.html"
    assert component["image_urls"] == {
        "small": "https://assets.lcsc.com/images/lcsc/96x96/C1001_front.jpg",
        "medium": "https://assets.lcsc.com/images/lcsc/224x224/C1001_front.jpg",
        "large": "https://assets.lcsc.com/images/lcsc/900x900/C1001_front.jpg",
    }
    assert missing_image["lcsc_url"] == "https://www.lcsc.com/search?q=C1005"
    assert missing_image["image_urls"] is None


def test_compare_components_preserves_order_reports_missing_and_differences(tmp_path):
    query_path = _build_query_fixture(tmp_path)

    with CachedComponentQueryService(query_path) as service:
        comparison = service.compare_components(
            ["C1002", "C9999", "C1001"],
            quantity=100,
            attributes=["Resistance", "Package", "Basic/Extended"],
            only_differences=True,
        )

    assert comparison["missing_lcsc"] == ["C9999"]
    assert [component["lcsc"] for component in comparison["components"]] == ["C1002", "C1001"]
    assert [component["selected_price"] for component in comparison["components"]] == [0.01, 0.005]
    assert set(comparison["differing_attributes"]) == {"Basic/Extended", "Resistance"}
    assert all("Package" not in component["attributes"] for component in comparison["components"])


def test_compare_components_supports_ordering_and_stock_filter(tmp_path):
    query_path = _build_query_fixture(tmp_path)

    with CachedComponentQueryService(query_path) as service:
        keep_order = service.compare_components(["C1005", "C1001", "C1003"])
        sorted_order = service.compare_components(
            ["C1005", "C1001", "C1003"],
            keep_order=False,
        )
        in_stock = service.compare_components(
            ["C1002", "C9999", "C1001"],
            quantity=100,
            in_stock=True,
        )

    assert [component["lcsc"] for component in keep_order["components"]] == [
        "C1005",
        "C1001",
        "C1003",
    ]
    assert [component["lcsc"] for component in sorted_order["components"]] == [
        "C1001",
        "C1003",
        "C1005",
    ]
    assert in_stock["missing_lcsc"] == ["C9999"]
    assert [component["lcsc"] for component in in_stock["components"]] == ["C1001"]


def test_lcsc_codes_are_stored_as_text_not_integer_payloads(tmp_path):
    query_path = _build_query_fixture(tmp_path)

    with CachedComponentQueryService(query_path) as service:
        component = service.get_component("C1001")

    assert component["lcsc"] == "C1001"
    assert lcscToDb(component["lcsc"]) == 1001
