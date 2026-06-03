import json
import math
import os
import re
import sqlite3
import time

from .datatables import extractComponent
from .partLib import lcscToDb
from .sourceDb import SourceDb


QUERY_CACHE_FORMAT = "query-cache-v1"
COMPONENT_EXTRACTION_SCHEMA = ["img", "url", "attributes"]

_NON_NUMERIC_QUANTITY_TYPES = {"identifier", "string"}

_SI_UNITS = {
    "capacitance": "F",
    "charge": "C",
    "current": "A",
    "data_rate": "bps",
    "energy": "J",
    "frequency": "Hz",
    "inductance": "H",
    "length": "m",
    "luminous_intensity": "cd",
    "magnetic_flux_density": "T",
    "power": "W",
    "radiant_intensity": "W/sr",
    "resistance": "Ohm",
    "slew_rate": "V/s",
    "time": "s",
    "voltage": "V",
}


def _canonical_json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _json_loads(value, fallback=None):
    if fallback is None:
        fallback = {}
    if value in [None, ""]:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _format_number(value):
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return f"{value:.12g}"


def _format_si(value, unit):
    if value == "NaN":
        return "-"
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return str(value)
    if value == 0:
        return f"0 {unit}"

    prefixes = [
        (1e-12, "p"),
        (1e-9, "n"),
        (1e-6, "u"),
        (1e-3, "m"),
        (1, ""),
        (1e3, "k"),
        (1e6, "M"),
        (1e9, "G"),
    ]
    magnitude, prefix = prefixes[-1]
    for index, candidate in enumerate(prefixes):
        if index == len(prefixes) - 1 or abs(value) < prefixes[index + 1][0]:
            magnitude, prefix = candidate
            break
    return f"{_format_number(value / magnitude)} {prefix}{unit}"


def _format_resistance(value):
    if value == "NaN":
        return "-"
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return str(value)
    if value == 0:
        return "0R"
    if value < 1:
        return f"{_format_number(value * 1000)}mR"
    if value < 1e3:
        return f"{_format_number(value)}R"
    if value < 1e6:
        return f"{_format_number(value / 1e3)}k"
    if value < 1e9:
        return f"{_format_number(value / 1e6)}M"
    return f"{_format_number(value / 1e9)}G"


def format_quantity(value, quantity_type):
    if quantity_type in ["identifier", "string"]:
        return "" if value is None else str(value)
    if quantity_type == "resistance":
        return _format_resistance(value)
    if quantity_type in _SI_UNITS:
        return _format_si(value, _SI_UNITS[quantity_type])
    if quantity_type == "percentage":
        return "-" if value == "NaN" else f"{_format_number(value)} %"
    if quantity_type == "ppm":
        return "-" if value == "NaN" else f"{_format_number(value)} ppm"
    if quantity_type == "temperature":
        return "-" if value == "NaN" else f"{_format_number(value)} °C"
    if quantity_type == "kelvin":
        return "-" if value == "NaN" else f"{_format_number(value)} K"
    if quantity_type == "angle":
        return "-" if value == "NaN" else f"{_format_number(value)}°"
    if quantity_type == "count":
        return "" if value is None else str(value)
    return "" if value is None else str(value)


def attribute_display(attribute):
    if not isinstance(attribute, dict):
        return ""
    values = attribute.get("values")
    display = attribute.get("format")
    if not isinstance(values, dict) or not isinstance(display, str):
        return ""
    for name, value in values.items():
        if not isinstance(value, list) or len(value) < 2:
            replacement = ""
        else:
            replacement = format_quantity(value[0], value[1])
        display = display.replace("${" + name + "}", replacement)
    return display


def attribute_quantity_types(attribute):
    if not isinstance(attribute, dict):
        return []
    values = attribute.get("values", {})
    if not isinstance(values, dict):
        return []
    return sorted({
        value[1]
        for value in values.values()
        if isinstance(value, list) and len(value) >= 2
    })


def numeric_attribute_values(attribute):
    if not isinstance(attribute, dict):
        return []
    values = attribute.get("values", {})
    if not isinstance(values, dict):
        return []

    result = []
    for value_name, value in values.items():
        if not isinstance(value, list) or len(value) < 2:
            continue
        number, quantity_type = value[0], value[1]
        if quantity_type in _NON_NUMERIC_QUANTITY_TYPES:
            continue
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            continue
        if not math.isfinite(number):
            continue
        result.append((value_name, quantity_type, float(number)))
    return result


def build_query_cache(source_db_path, query_db_path):
    tmp_path = f"{query_db_path}.tmp"
    if os.path.exists(tmp_path):
        os.unlink(tmp_path)

    source = SourceDb(source_db_path, create=False)
    conn = sqlite3.connect(tmp_path)
    conn.row_factory = sqlite3.Row
    try:
        _create_schema(conn)
        _populate(conn, source, source_db_path)
        conn.commit()
        conn.execute("VACUUM")
    except Exception:
        conn.close()
        source.close()
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
    else:
        conn.close()
        source.close()
        os.replace(tmp_path, query_db_path)


def _create_schema(conn):
    conn.executescript("""
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY NOT NULL,
            value TEXT NOT NULL
        );

        CREATE TABLE categories (
            id INTEGER PRIMARY KEY NOT NULL,
            category TEXT NOT NULL,
            subcategory TEXT NOT NULL,
            component_count INTEGER NOT NULL,
            UNIQUE(category, subcategory)
        );

        CREATE TABLE components (
            lcsc TEXT PRIMARY KEY NOT NULL,
            lcsc_number INTEGER NOT NULL,
            category_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            subcategory TEXT NOT NULL,
            mfr TEXT NOT NULL,
            manufacturer TEXT NOT NULL,
            package TEXT NOT NULL,
            joints INTEGER NOT NULL,
            stock INTEGER NOT NULL,
            basic INTEGER NOT NULL,
            preferred INTEGER NOT NULL,
            library_type TEXT NOT NULL,
            description TEXT NOT NULL,
            datasheet TEXT NOT NULL,
            price_json TEXT NOT NULL,
            image TEXT,
            url TEXT,
            url_slug TEXT,
            extra_json TEXT NOT NULL,
            jlc_extra_json TEXT NOT NULL,
            rohs INTEGER,
            eccn TEXT NOT NULL,
            assembly INTEGER,
            assembly_process TEXT,
            assembly_mode TEXT,
            website_component_id TEXT,
            attrition_json TEXT NOT NULL,
            attributes_json TEXT NOT NULL,
            text_search TEXT NOT NULL
        );

        CREATE TABLE attribute_keys (
            id INTEGER PRIMARY KEY NOT NULL,
            name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE attribute_values (
            id INTEGER PRIMARY KEY NOT NULL,
            attribute_id INTEGER NOT NULL,
            value_json TEXT NOT NULL,
            display TEXT NOT NULL,
            quantity_types_json TEXT NOT NULL,
            UNIQUE(attribute_id, value_json)
        );

        CREATE TABLE component_attributes (
            component_lcsc TEXT NOT NULL,
            attribute_id INTEGER NOT NULL,
            value_id INTEGER NOT NULL,
            attribute_json TEXT NOT NULL,
            sort_kind INTEGER NOT NULL,
            sort_number REAL NOT NULL,
            sort_text TEXT NOT NULL,
            PRIMARY KEY(component_lcsc, attribute_id)
        );

        CREATE TABLE numeric_attributes (
            component_lcsc TEXT NOT NULL,
            attribute_id INTEGER NOT NULL,
            value_name TEXT NOT NULL,
            quantity_type TEXT NOT NULL,
            value REAL NOT NULL
        );

        CREATE TABLE price_tiers (
            component_lcsc TEXT NOT NULL,
            tier_index INTEGER NOT NULL,
            q_from INTEGER NOT NULL,
            q_to INTEGER,
            price REAL NOT NULL,
            PRIMARY KEY(component_lcsc, tier_index)
        );

        CREATE INDEX components_category_idx ON components(category_id, lcsc_number);
        CREATE INDEX components_stock_idx ON components(stock);
        CREATE INDEX components_library_idx ON components(basic, preferred);
        CREATE INDEX components_assembly_idx
            ON components(assembly, assembly_process, assembly_mode);
        CREATE INDEX components_rohs_eccn_idx ON components(rohs, eccn);
        CREATE INDEX attribute_values_attribute_idx ON attribute_values(attribute_id);
        CREATE INDEX component_attributes_attribute_idx ON component_attributes(attribute_id, value_id);
        CREATE INDEX component_attributes_value_idx ON component_attributes(value_id);
        CREATE INDEX numeric_attributes_lookup_idx
            ON numeric_attributes(attribute_id, quantity_type, value);
        CREATE INDEX price_tiers_component_idx ON price_tiers(component_lcsc, q_from, q_to);
    """)

    try:
        conn.execute("CREATE VIRTUAL TABLE component_fts USING fts5(lcsc UNINDEXED, text)")
        conn.execute(
            "INSERT INTO metadata(key, value) VALUES ('text_support', 'fts5')"
        )
    except sqlite3.Error:
        conn.execute("""
            CREATE TABLE component_text (
                lcsc TEXT PRIMARY KEY NOT NULL,
                text TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX component_text_idx ON component_text(text)")
        conn.execute(
            "INSERT INTO metadata(key, value) VALUES ('text_support', 'like')"
        )


def _populate(conn, source, source_db_path):
    conn.executemany(
        "INSERT INTO metadata(key, value) VALUES (?, ?)",
        [
            ("format", QUERY_CACHE_FORMAT),
            ("source_db_path", str(source_db_path)),
            ("built_at", str(int(time.time()))),
        ],
    )

    category_id_by_pair = {}
    component_count = 0
    for category, subcategories in source.categories().items():
        for subcategory in subcategories:
            category_id = source.getCategoryId(category, subcategory)
            count = source.countCategoryComponents(category, subcategory)
            category_id_by_pair[(category, subcategory)] = category_id
            conn.execute(
                """
                INSERT INTO categories(id, category, subcategory, component_count)
                VALUES (?, ?, ?, ?)
                """,
                (category_id, category, subcategory, count),
            )

    for (category, subcategory), category_id in category_id_by_pair.items():
        for component in source.iterCategoryComponents(category, subcategory):
            _insert_component(conn, category_id, component)
            component_count += 1

    conn.execute(
        "INSERT INTO metadata(key, value) VALUES ('component_count', ?)",
        (str(component_count),),
    )


def _insert_component(conn, category_id, component):
    image, url_slug, normalized_attributes = extractComponent(
        component,
        COMPONENT_EXTRACTION_SCHEMA,
    )
    extra = component.get("extra", {})
    url = extra.get("url") if isinstance(extra, dict) else None
    if not url and url_slug:
        url = f"https://lcsc.com/product-detail/{url_slug}_{component['lcsc']}.html"

    library_type = _component_library_type(component)
    price = component.get("price") or []
    jlc_extra = component.get("jlc_extra") or {}
    attrition = jlc_extra.get("attrition") if isinstance(jlc_extra, dict) else {}
    text_search = _component_search_text(component, normalized_attributes)

    conn.execute(
        """
        INSERT INTO components (
            lcsc, lcsc_number, category_id, category, subcategory, mfr,
            manufacturer, package, joints, stock, basic, preferred,
            library_type, description, datasheet, price_json, image, url,
            url_slug, extra_json, jlc_extra_json, rohs, eccn, assembly,
            assembly_process, assembly_mode, website_component_id,
            attrition_json, attributes_json, text_search
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            component["lcsc"],
            lcscToDb(component["lcsc"]),
            category_id,
            component["category"],
            component["subcategory"],
            component["mfr"],
            component.get("manufacturer") or "",
            component.get("package") or "",
            int(component.get("joints") or 0),
            int(component.get("stock") or 0),
            int(bool(component.get("basic"))),
            int(bool(component.get("preferred"))),
            library_type,
            component.get("description") or "",
            component.get("datasheet") or "",
            _canonical_json(price),
            image,
            url,
            url_slug,
            _canonical_json(extra or {}),
            _canonical_json(jlc_extra),
            None if jlc_extra.get("rohs") is None else int(bool(jlc_extra.get("rohs"))),
            jlc_extra.get("eccn") or "",
            None if jlc_extra.get("assembly") is None else int(bool(jlc_extra.get("assembly"))),
            jlc_extra.get("assemblyProcess"),
            jlc_extra.get("assemblyMode"),
            None if jlc_extra.get("websiteComponentId") is None else str(jlc_extra.get("websiteComponentId")),
            _canonical_json(attrition if isinstance(attrition, dict) else {}),
            _canonical_json(normalized_attributes),
            text_search,
        ),
    )

    _insert_text_row(conn, component["lcsc"], text_search)
    _insert_price_tiers(conn, component["lcsc"], price)

    for attribute_name, attribute in normalized_attributes.items():
        attribute_id = _attribute_id(conn, attribute_name)
        value_json = _canonical_json(attribute)
        value_id = _attribute_value_id(conn, attribute_id, attribute, value_json)
        sort_kind, sort_number, sort_text = attribute_sort_key(attribute)
        conn.execute(
            """
            INSERT INTO component_attributes(
                component_lcsc, attribute_id, value_id, attribute_json,
                sort_kind, sort_number, sort_text
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                component["lcsc"], attribute_id, value_id, value_json,
                sort_kind, sort_number, sort_text,
            ),
        )
        for value_name, quantity_type, number in numeric_attribute_values(attribute):
            conn.execute(
                """
                INSERT INTO numeric_attributes(
                    component_lcsc, attribute_id, value_name, quantity_type, value
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (component["lcsc"], attribute_id, value_name, quantity_type, number),
            )


def _insert_price_tiers(conn, lcsc, price):
    for index, pricepoint in enumerate(price):
        if not isinstance(pricepoint, dict):
            continue
        q_from = pricepoint.get("qFrom")
        unit_price = pricepoint.get("price")
        if q_from is None or unit_price is None:
            continue
        conn.execute(
            """
            INSERT INTO price_tiers(component_lcsc, tier_index, q_from, q_to, price)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                lcsc,
                index,
                int(q_from),
                None if pricepoint.get("qTo") in [None, ""] else int(pricepoint.get("qTo")),
                float(unit_price),
            ),
        )


def _insert_text_row(conn, lcsc, text_search):
    text_support = conn.execute(
        "SELECT value FROM metadata WHERE key = 'text_support'"
    ).fetchone()[0]
    if text_support == "fts5":
        conn.execute(
            "INSERT INTO component_fts(lcsc, text) VALUES (?, ?)",
            (lcsc, text_search),
        )
    else:
        conn.execute(
            "INSERT INTO component_text(lcsc, text) VALUES (?, ?)",
            (lcsc, text_search),
        )


def _attribute_id(conn, name):
    conn.execute(
        "INSERT OR IGNORE INTO attribute_keys(name) VALUES (?)",
        (name,),
    )
    return conn.execute(
        "SELECT id FROM attribute_keys WHERE name = ?",
        (name,),
    ).fetchone()["id"]


def _attribute_value_id(conn, attribute_id, attribute, value_json):
    conn.execute(
        """
        INSERT OR IGNORE INTO attribute_values(
            attribute_id, value_json, display, quantity_types_json
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            attribute_id,
            value_json,
            attribute_display(attribute),
            _canonical_json(attribute_quantity_types(attribute)),
        ),
    )
    return conn.execute(
        """
        SELECT id FROM attribute_values
        WHERE attribute_id = ? AND value_json = ?
        """,
        (attribute_id, value_json),
    ).fetchone()["id"]


def _component_library_type(component):
    if component.get("preferred"):
        return "preferred"
    if component.get("basic"):
        return "basic"
    return "extended"


def _component_search_text(component, attributes):
    parts = [
        component.get("lcsc"),
        component.get("category"),
        component.get("subcategory"),
        component.get("mfr"),
        component.get("manufacturer"),
        component.get("package"),
        component.get("description"),
    ]
    for name, attribute in attributes.items():
        parts.append(name)
        parts.append(attribute_display(attribute))
    return " ".join(str(part) for part in parts if part).lower()


def tokenize_text_query(text_query):
    return re.findall(r"[a-z0-9]+", (text_query or "").lower())


def attribute_sort_key(attribute):
    if not isinstance(attribute, dict):
        return 3, 0, ""
    values = attribute.get("values", {})
    primary = attribute.get("primary")
    value = None
    if isinstance(values, dict):
        for key in [primary, attribute.get("default"), *values.keys()]:
            if key in values:
                value = values[key]
                break
    if isinstance(value, list) and len(value) >= 2:
        if isinstance(value[0], (int, float)) and not isinstance(value[0], bool):
            return 0, float(value[0]), ""
        if value[0] == "NaN":
            return 1, 0, ""
        return 2, 0, str(value[0])
    return 3, 0, ""
