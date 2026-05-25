import { naturalCompare } from '@discoveryjs/natural-compare';

// Return comparator for given quantity
export function quantityComparator(quantityName) {
    const numericQuantities = [
        "resistance", "voltage", "current", "power", "count", "capacitance",
        "length", "inductance", "temperature", "charge", "frequency",
        "percentage", "ppm", "time", "data_rate", "luminous_intensity", "radiant_intensity", "energy",
        "voltage_noise_density", "voltage_temperature_drift", "temperature_coefficient", "decibel", "decibel_milliwatt", "ratio", "kelvin", "angle",
        "data_size", "melting_i2t", "slew_rate", "area_mm2", "awg", "magnetic_flux_density", "lsb"
    ];
    if (numericQuantities.includes(quantityName))
        return numericComparator;
    return naturalCompare;
}

// Return formatter for given quantity
export function quantityFormatter(quantityName) {
    const formatters = {
        resistance: resistanceFormatter,
        voltage: siFormatter("V"),
        current: siFormatter("A"),
        power: siFormatter("W"),
        energy: siFormatter("J"),
        decibel: x => x === "NaN" ? "-" : `${x} dB`,
        decibel_milliwatt: x => x === "NaN" ? "-" : `${x} dBm`,
        ratio: x => x === "NaN" ? "-" : String(x),
        capacitance: siFormatter("F"),
        frequency: siFormatter("Hz"),
        data_rate: siFormatter("bps"),
        slew_rate: siFormatter("V/s"),
        data_size: dataSizeFormatter,
        melting_i2t: siFormatter("A²s"),
        area_mm2: x => x === "NaN" ? "-" : `${x} mm²`,
        luminous_intensity: siFormatter("cd"),
        radiant_intensity: siFormatter("W/sr"),
        voltage_noise_density: siFormatter("V/√Hz"),
        voltage_temperature_drift: siFormatter("V/°C"),
        temperature_coefficient: x => x === "NaN" ? "-" : `${x} ppm/°C`,
        lsb: x => x === "NaN" ? "-" : `${x} LSB`,
        awg: awgFormatter,
        magnetic_flux_density: siFormatter("T"),
        length: siFormatter("m"),
        inductance: siFormatter("H"),
        charge: siFormatter("C"),
        percentage: x => x === "NaN" ? "-" : `${x} %`,
        ppm: x => x === "NaN" ? "-" : `${x} ppm`,
        time: siFormatter("s"),
        count: x => String(x),
        temperature: x => `${x} °C`,
        kelvin: x => x === "NaN" ? "-" : `${x} K`,
        angle: x => x === "NaN" ? "-" : `${x}°`
    };

    let formatter = formatters[quantityName];
    if (formatter)
        return formatter
    return x => String(x);
}

function numericComparator(a, b) {
    if (a === "NaN")
        a = undefined;
    if (b === "NaN")
        b = undefined;
    if (a === undefined && b === undefined)
        return 0;
    if (a === undefined)
        return 1;
    if (b === undefined)
        return -1;

    return a - b;
}

function removeTrailingChar(str, charToRemove) {
    while(str.endsWith(charToRemove)) {
        str = str.slice(0, -1);
    }
    return str;
}


// Format values like 1u6, 1k6, 1M9
function infixMagnitudeFormatter(value, letter, order) {
    value = value / order;
    let integralPart = Math.floor(value);
    let fractionalPart = (value - integralPart) * 1000; // Number of significant digits
    let fractionalPartStr = removeTrailingChar(fractionalPart.toFixed(0).padStart(3, '0'), '0')

    return String(integralPart) + letter + fractionalPartStr;
}

function siFormatterImpl(value, unit) {
    if (value === "NaN")
        return "-";
    if (value === 0)
        return "0 " + unit;
    let prefixes = [
        { magnitude: 1e-12, prefix: "p" },
        { magnitude: 1e-9, prefix: "n" },
        { magnitude: 1e-6, prefix: "μ" },
        { magnitude: 1e-3, prefix: "m" },
        { magnitude: 1, prefix: "" },
        { magnitude: 1e3, prefix: "k" },
        { magnitude: 1e6, prefix: "M" },
        { magnitude: 1e9, prefix: "G" }
    ];
    // Choose prefix to use
    let prefix;
    for (var idx = 0; idx < prefixes.length; idx++) {
        if (idx === prefixes.length - 1 || Math.abs(value) < prefixes[idx + 1].magnitude) {
            prefix = prefixes[idx];
            break;
        }
    }

    return (value / prefix.magnitude)
                .toFixed(6)
                .replace(/0*$/,'')
                .replace(/[.,]$/,'') + " " + prefix.prefix + unit;
}

function siFormatter(unit) {
    return value => siFormatterImpl(value, unit);
}

function dataSizeFormatter(value) {
    if (value === "NaN")
        return "-";
    let units = [
        { magnitude: 1024 * 1024 * 1024, unit: "GB" },
        { magnitude: 1024 * 1024, unit: "MB" },
        { magnitude: 1024, unit: "KB" },
        { magnitude: 1, unit: "B" }
    ];
    for (let idx = 0; idx < units.length; idx++) {
        let candidate = units[idx];
        if (Math.abs(value) >= candidate.magnitude || candidate.magnitude === 1) {
            return (value / candidate.magnitude)
                .toFixed(6)
                .replace(/0*$/,'')
                .replace(/[.,]$/,'') + " " + candidate.unit;
        }
    }
}

function awgFormatter(value) {
    if (value === "NaN")
        return "-";
    if (Number.isInteger(value) && value <= 0)
        return `${1 - value}/0 AWG`;
    return `${value} AWG`;
}

function resistanceFormatter(resistance) {
    if (resistance === "NaN")
        return "-"
    if (resistance === 0)
        return "0R";
    if (resistance < 1) {
        return (resistance * 1000).toFixed(6).replace(/0*$/,'').replace(/[.,]$/,'') + "mR";
    }
    if (resistance < 1e3) {
        // Format with R, e.g., 1R 5R6
        return infixMagnitudeFormatter(resistance, "R", 1);
    }
    if (resistance < 1e6) {
        // Format with k, e.g, 3k3 56k
        return infixMagnitudeFormatter(resistance, "k", 1e3);
    }
    if (resistance < 1e9) {
        // Format with M, e.g., 1M, 5M6
        return infixMagnitudeFormatter(resistance, "M", 1e6);
    }
    // Format with G
    return infixMagnitudeFormatter(resistance, "G", 1e9);
}
