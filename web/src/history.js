import React, { useEffect, useState } from 'react';
import { fetchJson, getCategories, getComponentByLcsc } from './db'
import { Spinbox, InlineSpinbox, ZoomableLazyImage,
         formatAttribute, findCategoryById, getImageUrl,
         restoreLcscUrl } from './componentTable'
import { getQuantityPrice } from './jlc'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'

export function History(props) {
    return <div className="bg-gray-200 p-2">
        <HistoryTable/>
    </div>
}

function HistoryItem({ categories, lcsc }) {
    const [info, setInfo] = useState();
    const [loaded, setLoaded] = useState(false);

    useEffect(() => {
        let cancelled = false;
        setInfo(undefined);
        setLoaded(false);
        getComponentByLcsc(lcsc).then(component => {
            if (!cancelled) {
                setInfo(component);
                setLoaded(true);
            }
        });
        return () => {
            cancelled = true;
        };
    }, [lcsc]);

    if (info !== undefined) {
        let price = getQuantityPrice(1, info.price)
        let unitPrice = Math.round((price + Number.EPSILON) * 1000) / 1000;
        let category = findCategoryById(categories, info.category);
        const imgSrc = getImageUrl(info.img, "small") ?? "./brokenimage.svg";
        return <tr>
            <td className="text-left pl-2">
                <a href={restoreLcscUrl(info.url, info.lcsc)}
                    className="underline text-blue-600"
                    onClick={e => e.stopPropagation()}
                    target="_blank"
                    rel="noopener noreferrer">
                        {info.lcsc}
                </a>
            </td>
            <td className="text-left">
                <a
                    href={info.datasheet}
                    onClick={e => e.stopPropagation()}
                    target="_blank"
                    rel="noopener noreferrer">
                        <FontAwesomeIcon icon="file-pdf"/> {info.mfr}
                </a>
            </td>
            <td className="text-center">
                {formatAttribute(info.attributes["Basic/Extended"])[0]}
            </td>
            <td className="text-center">
                <ZoomableLazyImage
                    height={90}
                    width={90}
                    src={imgSrc}
                    zoomWidth={350}
                    zoomHeight={350}
                    zoomSrc={imgSrc}/>
            </td>
            <td className="text-left">
                {info.description}
            </td>
            <td className="text-left">
                {category.category}: {category.subcategory}
            </td>
            <td className="text-left">
                {`${unitPrice}$/unit`}
            </td>
            <td className="text-right pr-2">
                {info.stock}
            </td>
        </tr>
    }

    if (loaded) {
        return <tr className="text-center">
            <td className="text-left pl-2">
                {lcsc}
            </td>
            <td className="" colSpan={7}>
                Component is missing in database. Do you use the latest database?
            </td>
        </tr>
    }

    return <tr className="text-center">
        <td className="text-left pl-2">
            {lcsc}
        </td>
        <td className="" colSpan={7}>
            <InlineSpinbox/>
        </td>
    </tr>
}

function DayTable(props) {
    return <table className="w-full bg-white p-2 mb-4">
        <thead className="bg-white">
            <tr>{
                ["LCSC", "MFR", "Basic/Extended", "Image", "Description",
                 "Category", "Price", "Stock"].map( label => {
                    return <th key={label} className="bg-blue-500 mx-1 p-2 border-r-2 rounded">
                        {label}
                    </th>
                })
            }</tr>
        </thead>
        <tbody>
            {
                props.components.map(
                    lcsc =>
                        <HistoryItem
                        key={lcsc}
                        lcsc={lcsc}
                        categories={props.categories}/>)
            }
        </tbody>
    </table>
}

function HistoryTable() {
    const [table, setTable] = useState();
    const [categories, setCategories] = useState();

    useEffect(() => {
        let cancelled = false;
        fetchJson(process.env.PUBLIC_URL + "/data/changelog.json")
            .then(response => {
                let log = [];
                for (const day in response) {
                    log.push({
                        day: new Date(day),
                        components: response[day]
                    });
                }
                log.sort((a, b) => b.day - a.day);
                if (!cancelled)
                    setTable(log);
            })
            .catch(() => {
                if (!cancelled)
                    setTable([]);
            });
        getCategories().then(categories => {
            if (!cancelled)
                setCategories(categories);
        });
        return () => {
            cancelled = true;
        };
    }, []);

    if (table === undefined) {
        return <Spinbox/>
    }
    return table.map(item => {
        if (item.components.length === 0)
            return null;
        let day = item.day;
        return <div key={item.day}>
            <h2 className="w-full text-lg font-bold mt-6">
                Newly added components on {day.getDate()}. {day.getMonth() + 1}. {day.getFullYear()}:
            </h2>
            <DayTable
                components={item.components}
                categories={categories}
                />
        </div>
    });
}
