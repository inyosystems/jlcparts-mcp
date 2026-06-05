import datetime
import hashlib
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse

import requests


DEFAULT_UPSTREAM_DATA_URL = "https://yaqwsx.github.io/jlcparts/data"
DEFAULT_CATALOG_NAME = "catalog"
CATALOG_METADATA_SCHEMA_VERSION = "catalog-metadata-v1"


@dataclass(frozen=True)
class CatalogDownloadResult:
    output_dir: Path
    manifest_path: Path
    metadata_path: Path
    downloaded_files: tuple[Path, ...]
    source_url: str
    component_count: int
    etag: str | None = None
    last_modified: str | None = None
    sha256: str | None = None


@dataclass(frozen=True)
class _FetchedResource:
    data: bytes | None
    etag: str | None = None
    last_modified: str | None = None
    not_modified: bool = False


class UpstreamCatalogDownloader:
    def __init__(self, timeout: int = 30, retries: int = 3, retry_delay: float = 0.5, workers: int = 8):
        self.timeout = timeout
        self.retries = retries
        self.retry_delay = retry_delay
        self.workers = max(1, int(workers))

    def download_manifest_source(
        self,
        output_dir: Path,
        data_url: str = DEFAULT_UPSTREAM_DATA_URL,
        force: bool = False,
    ) -> CatalogDownloadResult:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        base_url = data_url.rstrip("/")

        manifest_target = output_dir / "manifest.json"
        metadata_target = output_dir / "catalog-metadata.json"
        existing_metadata = _read_existing_metadata(metadata_target) if not force else {}

        manifest_resource = self._fetch(
            f"{base_url}/manifest.json",
            headers=_conditional_headers(existing_metadata),
        )
        if manifest_resource.not_modified:
            return _existing_result(output_dir, manifest_target, metadata_target, base_url)
        if manifest_resource.data is None:
            raise RuntimeError(f"failed to download {base_url}/manifest.json")
        manifest_sha256 = _sha256(manifest_resource.data)
        manifest = _load_manifest(manifest_resource.data)
        _validate_manifest(manifest)

        file_entries = _manifest_file_entries(manifest)
        downloaded = []
        temp_paths = []
        try:
            manifest_tmp = _write_temp(output_dir, "manifest.json", manifest_resource.data)
            temp_paths.append(manifest_tmp)

            file_temps = {}
            filenames = _referenced_filenames(manifest)
            with ThreadPoolExecutor(max_workers=min(self.workers, max(1, len(filenames)))) as executor:
                futures = {
                    executor.submit(self._fetch, _join_url(base_url, filename)): filename
                    for filename in filenames
                }
                for future in as_completed(futures):
                    filename = futures[future]
                    _ensure_relative_filename(filename)
                    resource = future.result()
                    if resource.data is None:
                        raise RuntimeError(f"failed to download {filename}")
                    expected_sha256 = file_entries.get(filename, {}).get("sha256")
                    if expected_sha256:
                        actual_sha256 = _sha256(resource.data)
                        if actual_sha256 != expected_sha256:
                            raise ValueError(
                                f"sha256 mismatch for {filename}: "
                                f"expected {expected_sha256}, got {actual_sha256}"
                            )
                    tmp = _write_temp(output_dir, filename, resource.data)
                    temp_paths.append(tmp)
                    file_temps[filename] = tmp

            metadata = {
                "catalog_source": DEFAULT_CATALOG_NAME,
                "source_url": base_url,
                "downloaded_at": datetime.datetime.now(
                    datetime.timezone.utc
                ).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "etag": manifest_resource.etag,
                "last_modified": manifest_resource.last_modified,
                "sha256": manifest_sha256,
                "component_count": manifest["totalComponents"],
                "schema_version": CATALOG_METADATA_SCHEMA_VERSION,
            }
            metadata_tmp = _write_temp(
                output_dir,
                "catalog-metadata.json",
                json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True).encode(
                    "utf-8"
                )
                + b"\n",
            )
            temp_paths.append(metadata_tmp)

            _replace(manifest_tmp, manifest_target)
            downloaded.append(manifest_target)
            for filename in _referenced_filenames(manifest):
                target = output_dir / filename
                _replace(file_temps[filename], target)
                downloaded.append(target)
            _replace(metadata_tmp, metadata_target)
        finally:
            for tmp in temp_paths:
                if tmp.exists():
                    tmp.unlink()

        return CatalogDownloadResult(
            output_dir=output_dir,
            manifest_path=manifest_target,
            metadata_path=metadata_target,
            downloaded_files=tuple(downloaded),
            source_url=base_url,
            component_count=manifest["totalComponents"],
            etag=manifest_resource.etag,
            last_modified=manifest_resource.last_modified,
            sha256=manifest_sha256,
        )

    def _fetch(self, url: str, headers: dict[str, str] | None = None) -> _FetchedResource:
        parsed = urlparse(url)
        if parsed.scheme in ["", "file"]:
            path = Path(parsed.path if parsed.scheme == "file" else url)
            return _FetchedResource(path.read_bytes())

        session = requests.Session()
        session.trust_env = False
        last_error = None
        for attempt in range(max(1, self.retries)):
            try:
                response = session.get(url, timeout=self.timeout, headers=headers)
                if response.status_code == 304:
                    return _FetchedResource(
                        None,
                        response.headers.get("ETag"),
                        response.headers.get("Last-Modified"),
                        not_modified=True,
                    )
                response.raise_for_status()
                return _FetchedResource(
                    response.content,
                    response.headers.get("ETag"),
                    response.headers.get("Last-Modified"),
                )
            except requests.RequestException as exc:
                last_error = exc
                if attempt + 1 >= max(1, self.retries):
                    break
                time.sleep(self.retry_delay)
        raise RuntimeError(f"failed to download {url}: {last_error}") from last_error


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_manifest(data: bytes) -> dict:
    try:
        manifest = json.loads(data.decode("utf-8"))
    except Exception as exc:
        raise ValueError(f"invalid manifest JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ValueError("invalid manifest schema: root must be an object")
    return manifest


def _validate_manifest(manifest: dict) -> None:
    missing = [
        key for key in ["version", "totalComponents", "files"] if key not in manifest
    ]
    if missing:
        raise ValueError(f"invalid manifest schema: missing {', '.join(missing)}")
    if not isinstance(manifest["totalComponents"], int):
        raise ValueError("invalid manifest schema: totalComponents must be an integer")
    if not isinstance(manifest["files"], dict):
        raise ValueError("invalid manifest schema: files must be an object")
    for filename, entry in manifest["files"].items():
        if not isinstance(filename, str) or not filename:
            raise ValueError("invalid manifest schema: file names must be strings")
        _ensure_relative_filename(filename)
        if not isinstance(entry, dict):
            raise ValueError(f"invalid manifest schema: files.{filename} must be an object")
        if entry.get("name", filename) != filename:
            raise ValueError(
                f"invalid manifest schema: files.{filename}.name does not match key"
            )
        sha256 = entry.get("sha256")
        if sha256 is not None and (
            not isinstance(sha256, str)
            or len(sha256) != 64
            or any(char not in "0123456789abcdefABCDEF" for char in sha256)
        ):
            raise ValueError(f"invalid manifest schema: files.{filename}.sha256 is invalid")


def _manifest_file_entries(manifest: dict) -> dict[str, dict]:
    return manifest.get("files", {})


def _read_existing_metadata(metadata_target: Path) -> dict:
    if not metadata_target.exists():
        return {}
    try:
        metadata = json.loads(metadata_target.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return metadata if isinstance(metadata, dict) else {}


def _conditional_headers(metadata: dict) -> dict[str, str]:
    headers = {}
    etag = metadata.get("etag")
    last_modified = metadata.get("last_modified")
    if isinstance(etag, str) and etag:
        headers["If-None-Match"] = etag
    if isinstance(last_modified, str) and last_modified:
        headers["If-Modified-Since"] = last_modified
    return headers


def _existing_result(
    output_dir: Path,
    manifest_target: Path,
    metadata_target: Path,
    source_url: str,
) -> CatalogDownloadResult:
    if not manifest_target.exists() or not metadata_target.exists():
        raise RuntimeError("upstream returned not-modified but local catalog is incomplete")
    manifest = _load_manifest(manifest_target.read_bytes())
    _validate_manifest(manifest)
    missing_files = [
        filename
        for filename in _referenced_filenames(manifest)
        if not (output_dir / filename).exists()
    ]
    if missing_files:
        raise RuntimeError(
            "upstream returned not-modified but local catalog is incomplete: "
            + ", ".join(missing_files)
        )
    metadata = _read_existing_metadata(metadata_target)
    return CatalogDownloadResult(
        output_dir=output_dir,
        manifest_path=manifest_target,
        metadata_path=metadata_target,
        downloaded_files=(),
        source_url=source_url,
        component_count=int(metadata.get("component_count", 0) or 0),
        etag=metadata.get("etag") if isinstance(metadata.get("etag"), str) else None,
        last_modified=(
            metadata.get("last_modified")
            if isinstance(metadata.get("last_modified"), str)
            else None
        ),
        sha256=metadata.get("sha256") if isinstance(metadata.get("sha256"), str) else None,
    )


def _referenced_filenames(manifest: dict) -> tuple[str, ...]:
    filenames = set()

    attributes_lut = manifest.get("attributesLut")
    if isinstance(attributes_lut, str) and attributes_lut:
        filenames.add(attributes_lut)

    categories = manifest.get("categories")
    if isinstance(categories, list):
        for category in categories:
            if not isinstance(category, dict):
                continue
            values = category.get("shards")
            if isinstance(values, list):
                for value in values:
                    if isinstance(value, str) and value:
                        filenames.add(value)

    for filename in filenames:
        _ensure_relative_filename(filename)
    return tuple(sorted(filenames))


def _ensure_relative_filename(filename: str) -> None:
    parsed = urlparse(filename)
    if parsed.scheme or parsed.netloc:
        raise ValueError(f"invalid manifest file reference: {filename}")
    path = Path(filename)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"invalid manifest file reference: {filename}")


def _join_url(base_url: str, filename: str) -> str:
    return urljoin(f"{base_url.rstrip('/')}/", quote(filename, safe="/"))


def _write_temp(output_dir: Path, filename: str, data: bytes) -> Path:
    _ensure_relative_filename(filename)
    target = output_dir / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.parent / f".{target.name}.{uuid.uuid4().hex}.tmp"
    with tmp.open("wb") as handle:
        handle.write(data)
        handle.flush()
    return tmp


def _replace(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    source.replace(target)
