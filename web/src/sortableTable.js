import React, { useEffect, useMemo, useState } from 'react';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { Waypoint } from 'react-waypoint';


function SortableHeaderField(props) {
    var sortIcons;
    var className = "bg-blue-500 mx-1 p-2 border-r-2 rounded"
    if (props.sortable) {
        className += " cursor-pointer"
        let icon = "sort";
        if (props.sortDirection === "asc")
            icon = "sort-amount-up";
        if (props.sortDirection === "desc")
            icon = "sort-amount-down";
        sortIcons = <FontAwesomeIcon icon={icon}/>
    } else {
        sortIcons = null;
    }

    return <>
        <th onClick={() => props.onClick()} className={className}>
            <div className="w-full flex">
                <div className="flex-1">
                    {props.header}
                    {sortIcons}
                </div>
                {
                    props.onDelete && (
                        <div className="flex-none" onClick={e => {
                            e.stopPropagation();
                            props.onDelete();
                        }}>
                            <FontAwesomeIcon icon="times-circle"/>
                        </div>
                    )
                }
            </div>
        </th>
    </>
}

export function SortableTable(props) {
    const [sortBy, setSortBy] = useState(null);
    const [sortDirection, setSortDirection] = useState("asc");
    const [visibleItems, setVisibleItems] = useState(100);

    useEffect(() => {
        setVisibleItems(100);
    }, [props.data]);

    const handleHeaderClick = name => {
        if (sortBy === name) {
            setSortDirection(current => current === "asc" ? "desc" : "asc");
        }
        else {
            setSortBy(name);
            setSortDirection("asc");
        }
    };

    const showMore = () => {
        setVisibleItems(current => current < props.data.length ? current + 50 : current);
    };

    const sortedData = useMemo(() => {
        var t0 = performance.now()
        var sortedData = [...props.data];
        if (sortBy) {
            let pureComparator = props.header.find(obj => obj.name === sortBy)?.comparator;
            let comparator;
            if (sortDirection === "desc")
                comparator = (a, b) => - pureComparator(a, b);
            else
                comparator = pureComparator;

            if (comparator)
                sortedData.sort(comparator);
        }
        var t1 = performance.now()
        console.log("Sorting took " + (t1 - t0) + " milliseconds.")
        return sortedData;
    }, [props.data, props.header, sortBy, sortDirection]);

    const visibleData = sortedData.slice(0, visibleItems);
    return <>
        <table className={props.className}>
            <thead className="sticky top-0 bg-white">
                <tr>{
                    props.header.map( x => {
                        let activeSortDirection = null;
                        if (sortBy === x.name)
                            activeSortDirection = sortDirection;
                        return <SortableHeaderField
                                    key={x.name}
                                    header={x.name}
                                    sortable={x.sortable}
                                    onClick={() => handleHeaderClick(x.name)}
                                    sortDirection={activeSortDirection}
                                    onDelete={x.onDelete}/>;
                    })
                }</tr>
            </thead>
            <tbody>{
                visibleData.map((row, index) => {
                    let className = props.rowClassName ?? "";
                    if ( index % 2 === 0 )
                        className += " " + (props.evenRowClassName ?? "");
                    else
                        className += " " + (props.oddRowClassName ?? "");
                    return <ExpandableTableRow className={className}
                                              key={props.keyFun(row)}
                                              expandableContent={props.expandableContent(row)}>
                            {
                                props.header.map(cell => {
                                    return <td key={cell.name} className={cell.className}>
                                        { cell.displayGetter(row) }
                                    </td>
                                })
                            }
                        </ExpandableTableRow>
                })
            }</tbody>
        </table>
        {
            visibleItems < props.data.length && (
                <p className="w-full text-center m-4">Loading more components...</p>
            )
        }
        <Waypoint key="tableEnd" onEnter={showMore}/>
    </>
}

function ExpandableTableRow(props) {
    const [expanded, setExpanded] = useState(false);

    const handleClick = (e) => {
        e.preventDefault();
        setExpanded(current => !current);
    };

    let expandableContent = null;
    let className = props.className ?? "";
    if (expanded && props.expandableContent) {
        expandableContent = <tr>
                <td colSpan={React.Children.count(props.children)}>
                    {props.expandableContent}
                </td>
            </tr>;
    }
    if (props.expandableContent)
        className += " cursor-pointer";
    return <>
        <tr className={className} onClick={handleClick}>
            {props.children}
        </tr>
        {expandableContent}
    </>
}
