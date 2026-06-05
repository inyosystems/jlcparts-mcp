import gzip
import hashlib
import json
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from .partLib import lcscToDb
from .query_cache import (
    _canonical_json,
    attribute_display,
    attribute_quantity_types,
    numeric_attribute_values,
)


COMPACT_INDEX_SCHEMA_VERSION = 1
DEFAULT_INDEX_NAME = "mcp-index.sqlite3"


@dataclass
class CompactIndexBuildResult:
    index_path: str
    component_count: int
    category_count: int
    attribute_key_count: int
    attribute_value_count: int
    build_seconds: float


class CompactIndexBuilder:
    def __init__(self, catalog_path: Path, index_path: Path, progress_interval: int = 10000):
        self.catalog_path = Path(catalog_path).expanduser()
        self.index_path = Path(index_path).expanduser()
        self.progress_interval = int(progress_interval or 0)
        self.category_by_id = {}
        self.manufacturer_cache = {}
        self.package_cache = {}
        self.attribute_key_cache = {}
        self.attribute_value_cache = {}
        self.component_count = 0

    def build(self, force: bool = False) -> CompactIndexBuildResult:
        if self.index_path.exists() and not force:
            raise FileExistsError(f"Index already exists: {self.index_path}")
        manifest = self._load_manifest()
        attributes_lut = self._load_attributes_lut(manifest)
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.index_path.with_suffix(".sqlite3.tmp")
        if tmp_path.exists():
            tmp_path.unlink()

        started = time.monotonic()
        conn = sqlite3.connect(tmp_path)
        conn.row_factory = sqlite3.Row
        try:
            self._configure(conn)
            self._create_schema(conn)
            self._insert_categories(conn, manifest)
            for category in manifest["categories"]:
                for shard_name in category.get("shards") or []:
                    self._insert_shard(conn, manifest, shard_name, attributes_lut)
            self._finalize(conn, manifest, started)
        except Exception:
            conn.close()
            if tmp_path.exists():
                tmp_path.unlink()
            raise
        else:
            conn.close()
            os.replace(tmp_path, self.index_path)

        return CompactIndexBuildResult(
            index_path=str(self.index_path),
            component_count=self.component_count,
            category_count=len(self.category_by_id),
            attribute_key_count=len(self.attribute_key_cache),
            attribute_value_count=len(self.attribute_value_cache),
            build_seconds=time.monotonic() - started,
        )

    def _configure(self, conn):
        conn.execute("PRAGMA journal_mode = OFF")
        conn.execute("PRAGMA synchronous = OFF")
        conn.execute("PRAGMA temp_store = MEMORY")
        conn.execute("PRAGMA locking_mode = EXCLUSIVE")

    def _create_schema(self, conn):
        conn.executescript(
            """
            CREATE TABLE metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE categories (
                category_id INTEGER PRIMARY KEY,
                path TEXT NOT NULL,
                name TEXT NOT NULL,
                parent_path TEXT,
                source_name TEXT
            );

            CREATE TABLE manufacturers (
                manufacturer_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE
            );

            CREATE TABLE packages (
                package_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE
            );

            CREATE TABLE components (
                component_id INTEGER PRIMARY KEY,
                lcsc TEXT NOT NULL UNIQUE,
                lcsc_number INTEGER NOT NULL,
                category_id INTEGER,
                manufacturer_id INTEGER,
                package_id INTEGER,
                mfr TEXT,
                description TEXT,
                stock INTEGER,
                basic INTEGER,
                preferred INTEGER,
                discontinued INTEGER,
                rohs TEXT,
                eccn TEXT,
                assembly TEXT,
                assembly_process TEXT,
                assembly_mode TEXT,
                joints INTEGER,
                datasheet TEXT,
                img TEXT,
                url TEXT,
                source_updated_at TEXT,
                website_checked_at TEXT
            );

            CREATE TABLE attribute_keys (
                attribute_key_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE
            );

            CREATE TABLE attribute_values (
                attribute_value_id INTEGER PRIMARY KEY,
                value_key TEXT NOT NULL UNIQUE,
                display TEXT NOT NULL,
                value_json TEXT NOT NULL,
                quantity_types_json TEXT NOT NULL
            );

            CREATE TABLE component_attributes (
                component_id INTEGER NOT NULL,
                attribute_key_id INTEGER NOT NULL,
                attribute_value_id INTEGER NOT NULL,
                PRIMARY KEY(component_id, attribute_key_id, attribute_value_id)
            ) WITHOUT ROWID;

            CREATE TABLE numeric_attribute_values (
                attribute_key_id INTEGER NOT NULL,
                attribute_value_id INTEGER NOT NULL,
                value_name TEXT NOT NULL,
                quantity_type TEXT NOT NULL,
                value REAL NOT NULL,
                PRIMARY KEY(attribute_key_id, quantity_type, value, attribute_value_id, value_name)
            ) WITHOUT ROWID;

            CREATE TABLE price_tiers (
                component_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                quantity_to INTEGER,
                price REAL NOT NULL,
                currency TEXT,
                PRIMARY KEY(component_id, quantity)
            ) WITHOUT ROWID;

            CREATE TABLE website_component_details (
                lcsc TEXT PRIMARY KEY,
                checked_at TEXT NOT NULL,
                website_json TEXT
            );

            CREATE VIRTUAL TABLE components_fts USING fts5(
                lcsc,
                mfr,
                description,
                manufacturer,
                package,
                category_path,
                content='',
                columnsize=0,
                detail='none',
                tokenize='unicode61'
            );
            """
        )

    def _load_manifest(self):
        path = self.catalog_path / "manifest.json"
        if not path.exists():
            raise FileNotFoundError(f"Missing upstream catalog manifest: {path}")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        required = ["version", "attributesLut", "categories", "files"]
        missing = [key for key in required if key not in manifest]
        if missing:
            raise ValueError(f"Invalid upstream catalog manifest; missing {', '.join(missing)}")
        if int(manifest.get("version", 0)) != 4:
            raise ValueError(f"Unsupported upstream catalog version: {manifest.get('version')}")
        return manifest

    def _load_attributes_lut(self, manifest):
        attr_path = self.catalog_path / manifest["attributesLut"]
        if not attr_path.exists():
            raise FileNotFoundError(f"Missing attributes LUT: {attr_path}")
        with gzip.open(attr_path, "rt", encoding="utf-8") as f:
            lut = json.load(f)
        if not isinstance(lut, list):
            raise ValueError("Invalid attributes LUT; expected a JSON array")
        return lut

    def _insert_categories(self, conn, manifest):
        for category in manifest["categories"]:
            category_id = int(category["id"])
            parent = str(category.get("category") or "")
            name = str(category.get("subcategory") or "")
            path = f"{parent} / {name}" if parent else name
            source_name = _canonical_json(category.get("rawCategories") or [])
            conn.execute(
                """
                INSERT INTO categories(category_id, path, name, parent_path, source_name)
                VALUES (?, ?, ?, ?, ?)
                """,
                (category_id, path, name, parent, source_name),
            )
            self.category_by_id[category_id] = {
                "path": path,
                "name": name,
                "parent_path": parent,
            }

    def _insert_shard(self, conn, manifest, shard_name, attributes_lut):
        shard_path = self.catalog_path / shard_name
        if not shard_path.exists():
            raise FileNotFoundError(f"Missing component shard: {shard_path}")

        with gzip.open(shard_path, "rt", encoding="utf-8") as f:
            schema = None
            for line_number, line in enumerate(f):
                if not line.strip():
                    continue
                row = json.loads(line)
                if schema is None:
                    schema = self._validate_shard_schema(row, shard_name)
                    continue
                self._insert_component_row(conn, manifest, schema, row, attributes_lut)
                if self.progress_interval and self.component_count % self.progress_interval == 0:
                    print(f"Indexed {self.component_count} components")

    def _validate_shard_schema(self, schema, shard_name):
        required = [
            "lcsc",
            "mfr",
            "joints",
            "description",
            "datasheet",
            "price",
            "img",
            "url",
            "attributes",
            "stock",
            "subcategory",
        ]
        if not isinstance(schema, dict):
            raise ValueError(f"Invalid shard schema in {shard_name}")
        missing = [key for key in required if key not in schema]
        if missing:
            raise ValueError(f"Invalid shard schema in {shard_name}; missing {', '.join(missing)}")
        return schema

    def _insert_component_row(self, conn, manifest, schema, row, attributes_lut):
        lcsc = _value(row, schema, "lcsc")
        if not lcsc:
            return
        lcsc = str(lcsc)
        attributes = self._decode_attributes(_value(row, schema, "attributes") or [], attributes_lut)
        manufacturer = _attribute_display(attributes, "Manufacturer")
        package = _attribute_display(attributes, "Package")
        library_type = (_attribute_display(attributes, "Basic/Extended") or "").lower()
        basic = 1 if library_type == "basic" else 0
        preferred = 1 if library_type == "preferred" else 0
        status = (_attribute_display(attributes, "Status") or "").lower()
        discontinued = 1 if status and status not in {"active", "normally"} else 0
        rohs = _attribute_display(attributes, "RoHS")
        if not rohs and "rohs" in str(_value(row, schema, "description") or "").lower():
            rohs = "Yes"
        assembly_process = (
            _attribute_display(attributes, "Assembly Process")
            or _attribute_display(attributes, "Assembly")
        )
        assembly = "Yes" if assembly_process else None
        category_id = int(_value(row, schema, "subcategory") or 0)
        category = self.category_by_id.get(category_id, {})
        manufacturer_id = self._lookup_id(conn, "manufacturers", "manufacturer_id", "name", manufacturer, self.manufacturer_cache)
        package_id = self._lookup_id(conn, "packages", "package_id", "name", package, self.package_cache)
        price = _value(row, schema, "price") or []
        url_slug = _value(row, schema, "url")

        cursor = conn.execute(
            """
            INSERT OR REPLACE INTO components(
                lcsc, lcsc_number, category_id, manufacturer_id, package_id,
                mfr, description, stock, basic, preferred, discontinued,
                rohs, eccn, assembly, assembly_process, assembly_mode,
                joints, datasheet, img, url, source_updated_at,
                website_checked_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                lcsc,
                lcscToDb(lcsc),
                category_id,
                manufacturer_id,
                package_id,
                _value(row, schema, "mfr") or "",
                _value(row, schema, "description") or "",
                int(_value(row, schema, "stock") or 0),
                basic,
                preferred,
                discontinued,
                rohs,
                _attribute_display(attributes, "ECCN"),
                assembly,
                assembly_process,
                _attribute_display(attributes, "Assembly Mode"),
                int(_value(row, schema, "joints") or 0),
                _value(row, schema, "datasheet") or "",
                _value(row, schema, "img"),
                url_slug,
                manifest.get("created"),
            ),
        )
        component_id = cursor.lastrowid
        self.component_count += 1

        conn.execute(
            """
            INSERT INTO components_fts(
                rowid, lcsc, mfr, description, manufacturer, package, category_path
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                component_id,
                lcsc,
                _value(row, schema, "mfr") or "",
                _value(row, schema, "description") or "",
                manufacturer,
                package,
                category.get("path") or "",
            ),
        )
        self._insert_price_tiers(conn, component_id, price)
        self._insert_attributes(conn, component_id, attributes)

    def _decode_attributes(self, attribute_ids, attributes_lut):
        decoded = {}
        for attribute_id in attribute_ids:
            try:
                name, value = attributes_lut[int(attribute_id)]
            except (TypeError, ValueError, IndexError):
                continue
            if not name:
                continue
            decoded[str(name)] = value
        return decoded

    def _insert_attributes(self, conn, component_id, attributes):
        for name, value in attributes.items():
            attribute_key_id = self._lookup_id(
                conn,
                "attribute_keys",
                "attribute_key_id",
                "name",
                name,
                self.attribute_key_cache,
            )
            value_json = _canonical_json(value)
            value_key = hashlib.sha1(value_json.encode("utf-8")).hexdigest()
            attribute_value_id = self.attribute_value_cache.get(value_key)
            if attribute_value_id is None:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO attribute_values(
                        value_key, display, value_json, quantity_types_json
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        value_key,
                        attribute_display(value),
                        value_json,
                        _canonical_json(attribute_quantity_types(value)),
                    ),
                )
                attribute_value_id = conn.execute(
                    "SELECT attribute_value_id FROM attribute_values WHERE value_key = ?",
                    (value_key,),
                ).fetchone()["attribute_value_id"]
                self.attribute_value_cache[value_key] = attribute_value_id
            conn.execute(
                """
                INSERT OR IGNORE INTO component_attributes(
                    component_id, attribute_key_id, attribute_value_id
                )
                VALUES (?, ?, ?)
                """,
                (component_id, attribute_key_id, attribute_value_id),
            )
            for value_name, quantity_type, number in numeric_attribute_values(value):
                conn.execute(
                    """
                    INSERT OR IGNORE INTO numeric_attribute_values(
                        attribute_key_id, attribute_value_id, value_name,
                        quantity_type, value
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (attribute_key_id, attribute_value_id, value_name, quantity_type, number),
                )

    def _insert_price_tiers(self, conn, component_id, price):
        for tier in price:
            if not isinstance(tier, dict):
                continue
            quantity = tier.get("qFrom")
            unit_price = tier.get("price")
            if quantity is None or unit_price is None:
                continue
            conn.execute(
                """
                INSERT OR REPLACE INTO price_tiers(
                    component_id, quantity, quantity_to, price, currency
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    component_id,
                    int(quantity),
                    None if tier.get("qTo") in [None, ""] else int(tier.get("qTo")),
                    float(unit_price),
                    tier.get("currency") or "USD",
                ),
            )

    def _lookup_id(self, conn, table, id_column, value_column, value, cache):
        if not value:
            return None
        if value in cache:
            return cache[value]
        conn.execute(
            f"INSERT OR IGNORE INTO {table}({value_column}) VALUES (?)",
            (value,),
        )
        value_id = conn.execute(
            f"SELECT {id_column} FROM {table} WHERE {value_column} = ?",
            (value,),
        ).fetchone()[id_column]
        cache[value] = value_id
        return value_id

    def _finalize(self, conn, manifest, started):
        conn.executescript(
            """
            CREATE INDEX components_category_id ON components(category_id);
            CREATE INDEX components_stock ON components(stock);
            CREATE INDEX components_library ON components(basic, preferred);
            CREATE INDEX components_manufacturer_id ON components(manufacturer_id);
            CREATE INDEX components_package_id ON components(package_id);
            CREATE INDEX components_rohs_eccn ON components(rohs, eccn);
            CREATE INDEX component_attributes_key_value
                ON component_attributes(attribute_key_id, attribute_value_id, component_id);
            """
        )
        metadata = self._metadata(manifest, started)
        conn.executemany(
            "INSERT INTO metadata(key, value) VALUES (?, ?)",
            [(key, str(value)) for key, value in metadata.items() if value is not None],
        )
        conn.execute("ANALYZE")
        conn.commit()
        conn.execute("VACUUM")
        conn.commit()

    def _metadata(self, manifest, started):
        catalog_metadata = {}
        metadata_path = self.catalog_path / "catalog-metadata.json"
        if metadata_path.exists():
            catalog_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        return {
            "schema_version": COMPACT_INDEX_SCHEMA_VERSION,
            "source_kind": "yaqwsx-generated-catalog",
            "source_path": str(self.catalog_path),
            "source_url": catalog_metadata.get("source_url"),
            "source_downloaded_at": catalog_metadata.get("downloaded_at"),
            "source_last_modified": catalog_metadata.get("last_modified"),
            "source_etag": catalog_metadata.get("etag"),
            "source_sha256": catalog_metadata.get("sha256"),
            "source_schema_version": manifest.get("version"),
            "source_created": manifest.get("created"),
            "built_at": int(time.time()),
            "build_seconds": f"{time.monotonic() - started:.2f}",
            "component_count": self.component_count,
            "category_count": len(self.category_by_id),
            "attribute_key_count": len(self.attribute_key_cache),
            "attribute_value_count": len(self.attribute_value_cache),
            "source_component_count": manifest.get("totalComponents"),
        }


def _value(row, schema, key):
    index = schema[key]
    if index >= len(row):
        return None
    return row[index]


def _attribute_display(attributes, name):
    value = attributes.get(name)
    if value is None:
        return ""
    return attribute_display(value)
