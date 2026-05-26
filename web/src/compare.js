import React, { useEffect, useMemo, useState } from 'react';
import { BooleanParam, StringParam, useQueryParams } from 'use-query-params';
import { CopyToClipboard } from 'react-copy-to-clipboard';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { naturalCompare } from '@discoveryjs/natural-compare';

import { getCategories, getComponentsByLcscList, subscribeToComponentLibraryChanges } from './db';
import { getQuantityPrice } from './jlc';
import { SortableTable } from './sortableTable';
import {
    ExpandedComponent,
    ZoomableLazyImage,
    attributeComparator,
    findCategoryById,
    formatAttribute,
    getImageUrl,
    restoreLcscUrl,
} from './componentTable';

const CompareQueryParams = {
    parts: StringParam,
    order: BooleanParam,
};

function normalizeLcsc(value) {
    const lcsc = value.match(/C\d+/i)?.[0];
    if (lcsc) {
        return lcsc.toUpperCase();
    }
    if (/^\d+$/.test(value)) {
        return `C${value}`;
    }
    return null;
}

function parseLcscList(text) {
    const parts = [];
    const invalid = [];
    const seen = new Set();
    const tokens = text
        .split(/[\s,;]+/)
        .map(token => token.trim())
        .filter(Boolean);

    for (const token of tokens) {
        const lcsc = normalizeLcsc(token);
        if (!lcsc) {
            invalid.push(token);
            continue;
        }
        if (!seen.has(lcsc)) {
            seen.add(lcsc);
            parts.push(lcsc);
        }
    }

    return { parts, invalid };
}

function displayPrice(price, quantity) {
    if (price === undefined) {
        return "Not available";
    }
    const unitPrice = Math.round((price + Number.EPSILON) * 1000) / 1000;
    const sumPrice = Math.round((price * quantity + Number.EPSILON) * 1000) / 1000;
    return <>
        {`${unitPrice}$/unit`}
        <br/>
        {`${sumPrice}$/${quantity} units`}
    </>;
}

function attributeFootprint(component, attribute) {
    return JSON.stringify(component.attributes?.[attribute] ?? null);
}

function collectDifferingAttributes(components) {
    const attributes = new Set();
    for (const component of components) {
        for (const attribute of Object.keys(component.attributes ?? {})) {
            attributes.add(attribute);
        }
    }
    return Array.from(attributes)
        .filter(attribute => {
            const values = new Set(components.map(component => attributeFootprint(component, attribute)));
            return values.size > 1;
        })
        .sort((a, b) => a.localeCompare(b));
}

function CompareProgress({ progress }) {
    if (!progress) {
        return null;
    }
    const width = Math.max(0, Math.min(100, (progress.progress ?? 0) * 100));
    return <div className="p-2">
        <div className="flex text-sm">
            <span>{progress.phase}</span>
            <span className="ml-auto">
                {progress.filesDone ?? 0}/{progress.filesTotal ?? 0} files
            </span>
        </div>
        <div className="w-full bg-gray-300 mt-1 h-2">
            <div className="bg-blue-500 h-2" style={{width: `${width}%`}}></div>
        </div>
    </div>;
}

export function CompareParts() {
    const [query, setQuery] = useQueryParams(CompareQueryParams);
    const initialParts = query.parts ?? "";
    const [input, setInput] = useState(initialParts);
    const [components, setComponents] = useState([]);
    const [missing, setMissing] = useState([]);
    const [categories, setCategories] = useState([]);
    const [loaded, setLoaded] = useState(false);
    const [progress, setProgress] = useState(null);
    const [quantity, setQuantity] = useState(1);
    const [stockRequired, setStockRequired] = useState(false);
    const [tableAttributes, setTableAttributes] = useState([]);
    const keepOrder = query.order !== false;

    const parsedInput = useMemo(() => parseLcscList(input), [input]);

    useEffect(() => {
        let cancelled = false;
        const loadCategories = () => getCategories().then(nextCategories => {
            if (!cancelled) {
                setCategories(nextCategories);
            }
        });
        const unsubscribe = subscribeToComponentLibraryChanges(loadCategories);
        loadCategories();
        return () => {
            cancelled = true;
            unsubscribe();
        };
    }, []);

    useEffect(() => {
        setInput(query.parts ?? "");
    }, [query.parts]);

    useEffect(() => {
        const { parts } = parseLcscList(query.parts ?? "");
        let cancelled = false;
        if (parts.length === 0) {
            setComponents([]);
            setMissing([]);
            setLoaded(false);
            setProgress(null);
            return () => {
                cancelled = true;
            };
        }

        setLoaded(false);
        setProgress(null);
        getComponentsByLcscList(parts, nextProgress => {
            if (!cancelled) {
                setProgress(nextProgress);
            }
        }).then(({components: foundComponents, missing: missingComponents}) => {
            if (cancelled) {
                return;
            }
            const orderedComponents = keepOrder
                ? foundComponents
                : [...foundComponents].sort((a, b) => naturalCompare(a.lcsc, b.lcsc));
            setComponents(orderedComponents);
            setMissing(missingComponents);
            setLoaded(true);
            setProgress(null);
        });
        return () => {
            cancelled = true;
        };
    }, [query.parts, keepOrder]);

    const handleCompare = () => {
        const parts = parsedInput.parts;
        setQuery({
            parts: parts.length > 0 ? parts.join(",") : undefined,
            order: keepOrder ? undefined : false,
        }, "pushIn");
    };

    const handleKeepOrderChange = checked => {
        setQuery({
            order: checked ? undefined : false,
        }, "pushIn");
    };

    const differingAttributes = useMemo(
        () => collectDifferingAttributes(components),
        [components]
    );

    const visibleComponents = stockRequired
        ? components.filter(component => component.stock >= quantity)
        : components;

    const addDifferingAttributes = () => {
        setTableAttributes(differingAttributes);
    };

    const removeAttribute = attribute => {
        setTableAttributes(tableAttributes.filter(item => item !== attribute));
    };

    const addAttribute = attribute => {
        if (!tableAttributes.includes(attribute)) {
            setTableAttributes([...tableAttributes, attribute]);
        }
    };

    const availableAttributes = useMemo(
        () => collectDifferingAttributes(components)
            .filter(attribute => !tableAttributes.includes(attribute)),
        [components, tableAttributes]
    );

    const header = [
        {
            name: "LCSC",
            sortable: true,
            className: "px-1 whitespace-no-wrap text-center",
            displayGetter: component => <>
                <CopyToClipboard text={component.lcsc}>
                    <button className="py-2 px-4 pl-1" onClick={event => event.stopPropagation()}>
                        <FontAwesomeIcon icon="clipboard"/>
                    </button>
                </CopyToClipboard>
                <a href={restoreLcscUrl(component.url, component.lcsc)}
                    className="underline text-blue-600"
                    onClick={event => event.stopPropagation()}
                    target="_blank"
                    rel="noopener noreferrer">
                        {component.lcsc}
                </a>
            </>,
            comparator: (a, b) => naturalCompare(a.lcsc, b.lcsc)
        },
        {
            name: "MFR",
            sortable: true,
            displayGetter: component => component.datasheet ? (
                <a
                    href={component.datasheet}
                    className="underline text-blue-600"
                    onClick={event => event.stopPropagation()}
                    target="_blank"
                    rel="noopener noreferrer">
                        <FontAwesomeIcon icon="file-pdf"/> {component.mfr}
                </a>
            ) : component.mfr,
            comparator: (a, b) => naturalCompare(a.mfr, b.mfr),
            className: "px-1 whitespace-no-wrap"
        },
        {
            name: "Image",
            sortable: false,
            displayGetter: component => {
                const imgSrc = getImageUrl(component.img, "small") ?? "./brokenimage.svg";
                const zoomImgSrc = getImageUrl(component.img, "big") ?? "./brokenimage.svg";
                return <ZoomableLazyImage
                    height={90}
                    width={90}
                    src={imgSrc}
                    zoomWidth={450}
                    zoomHeight={450}
                    zoomSrc={zoomImgSrc}/>;
            }
        },
        {
            name: "Description",
            sortable: true,
            displayGetter: component => component.description,
            comparator: (a, b) => a.description.localeCompare(b.description)
        },
        {
            name: "Category",
            sortable: true,
            displayGetter: component => {
                const category = findCategoryById(categories, component.category);
                return `${category.category}: ${category.subcategory}`;
            },
            comparator: (a, b) => {
                const categoryA = findCategoryById(categories, a.category);
                const categoryB = findCategoryById(categories, b.category);
                return `${categoryA.category}: ${categoryA.subcategory}`
                    .localeCompare(`${categoryB.category}: ${categoryB.subcategory}`);
            }
        },
        {
            name: "Stock",
            sortable: true,
            displayGetter: component => component.stock,
            comparator: (a, b) => a.stock - b.stock
        },
        {
            name: "Price",
            sortable: true,
            displayGetter: component => displayPrice(getQuantityPrice(quantity, component.price), quantity),
            comparator: (a, b) => {
                const aPrice = getQuantityPrice(quantity, a.price);
                const bPrice = getQuantityPrice(quantity, b.price);
                if (aPrice === undefined && bPrice === undefined) {
                    return 0;
                }
                if (aPrice === undefined) {
                    return 1;
                }
                if (bPrice === undefined) {
                    return -1;
                }
                return aPrice - bPrice;
            }
        },
    ];

    for (const attribute of tableAttributes) {
        header.push({
            name: attribute,
            sortable: true,
            displayGetter: component => formatAttribute(component.attributes[attribute]),
            comparator: (a, b) => attributeComparator(a.attributes[attribute], b.attributes[attribute]),
            onDelete: () => removeAttribute(attribute),
            className: "text-center"
        });
    }

    return <div className="w-full bg-gray-200 p-2">
        <h3 className="block w-full text-lg mx-2 font-bold">
            Compare LCSC parts
        </h3>
        <div className="p-2">
            <textarea
                className="block w-full bg-white appearance-none border-2 border-gray-500 rounded py-2 px-3 text-gray-700 leading-tight focus:outline-none focus:bg-white focus:border-blue-500"
                rows={5}
                placeholder="Paste LCSC numbers, one per line or separated by commas"
                value={input}
                onChange={event => setInput(event.target.value)}/>
            <div className="flex flex-wrap items-center mt-2 gap-2">
                <button className="bg-blue-500 hover:bg-blue-700 text-black py-1 px-2 rounded" onClick={handleCompare}>
                    Compare {parsedInput.parts.length} parts
                </button>
                <label className="inline-flex items-center">
                    <input
                        className="mr-2 leading-tight"
                        type="checkbox"
                        checked={keepOrder}
                        onChange={event => handleKeepOrderChange(event.target.checked)}/>
                    Keep pasted order
                </label>
                <label className="inline-flex items-center ml-auto">
                    Quantity:
                    <input
                        type="number"
                        min={1}
                        className="ml-2 w-24 bg-white appearance-none border-2 border-gray-500 rounded py-1 px-2 text-gray-700"
                        value={quantity}
                        onChange={event => setQuantity(Math.max(1, Number(event.target.value) || 1))}/>
                </label>
                <label className="inline-flex items-center">
                    <input
                        className="mr-2 leading-tight"
                        type="checkbox"
                        checked={stockRequired}
                        onChange={event => setStockRequired(event.target.checked)}/>
                    Require stock
                </label>
            </div>
            {parsedInput.invalid.length > 0
                ? <p className="mt-2 text-red-700">
                    Ignored invalid entries: {parsedInput.invalid.join(", ")}
                </p>
                : null}
            {parsedInput.parts.length > 0
                ? <div className="flex flex-wrap mt-2">
                    {parsedInput.parts.slice(0, 80).map(lcsc =>
                        <span key={lcsc} className="inline-block bg-gray-300 rounded px-2 py-1 mr-1 mb-1 text-sm">
                            {lcsc}
                        </span>
                    )}
                    {parsedInput.parts.length > 80
                        ? <span className="inline-block px-2 py-1 text-sm">
                            and {parsedInput.parts.length - 80} more
                        </span>
                        : null}
                </div>
                : null}
        </div>
        <CompareProgress progress={progress}/>
        {loaded
            ? <div className="p-2">
                <p>
                    Found {components.length} of {parseLcscList(query.parts ?? "").parts.length} parts.
                    {missing.length > 0 ? ` Missing: ${missing.join(", ")}` : ""}
                </p>
            </div>
            : null}
        {components.length > 0
            ? <>
                <div className="flex flex-wrap items-center p-2 gap-2">
                    <button className="bg-blue-500 hover:bg-blue-700 text-black py-1 px-2 rounded" onClick={addDifferingAttributes}>
                        Show all differing properties ({differingAttributes.length})
                    </button>
                    <button className="bg-blue-500 hover:bg-blue-700 text-black py-1 px-2 rounded" onClick={() => setTableAttributes([])}>
                        Clear property columns
                    </button>
                    {availableAttributes.length > 0
                        ? <select
                            className="bg-white border-2 border-gray-500 rounded py-1 px-2"
                            value=""
                            onChange={event => {
                                if (event.target.value) {
                                    addAttribute(event.target.value);
                                }
                            }}>
                            <option value="">Add property column...</option>
                            {availableAttributes.map(attribute =>
                                <option key={attribute} value={attribute}>{attribute}</option>
                            )}
                        </select>
                        : null}
                </div>
                <div className="pt-4" id="results">
                    <div className="w-full flex py-2">
                        <p className="flex-none p-2">Compared components: {visibleComponents.length}</p>
                    </div>
                    <SortableTable
                        className="w-full"
                        headerClassName="bg-blue-500"
                        header={header}
                        data={visibleComponents}
                        evenRowClassName="bg-gray-100"
                        oddRowClassName="bg-gray-300"
                        keyFun={item => item.lcsc}
                        expandableContent={component =>
                            <ExpandedComponent
                                component={component}
                                categories={categories}
                                componentQuantity={quantity}/>}/>
                </div>
            </>
            : loaded
            ? <div className="p-8 text-center text-lg">
                No requested parts were found in the local component database.
            </div>
            : null}
    </div>;
}
