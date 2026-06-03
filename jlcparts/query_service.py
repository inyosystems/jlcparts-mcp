import json
import sqlite3

from .pricing import get_quantity_price
from .query_cache import _canonical_json, attribute_sort_key, tokenize_text_query


class CachedComponentQueryService:
    def __init__(self, query_db_path):
        self.conn = sqlite3.connect(query_db_path)
        self.conn.row_factory = sqlite3.Row
        self.text_support = self._metadata("text_support", "like")

    def close(self):
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()

    def list_categories(self, search=None):
        clauses = []
        params = []
        for token in tokenize_text_query(search):
            clauses.append("(lower(category) LIKE ? OR lower(subcategory) LIKE ?)")
            like = f"%{token}%"
            params.extend([like, like])
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        rows = self.conn.execute(
            f"""
            SELECT id, category, subcategory, component_count
            FROM categories
            {where}
            ORDER BY category, subcategory
            """,
            params,
        )
        return [dict(row) for row in rows]

    def list_attributes(self, category_ids=None, text_query=None, limit=100):
        category_ids = _normalize_category_ids(category_ids)
        filter_sql, params = self._component_filter_sql("c", category_ids, text_query)
        rows = self.conn.execute(
            f"""
            SELECT ak.id, ak.name, COUNT(DISTINCT ca.component_lcsc) AS count
            FROM component_attributes ca
            JOIN attribute_keys ak ON ak.id = ca.attribute_id
            JOIN components c ON c.lcsc = ca.component_lcsc
            WHERE {filter_sql}
            GROUP BY ak.id, ak.name
            ORDER BY count DESC, ak.name
            LIMIT ?
            """,
            [*params, int(limit)],
        ).fetchall()

        result = []
        for row in rows:
            quantity_types = self._quantity_types_for_attribute(
                row["id"],
                category_ids=category_ids,
                text_query=text_query,
            )
            result.append({
                "name": row["name"],
                "count": row["count"],
                "quantity_types": quantity_types,
            })
        return result

    def list_attribute_values(
        self,
        attribute,
        category_ids=None,
        text_query=None,
        limit=100,
    ):
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
                COUNT(DISTINCT ca.component_lcsc) AS count
            FROM component_attributes ca
            JOIN attribute_values av ON av.id = ca.value_id
            JOIN components c ON c.lcsc = ca.component_lcsc
            WHERE ca.attribute_id = ? AND {filter_sql}
            GROUP BY av.id
            ORDER BY count DESC, av.display
            LIMIT ?
            """,
            [attribute_id, *params, int(limit)],
        ).fetchall()
        values = [{
            "value": _json_loads(row["value_json"], {}),
            "value_json": row["value_json"],
            "display": row["display"],
            "count": row["count"],
            "quantity_types": _json_loads(row["quantity_types_json"], []),
        } for row in rows]

        numeric = self._numeric_range_for_attribute(
            attribute_id,
            category_ids=category_ids,
            text_query=text_query,
        )
        return {"attribute": attribute, "values": values, "numeric": numeric}

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
        )
        sort_direction = _normalize_sort_direction(sort_direction)
        if self._can_page_in_sql(sort, sort_attribute):
            joins, join_params = self._sort_joins(sort, sort_attribute)
            total = self.conn.execute(
                f"SELECT COUNT(*) FROM components c {joins} WHERE {where_sql}",
                [*join_params, *params],
            ).fetchone()[0]
            rows = self.conn.execute(
                f"""
                SELECT *
                FROM components c
                {joins}
                WHERE {where_sql}
                ORDER BY {self._sql_order_by(sort, sort_attribute, quantity, sort_direction)}
                LIMIT ? OFFSET ?
                """,
                [*join_params, *params, limit, offset],
            ).fetchall()
            page = [
                self._component_from_row(row, quantity=quantity)
                for row in rows
            ]
        else:
            rows = self.conn.execute(
                f"""
                SELECT *
                FROM components c
                WHERE {where_sql}
                """,
                params,
            ).fetchall()
            components = [
                self._component_from_row(row, quantity=quantity)
                for row in rows
            ]
            components.sort(
                key=self._sort_key(sort, sort_attribute),
                reverse=sort_direction == "desc",
            )
            total = len(components)
            page = components[offset:offset + limit]
        if include_attributes is not None:
            for component in page:
                self._restrict_attributes(component, include_attributes)
        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "components": page,
        }

    def get_component(self, lcsc):
        row = self.conn.execute(
            "SELECT * FROM components WHERE lcsc = ?",
            (_normalize_lcsc(lcsc),),
        ).fetchone()
        if row is None:
            return None
        return self._component_from_row(row)

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
            components.sort(key=lambda component: (
                _lcsc_sort_number(component["lcsc"]),
                component["lcsc"],
            ))

        attribute_names = list(attributes) if attributes is not None else sorted({
            name
            for component in components
            for name in component["attributes"].keys()
        })

        differing = []
        for name in attribute_names:
            values = {
                _canonical_json(component["attributes"].get(name))
                for component in components
            }
            if len(values) > 1:
                differing.append(name)

        selected_attributes = differing if only_differences else attribute_names
        for component in components:
            self._restrict_attributes(component, selected_attributes)

        return {
            "components": components,
            "missing_lcsc": missing,
            "differing_attributes": differing,
        }

    def _search_where_sql(
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
    ):
        clauses = []
        params = []

        filter_sql, filter_params = self._component_filter_sql(
            "c",
            category_ids,
            text_query,
        )
        clauses.append(filter_sql)
        params.extend(filter_params)

        if in_stock:
            clauses.append("c.stock >= ?")
            params.append(int(quantity))

        if rohs is not None:
            clauses.append("c.rohs = ?")
            params.append(int(bool(rohs)))

        if eccn:
            clauses.append("lower(c.eccn) = lower(?)")
            params.append(str(eccn))

        if assembly is not None:
            clauses.append("c.assembly = ?")
            params.append(int(bool(assembly)))

        if assembly_process:
            clauses.append("lower(c.assembly_process) = lower(?)")
            params.append(str(assembly_process))

        if assembly_mode:
            clauses.append("lower(c.assembly_mode) = lower(?)")
            params.append(str(assembly_mode))

        if has_website_detail is not None:
            clauses.append(
                "c.website_component_id IS NOT NULL"
                if has_website_detail else
                "c.website_component_id IS NULL"
            )

        library_sql, library_params = self._library_filter_sql(library_types)
        if library_sql:
            clauses.append(library_sql)
            params.extend(library_params)

        for attribute in required_attributes or []:
            clauses.append("""
                EXISTS (
                    SELECT 1
                    FROM component_attributes required_ca
                    JOIN attribute_keys required_ak
                        ON required_ak.id = required_ca.attribute_id
                    WHERE required_ca.component_lcsc = c.lcsc
                        AND required_ak.name = ?
                )
            """)
            params.append(str(attribute))

        for attribute, values in self._exact_filters(exact_filters):
            attribute_id = self._attribute_id(attribute)
            if attribute_id is None:
                return "0", []
            value_jsons = [_filter_value_json(value) for value in values]
            placeholders = ",".join("?" for _ in value_jsons)
            clauses.append(f"""
                EXISTS (
                    SELECT 1
                    FROM component_attributes ca
                    JOIN attribute_values av ON av.id = ca.value_id
                    WHERE ca.component_lcsc = c.lcsc
                        AND ca.attribute_id = ?
                        AND av.value_json IN ({placeholders})
                )
            """)
            params.append(attribute_id)
            params.extend(value_jsons)

        for numeric_filter in numeric_filters or []:
            sql, numeric_params = self._numeric_filter_sql(numeric_filter)
            clauses.append(sql)
            params.extend(numeric_params)

        return " AND ".join(f"({clause})" for clause in clauses), params

    def _component_filter_sql(self, alias, category_ids=None, text_query=None):
        clauses = ["1"]
        params = []

        if category_ids:
            category_ids = list(category_ids)
            placeholders = ",".join("?" for _ in category_ids)
            clauses.append(f"{alias}.category_id IN ({placeholders})")
            params.extend(int(category_id) for category_id in category_ids)

        for token in tokenize_text_query(text_query):
            if self.text_support == "fts5":
                clauses.append(f"""
                    {alias}.lcsc IN (
                        SELECT lcsc FROM component_fts
                        WHERE component_fts MATCH ?
                    )
                """)
                params.append(f"{token}*")
            else:
                clauses.append(f"""
                    {alias}.lcsc IN (
                        SELECT lcsc FROM component_text
                        WHERE lower(text) LIKE ?
                    )
                """)
                params.append(f"%{token}%")

        return " AND ".join(clauses), params

    def _library_filter_sql(self, library_types):
        if not library_types:
            return None, []

        clauses = []
        for library_type in {str(value).lower() for value in library_types}:
            if library_type == "basic":
                clauses.append("(c.basic = 1 AND c.preferred = 0)")
            elif library_type == "extended":
                clauses.append("(c.basic = 0 AND c.preferred = 0)")
            elif library_type == "preferred":
                clauses.append("c.preferred = 1")

        if not clauses:
            return "0", []
        return "(" + " OR ".join(clauses) + ")", []

    def _exact_filters(self, exact_filters):
        if not exact_filters:
            return []
        if isinstance(exact_filters, dict):
            result = []
            for attribute, values in exact_filters.items():
                if isinstance(values, list):
                    result.append((attribute, values))
                else:
                    result.append((attribute, [values]))
            return result

        result = []
        for item in exact_filters:
            attribute = item.get("attribute") or item.get("name")
            value = item.get("value")
            values = item.get("values")
            if attribute and values is not None:
                result.append((attribute, values if isinstance(values, list) else [values]))
            elif attribute:
                result.append((attribute, [value]))
        return result

    def _numeric_filter_sql(self, numeric_filter):
        clauses = ["na.component_lcsc = c.lcsc"]
        params = []

        attribute = numeric_filter.get("attribute") or numeric_filter.get("name")
        if attribute:
            attribute_id = self._attribute_id(attribute)
            if attribute_id is not None:
                clauses.append("na.attribute_id = ?")
                params.append(attribute_id)
            else:
                return "0", []

        unit = numeric_filter.get("unit")
        if unit:
            clauses.append("na.quantity_type = ?")
            params.append(unit)

        value_name = (
            numeric_filter.get("value_name")
            or numeric_filter.get("quantity_name")
            or numeric_filter.get("value")
        )
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
                FROM numeric_attributes na
                WHERE {' AND '.join(clauses)}
            )
        """, params

    def _attribute_id(self, attribute):
        row = self.conn.execute(
            "SELECT id FROM attribute_keys WHERE name = ?",
            (attribute,),
        ).fetchone()
        return None if row is None else row["id"]

    def _quantity_types_for_attribute(self, attribute_id, category_ids=None, text_query=None):
        filter_sql, params = self._component_filter_sql("c", category_ids, text_query)
        rows = self.conn.execute(
            f"""
            SELECT av.quantity_types_json
            FROM component_attributes ca
            JOIN attribute_values av ON av.id = ca.value_id
            JOIN components c ON c.lcsc = ca.component_lcsc
            WHERE ca.attribute_id = ? AND {filter_sql}
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
            FROM numeric_attributes na
            JOIN components c ON c.lcsc = na.component_lcsc
            WHERE na.attribute_id = ? AND {filter_sql}
            GROUP BY na.quantity_type
            ORDER BY na.quantity_type
            """,
            [attribute_id, *params],
        ).fetchall()
        if not rows:
            return None
        min_value = None
        max_value = None
        if len(rows) == 1:
            min_value = rows[0]["min_value"]
            max_value = rows[0]["max_value"]
        ranges = [
            {
                "unit": row["quantity_type"],
                "min": row["min_value"],
                "max": row["max_value"],
            }
            for row in rows
        ]
        return {
            "min": min_value,
            "max": max_value,
            "units": [row["quantity_type"] for row in rows],
            "ranges": ranges,
        }

    def _component_from_row(self, row, include_attributes=None, quantity=None):
        attributes = _json_loads(row["attributes_json"], {})
        if include_attributes is not None:
            include = set(include_attributes)
            attributes = {
                name: value
                for name, value in attributes.items()
                if name in include
            }

        price = _json_loads(row["price_json"], [])
        lcsc_url = row["url"] or f"https://www.lcsc.com/search?q={row['lcsc']}"
        image_urls = _image_urls(row["image"])
        component = {
            "lcsc": row["lcsc"],
            "category_id": row["category_id"],
            "category": row["category"],
            "subcategory": row["subcategory"],
            "mfr": row["mfr"],
            "manufacturer": row["manufacturer"],
            "package": row["package"],
            "joints": row["joints"],
            "stock": row["stock"],
            "basic": bool(row["basic"]),
            "preferred": bool(row["preferred"]),
            "library_type": row["library_type"],
            "description": row["description"],
            "datasheet": row["datasheet"],
            "price": price,
            "image": row["image"],
            "image_urls": image_urls,
            "url": row["url"],
            "lcsc_url": lcsc_url,
            "url_slug": row["url_slug"],
            "extra": _json_loads(row["extra_json"], {}),
            "jlc_extra": _json_loads(row["jlc_extra_json"], {}),
            "rohs": None if row["rohs"] is None else bool(row["rohs"]),
            "eccn": row["eccn"],
            "assembly": None if row["assembly"] is None else bool(row["assembly"]),
            "assembly_process": row["assembly_process"],
            "assembly_mode": row["assembly_mode"],
            "website_component_id": row["website_component_id"],
            "attrition": _json_loads(row["attrition_json"], {}),
            "attributes": attributes,
        }
        if quantity is not None:
            component["selected_price"] = get_quantity_price(quantity, price)
        return component

    def _sort_key(self, sort, sort_attribute):
        sort = _normalize_sort_key(sort)
        if sort_attribute:
            return lambda component: (
                _attribute_sort_value(component["attributes"].get(sort_attribute)),
                component["lcsc"],
            )
        if sort == "price":
            return lambda component: (
                component["selected_price"] is None,
                component["selected_price"] if component["selected_price"] is not None else 0,
                component["lcsc"],
            )
        if sort == "stock":
            return lambda component: (-component["stock"], component["lcsc"])
        if sort == "lcsc":
            return lambda component: (_lcsc_sort_number(component["lcsc"]), component["lcsc"])
        return lambda component: (component["lcsc"])

    def _can_page_in_sql(self, sort, sort_attribute):
        return True

    def _sort_joins(self, sort, sort_attribute):
        if sort_attribute:
            attribute_id = self._attribute_id(sort_attribute)
            if attribute_id is None:
                attribute_id = -1
            return """
                LEFT JOIN component_attributes sort_ca
                    ON sort_ca.component_lcsc = c.lcsc
                    AND sort_ca.attribute_id = ?
                """, [attribute_id]
        return "", []

    def _sql_order_by(self, sort, sort_attribute, quantity, sort_direction="asc"):
        sort = _normalize_sort_key(sort)
        direction = "DESC" if sort_direction == "desc" else "ASC"
        if sort_attribute:
            return """
                COALESCE(sort_ca.sort_kind, 3) ASC,
                COALESCE(sort_ca.sort_number, 0) {direction},
                COALESCE(sort_ca.sort_text, '') {direction},
                c.lcsc_number ASC
            """.format(direction=direction)
        if sort == "price":
            price_expr = self._price_sql(int(quantity))
            return f"""
                {price_expr} IS NULL ASC,
                {price_expr} {direction},
                c.lcsc_number ASC
            """
        sort_expressions = {
            "relevance": ["c.lcsc_number"],
            "lcsc": ["c.lcsc_number"],
            "mfr": ["lower(c.mfr)"],
            "manufacturer": ["lower(c.manufacturer)"],
            "description": ["lower(c.description)"],
            "category": ["lower(c.category)", "lower(c.subcategory)"],
            "stock": ["c.stock"],
            "library_type": ["lower(c.library_type)"],
        }
        expressions = sort_expressions.get(sort, sort_expressions["relevance"])
        order_parts = [f"{expression} {direction}" for expression in expressions]
        order_parts.append("c.lcsc_number ASC")
        return ", ".join(order_parts)

    def _price_sql(self, quantity):
        return f"""
            COALESCE(
                (
                    SELECT pt.price
                    FROM price_tiers pt
                    WHERE pt.component_lcsc = c.lcsc
                        AND {quantity} >= pt.q_from
                        AND (pt.q_to IS NULL OR {quantity} <= pt.q_to)
                    ORDER BY pt.q_from ASC
                    LIMIT 1
                ),
                (
                    SELECT pt.price
                    FROM price_tiers pt
                    WHERE pt.component_lcsc = c.lcsc
                    ORDER BY pt.tier_index ASC
                    LIMIT 1
                )
            )
        """

    def _restrict_attributes(self, component, include_attributes):
        component["attributes"] = {
            name: component["attributes"][name]
            for name in include_attributes
            if name in component["attributes"]
        }

    def _metadata(self, key, default=None):
        row = self.conn.execute(
            "SELECT value FROM metadata WHERE key = ? LIMIT 1",
            (key,),
        ).fetchone()
        return default if row is None else row["value"]


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
    if lcsc and lcsc[0].lower() == "c":
        return "C" + lcsc[1:]
    if lcsc.isdigit():
        return f"C{lcsc}"
    return lcsc


def _normalize_category_ids(category_ids):
    if category_ids is None:
        return None
    return list(category_ids)


def _normalize_sort_direction(sort_direction):
    return "desc" if str(sort_direction).lower() == "desc" else "asc"


def _normalize_sort_key(sort):
    normalized = str(sort or "relevance").strip().lower()
    normalized = normalized.replace("_", " ").replace("-", " ")
    aliases = {
        "basic extended": "library_type",
        "basic/extended": "library_type",
        "library": "library_type",
        "library type": "library_type",
        "lcsc": "lcsc",
        "mfr": "mfr",
        "mfr part": "mfr",
        "mfr.part": "mfr",
        "manufacturer": "manufacturer",
        "description": "description",
        "category": "category",
        "stock": "stock",
        "price": "price",
        "relevance": "relevance",
    }
    return aliases.get(normalized, normalized.replace(" ", "_"))


def _image_urls(image):
    if not image:
        return None
    return {
        "small": f"https://assets.lcsc.com/images/lcsc/96x96/{image}",
        "medium": f"https://assets.lcsc.com/images/lcsc/224x224/{image}",
        "large": f"https://assets.lcsc.com/images/lcsc/900x900/{image}",
    }


def _lcsc_sort_number(lcsc):
    lcsc = str(lcsc)
    if lcsc[:1].lower() == "c" and lcsc[1:].isdigit():
        return int(lcsc[1:])
    return 0


def _attribute_sort_value(attribute):
    return attribute_sort_key(attribute)
