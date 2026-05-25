import React from "react";

export function getQuantityPrice(quantity, pricelist) {
    return pricelist.find(pricepoint =>
        quantity >= pricepoint.qFrom && (quantity <= pricepoint.qTo || !pricepoint.qTo)
    )?.price ?? pricelist[0]?.price;
}

function attributeRawValue(attribute) {
    if (!attribute?.values) {
        return undefined;
    }
    const valueKey = attribute.primary ?? attribute.default ?? Object.keys(attribute.values)[0];
    return attribute.values[valueKey]?.[0];
}

function attributeNumber(component, name) {
    const value = attributeRawValue(component.attributes?.[name]);
    if (value === undefined || value === null || value === "NaN") {
        return undefined;
    }
    const number = Number(value);
    return Number.isFinite(number) ? number : undefined;
}

export class AttritionInfo extends React.Component {
    constructor(props) {
        super(props);
        this.props = props;
    }

    price() {
        const data = this.attritionData();
        let q = Math.max(parseInt(this.props.quantity) + (data.lossNumber ?? 0),
            data.leastNumber ?? 0);
        const unitPrice = getQuantityPrice(q, this.props.component.price);
        return unitPrice === undefined ? undefined : q * unitPrice;
    }

    attritionData() {
        const component = this.props.component;
        return {
            lossNumber: attributeNumber(component, "Attrition"),
            leastNumber: attributeNumber(component, "Minimum Order Quantity"),
        };
    }

    render() {
        let data = this.attritionData();
        if (data.lossNumber === undefined && data.leastNumber === undefined) {
            return <div className="bg-yellow-400 p-2 mt-2">
                No attrition data available in this component database.
            </div>
        }
        data.lossNumber ??= 0;
        data.leastNumber ??= 0;
        const price = this.price();
        return <table className="w-full">
                <tbody>
                { data.lossNumber > 0
                    ? <tr>
                        <td className="w-1 whitespace-no-wrap">Attrition:</td>
                        <td className="px-2">{data.lossNumber} pcs</td>
                      </tr>
                    : ""
                }
                { data.leastNumber > 0
                    ? <tr>
                        <td className="w-1 whitespace-no-wrap">Minimal order quantity:</td>
                        <td className="px-2">{data.leastNumber} pcs</td>
                      </tr>
                    : ""
                }
                <tr>
                    <td className="w-1 whitespace-no-wrap">Price for {this.props.quantity} pcs:</td>
                    <td className="px-2">
                        {price === undefined
                            ? "Not available"
                            : `${Math.round((price + Number.EPSILON) * 1000) / 1000} USD`}
                    </td>
                </tr>
                </tbody>
            </table>
    }
}
