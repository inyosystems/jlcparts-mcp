import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from jlcparts.upstream_catalog import UpstreamCatalogDownloader


def _json_bytes(value):
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


class _CatalogHandler(BaseHTTPRequestHandler):
    requests = []
    request_headers = []
    bodies = {}
    headers_by_path = {}
    statuses_by_path = {}

    def do_GET(self):
        self.__class__.requests.append(self.path)
        self.__class__.request_headers.append(dict(self.headers))
        status = self.__class__.statuses_by_path.get(self.path)
        if status is not None:
            self.send_response(status)
            for name, value in self.__class__.headers_by_path.get(self.path, {}).items():
                self.send_header(name, value)
            self.end_headers()
            return

        body = self.__class__.bodies.get(self.path)
        if body is None:
            self.send_response(404)
            self.end_headers()
            return

        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        for name, value in self.__class__.headers_by_path.get(self.path, {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


@pytest.fixture
def catalog_server():
    _CatalogHandler.requests = []
    _CatalogHandler.request_headers = []
    _CatalogHandler.bodies = {}
    _CatalogHandler.headers_by_path = {}
    _CatalogHandler.statuses_by_path = {}
    server = ThreadingHTTPServer(("127.0.0.1", 0), _CatalogHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        yield server, _CatalogHandler
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_download_manifest_source_requires_no_credentials_and_preserves_metadata(tmp_path, catalog_server, monkeypatch):
    server, handler = catalog_server
    base_url = f"http://127.0.0.1:{server.server_port}/data"
    attributes_lut = b"attributes"
    component_shard = b"components"
    browse_shard = b"browse"
    lookup = b"lookup"
    manifest = {
        "version": "web-v1",
        "totalComponents": 7,
        "attributesLut": "attributes-lut.json.gz",
        "categories": [
            {
                "id": 1,
                "category": "Passives",
                "subcategory": "Resistors",
                "componentCount": 7,
                "shards": ["components-passives-resistors-001.jsonl.gz"],
                "browseShards": ["browse-components-passives-resistors-001.jsonl.gz"],
            }
        ],
        "lookupBuckets": {"1": "lookup-00001.json.gz"},
        "files": {
            "attributes-lut.json.gz": {
                "name": "attributes-lut.json.gz",
                "kind": "attributes-lut",
                "sha256": _sha256(attributes_lut),
            },
            "components-passives-resistors-001.jsonl.gz": {
                "name": "components-passives-resistors-001.jsonl.gz",
                "kind": "components",
                "sha256": _sha256(component_shard),
            },
            "browse-components-passives-resistors-001.jsonl.gz": {
                "name": "browse-components-passives-resistors-001.jsonl.gz",
                "kind": "browse-components",
                "sha256": _sha256(browse_shard),
            },
            "lookup-00001.json.gz": {
                "name": "lookup-00001.json.gz",
                "kind": "lookup",
                "sha256": _sha256(lookup),
            },
        },
    }
    handler.bodies = {
        "/data/manifest.json": _json_bytes(manifest),
        "/data/attributes-lut.json.gz": attributes_lut,
        "/data/components-passives-resistors-001.jsonl.gz": component_shard,
        "/data/browse-components-passives-resistors-001.jsonl.gz": browse_shard,
        "/data/lookup-00001.json.gz": lookup,
    }
    handler.headers_by_path = {
        "/data/manifest.json": {
            "ETag": '"abc123"',
            "Last-Modified": "Thu, 04 Jun 2026 12:00:00 GMT",
        }
    }

    def fail_if_credentials_are_loaded(*args, **kwargs):
        raise AssertionError("downloader must not read credential environment variables")

    monkeypatch.setattr("os.getenv", fail_if_credentials_are_loaded)

    result = UpstreamCatalogDownloader().download_manifest_source(tmp_path, base_url)

    assert result.output_dir == tmp_path
    assert result.component_count == 7
    assert result.metadata_path == tmp_path / "catalog-metadata.json"
    assert sorted(path.name for path in result.downloaded_files) == [
        "attributes-lut.json.gz",
        "components-passives-resistors-001.jsonl.gz",
        "manifest.json",
    ]
    assert (tmp_path / "manifest.json").read_bytes() == handler.bodies["/data/manifest.json"]
    assert (tmp_path / "components-passives-resistors-001.jsonl.gz").read_bytes() == component_shard

    metadata = json.loads((tmp_path / "catalog-metadata.json").read_text(encoding="utf-8"))
    assert metadata["catalog_source"] == "catalog"
    assert metadata["source_url"] == base_url
    assert metadata["etag"] == '"abc123"'
    assert metadata["last_modified"] == "Thu, 04 Jun 2026 12:00:00 GMT"
    assert metadata["sha256"] == _sha256(handler.bodies["/data/manifest.json"])
    assert metadata["component_count"] == 7
    assert metadata["schema_version"] == "catalog-metadata-v1"


def test_download_manifest_source_rejects_invalid_manifest_schema(tmp_path, catalog_server):
    server, handler = catalog_server
    base_url = f"http://127.0.0.1:{server.server_port}/data"
    handler.bodies = {
        "/data/manifest.json": _json_bytes({"files": []}),
    }

    with pytest.raises(ValueError, match="manifest.*totalComponents"):
        UpstreamCatalogDownloader().download_manifest_source(tmp_path, base_url)

    assert not (tmp_path / "manifest.json").exists()
    assert not (tmp_path / "catalog-metadata.json").exists()


def test_download_manifest_source_validates_declared_sha256(tmp_path, catalog_server):
    server, handler = catalog_server
    base_url = f"http://127.0.0.1:{server.server_port}/data"
    payload = b"actual"
    manifest = {
        "version": "web-v1",
        "totalComponents": 1,
        "attributesLut": "attributes-lut.json.gz",
        "categories": [],
        "files": {
            "attributes-lut.json.gz": {
                "name": "attributes-lut.json.gz",
                "kind": "attributes-lut",
                "sha256": "0" * 64,
            }
        },
    }
    handler.bodies = {
        "/data/manifest.json": _json_bytes(manifest),
        "/data/attributes-lut.json.gz": payload,
    }

    with pytest.raises(ValueError, match="sha256"):
        UpstreamCatalogDownloader().download_manifest_source(tmp_path, base_url)

    assert not (tmp_path / "attributes-lut.json.gz").exists()
    assert not (tmp_path / "catalog-metadata.json").exists()


def test_download_manifest_source_reuses_existing_catalog_on_not_modified(tmp_path, catalog_server):
    server, handler = catalog_server
    base_url = f"http://127.0.0.1:{server.server_port}/data"
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    (tmp_path / "catalog-metadata.json").write_text(
        json.dumps(
            {
                "catalog_source": "upstream",
                "source_url": base_url,
                "downloaded_at": "2026-06-04T12:00:00Z",
                "etag": '"existing"',
                "last_modified": "Thu, 04 Jun 2026 12:00:00 GMT",
                "sha256": "a" * 64,
                "component_count": 12,
                "schema_version": "catalog-metadata-v1",
            }
        ),
        encoding="utf-8",
    )
    handler.statuses_by_path = {"/data/manifest.json": 304}

    result = UpstreamCatalogDownloader().download_manifest_source(tmp_path, base_url)

    assert result.component_count == 12
    assert result.downloaded_files == ()
    assert handler.request_headers[0]["If-None-Match"] == '"existing"'
    assert (
        handler.request_headers[0]["If-Modified-Since"]
        == "Thu, 04 Jun 2026 12:00:00 GMT"
    )
