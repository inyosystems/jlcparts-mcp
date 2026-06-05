import datetime
import json
import sqlite3
from pathlib import Path

from .pricing import get_quantity_price
from .query_cache import _canonical_json, attribute_sort_key, tokenize_text_query
from .query_service import _image_urls, _lcsc_sort_number, _normalize_sort_direction, _normalize_sort_key


class CompactQueryService:
    def __init__(self, index_path, read_only=True):
        self.index_path = str(Path(index_path).expanduser())
        self.read_only = bool(read_only)
        if self.read_only:
            self.conn = sqlite3.connect(f"file:{self.index_path}?mode=ro", uri=True)
        else:
            self.conn = sqlite3.connect(self.index_path)
        self.conn.row_factory = sqlite3.Row

    def close(self):
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()

    def cache_status(self):
        metadata = self._metadata_dict()
        return {
            "index_path": self.index_path,
            "index_exists": True,
            "ready": True,
            "schema_version": metadata.get("schema_version"),
            "source_kind": metadata.get("source_kind"),
            "source_path": metadata.get("source_path"),
            "source_url": metadata.get("source_url"),
            "source_downloaded_at": metadata.get("source_downloaded_at"),
            "source_created": metadata.get("source_created"),
            "source_last_modified": metadata.get("source_last_modified"),
            "source_etag": metadata.get("source_etag"),
            "component_count": _int_or_none(metadata.get("component_count")),
            "category_count": _int_or_none(metadata.get("category_count")),
            "attribute_key_count": _int_or_none(metadata.get("attribute_key_count")),
            "attribute_value_count": _int_or_none(metadata.get("attribute_value_count")),
            "remote_queries_for_cache_reads": False,
            "workflow": (
                "Use cache tools for fast local research/design work. Use "
                "lookup_component_website_detail or get_component(include_website_detail=True) "
                "only after narrowing to exact LCSC candidates. The upstream "
                "generated catalog is filtered for recently stocked PCBA parts "
                "and is not a full mirror of every live JLCPCB category reference."
            ),
        }

    def list_categories(self, search=None, limit=200):
        clauses = []
        params = []
        for token in tokenize_text_query(search):
            clauses.append("(lower(path) LIKE ? OR lower(name) LIKE ? OR lower(parent_path) LIKE ?)")
            like = f"%{token}%"
            params.extend([like, like, like])
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        rows = self.conn.execute(
            f"""
            SELECT
                cat.category_id,
                cat.path,
                cat.name,
                cat.parent_path,
                COUNT(c.component_id) AS component_count
            FROM categories cat
            LEFT JOIN components c ON c.category_id = cat.category_id
            {where}
            GROUP BY cat.category_id
            ORDER BY cat.path
            LIMIT ?
            """,
            [*params, int(limit)],
        ).fetchall()
        return [dict(row) for row in rows]

    def list_attributes(self, category_ids=None, text_query=None, limit=100):
        category_ids = _normalize_category_ids(category_ids)
        filter_sql, params = self._component_filter_sql("c", category_ids, text_query)
        rows = self.conn.execute(
            f"""
            SELECT ak.attribute_key_id, ak.name, COUNT(DISTINCT ca.component_id) AS count
            FROM component_attributes ca
            JOIN attribute_keys ak ON ak.attribute_key_id = ca.attribute_key_id
            JOIN components c ON c.component_id = ca.component_id
            WHERE {filter_sql}
            GROUP BY ak.attribute_key_id, ak.name
            ORDER BY count DESC, ak.name
            LIMIT ?
            """,
            [*params, int(limit)],
        ).fetchall()
        return [
            {
                "name": row["name"],
                "count": row["count"],
                "quantity_types": self._quantity_types_for_attribute(
                    row["attribute_key_id"], category_ids, text_query
                ),
            }
            for row in rows
        ]

    def list_attribute_values(self, attribute, category_ids=None, text_query=None, limit=100):
        category_ids = _normalize_category_ids(category_ids)
        attribute_id = self._attribute_id(attribute)
        if attribute_id is None:
            return {"attribute": attribute, "values": [], "numeric": None}
        filter_sql, params = self._component_filter_sql("c", category_ids, text_query)
        rows = self.conn.execute(
            f"""
            SELECT
                av.value_json,
                av.display,
                av.quantity_types_json,
                COUNT(DISTINCT ca.component_id) AS count
            FROM component_attributes ca
            JOIN attribute_values av ON av.attribute_value_id = ca.attribute_value_id
            JOIN components c ON c.component_id = ca.component_id
            WHERE ca.attribute_key_id = ? AND {filter_sql}
            GROUP BY av.attribute_value_id
            ORDER BY count DESC, av.display
            LIMIT ?
            """,
            [attribute_id, *params, int(limit)],
        ).fetchall()
        return {
            "attribute": attribute,
            "values": [
                {
                    "value": _json_loads(row["value_json"], {}),
                    "value_json": row["value_json"],
                    "display": row["display"],
                    "count": row["count"],
                    "quantity_types": _json_loads(row["quantity_types_json"], []),
                }
                for row in rows
            ],
            "numeric": self._numeric_range_for_attribute(attribute_id, category_ids, text_query),
        }

    def search_components(
        self,
        category_ids=None,
        text_query="",
        exact_filters=None,
        numeric_filters=None,
        required_attributes=None,
        quantity=1,
        in_stock=False,
        library_types=None,
        rohs=None,
        eccn=None,
        assembly=None,
        assembly_process=None,
        assembly_mode=None,
        has_website_detail=None,
        sort="relevance",
        sort_direction="asc",
        sort_attribute=None,
        offset=0,
        limit=25,
        include_attributes=None,
        category_path=None,
        manufacturers=None,
        packages=None,
        stock_min=None,
        basic=None,
        preferred=None,
        discontinued=None,
    ):
        category_ids = _normalize_category_ids(category_ids)
        offset = max(0, int(offset))
        limit = max(0, int(limit))
        where_sql, params = self._search_where_sql(
            category_ids=category_ids,
            text_query=text_query,
            exact_filters=exact_filters,
            numeric_filters=numeric_filters,
            required_attributes=required_attributes,
            quantity=quantity,
            in_stock=in_stock,
            library_types=library_types,
            rohs=rohs,
            eccn=eccn,
            assembly=assembly,
            assembly_process=assembly_process,
            assembly_mode=assembly_mode,
            has_website_detail=has_website_detail,
            category_path=category_path,
            manufacturers=manufacturers,
            packages=packages,
            stock_min=stock_min,
            basic=basic,
            preferred=preferred,
            discontinued=discontinued,
        )
        sort_direction = _normalize_sort_direction(sort_direction)
        joins, join_params = self._sort_joins(sort_attribute)
        total = self.conn.execute(
            f"SELECT COUNT(*) FROM components c {joins} WHERE {where_sql}",
            [*join_params, *params],
        ).fetchone()[0]
        rows = self.conn.execute(
            f"""
            SELECT c.*
            FROM components c
            {joins}
            WHERE {where_sql}
            ORDER BY {self._sql_order_by(sort, sort_attribute, quantity, sort_direction)}
            LIMIT ? OFFSET ?
            """,
            [*join_params, *params, limit, offset],
        ).fetchall()
        page = [self._component_from_row(row, quantity=quantity) for row in rows]
        if include_attributes is not None:
            for component in page:
                self._restrict_attributes(component, include_attributes)
        return {"total": total, "offset": offset, "limit": limit, "components": page}

    def get_component(self, lcsc):
        row = self.conn.execute(
            "SELECT * FROM components WHERE lcsc = ?",
            (_normalize_lcsc(lcsc),),
        ).fetchone()
        return None if row is None else self._component_from_row(row)

    def lookup_component_website_detail(self, lcsc, lookup_func=None):
        lcsc = _normalize_lcsc(lcsc)
        if lookup_func is None:
            from .jlcpcb import _website_component_enrichment

            lookup_func = _website_component_enrichment
        try:
            detail = lookup_func(lcsc)
        except Exception as exc:
            return {
                "lcsc": lcsc,
                "found": False,
                "error": f"{type(exc).__name__}: {exc}",
                "note": "Exact website detail lookup uses the public website and may fail independently of the cached catalog.",
            }
        result = {
            "lcsc": lcsc,
            "found": True,
            "source": "public_website",
            "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "website_detail": detail,
        }
        if not self.read_only:
            self._store_website_detail(lcsc, result)
        return result

    def compare_components(
        self,
        lcsc_codes,
        quantity=1,
        attributes=None,
        only_differences=False,
        keep_order=True,
        in_stock=False,
    ):
        components = []
        missing = []
        for lcsc in lcsc_codes:
            row = self.conn.execute(
                "SELECT * FROM components WHERE lcsc = ?",
                (_normalize_lcsc(lcsc),),
            ).fetchone()
            if row is None:
                missing.append(_normalize_lcsc(lcsc))
                continue
            if in_stock and row["stock"] < int(quantity):
                continue
            components.append(self._component_from_row(row, quantity=quantity))
        if not keep_order:
            components.sort(key=lambda component: (_lcsc_sort_number(component["lcsc"]), component["lcsc"]))
        attribute_names = list(attributes) if attributes is not None else sorted({
            name for component in components for name in component["attributes"]
        })
        differing = []
        for name in attribute_names:
            values = {_canonical_json(component["attributes"].get(name)) for component in components}
            if len(values) > 1:
                differing.append(name)
        selected = differing if only_differences else attribute_names
        for component in components:
            self._restrict_attributes(component, selected)
        return {
            "components": components,
            "missing_lcsc": missing,
            "differing_attributes": differing,
        }

    def _search_where_sql(self, **kwargs):
        clauses = []
        params = []
        filter_sql, filter_params = self._component_filter_sql(
            "c", kwargs["category_ids"], kwargs["text_query"]
        )
        clauses.append(filter_sql)
        params.extend(filter_params)
        quantity = int(kwargs["quantity"])
        if kwargs["in_stock"]:
            clauses.append("c.stock >= ?")
            params.append(quantity)
        if kwargs["stock_min"] is not None:
            clauses.append("c.stock >= ?")
            params.append(int(kwargs["stock_min"]))
        for flag in ["basic", "preferred", "discontinued"]:
            if kwargs.get(flag) is not None:
                clauses.append(f"c.{flag} = ?")
                params.append(int(bool(kwargs[flag])))
        if kwargs["rohs"] is not None:
            clauses.append("lower(COALESCE(c.rohs, '')) IN ('yes', 'true', '1')")
        if kwargs["eccn"]:
            clauses.append("lower(c.eccn) = lower(?)")
            params.append(str(kwargs["eccn"]))
        if kwargs["assembly"] is not None:
            clauses.append("c.assembly IS NOT NULL" if kwargs["assembly"] else "c.assembly IS NULL")
        if kwargs["assembly_process"]:
            clauses.append("lower(c.assembly_process) = lower(?)")
            params.append(str(kwargs["assembly_process"]))
        if kwargs["assembly_mode"]:
            clauses.append("lower(c.assembly_mode) = lower(?)")
            params.append(str(kwargs["assembly_mode"]))
        if kwargs["has_website_detail"] is not None:
            clauses.append(
                "c.website_checked_at IS NOT NULL"
                if kwargs["has_website_detail"] else
                "c.website_checked_at IS NULL"
            )
        if kwargs["category_path"]:
            clauses.append("c.category_id IN (SELECT category_id FROM categories WHERE lower(path) LIKE lower(?))")
            params.append(f"%{kwargs['category_path']}%")
        clauses.extend(self._in_lookup_clause("manufacturers", "manufacturer_id", "name", "c.manufacturer_id", kwargs["manufacturers"], params))
        clauses.extend(self._in_lookup_clause("packages", "package_id", "name", "c.package_id", kwargs["packages"], params))
        library_sql = self._library_filter_sql(kwargs["library_types"])
        if library_sql:
            clauses.append(library_sql)
        for attribute in kwargs["required_attributes"] or []:
            attribute_id = self._attribute_id(attribute)
            if attribute_id is None:
                return "0", []
            clauses.append("EXISTS (SELECT 1 FROM component_attributes required_ca WHERE required_ca.component_id = c.component_id AND required_ca.attribute_key_id = ?)")
            params.append(attribute_id)
        for attribute, values in self._exact_filters(kwargs["exact_filters"]):
            attribute_id = self._attribute_id(attribute)
            if attribute_id is None:
                return "0", []
            value_jsons = [_filter_value_json(value) for value in values]
            placeholders = ",".join("?" for _ in value_jsons)
            clauses.append(f"""
                EXISTS (
                    SELECT 1
                    FROM component_attributes ca
                    JOIN attribute_values av ON av.attribute_value_id = ca.attribute_value_id
                    WHERE ca.component_id = c.component_id
                        AND ca.attribute_key_id = ?
                        AND av.value_json IN ({placeholders})
                )
            """)
            params.append(attribute_id)
            params.extend(value_jsons)
        for numeric_filter in kwargs["numeric_filters"] or []:
            sql, numeric_params = self._numeric_filter_sql(numeric_filter)
            clauses.append(sql)
            params.extend(numeric_params)
        return " AND ".join(f"({clause})" for clause in clauses), params

    def _component_filter_sql(self, alias, category_ids=None, text_query=None):
        clauses = ["1"]
        params = []
        if category_ids:
            placeholders = ",".join("?" for _ in category_ids)
            clauses.append(f"{alias}.category_id IN ({placeholders})")
            params.extend(int(category_id) for category_id in category_ids)
        for token in tokenize_text_query(text_query):
            clauses.append(f"""
                {alias}.component_id IN (
                    SELECT rowid FROM components_fts WHERE components_fts MATCH ?
                )
            """)
            params.append(f"{token}*")
        return " AND ".join(clauses), params

    def _in_lookup_clause(self, table, id_column, value_column, component_column, values, params):
        if not values:
            return []
        values = values if isinstance(values, list) else [values]
        placeholders = ",".join("?" for _ in values)
        params.extend(str(value).lower() for value in values)
        return [f"{component_column} IN (SELECT {id_column} FROM {table} WHERE lower({value_column}) IN ({placeholders}))"]

    def _library_filter_sql(self, library_types):
        if not library_types:
            return None
        clauses = []
        for library_type in {str(value).lower() for value in library_types}:
            if library_type == "basic":
                clauses.append("(c.basic = 1 AND c.preferred = 0)")
            elif library_type == "extended":
                clauses.append("(c.basic = 0 AND c.preferred = 0)")
            elif library_type == "preferred":
                clauses.append("c.preferred = 1")
        return "(" + " OR ".join(clauses) + ")" if clauses else "0"

    def _exact_filters(self, exact_filters):
        if not exact_filters:
            return []
        if isinstance(exact_filters, dict):
            return [
                (attribute, values if isinstance(values, list) else [values])
                for attribute, values in exact_filters.items()
            ]
        result = []
        for item in exact_filters:
            attribute = item.get("attribute") or item.get("name")
            values = item.get("values")
            value = item.get("value")
            if attribute:
                result.append((attribute, values if isinstance(values, list) else [value if values is None else values]))
        return result

    def _numeric_filter_sql(self, numeric_filter):
        clauses = [
            "ca_num.component_id = c.component_id",
            "na.attribute_value_id = ca_num.attribute_value_id",
            "na.attribute_key_id = ca_num.attribute_key_id",
        ]
        params = []
        attribute = numeric_filter.get("attribute") or numeric_filter.get("name")
        if attribute:
            attribute_id = self._attribute_id(attribute)
            if attribute_id is None:
                return "0", []
            clauses.append("na.attribute_key_id = ?")
            params.append(attribute_id)
        unit = numeric_filter.get("unit")
        if unit:
            clauses.append("na.quantity_type = ?")
            params.append(unit)
        value_name = numeric_filter.get("value_name") or numeric_filter.get("quantity_name")
        if value_name is not None:
            clauses.append("lower(na.value_name) = lower(?)")
            params.append(str(value_name))
        if numeric_filter.get("min") is not None:
            clauses.append("na.value >= ?")
            params.append(float(numeric_filter["min"]))
        if numeric_filter.get("max") is not None:
            clauses.append("na.value <= ?")
            params.append(float(numeric_filter["max"]))
        return f"""
            EXISTS (
                SELECT 1
                FROM component_attributes ca_num
                JOIN numeric_attribute_values na
                    ON na.attribute_value_id = ca_num.attribute_value_id
                    AND na.attribute_key_id = ca_num.attribute_key_id
                WHERE {' AND '.join(clauses)}
            )
        """, params

    def _sort_joins(self, sort_attribute):
        if not sort_attribute:
            return "", []
        attribute_id = self._attribute_id(sort_attribute)
        if attribute_id is None:
            attribute_id = -1
        return """
            LEFT JOIN component_attributes sort_ca
                ON sort_ca.component_id = c.component_id
                AND sort_ca.attribute_key_id = ?
            LEFT JOIN attribute_values sort_av
                ON sort_av.attribute_value_id = sort_ca.attribute_value_id
        """, [attribute_id]

    def _sql_order_by(self, sort, sort_attribute, quantity, sort_direction="asc"):
        direction = "DESC" if sort_direction == "desc" else "ASC"
        if sort_attribute:
            return f"lower(COALESCE(sort_av.display, '')) {direction}, c.lcsc_number ASC"
        sort = _normalize_sort_key(sort)
        if sort == "price":
            price_expr = self._price_sql(int(quantity))
            return f"{price_expr} IS NULL ASC, {price_expr} {direction}, c.lcsc_number ASC"
        expressions = {
            "relevance": ["c.lcsc_number"],
            "lcsc": ["c.lcsc_number"],
            "mfr": ["lower(c.mfr)"],
            "manufacturer": ["(SELECT lower(name) FROM manufacturers m WHERE m.manufacturer_id = c.manufacturer_id)"],
            "description": ["lower(c.description)"],
            "category": ["c.category_id"],
            "stock": ["c.stock"],
            "library_type": ["c.basic", "c.preferred"],
        }.get(sort, ["c.lcsc_number"])
        parts = [f"{expression} {direction}" for expression in expressions]
        parts.append("c.lcsc_number ASC")
        return ", ".join(parts)

    def _price_sql(self, quantity):
        return f"""
            COALESCE(
                (
                    SELECT pt.price
                    FROM price_tiers pt
                    WHERE pt.component_id = c.component_id
                        AND {quantity} >= pt.quantity
                        AND (pt.quantity_to IS NULL OR {quantity} <= pt.quantity_to)
                    ORDER BY pt.quantity ASC
                    LIMIT 1
                ),
                (
                    SELECT pt.price
                    FROM price_tiers pt
                    WHERE pt.component_id = c.component_id
                    ORDER BY pt.quantity ASC
                    LIMIT 1
                )
            )
        """

    def _component_from_row(self, row, quantity=None):
        attributes = self._attributes_for_component(row["component_id"])
        price = self._price_for_component(row["component_id"])
        category = self.conn.execute(
            "SELECT * FROM categories WHERE category_id = ?",
            (row["category_id"],),
        ).fetchone()
        manufacturer = self._lookup_name("manufacturers", "manufacturer_id", row["manufacturer_id"])
        package = self._lookup_name("packages", "package_id", row["package_id"])
        image_urls = _image_urls(row["img"])
        lcsc_url = _lcsc_url(row["url"], row["lcsc"])
        component = {
            "lcsc": row["lcsc"],
            "category_id": row["category_id"],
            "category": None if category is None else category["parent_path"],
            "subcategory": None if category is None else category["name"],
            "category_path": None if category is None else category["path"],
            "mfr": row["mfr"],
            "manufacturer": manufacturer,
            "package": package,
            "joints": row["joints"],
            "stock": row["stock"],
            "basic": bool(row["basic"]),
            "preferred": bool(row["preferred"]),
            "library_type": "preferred" if row["preferred"] else ("basic" if row["basic"] else "extended"),
            "discontinued": bool(row["discontinued"]),
            "description": row["description"],
            "datasheet": row["datasheet"],
            "price": price,
            "image": row["img"],
            "image_urls": image_urls,
            "url": lcsc_url,
            "lcsc_url": lcsc_url,
            "rohs": row["rohs"],
            "eccn": row["eccn"],
            "assembly": row["assembly"],
            "assembly_process": row["assembly_process"],
            "assembly_mode": row["assembly_mode"],
            "website_checked_at": row["website_checked_at"],
            "attributes": attributes,
            "source": "upstream_catalog",
        }
        if quantity is not None:
            component["selected_price"] = get_quantity_price(quantity, price)
        return component

    def _attributes_for_component(self, component_id):
        rows = self.conn.execute(
            """
            SELECT ak.name, av.value_json
            FROM component_attributes ca
            JOIN attribute_keys ak ON ak.attribute_key_id = ca.attribute_key_id
            JOIN attribute_values av ON av.attribute_value_id = ca.attribute_value_id
            WHERE ca.component_id = ?
            ORDER BY ak.name
            """,
            (component_id,),
        ).fetchall()
        return {row["name"]: _json_loads(row["value_json"], {}) for row in rows}

    def _lookup_name(self, table, id_column, value):
        if value is None:
            return ""
        row = self.conn.execute(
            f"SELECT name FROM {table} WHERE {id_column} = ?",
            (value,),
        ).fetchone()
        return "" if row is None else row["name"]

    def _price_for_component(self, component_id):
        rows = self.conn.execute(
            """
            SELECT quantity, quantity_to, price, currency
            FROM price_tiers
            WHERE component_id = ?
            ORDER BY quantity
            """,
            (component_id,),
        ).fetchall()
        return [
            {
                "qFrom": row["quantity"],
                "qTo": row["quantity_to"],
                "price": row["price"],
                **({"currency": row["currency"]} if row["currency"] else {}),
            }
            for row in rows
        ]

    def _restrict_attributes(self, component, include_attributes):
        component["attributes"] = {
            name: component["attributes"][name]
            for name in include_attributes
            if name in component["attributes"]
        }

    def _attribute_id(self, attribute):
        row = self.conn.execute(
            "SELECT attribute_key_id FROM attribute_keys WHERE name = ?",
            (attribute,),
        ).fetchone()
        return None if row is None else row["attribute_key_id"]

    def _quantity_types_for_attribute(self, attribute_id, category_ids=None, text_query=None):
        filter_sql, params = self._component_filter_sql("c", category_ids, text_query)
        rows = self.conn.execute(
            f"""
            SELECT av.quantity_types_json
            FROM component_attributes ca
            JOIN attribute_values av ON av.attribute_value_id = ca.attribute_value_id
            JOIN components c ON c.component_id = ca.component_id
            WHERE ca.attribute_key_id = ? AND {filter_sql}
            """,
            [attribute_id, *params],
        )
        quantity_types = set()
        for row in rows:
            quantity_types.update(_json_loads(row["quantity_types_json"], []))
        return sorted(quantity_types)

    def _numeric_range_for_attribute(self, attribute_id, category_ids=None, text_query=None):
        filter_sql, params = self._component_filter_sql("c", category_ids, text_query)
        rows = self.conn.execute(
            f"""
            SELECT na.quantity_type, MIN(na.value) AS min_value, MAX(na.value) AS max_value
            FROM component_attributes ca
            JOIN numeric_attribute_values na
                ON na.attribute_value_id = ca.attribute_value_id
                AND na.attribute_key_id = ca.attribute_key_id
            JOIN components c ON c.component_id = ca.component_id
            WHERE ca.attribute_key_id = ? AND {filter_sql}
            GROUP BY na.quantity_type
            ORDER BY na.quantity_type
            """,
            [attribute_id, *params],
        ).fetchall()
        if not rows:
            return None
        return {
            "min": rows[0]["min_value"] if len(rows) == 1 else None,
            "max": rows[0]["max_value"] if len(rows) == 1 else None,
            "units": [row["quantity_type"] for row in rows],
            "ranges": [
                {"unit": row["quantity_type"], "min": row["min_value"], "max": row["max_value"]}
                for row in rows
            ],
        }

    def _metadata_dict(self):
        return {
            row["key"]: row["value"]
            for row in self.conn.execute("SELECT key, value FROM metadata")
        }

    def _store_website_detail(self, lcsc, result):
        self.conn.execute(
            """
            INSERT OR REPLACE INTO website_component_details(
                lcsc, checked_at, website_json
            )
            VALUES (?, ?, ?)
            """,
            (
                lcsc,
                result["checked_at"],
                json.dumps(result.get("website_detail"), separators=(",", ":")),
            ),
        )
        self.conn.execute(
            "UPDATE components SET website_checked_at = ? WHERE lcsc = ?",
            (result["checked_at"], lcsc),
        )
        self.conn.commit()


def _json_loads(value, fallback):
    if value in [None, ""]:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _filter_value_json(value):
    if isinstance(value, str) and value[:1] in ["{", "["]:
        try:
            return _canonical_json(json.loads(value))
        except Exception:
            pass
    return _canonical_json(value)


def _normalize_lcsc(lcsc):
    if isinstance(lcsc, int):
        return f"C{lcsc}"
    lcsc = str(lcsc)
    if lcsc[:1].lower() == "c":
        return "C" + lcsc[1:]
    if lcsc.isdigit():
        return f"C{lcsc}"
    return lcsc


def _normalize_category_ids(category_ids):
    if category_ids is None:
        return None
    return list(category_ids)


def _int_or_none(value):
    try:
        return None if value in [None, ""] else int(value)
    except (TypeError, ValueError):
        return None


def _lcsc_url(stored_url, lcsc):
    if stored_url:
        if str(stored_url).startswith("http"):
            return stored_url
        return f"https://lcsc.com/product-detail/{stored_url}_{lcsc}.html"
    return f"https://www.lcsc.com/search?q={lcsc}"
