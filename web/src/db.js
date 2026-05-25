import Dexie from 'dexie';
import * as pako from 'pako';

if (!window.indexedDB) {
    alert("This page requires IndexedDB to work.\n" +
            "Your browser does not support it. Please upgrade your browser.");
}

async function persist() {
    return await navigator.storage?.persist?.();
}

export const db = new Dexie('jlcparts');
db.version(1).stores({
    settings: 'key',
    components: 'lcsc, category, mfr, *indexWords',
    categories: 'id++,[category+subcategory], subcategory, category'
});
db.version(2).stores({
    settings: 'key',
    files: 'name'
});

const SOURCE_PATH = "data";
const MANIFEST_PATH = `${SOURCE_PATH}/manifest.json`;
const SHARD_LOAD_CONCURRENCY = 8;
const SMALL_SHARD_ESTIMATED_ROWS = 1000;
const BROWSE_SHARD_ESTIMATED_ROWS = 20000;
const parsedFileCache = new Map();
let manifestCache = undefined;

function dataUrl(name) {
    return `${SOURCE_PATH}/${name}`;
}

function normalizeBinary(data) {
    if (data instanceof ArrayBuffer) {
        return data;
    }
    if (ArrayBuffer.isView(data)) {
        return data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength);
    }
    return data;
}

function lineObjects(text, callback, checkAbort) {
    const lines = text.split(/\r?\n/);
    let idx = 0;
    for (const line of lines) {
        if (!line) {
            continue;
        }
        if (callback(JSON.parse(line), idx++) === 'abort') {
            return true;
        }
        if (checkAbort?.()) {
            return true;
        }
    }
    return false;
}

async function gunzipToText(buffer) {
    buffer = normalizeBinary(buffer);
    if (window.DecompressionStream && window.TextDecoderStream) {
        const stream = new Blob([buffer]).stream()
            .pipeThrough(new window.DecompressionStream('gzip'))
            .pipeThrough(new window.TextDecoderStream());
        const reader = stream.getReader();
        let text = '';
        try {
            while (true) {
                const { done, value } = await reader.read();
                if (done) {
                    break;
                }
                text += value;
            }
        } finally {
            reader.releaseLock();
        }
        return text;
    }
    return pako.ungzip(new Uint8Array(buffer), { to: 'string' });
}

async function streamJsonLines(name, callback, checkAbort, onDownloadProgress) {
    const buffer = await ensureBinaryFile(name, onDownloadProgress);
    if (window.DecompressionStream && window.TextDecoderStream) {
        const stream = new Blob([buffer]).stream()
            .pipeThrough(new window.DecompressionStream('gzip'))
            .pipeThrough(new window.TextDecoderStream());
        const reader = stream.getReader();
        let chunk = '';
        let idx = 0;
        try {
            while (true) {
                if (checkAbort?.()) {
                    return true;
                }
                const { done, value } = await reader.read();
                if (done) {
                    if (chunk && callback(JSON.parse(chunk), idx++) === 'abort') {
                        return true;
                    }
                    return false;
                }
                chunk += value;
                while (true) {
                    const newline = chunk.indexOf('\n');
                    if (newline === -1) {
                        break;
                    }
                    const line = chunk.slice(0, newline).trim();
                    chunk = chunk.slice(newline + 1);
                    if (!line) {
                        continue;
                    }
                    if (callback(JSON.parse(line), idx++) === 'abort') {
                        return true;
                    }
                    if (checkAbort?.()) {
                        return true;
                    }
                }
            }
        } finally {
            reader.releaseLock();
        }
    }
    return lineObjects(await gunzipToText(buffer), callback, checkAbort);
}

async function streamTextLines(name, callback, checkAbort, onDownloadProgress) {
    const buffer = await ensureBinaryFile(name, onDownloadProgress);
    if (window.DecompressionStream && window.TextDecoderStream) {
        const stream = new Blob([buffer]).stream()
            .pipeThrough(new window.DecompressionStream('gzip'))
            .pipeThrough(new window.TextDecoderStream());
        const reader = stream.getReader();
        let chunk = '';
        let idx = 0;
        try {
            while (true) {
                if (checkAbort?.()) {
                    return true;
                }
                const { done, value } = await reader.read();
                if (done) {
                    if (chunk && callback(chunk, idx++) === 'abort') {
                        return true;
                    }
                    return false;
                }
                chunk += value;
                while (true) {
                    const newline = chunk.indexOf('\n');
                    if (newline === -1) {
                        break;
                    }
                    const line = chunk.slice(0, newline).trimEnd();
                    chunk = chunk.slice(newline + 1);
                    if (!line) {
                        continue;
                    }
                    if (callback(line, idx++) === 'abort') {
                        return true;
                    }
                    if (checkAbort?.()) {
                        return true;
                    }
                }
            }
        } finally {
            reader.releaseLock();
        }
    }

    const lines = (await gunzipToText(buffer)).split(/\r?\n/);
    let idx = 0;
    for (const line of lines) {
        if (!line) {
            continue;
        }
        if (callback(line, idx++) === 'abort') {
            return true;
        }
        if (checkAbort?.()) {
            return true;
        }
    }
    return false;
}

function decodeAttributes(attributeIds, attributeLut) {
    const attributes = {};
    for (const id of attributeIds || []) {
        const entry = attributeLut[id];
        if (!entry) {
            continue;
        }
        attributes[entry[0]] = entry[1];
    }
    return attributes;
}

function decodeComponentRow(row, schema, attributeLut) {
    return {
        lcsc: row[schema.lcsc],
        mfr: row[schema.mfr],
        joints: row[schema.joints],
        description: row[schema.description],
        datasheet: row[schema.datasheet],
        price: row[schema.price],
        img: row[schema.img],
        url: row[schema.url],
        stock: row[schema.stock],
        category: row[schema.subcategory],
        attributes: decodeAttributes(row[schema.attributes], attributeLut),
    };
}

function componentRowText(row, schema) {
    return (
        row[schema.lcsc] + " " +
        row[schema.mfr] + " " +
        row[schema.description]
    ).toLocaleLowerCase();
}

function splitSearchWords(searchString) {
    return searchString.split(/\s+/)
        .filter(x => x.length > 0)
        .map(x => x.toLocaleLowerCase());
}

function textMatchesSearch(text, words) {
    if (words.length === 0) {
        return true;
    }
    return words.every(word => text.includes(word));
}

async function mapConcurrent(items, limit, callback) {
    const results = new Array(items.length);
    let nextIndex = 0;
    let aborted = false;
    const workers = Array.from({ length: Math.min(limit, items.length) }, async () => {
        while (!aborted) {
            const index = nextIndex++;
            if (index >= items.length) {
                return;
            }
            const result = await callback(items[index], index);
            if (result === null) {
                aborted = true;
                results[index] = null;
                return;
            }
            results[index] = result;
        }
    });
    await Promise.all(workers);
    return aborted ? null : results;
}

function searchTrigrams(word, gramSize) {
    if (word.length < gramSize) {
        return [];
    }
    const grams = [];
    for (let i = 0; i <= word.length - gramSize; i++) {
        grams.push(word.slice(i, i + gramSize));
    }
    return grams;
}

function selectSearchIndexFile(manifest, words) {
    const trigrams = manifest.searchTrigrams;
    if (!trigrams?.buckets) {
        return { file: manifest.searchIndex };
    }

    const candidates = [];
    for (const word of words) {
        for (const gram of searchTrigrams(word, trigrams.gramSize || 3)) {
            const bucket = trigrams.buckets[gram];
            if (bucket) {
                candidates.push({ ...bucket, gram });
            }
        }
    }

    if (candidates.length === 0) {
        return { file: manifest.searchIndex };
    }
    candidates.sort((a, b) => a.rows - b.rows);
    return candidates[0];
}

function parseSearchIndexLine(line) {
    const firstTab = line.indexOf('\t');
    const secondTab = line.indexOf('\t', firstTab + 1);
    if (firstTab === -1 || secondTab === -1) {
        return null;
    }
    return {
        lcsc: line.slice(0, firstTab),
        shard: line.slice(firstTab + 1, secondTab),
        text: line.slice(secondTab + 1),
    };
}

async function collectTsvSearchIndexMatches(searchIndexFile, words, checkAbort, onProgress) {
    const matchesByShard = new Map();
    const aborted = await streamTextLines(searchIndexFile.file, line => {
        if (searchIndexFile.gram) {
            const firstTab = line.indexOf('\t');
            if (firstTab === -1 || line.slice(0, firstTab) !== searchIndexFile.gram) {
                return;
            }
            line = line.slice(firstTab + 1);
        }
        const row = parseSearchIndexLine(line);
        if (!row) {
            return;
        }
        if (textMatchesSearch(row.text, words)) {
            if (!matchesByShard.has(row.shard)) {
                matchesByShard.set(row.shard, new Set());
            }
            matchesByShard.get(row.shard).add(row.lcsc);
        }
        if (checkAbort?.()) {
            return 'abort';
        }
    }, checkAbort, onProgress);
    return aborted ? null : matchesByShard;
}

async function collectJsonSearchIndexMatches(manifest, words, checkAbort, onProgress) {
    const matchesByShard = new Map();
    let schema = null;
    const aborted = await streamJsonLines(manifest.searchIndex, (row, idx) => {
        if (idx === 0) {
            schema = row;
            return;
        }
        if (textMatchesSearch(row[schema.text], words)) {
            const shardName = row[schema.shard];
            if (!matchesByShard.has(shardName)) {
                matchesByShard.set(shardName, new Set());
            }
            matchesByShard.get(shardName).add(row[schema.lcsc]);
        }
        if (checkAbort?.()) {
            return 'abort';
        }
    }, checkAbort, onProgress);
    return aborted ? null : matchesByShard;
}

function componentCountForFile(manifest, name, fallback = SMALL_SHARD_ESTIMATED_ROWS) {
    return manifest.files[name]?.componentCount ?? fallback;
}

function createFileProgressReporter(onProgress, phase, fileNames) {
    if (!onProgress) {
        return {
            fileProgress: () => undefined,
            fileFinished: () => undefined,
        };
    }

    const uniqueFileNames = Array.from(new Set(fileNames));
    const files = new Map(uniqueFileNames.map(name => [name, {
        loaded: 0,
        total: null,
        done: false,
        cached: false,
    }]));
    const started = performance.now();

    const report = () => {
        let loadedBytes = 0;
        let totalBytes = 0;
        let knownTotal = true;
        let doneFiles = 0;
        let cachedFiles = 0;

        for (const file of files.values()) {
            loadedBytes += file.loaded;
            if (file.total === null) {
                knownTotal = false;
            } else {
                totalBytes += file.total;
            }
            if (file.done) {
                doneFiles += 1;
            }
            if (file.cached) {
                cachedFiles += 1;
            }
        }

        const fileProgress = files.size === 0 ? 1 : doneFiles / files.size;
        const byteProgress = knownTotal && totalBytes > 0 ? loadedBytes / totalBytes : null;
        const progress = byteProgress ?? fileProgress;
        const elapsedSeconds = (performance.now() - started) / 1000;
        const etaSeconds = progress > 0 && progress < 1
            ? elapsedSeconds * (1 - progress) / progress
            : null;

        onProgress({
            phase,
            filesDone: doneFiles,
            filesTotal: files.size,
            cachedFiles,
            loadedBytes,
            totalBytes: knownTotal ? totalBytes : null,
            progress,
            etaSeconds,
        });
    };

    report();
    return {
        fileProgress: name => progress => {
            const file = files.get(name);
            if (!file) {
                return;
            }
            file.loaded = progress.loaded ?? file.loaded;
            file.total = progress.total ?? file.total;
            file.cached = Boolean(progress.cached);
            if (file.cached || (file.total !== null && file.loaded >= file.total)) {
                file.done = true;
            }
            report();
        },
        fileFinished: name => {
            const file = files.get(name);
            if (!file) {
                return;
            }
            file.done = true;
            if (file.total === null) {
                file.total = file.loaded;
            }
            report();
        },
    };
}

function chooseHydrationPlans(manifest, matchesByShard) {
    const categoriesById = new Map(manifest.categories.map(category => [category.id, category]));
    const matchesByCategory = new Map();
    const smallPlans = [];

    for (const [shardName, lcscMatches] of matchesByShard) {
        const categoryId = manifest.files[shardName]?.subcategoryId;
        const category = categoriesById.get(categoryId);
        if (!category?.browseShards?.length) {
            smallPlans.push({ shardNames: [shardName], lcscMatches });
            continue;
        }
        if (!matchesByCategory.has(categoryId)) {
            matchesByCategory.set(categoryId, {
                category,
                lcscMatches: new Set(),
                smallShardNames: [],
            });
        }
        const categoryMatches = matchesByCategory.get(categoryId);
        categoryMatches.smallShardNames.push(shardName);
        for (const lcsc of lcscMatches) {
            categoryMatches.lcscMatches.add(lcsc);
        }
    }

    const plans = [...smallPlans];
    for (const { category, lcscMatches, smallShardNames } of matchesByCategory.values()) {
        const smallRows = smallShardNames.reduce(
            (total, shardName) => total + componentCountForFile(manifest, shardName),
            0
        );
        const browseRows = category.browseShards.reduce(
            (total, shardName) => total + componentCountForFile(manifest, shardName, BROWSE_SHARD_ESTIMATED_ROWS),
            0
        );
        const fewerBrowseFiles = category.browseShards.length * 3 < smallShardNames.length;
        if (fewerBrowseFiles && browseRows <= smallRows * 1.25) {
            plans.push({ shardNames: category.browseShards, lcscMatches });
        } else {
            for (const shardName of smallShardNames) {
                plans.push({ shardNames: [shardName], lcscMatches: matchesByShard.get(shardName) });
            }
        }
    }
    return plans;
}

async function queryComponentsFromMatches(manifest, matchesByShard, checkAbort, onProgress) {
    if (matchesByShard.size === 0) {
        return [];
    }

    const attributeLut = await ensureJsonFile(manifest.attributesLut);
    const shardNamesForPlan = plan => plan.shardNames.map(shardName => [shardName, plan.lcscMatches]);
    const shardItems = chooseHydrationPlans(manifest, matchesByShard).flatMap(shardNamesForPlan);
    const progress = createFileProgressReporter(
        onProgress, "Performing component query", shardItems.map(([shardName]) => shardName)
    );
    const shardResults = await mapConcurrent(
        shardItems,
        SHARD_LOAD_CONCURRENCY,
        async ([shardName, lcscMatches]) => {
            const results = [];
            let schema = null;
            const aborted = await streamJsonLines(shardName, (row, idx) => {
                if (idx === 0) {
                    schema = row;
                    return;
                }
                if (lcscMatches.has(row[schema.lcsc])) {
                    results.push(decodeComponentRow(row, schema, attributeLut));
                }
                if (checkAbort?.()) {
                    return 'abort';
                }
            }, checkAbort, progress.fileProgress(shardName));
            progress.fileFinished(shardName);
            if (aborted) {
                return null;
            }
            return results;
        }
    );
    if (shardResults === null || checkAbort?.()) {
        return null;
    }
    return shardResults.flat();
}

export async function fetchJson(path, errorIntro = "Cannot fetch JSON: ") {
    const response = await fetch(path);
    if (!response.ok) {
        throw Error(errorIntro + response.statusText);
    }

    const contentType = response.headers.get('Content-Type') || '';
    try {
        if (contentType.includes("application/json") || path.endsWith(".json")) {
            return await response.json();
        }
        if (contentType.includes("application/gzip") || contentType.includes("application/x-gzip") ||
                path.endsWith(".json.gz")) {
            return JSON.parse(await gunzipToText(await response.arrayBuffer()));
        }
    } catch (error) {
        throw Error(errorIntro + `${error}: ` + path);
    }

    throw Error(errorIntro + `Unsupported response for ${path}: ${contentType}`);
}

async function getSetting(key) {
    return (await db.settings.get(key))?.value;
}

async function setSetting(key, value) {
    await db.settings.put({ key, value });
}

export async function getLocalManifest() {
    if (manifestCache !== undefined) {
        return manifestCache;
    }
    manifestCache = (await getSetting("manifest")) ?? null;
    return manifestCache;
}

async function storeManifest(manifest) {
    manifestCache = manifest;
    await Promise.all([
        setSetting("manifest", manifest),
        setSetting("lastUpdate", manifest.created),
        setSetting("formatVersion", manifest.version),
    ]);
}

async function fetchRemoteManifest() {
    return await fetchJson(MANIFEST_PATH, "Cannot fetch component manifest: ");
}

async function responseArrayBuffer(response, onProgress) {
    const contentLength = Number.parseInt(response.headers.get("Content-Length"), 10);
    if (!response.body || !Number.isFinite(contentLength) || contentLength <= 0) {
        onProgress?.({loaded: 0, total: null});
        const data = await response.arrayBuffer();
        onProgress?.({loaded: data.byteLength, total: null});
        return data;
    }

    const reader = response.body.getReader();
    const chunks = [];
    let loaded = 0;
    try {
        while (true) {
            const {done, value} = await reader.read();
            if (done) {
                break;
            }
            chunks.push(value);
            loaded += value.byteLength;
            onProgress?.({loaded, total: contentLength});
        }
    } finally {
        reader.releaseLock();
    }

    const data = new Uint8Array(loaded);
    let offset = 0;
    for (const chunk of chunks) {
        data.set(chunk, offset);
        offset += chunk.byteLength;
    }
    return data.buffer;
}

async function pruneCachedFiles(manifest) {
    const expectedHashes = new Map(
        Object.entries(manifest.files).map(([name, info]) => [name, info.sha256])
    );
    const staleFiles = [];
    await db.files.each(record => {
        if (expectedHashes.get(record.name) !== record.sha256) {
            parsedFileCache.delete(record.name);
            staleFiles.push(record.name);
        }
    });
    if (staleFiles.length > 0) {
        await db.files.bulkDelete(staleFiles);
    }
}

async function ensureBinaryFile(name, onDownloadProgress) {
    const manifest = await getLocalManifest();
    if (!manifest) {
        throw Error("Component manifest is not cached locally");
    }
    const fileInfo = manifest.files[name];
    if (!fileInfo) {
        throw Error(`Unknown cached file ${name}`);
    }

    const cached = await db.files.get(name);
    if (cached && cached.sha256 === fileInfo.sha256) {
        const data = normalizeBinary(cached.data);
        onDownloadProgress?.({loaded: data.byteLength, total: data.byteLength, cached: true});
        return data;
    }

    const response = await fetch(dataUrl(name));
    if (!response.ok) {
        throw Error(`Cannot fetch ${name}: ${response.statusText}`);
    }
    const data = await responseArrayBuffer(response, onDownloadProgress);
    await db.files.put({
        name,
        sha256: fileInfo.sha256,
        data
    });
    parsedFileCache.delete(name);
    return data;
}

async function ensureJsonFile(name, onDownloadProgress) {
    if (parsedFileCache.has(name)) {
        return await parsedFileCache.get(name);
    }
    const promise = (async () => {
        return JSON.parse(await gunzipToText(await ensureBinaryFile(name, onDownloadProgress)));
    })();
    parsedFileCache.set(name, promise);
    try {
        return await promise;
    } catch (error) {
        parsedFileCache.delete(name);
        throw error;
    }
}

export async function getCategories() {
    return (await getLocalManifest())?.categories ?? [];
}

export async function hasLocalComponentLibrary() {
    return (await getLocalManifest()) !== null;
}

export async function getComponentCount() {
    return (await getLocalManifest())?.totalComponents ?? 0;
}

export async function updateComponentLibrary(report) {
    await persist();
    const progress = {};
    const updateProgress = (name, status) => {
        progress[name] = status;
        report(progress);
    };

    updateProgress("Manifest", ["Fetching", false]);
    const manifest = await fetchRemoteManifest();
    updateProgress("Manifest", ["Fetched", true]);

    updateProgress("Cache", ["Pruning stale files", false]);
    await pruneCachedFiles(manifest);
    updateProgress("Cache", ["Ready", true]);

    await storeManifest(manifest);

    updateProgress("Metadata", ["Caching attributes", false]);
    await ensureJsonFile(manifest.attributesLut, progress => {
        if (progress.cached) {
            updateProgress("Metadata", ["Attributes already cached", true, 1]);
            return;
        }
        if (progress.total) {
            const percent = Math.round(progress.loaded / progress.total * 100);
            updateProgress("Metadata", [`Downloading attributes (${percent}%)`, false, progress.loaded / progress.total]);
            return;
        }
        updateProgress("Metadata", ["Downloading attributes", false, null]);
    });
    updateProgress("Metadata", ["Ready", true, 1]);
}

export async function checkForComponentLibraryUpdate() {
    try {
        const [localManifest, remoteManifest] = await Promise.all([
            getLocalManifest(),
            fetchRemoteManifest()
        ]);
        if (!localManifest) {
            return true;
        }
        return localManifest.version !== remoteManifest.version ||
            localManifest.created !== remoteManifest.created;
    } catch (error) {
        console.warn(error);
        return false;
    }
}

export async function queryComponents({ categoryIds, allCategories, searchString, checkAbort, onProgress }) {
    const manifest = await getLocalManifest();
    if (!manifest) {
        return [];
    }

    if (allCategories && searchString.trim().length < 3) {
        return [];
    }

    const words = splitSearchWords(searchString);
    if (allCategories && words.length > 0 && manifest.searchIndex) {
        const searchIndexFile = manifest.searchIndexFormat === "tsv-v1"
            ? selectSearchIndexFile(manifest, words)
            : { file: manifest.searchIndex };
        const progress = createFileProgressReporter(
            onProgress, "Scanning search index", [searchIndexFile.file]
        );
        const matchesByShard = manifest.searchIndexFormat === "tsv-v1"
            ? await collectTsvSearchIndexMatches(
                searchIndexFile, words, checkAbort, progress.fileProgress(searchIndexFile.file)
            )
            : await collectJsonSearchIndexMatches(
                manifest, words, checkAbort, progress.fileProgress(searchIndexFile.file)
            );
        progress.fileFinished(searchIndexFile.file);
        if (matchesByShard === null) {
            return null;
        }
        return await queryComponentsFromMatches(manifest, matchesByShard, checkAbort, onProgress);
    }

    const selectedCategories = new Set(categoryIds || []);
    const shardNames = [];
    for (const category of manifest.categories) {
        if (allCategories || selectedCategories.has(category.id)) {
            shardNames.push(...(category.browseShards ?? category.shards));
        }
    }
    if (shardNames.length === 0) {
        return [];
    }

    const attributeLut = await ensureJsonFile(manifest.attributesLut);
    const uniqueShardNames = Array.from(new Set(shardNames));
    const progress = createFileProgressReporter(onProgress, "Performing component query", uniqueShardNames);
    const shardResults = await mapConcurrent(uniqueShardNames, SHARD_LOAD_CONCURRENCY, async shardName => {
        const results = [];
        let schema = null;
        const aborted = await streamJsonLines(shardName, (row, idx) => {
            if (idx === 0) {
                schema = row;
                return;
            }
            if (textMatchesSearch(componentRowText(row, schema), words)) {
                results.push(decodeComponentRow(row, schema, attributeLut));
            }
            if (checkAbort?.()) {
                return 'abort';
            }
        }, checkAbort, progress.fileProgress(shardName));
        progress.fileFinished(shardName);
        if (aborted) {
            return null;
        }
        return results;
    });
    if (shardResults === null || checkAbort?.()) {
        return null;
    }
    return shardResults.flat();
}

function lookupFileForLcsc(manifest, lcsc) {
    const numeric = Number.parseInt(lcsc.slice(1), 10);
    if (!Number.isFinite(numeric)) {
        return null;
    }
    const bucket = Math.floor(numeric / manifest.lookupBucketSize);
    return manifest.lookupBuckets[String(bucket)] ?? null;
}

export async function getComponentByLcsc(lcsc) {
    const manifest = await getLocalManifest();
    if (!manifest) {
        return undefined;
    }

    const lookupFile = lookupFileForLcsc(manifest, lcsc);
    if (!lookupFile) {
        return undefined;
    }

    const lookup = await ensureJsonFile(lookupFile);
    const shardName = lookup[lcsc];
    if (!shardName) {
        return undefined;
    }

    const attributeLut = await ensureJsonFile(manifest.attributesLut);
    let schema = null;
    let found = undefined;
    await streamJsonLines(shardName, (row, idx) => {
        if (idx === 0) {
            schema = row;
            return;
        }
        if (row[schema.lcsc] !== lcsc) {
            return;
        }
        found = decodeComponentRow(row, schema, attributeLut);
        return 'abort';
    });
    return found;
}

export async function getComponentsByLcscList(lcscList, onProgress) {
    const manifest = await getLocalManifest();
    if (!manifest) {
        return { components: [], missing: lcscList };
    }

    const requested = Array.from(new Set(lcscList));
    const lookupFiles = new Map();
    for (const lcsc of requested) {
        const lookupFile = lookupFileForLcsc(manifest, lcsc);
        if (!lookupFile) {
            continue;
        }
        if (!lookupFiles.has(lookupFile)) {
            lookupFiles.set(lookupFile, []);
        }
        lookupFiles.get(lookupFile).push(lcsc);
    }

    const matchesByShard = new Map();
    const missing = new Set(requested);
    const lookupFileNames = Array.from(lookupFiles.keys());
    const lookupProgress = createFileProgressReporter(onProgress, "Loading part lookup", lookupFileNames);
    for (const [lookupFile, lcscs] of lookupFiles) {
        const lookup = await ensureJsonFile(lookupFile, lookupProgress.fileProgress(lookupFile));
        lookupProgress.fileFinished(lookupFile);
        for (const lcsc of lcscs) {
            const shardName = lookup[lcsc];
            if (!shardName) {
                continue;
            }
            if (!matchesByShard.has(shardName)) {
                matchesByShard.set(shardName, new Set());
            }
            matchesByShard.get(shardName).add(lcsc);
        }
    }

    if (matchesByShard.size === 0) {
        return { components: [], missing: requested };
    }

    const components = await queryComponentsFromMatches(
        manifest, matchesByShard, undefined, onProgress
    );
    for (const component of components) {
        missing.delete(component.lcsc);
    }

    const componentByLcsc = new Map(components.map(component => [component.lcsc, component]));
    return {
        components: requested
            .map(lcsc => componentByLcsc.get(lcsc))
            .filter(component => component !== undefined),
        missing: requested.filter(lcsc => missing.has(lcsc)),
    };
}
