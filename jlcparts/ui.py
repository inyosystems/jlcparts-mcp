from multiprocessing import Pool
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import time
from pathlib import Path

import click

from jlcparts.compact_index import CompactIndexBuilder
from jlcparts.upstream_catalog import (
    DEFAULT_UPSTREAM_DATA_URL,
    UpstreamCatalogDownloader,
)
from jlcparts.datatables import buildtables, normalizeAttribute
from jlcparts.lcsc import pullPreferredComponents
from jlcparts.partLib import (PartLibrary, PartLibraryDb, getLcscExtraNew,
                              loadJlcTable, loadJlcTableLazy, parsePrice)
from jlcparts.sourceDb import SourceDb, migrateCache
from jlcparts.webdb import buildwebdb


def fetchLcscData(lcsc):
    try:
        extra = getLcscExtraNew(lcsc)
        return (lcsc, extra, None)
    except Exception as e:
        return (lcsc, None, f"{type(e).__name__}: {e}")

def refreshExtraData(db, missing, age, limit):
    missing = set(missing)
    missing.update(db.getMissingExtra(max(0, limit - len(missing))))

    ageCount = min(age, max(0, limit - len(missing)))
    print(f"{ageCount} components will be aged and thus refreshed")
    missing = missing.union(db.getNOldest(ageCount))

    # Truncate the missing components to respect the limit:
    missing = list(missing)[:limit]
    if not missing:
        return

    with Pool(processes=10) as pool:
        for i, (lcsc, extra, error) in enumerate(pool.imap_unordered(fetchLcscData, missing)):
            if error is not None:
                print(f"  {lcsc} skipped. {((i+1) / len(missing) * 100):.2f} % ({error})")
                continue
            print(f"  {lcsc} fetched. {((i+1) / len(missing) * 100):.2f} %")
            db.updateExtra(lcsc, extra)

def apiComponentToDbComponent(component):
    from .jlcpcb import normalizeComponent

    c = normalizeComponent(component)
    return {
        "lcsc": c["lcscPart"],
        "category": c["firstCategory"],
        "subcategory": c["secondCategory"],
        "mfr": c["mfrPart"],
        "package": c["package"],
        "joints": int(c["solderJoint"]),
        "manufacturer": c["manufacturer"],
        "basic": c["libraryType"].lower() == "base",
        "description": c["description"],
        "datasheet": c["datasheet"],
        "stock": int(c["stock"]),
        "price": parsePrice(c["price"]),
        "jlc_extra": c["jlcExtra"],
        "jlc_raw": component,
    }


def refreshSourceDb(
    db,
    checkpoint=None,
    max_seconds=None,
    age=0,
    limit=10000,
    retries=10,
    retry_delay=5,
    verbose=False,
    credentials=None,
    enrich_website=False,
):
    """
    Fetch JLC PCB component data directly into a SourceDb cache.
    """
    from .jlcpcb import (
        createComponentInterface,
        enrichComponentsFromWebsite,
        loadCheckpoint,
        writeCheckpoint,
    )

    if max_seconds is not None and checkpoint is None:
        raise RuntimeError("max-seconds requires a checkpoint so the fetch can resume")

    OLD = 0
    REFRESHED = 1

    lib = SourceDb(db)
    lib.setMeta("last_refresh_started_at", str(int(time.time())))
    checkpointState = loadCheckpoint(checkpoint)
    count = int(checkpointState.get("count", 0))
    done = False
    missing = set()

    if checkpointState.get("done"):
        component_count = lib.componentCount()
        if checkpoint and os.path.exists(checkpoint):
            os.remove(checkpoint)
        lib.close()
        return {
            "done": True,
            "count": count,
            "checkpointed": False,
            "component_count": component_count,
        }

    try:
        if not checkpointState:
            with lib.startTransaction():
                lib.resetFlag(value=OLD)

        interf = createComponentInterface(
            lastKey=checkpointState.get("lastKey"),
            credentials=credentials,
        )
        start = time.monotonic()

        while True:
            if max_seconds is not None and time.monotonic() - start >= max_seconds:
                writeCheckpoint(checkpoint, db, interf.lastPage, count, False)
                break

            for i in range(retries):
                try:
                    page = interf.getPage()
                    break
                except Exception as e:
                    if i == retries - 1:
                        raise e from None
                    time.sleep(retry_delay)
            if page is None:
                with lib.startTransaction():
                    lib.removeWithFlag(value=OLD)
                if checkpoint and os.path.exists(checkpoint):
                    os.remove(checkpoint)
                done = True
                break

            if enrich_website:
                page = enrichComponentsFromWebsite(page)

            with lib.startTransaction():
                for apiComponent in page:
                    isNew = not lib.exists(apiComponent["componentCode"])
                    lib.updateJlcPayload(apiComponent, flag=REFRESHED)
                    if isNew:
                        missing.add(apiComponent["componentCode"])

            count += len(page)
            if verbose:
                print(f"Fetched {count}")
            writeCheckpoint(checkpoint, db, interf.lastPage, count, False)

        refreshExtraData(lib, missing, age, limit)
        component_count = lib.componentCount()
        if done:
            lib.setMetas({
                "last_successful_refresh": str(int(time.time())),
                "last_refresh_count": count,
                "component_count": component_count,
                "last_refresh_error": "",
            })
        if verbose:
            print("Fetch complete" if done else "Fetch checkpointed")
        return {
            "done": done,
            "count": count,
            "checkpointed": not done,
            "component_count": component_count,
            "website_enrichment": bool(enrich_website),
        }
    except Exception as e:
        lib.setMeta("last_refresh_error", f"{type(e).__name__}: {e}")
        raise
    finally:
        lib.close()


def enrichWebsiteDetails(
    db,
    limit=None,
    include_existing=False,
    workers=8,
    verbose=False,
    query_cache=None,
):
    """
    Enrich an existing SourceDb cache with best-effort JLCPCB website fields.
    """
    from .jlcpcb import _website_component_enrichment
    from .query_cache import build_query_cache

    lib = None
    try:
        lib = SourceDb(db)
        started_at = int(time.time())
        lib.setMetas({
            "last_website_enrichment_started_at": str(started_at),
            "last_website_enrichment_error": "",
        })
        candidates = list(lib.iterWebsiteEnrichmentCandidates(
            includeExisting=include_existing,
            limit=limit,
        ))
        total = len(candidates)
        enriched = 0
        failed = 0
        started = time.monotonic()
        executor = ThreadPoolExecutor(max_workers=max(1, int(workers)))
        futures = {
            executor.submit(_website_component_enrichment, lcsc): lcsc
            for lcsc in candidates
        }
        try:
            for index, future in enumerate(as_completed(futures), start=1):
                lcsc = futures[future]
                try:
                    enrichment = future.result()
                    if lib.updateWebsiteEnrichment(lcsc, enrichment):
                        enriched += 1
                        if verbose:
                            print(f"  {lcsc} enriched. {(index / total * 100):.2f} %")
                    else:
                        failed += 1
                        if verbose:
                            print(f"  {lcsc} skipped; not present in cache. {(index / total * 100):.2f} %")
                except Exception as e:
                    failed += 1
                    if verbose:
                        print(f"  {lcsc} skipped. {(index / total * 100):.2f} % ({type(e).__name__}: {e})")
        except BaseException:
            executor.shutdown(wait=False, cancel_futures=True)
            lib.close()
            raise
        else:
            executor.shutdown(wait=True)

        completed_at = int(time.time())
        lib.setMetas({
            "last_successful_website_enrichment": str(completed_at),
            "last_website_enrichment_count": str(enriched),
            "last_website_enrichment_failed": str(failed),
            "last_website_enrichment_candidate_count": str(total),
            "last_website_enrichment_seconds": f"{time.monotonic() - started:.2f}",
            "last_website_enrichment_error": "",
        })
        lib.close()
    except Exception as e:
        try:
            if lib is not None:
                lib.setMeta("last_website_enrichment_error", f"{type(e).__name__}: {e}")
                lib.close()
        except Exception:
            pass
        raise

    rebuilt_query_cache = False
    if query_cache:
        build_query_cache(db, query_cache)
        rebuilt_query_cache = True

    return {
        "candidate_count": total,
        "enriched": enriched,
        "failed": failed,
        "seconds": time.monotonic() - started,
        "rebuilt_query_cache": rebuilt_query_cache,
    }


def _credentialsFromOptions(app_id, access_key, secret_key):
    from .jlcpcb import JlcPcbCredentials

    return JlcPcbCredentials(
        app_id=app_id or os.environ.get("JLCPCB_APP_ID"),
        access_key=access_key or os.environ.get("JLCPCB_ACCESS_KEY"),
        secret_key=secret_key or os.environ.get("JLCPCB_SECRET_KEY"),
    )


def _defaultQueryCachePath(cache):
    return os.path.join(os.path.dirname(cache), "query-cache.sqlite3")


def _defaultCheckpointPath(cache):
    return os.path.join(os.path.dirname(cache), "refresh-checkpoint.json")


def _defaultCatalogPath():
    return os.path.abspath(os.path.expanduser("~/.cache/jlcparts/catalog"))


def _defaultIndexPath():
    return os.path.abspath(os.path.expanduser("~/.cache/jlcparts/mcp-index.sqlite3"))


@click.command("download-catalog")
@click.option("--catalog", "catalog_path", default="~/.cache/jlcparts/catalog",
    help="Directory for the upstream generated catalog")
@click.option("--data-url", default=DEFAULT_UPSTREAM_DATA_URL,
    help="Upstream generated catalog data URL")
@click.option("--force", is_flag=True,
    help="Overwrite local catalog files even if present")
@click.option("--workers", type=int, default=8,
    help="Number of concurrent catalog file downloads")
def downloadCatalog(catalog_path, data_url, force, workers):
    """
    Download the upstream generated yaqwsx component catalog.
    """
    catalog_path = os.path.abspath(os.path.expanduser(catalog_path))
    result = UpstreamCatalogDownloader(workers=workers).download_manifest_source(
        Path(catalog_path),
        data_url=data_url,
        force=force,
    )
    print(json.dumps({
        "catalog_path": str(result.output_dir),
        "manifest_path": str(result.manifest_path),
        "metadata_path": str(result.metadata_path),
        "downloaded_files": len(result.downloaded_files),
        "source_url": result.source_url,
        "component_count": result.component_count,
        "etag": result.etag,
        "last_modified": result.last_modified,
        "sha256": result.sha256,
    }, indent=2, sort_keys=True))


@click.command("build-index")
@click.option("--catalog", "catalog_path", default="~/.cache/jlcparts/catalog",
    help="Directory containing the upstream generated catalog")
@click.option("--index", "index_path", default="~/.cache/jlcparts/mcp-index.sqlite3",
    help="Compact MCP index SQLite path")
@click.option("--force", is_flag=True,
    help="Overwrite an existing compact MCP index")
@click.option("--progress-interval", type=int, default=10000,
    help="Print progress every N indexed components; 0 disables progress")
def buildIndex(catalog_path, index_path, force, progress_interval):
    """
    Build the compact MCP SQLite index from the upstream catalog.
    """
    catalog_path = os.path.abspath(os.path.expanduser(catalog_path))
    index_path = os.path.abspath(os.path.expanduser(index_path))
    result = CompactIndexBuilder(
        Path(catalog_path),
        Path(index_path),
        progress_interval=progress_interval,
    ).build(force=force)
    print(json.dumps({
        "index_path": result.index_path,
        "component_count": result.component_count,
        "category_count": result.category_count,
        "attribute_key_count": result.attribute_key_count,
        "attribute_value_count": result.attribute_value_count,
        "build_seconds": result.build_seconds,
    }, indent=2, sort_keys=True))


@click.command("mcp")
@click.option("--index", "index_path", default="~/.cache/jlcparts/mcp-index.sqlite3",
    help="Compact MCP index SQLite path")
@click.option("--transport", type=click.Choice(["stdio", "http"]), default="stdio",
    help="MCP transport")
@click.option("--host", default="127.0.0.1",
    help="HTTP bind host")
@click.option("--port", type=int, default=8765,
    help="HTTP bind port")
def mcp(index_path, transport, host, port):
    """
    Run the local cache-first MCP server.
    """
    from .mcp_server import main as mcp_main

    argv = ["--index", index_path, "--transport", transport, "--host", host, "--port", str(port)]
    mcp_main(argv)


@click.command("enrich-cache")
@click.option("--index", "index_path", default="~/.cache/jlcparts/mcp-index.sqlite3",
    help="Compact MCP index SQLite path")
@click.option("--limit", type=int, default=0,
    help="Enrich at most this many components; 0 means no artificial limit")
@click.option("--verbose", is_flag=True,
    help="Be verbose")
def enrichCache(index_path, limit, verbose):
    """
    Fetch exact public website detail for indexed components as maintenance.
    """
    from .compact_query import CompactQueryService

    index_path = os.path.abspath(os.path.expanduser(index_path))
    max_count = None if limit == 0 else max(0, int(limit))
    processed = 0
    enriched = 0
    failed = 0
    conn = sqlite3.connect(index_path)
    try:
        rows = conn.execute(
            """
            SELECT lcsc FROM components
            WHERE website_checked_at IS NULL
            ORDER BY lcsc_number
            """
        ).fetchall()
        if max_count is not None:
            rows = rows[:max_count]
        service = CompactQueryService(index_path)
        try:
            for row in rows:
                lcsc = row[0]
                processed += 1
                result = service.lookup_component_website_detail(lcsc)
                if result.get("found"):
                    conn.execute(
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
                    conn.execute(
                        "UPDATE components SET website_checked_at = ? WHERE lcsc = ?",
                        (result["checked_at"], lcsc),
                    )
                    enriched += 1
                else:
                    failed += 1
                if verbose:
                    print(f"{lcsc}: {'enriched' if result.get('found') else 'failed'}")
        finally:
            service.close()
        conn.commit()
    finally:
        conn.close()
    print(json.dumps({
        "index_path": index_path,
        "processed": processed,
        "enriched": enriched,
        "failed": failed,
    }, indent=2, sort_keys=True))


@click.command("refresh-cache")
@click.option("--cache", "cache_path", default="~/.cache/jlcparts/cache.sqlite3",
    help="Source cache SQLite path")
@click.option("--query-cache", default=None,
    help="Query index SQLite path")
@click.option("--checkpoint", default=None,
    help="Read/write a checkpoint JSON for resumable refreshes")
@click.option("--max-seconds", type=int, default=None,
    help="Stop after roughly this many seconds and save the checkpoint")
@click.option("--age", type=int, default=0,
    help="Automatically discard n oldest LCSC extra records and fetch them again")
@click.option("--limit", type=int, default=10000,
    help="Limit number of newly added LCSC extra records")
@click.option("--retries", type=int, default=10,
    help="Retry failed JLCPCB API pages this many times")
@click.option("--retry-delay", type=int, default=5,
    help="Wait this many seconds between JLCPCB API retries")
@click.option("--jlcpcb-app-id", default=None,
    help="JLCPCB OpenAPI app id")
@click.option("--jlcpcb-access-key", default=None,
    help="JLCPCB OpenAPI access key")
@click.option("--jlcpcb-secret-key", default=None,
    help="JLCPCB OpenAPI secret key")
@click.option("--verbose", is_flag=True,
    help="Be verbose")
def refreshCache(cache_path, query_cache, checkpoint, max_seconds, age, limit,
                 retries, retry_delay, jlcpcb_app_id, jlcpcb_access_key,
                 jlcpcb_secret_key, verbose):
    """
    Run or resume a full official JLCPCB OpenAPI cache refresh.
    """
    from .query_cache import build_query_cache

    cache_path = os.path.abspath(os.path.expanduser(cache_path))
    query_cache = os.path.abspath(os.path.expanduser(
        query_cache or _defaultQueryCachePath(cache_path)
    ))
    checkpoint = os.path.abspath(os.path.expanduser(
        checkpoint or _defaultCheckpointPath(cache_path)
    ))
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    os.makedirs(os.path.dirname(query_cache), exist_ok=True)
    result = refreshSourceDb(
        cache_path,
        checkpoint=checkpoint,
        max_seconds=max_seconds,
        age=age,
        limit=limit,
        retries=retries,
        retry_delay=retry_delay,
        verbose=verbose,
        credentials=_credentialsFromOptions(
            jlcpcb_app_id,
            jlcpcb_access_key,
            jlcpcb_secret_key,
        ),
        enrich_website=False,
    )
    rebuilt_query_cache = False
    if result.get("done"):
        build_query_cache(cache_path, query_cache)
        rebuilt_query_cache = True
    print(json.dumps({
        "cache_path": cache_path,
        "query_cache_path": query_cache,
        "checkpoint_path": checkpoint,
        "refresh_result": result,
        "rebuilt_query_cache": rebuilt_query_cache,
        "monitoring": (
            "If refresh_result.checkpointed is true, rerun this command with "
            "the same cache/checkpoint paths to resume."
        ),
    }, indent=2, sort_keys=True))


@click.command()
@click.argument("source", type=click.Path(dir_okay=False, exists=True))
@click.argument("db", type=click.Path(dir_okay=False, writable=True))
@click.option("--age", type=int, default=0,
    help="Automatically discard n oldest components and fetch them again")
@click.option("--limit", type=int, default=10000,
    help="Limit number of newly added components")
@click.option("--partial", is_flag=True,
    help="Do not remove DB components missing from SOURCE")
@click.option("--skip", type=int, default=0,
    help="Skip this many rows from SOURCE before importing")
def getLibrary(source, db, age, limit, partial, skip):
    """
    Download library inside OUTPUT (JSON format) based on SOURCE (csv table
    provided by JLC PCB).

    You can specify previously downloaded library as a cache to save requests to
    fetch LCSC extra data.
    """
    OLD = 0
    REFRESHED = 1

    db = PartLibraryDb(db)
    missing = set()
    total = 0
    skipped = 0
    with db.startTransaction():
        if not partial:
            db.resetFlag(value=OLD)
        with open(source, newline="") as f:
            jlcTable = loadJlcTableLazy(f)
            for component in jlcTable:
                if skipped < skip:
                    skipped += 1
                    continue
                total += 1
                if db.exists(component["lcsc"]):
                    db.updateJlcPart(component, flag=None if partial else REFRESHED)
                else:
                    component["extra"] = {}
                    db.addComponent(component, flag=None if partial else REFRESHED)
                    missing.add(component["lcsc"])
        if skipped != 0:
            print(f"Skipped {skipped} components")
        print(f"New {len(missing)} components out of {total} total")
        refreshExtraData(db, missing, age, limit)
        if not partial:
            db.removeWithFlag(value=OLD)
    # Temporary work-around for space-related issues in CI - simply don't rebuild the DB
    # db.vacuum()

@click.command()
@click.argument("db", type=click.Path(dir_okay=False, writable=True))
@click.option("--checkpoint", type=click.Path(dir_okay=False), default=None,
    help="Read/write a checkpoint JSON for resumable fetches")
@click.option("--max-seconds", type=int, default=None,
    help="Stop after roughly this many seconds and save the checkpoint")
@click.option("--age", type=int, default=0,
    help="Automatically discard n oldest components and fetch them again")
@click.option("--limit", type=int, default=10000,
    help="Limit number of newly added LCSC extra records")
@click.option("--retries", type=int, default=10,
    help="Retry failed JLCPCB API pages this many times")
@click.option("--retry-delay", type=int, default=5,
    help="Wait this many seconds between JLCPCB API retries")
@click.option("--verbose", is_flag=True,
    help="Be verbose")
@click.option("--enrich-website", is_flag=True,
    help="Also fetch best-effort JLCPCB website enrichment during refresh")
def fetchDb(db, checkpoint, max_seconds, age, limit, retries, retry_delay, verbose, enrich_website):
    """
    Fetch JLC PCB component data directly into DB.
    """
    refreshSourceDb(
        db,
        checkpoint=checkpoint,
        max_seconds=max_seconds,
        age=age,
        limit=limit,
        retries=retries,
        retry_delay=retry_delay,
        verbose=verbose,
        enrich_website=enrich_website,
    )


@click.command("enrich-website")
@click.argument("db", type=click.Path(dir_okay=False, exists=True, writable=True))
@click.option("--limit", type=int, default=None,
    help="Enrich at most this many components")
@click.option("--all", "include_existing", is_flag=True,
    help="Refresh all present components, including already enriched rows")
@click.option("--workers", type=int, default=8,
    help="Number of concurrent website requests")
@click.option("--query-cache", type=click.Path(dir_okay=False), default=None,
    help="Rebuild this query cache after enrichment")
@click.option("--verbose", is_flag=True,
    help="Be verbose")
def enrichWebsite(db, limit, include_existing, workers, query_cache, verbose):
    """
    Fetch hidden/best-effort JLCPCB website fields for an existing SourceDb.
    """
    result = enrichWebsiteDetails(
        db,
        limit=limit,
        include_existing=include_existing,
        workers=workers,
        verbose=verbose,
        query_cache=query_cache,
    )
    print(json.dumps(result, indent=2, sort_keys=True))



@click.command()
@click.argument("db", type=click.Path(dir_okay=False, writable=True))
def updatePreferred(db):
    """
    Download list of preferred components from JLC PCB and mark them into the DB.
    """
    preferred = pullPreferredComponents()
    lib = SourceDb(db)
    lib.setPreferred(preferred)


@click.command()
@click.argument("source", type=click.Path(dir_okay=False, exists=True))
@click.argument("output", type=click.Path(dir_okay=False), required=False)
def migratecache(source, output):
    """
    Migrate a legacy cache.sqlite3 into the compact source-db-v2 format.
    """
    migrateCache(source, output)


@click.command()
@click.argument("libraryFilename")
def listcategories(libraryfilename):
    """
    Print all categories from library specified by LIBRARYFILENAMEto standard
    output
    """
    lib = PartLibrary(libraryfilename)
    for c, subcats in lib.categories().items():
        print(f"{c}:")
        for s in subcats:
            print(f"  {s}")

@click.command()
@click.argument("libraryFilename")
def listattributes(libraryfilename):
    """
    Print all keys in the extra["attributes"] arguments from library specified by
    LIBRARYFILENAME to standard output
    """
    keys = set()
    lib = PartLibrary(libraryfilename)
    for subcats in lib.lib.values():
        for parts in subcats.values():
            for data in parts.values():
                if "extra" not in data:
                    continue
                extra = data["extra"]
                attr = extra.get("attributes", {})
                if not isinstance(attr, list):
                    for k in extra.get("attributes", {}).keys():
                        keys.add(k)
    for k in keys:
        print(k)

@click.command()
@click.argument("lcsc_code")
def fetchDetails(lcsc_code):
    """
    Fetch LCSC extra information for a given LCSC code
    """
    print(getLcscExtraNew(lcsc_code))

@click.command()
@click.argument("filename", type=click.Path(writable=True))
@click.option("--verbose", is_flag=True,
    help="Be verbose")
@click.option("--limit", type=int, default=None,
    help="Fetch at most this many components")
@click.option("--checkpoint", type=click.Path(dir_okay=False), default=None,
    help="Read/write a checkpoint JSON for resumable fetches")
@click.option("--max-seconds", type=int, default=None,
    help="Stop after roughly this many seconds and save the checkpoint")
def fetchTable(filename, verbose, limit, checkpoint, max_seconds):
    """
    Fetch JLC PCB component table
    """
    from .jlcpcb import pullComponentTable

    def report(count: int) -> None:
        if (verbose):
            print(f"Fetched {count}")

    pullComponentTable(filename, report, limit=limit, checkpoint=checkpoint,
                       maxSeconds=max_seconds)

@click.command()
@click.argument("lcsc")
def testComponent(lcsc):
    """
    Tests parsing attributes of given component
    """
    extra = getLcscExtraNew(lcsc)["attributes"]

    extra.pop("url", None)
    extra.pop("images", None)
    extra.pop("prices", None)
    extra.pop("datasheet", None)
    extra.pop("id", None)
    extra.pop("manufacturer", None)
    extra.pop("number", None)
    extra.pop("title", None)
    extra.pop("quantity", None)
    for i in range(10):
        extra.pop(f"quantity{i}", None)
    normalized = dict(normalizeAttribute(key, val) for key, val in extra.items())
    print(json.dumps(normalized, indent=4))


@click.group()
def cli():
    pass

cli.add_command(getLibrary)
cli.add_command(listcategories)
cli.add_command(listattributes)
cli.add_command(downloadCatalog)
cli.add_command(buildIndex)
cli.add_command(enrichCache)
cli.add_command(mcp)
cli.add_command(buildtables)
cli.add_command(buildwebdb)
cli.add_command(updatePreferred)
cli.add_command(migratecache)
cli.add_command(fetchDetails)
cli.add_command(fetchTable)
cli.add_command(testComponent)

if __name__ == "__main__":
    cli()
