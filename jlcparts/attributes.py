import re
import sys
import math

# This module tries to parse LSCS attribute strings into structured data The
# whole process is messy and there is no strong guarantee it will work in all
# cases: there are lots of inconsistencies and typos in the attributes. So we
# try to deliver best effort results

def erase(string, what):
    """
    Given a  string and a list of string, removes all occurences of items from
    what in the string
    """
    for x in what:
        string = string.replace(x, "")
    return string

def stringAttribute(value, name="default"):
    return {
        "format": "${" + name +"}",
        "primary": name,
        "values": {
            name: [value, "string"]
        }
    }

def readWithSiPrefix(value):
    """
    Given a string in format <number><unitPrefix> (without the actual unit),
    read its value. E.g., 10k ~> 10000, 10m ~> 0.01
    """
    value = value.strip()
    if value == "-" or value == "" or value == "null":
        return "NaN"
    unitPrexies = {
        "f": 1e-15,
        "p": 1e-12,
        "n": 1e-9,
        "u": 1e-6,
        "U": 1e-6,
        "μ": 1e-6,
        "µ": 1e-6,
        "?": 1e-3, # There is a common typo instead of 'm' there is '?' - the keys are close on keyboard
        "m": 1e-3,
        "k": 1e3,
        "K": 1e3,
        "M": 1e6,
        "G": 1e9
    }
    if value[-1].isalpha() or value[-1] == "?": # Again, watch for the ? typo
        return float(value[:-1]) * unitPrexies[value[-1]]
    return float(value)

def readResistance(value):
    """
    Given a string, try to parse resistance and return it as Ohms (float)
    """
    value = value.split("@")[0]
    value = erase(value, ["Ω", "Ohms", "Ohm", "(Max)", "Max"]).strip()
    value = value.replace(" ", "") # Sometimes there are spaces after decimal place
    unitPrefixes = {
        "m": [1e-3, 1e-6],
        "K": [1e3, 1],
        "k": [1e3, 1],
        "M": [1e6, 1e3],
        "G": [1e9, 1e6]
    }
    for prefix, table in unitPrefixes.items():
        if prefix in value:
            split = [float(x) if x != "" else 0 for x in value.split(prefix)]
            value = split[0] * table[0] + split[1] * table[1]
            break
    if value == "-" or value == "" or value == "null":
        value = "NaN"
    else:
        value = float(value)
    return value

def readCurrent(value):
    """
    Given a string, try to parse current and return it as Amperes (float)
    """
    value = erase(value, ["PNP"])
    value = value.split("@")[0]
    value = re.sub(r"([0-9.])a\b", r"\1A", value)
    value = re.sub(r"([0-9])\.A\b", r"\1A", value)
    value = value.replace("A", "").strip()
    value = value.split("..")[-1] # Some transistors give a range for current in Rds
    if value in ["-", "--"] or "null" in value:
        return "NaN"
    v = readWithSiPrefix(value)
    return v

def readVoltage(value):
    value = value.replace("v", "V")
    value = value.replace("V-", "V")
    value = value.replace("VDC", "V").replace("VAC", "V")
    value = re.sub(r"\bV(?:DS|GS)\s*=\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\b(?:AC|DC)\s*", "", value, flags=re.IGNORECASE)
    value = value.replace("V", "").strip()
    if value in ["-", "--"] or "null" in value:
        return "NaN"
    return readWithSiPrefix(value)

def readVoltageNoiseDensity(value):
    value = value.strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    value = value.split("@", 1)[0]
    value = re.sub(r"/\s*(?:√Hz|sqrt\s*Hz)$", "", value, flags=re.I).strip()
    return readVoltage(value)

def readVoltageTemperatureDrift(value):
    value = value.strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    value = re.sub(r"/\s*(?:℃|°C|C)$", "", value, flags=re.I).strip()
    return readVoltage(value)

def readTemperatureCoefficient(value):
    value = value.strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    value = value.replace("±", "").replace("+", "")
    ppb = re.search(r"ppb\s*/?\s*(?:℃|°C|K)?$", value, flags=re.I)
    value = re.sub(r"pp[mb]\s*/?\s*(?:℃|°C|K)?", "", value, flags=re.I).strip()
    coefficient = float(value)
    if ppb:
        return coefficient / 1000
    return coefficient

def readPpm(value):
    value = value.strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    value = re.sub(r"ppm(?:p-p)?$", "", value, flags=re.I).strip()
    return float(value)

def readPower(value):
    """
    Parse power value (in watts), it can also handle fractions
    """
    if value in ["-", "--"] or "null" in value:
        return "NaN"
    if ";" in value:
        return readPower(value.split(";")[0])
    if "/" in value:
        # Fraction
        numerator, denominator, unit = re.fullmatch(r"(\d+)/(\d+)\s*(\w+)", value).groups()
        value = str(float(numerator) / float(denominator)) + unit
    value = value.replace("W", "").strip()
    return readWithSiPrefix(value)

def readEnergy(value):
    value = value.strip()
    if value in ["-", "--"] or "null" in value:
        return "NaN"
    value = value.replace("J", "").strip()
    return readWithSiPrefix(value)

def readCapacitance(value):
    value = value.replace("F", "").strip()
    if value in ["-", "--"] or "null" in value:
        return "NaN"
    return readWithSiPrefix(value)

def readCharge(value):
    value = value.replace("C", "").strip()
    return readWithSiPrefix(value)

def readFrequency(value):
    if value.strip().upper() == "DC":
        return 0
    value = re.sub(r"hz$", "", value.strip(), flags=re.IGNORECASE)
    value = erase(value, ["H"]).strip()
    return readWithSiPrefix(value)

def readDataRate(value):
    value = value.strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    value = re.sub(r"(?:bit/s|bps)$", "", value, flags=re.IGNORECASE)
    value = erase(value, ["Hz", "HZ", "H"]).strip()
    value = re.sub(r"([0-9.])([kmg])$", lambda m: m.group(1) + m.group(2).upper(), value)
    return readWithSiPrefix(value)

def readSlewRate(value):
    value = value.strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    value = value.replace("µ", "u").replace("μ", "u")
    match = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)\s*((?:m|u)?V)\s*/\s*(ns|us|ms|s)", value, re.I)
    if match is None:
        raise ValueError(f"Cannot parse slew rate {value}")
    number = float(match.group(1))
    voltage_unit = match.group(2).lower()
    time_unit = match.group(3).lower()
    voltage_scales = {
        "uv": 1e-6,
        "mv": 1e-3,
        "v": 1,
    }
    time_scales = {
        "ns": 1e-9,
        "us": 1e-6,
        "ms": 1e-3,
        "s": 1,
    }
    return number * voltage_scales[voltage_unit] / time_scales[time_unit]

def readInductance(value):
    value = value.replace("H", "").strip()
    return readWithSiPrefix(value)

def readLuminousIntensity(value):
    value = value.strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    value = re.sub(r"cd$", "", value, flags=re.IGNORECASE).strip()
    return readWithSiPrefix(value)

def readRadiantIntensity(value):
    value = value.strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    value = re.sub(r"/\s*sr$", "", value, flags=re.IGNORECASE).strip()
    return readPower(value)

def readLength(value):
    value = value.strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    parenthesizedMetric = re.search(r"\(([^)]*(?:nm|um|mm|cm|m|mil|in|inch|inches))\)", value, re.I)
    if parenthesizedMetric is not None:
        value = parenthesizedMetric.group(1)
    elif value.endswith("'"):
        return float(value[:-1]) * 0.3048
    value = value.replace("µ", "u").replace("μ", "u")
    match = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)\s*(nm|um|mm|cm|m|mil|in|inch|inches)?", value, re.I)
    if match is None:
        raise ValueError(f"Cannot parse length {value}")
    number = float(match.group(1))
    unit = (match.group(2) or "m").lower()
    scales = {
        "nm": 1e-9,
        "um": 1e-6,
        "mm": 1e-3,
        "cm": 1e-2,
        "m": 1,
        "mil": 25.4e-6,
        "in": 0.0254,
        "inch": 0.0254,
        "inches": 0.0254,
    }
    return number * scales[unit]

def readSquareMillimeter(value):
    value = value.strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    return float(value)

def readAwg(value):
    value = value.strip()
    if value in ["-", "--", "null", "~"]:
        return "NaN"
    aught = re.fullmatch(r"(\d+)/0", value)
    if aught is not None:
        return 1 - int(aught.group(1))
    return float(value)

def readMagneticFluxDensity(value):
    value = value.strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    match = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)\s*(mT|Gs)", value, re.I)
    if match is None:
        raise ValueError(f"Cannot parse magnetic flux density {value}")
    number = float(match.group(1))
    unit = match.group(2).lower()
    scales = {
        "mt": 1e-3,
        "gs": 1e-4,
    }
    return number * scales[unit]

def readTime(value):
    value = value.strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    value = value.replace("µ", "u").replace("μ", "u")
    match = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)\s*(ps|ns|us|ms|s|sec|secs|min|mins|h|hr|hrs|hour|hours)?", value, re.I)
    if match is None:
        raise ValueError(f"Cannot parse time {value}")
    number = float(match.group(1))
    unit = (match.group(2) or "s").lower()
    scales = {
        "ps": 1e-12,
        "ns": 1e-9,
        "us": 1e-6,
        "ms": 1e-3,
        "s": 1,
        "sec": 1,
        "secs": 1,
        "min": 60,
        "mins": 60,
        "h": 3600,
        "hr": 3600,
        "hrs": 3600,
        "hour": 3600,
        "hours": 3600,
    }
    return number * scales[unit]

def readKelvin(value):
    value = value.strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    match = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)\s*K", value, re.I)
    if match is None:
        raise ValueError(f"Cannot parse kelvin value {value}")
    return float(match.group(1))

def readAngle(value):
    value = value.strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    value = value.replace("±", "")
    value = value.replace("°", "")
    return float(value)

def readDataSize(value):
    value = value.strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    match = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)\s*(Byte|B|KB|MB)", value, re.I)
    if match is None:
        raise ValueError(f"Cannot parse data size {value}")
    number = float(match.group(1))
    unit = match.group(2).lower()
    scales = {
        "byte": 1,
        "b": 1,
        "kb": 1024,
        "mb": 1024 * 1024,
    }
    return number * scales[unit]

def readMeltingI2t(value):
    value = value.strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    return float(value)

def readLsb(value):
    value = value.strip().replace("±", "")
    if value in ["-", "--", "null"]:
        return "NaN"
    value = re.sub(r"LSB$", "", value, flags=re.I).strip()
    if "/" in value:
        numerator, denominator = value.split("/", 1)
        return float(numerator) / float(denominator)
    return float(value)

def readPercentage(value):
    value = value.strip().replace("±", "")
    if value in ["-", "--", "null"]:
        return "NaN"
    if "/" in value:
        numerator, denominator = value.split("/", 1)
        return float(numerator) / float(denominator) * 100
    if value.endswith("%"):
        value = value[:-1]
    return float(value)

def readEfficiencyPercentage(value):
    value = value.strip()
    if value.endswith("%") or value in ["-", "--", "null"]:
        return readPercentage(value)
    parsed = readPercentage(value)
    if parsed != "NaN" and 0 <= parsed <= 1:
        return parsed * 100
    return parsed

def readDecibel(value):
    value = value.strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    value = re.sub(r"dB(?:i|ic)?$", "", value, flags=re.IGNORECASE).strip()
    return float(value)

def readDecibelMilliwatt(value):
    value = value.strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    value = re.sub(r"dBm$", "", value, flags=re.IGNORECASE).strip()
    return float(value)

def _stripCondition(value):
    return value.split("@", 1)[0].strip()

def _hasCompoundValues(value):
    return any(separator in value for separator in [",", ";"])

def _rangeParts(value):
    value = value.strip()
    value = re.sub(r"\(.*?\)", "", value)
    value = value.replace(" to ", "~")
    if "..." in value:
        return value.split("...", 1)
    if ".." in value:
        return value.split("..", 1)
    if "~" in value:
        return value.split("~", 1)
    if re.match(r"^\s*DC\s*-\s*", value, flags=re.IGNORECASE):
        return re.split(r"\s*-\s*", value, 1)
    dcSuffix = re.match(r"^\s*(.*?)\s+DC\s*$", value, flags=re.IGNORECASE)
    if dcSuffix is not None:
        return ["DC", dcSuffix.group(1)]
    if re.search(r"\d\s*-\s*\d", value):
        return re.split(r"\s*-\s*", value, 1)
    return None

def scalarAttribute(value, reader, unit, name="value"):
    value = str(value)
    parsed = reader(_stripCondition(value))
    return {
        "format": "${" + name + "}",
        "primary": name,
        "values": {
            name: [parsed, unit]
        }
    }

def scalarListAttribute(value, reader, unit, name="value"):
    value = str(value)
    parts = [x.strip() for x in value.split(",")]
    values = {}
    for i, part in enumerate(parts, start=1):
        values[f"{name} {i}"] = [reader(_stripCondition(part)), unit]
    return {
        "format": ", ".join("${" + f"{name} {i}" + "}" for i in range(1, len(parts) + 1)),
        "primary": f"{name} 1",
        "values": values
    }

def rangeOrScalarAttribute(value, reader, unit, name="value"):
    value = str(value)
    if value in ["-", "--", "null"]:
        return scalarAttribute(value, reader, unit, name)
    parts = _rangeParts(value)
    if parts is None:
        return scalarAttribute(value, reader, unit, name)
    if _hasCompoundValues(value):
        raise ValueError(f"Compound value cannot be represented as scalar range: {value}")
    low, high = parts
    low = _stripCondition(low)
    high = _stripCondition(high)
    return {
        "format": "${" + name + " min} ~ ${" + name + " max}",
        "primary": name + " min",
        "values": {
            name + " min": [reader(low), unit],
            name + " max": [reader(high), unit]
        }
    }

def resistanceAttribute(value):
    if ";" in value:
        # This is a resistor array
        values = value.split(value)
        values = [readResistance(x.strip()) for x in values]
        values = { "resistance" + (str(i + 1) if i != 0 else ""): [x, "resistance"] for i, x in enumerate(values)}
        format = ", ".join(values.keys())
        return {
            "format": format,
            "primary": "resistance",
            "values": values
        }
    else:
        value = readResistance(value)
        return {
            "format": "${resistance}",
            "primary": "resistance",
            "values": {
                "resistance": [value, "resistance"]
            }
        }

def resistanceListAttribute(value):
    value = str(value).replace(";", ",")
    return scalarListAttribute(value, readResistance, "resistance", "resistance")

def impedanceAttribute(value):
    value = readResistance(value)
    return {
        "format": "${impedance}",
        "primary": "impedance",
        "values": {
            "impedance": [value, "resistance"]
        }
    }


def voltageAttribute(value):
    value = str(value)
    value = re.sub(r"\(.*?\)", "", value)
     # Remove multiple current values
    value = value.split("x")[-1]
    value = value.split("/")[-1]
    value = value.split(",")[-1]
    value = value.split("~")[-1]
    value = value.split("or")[-1]
    value = value.split("@")[0]
    value = value.replace("VIN", "V").replace("Vin", "V")
    value = value.replace("VDC", "V").replace("VAC", "V")
    value = value.replace("Vdc", "V").replace("Vac", "V")
    value = value.replace("AC:", "").replace("DC:", "")
    value = re.sub(r"\bDC\s+", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\bAC\s+", "", value, flags=re.IGNORECASE)
    value = value.replace("X1:", "")
    value = value.replace("A", "V") # Common typo
    value = erase(value, "±")
    value = re.sub(";.*", "", value)

    if value.strip() in ["-", "Tracking", "nV"]:
        value = "NaN"
    else:
        value = readVoltage(value)
    return {
        "format": "${voltage}",
        "primary": "voltage",
        "values": {
            "voltage": [value, "voltage"]
        }
    }

def currentAttribute(value):
    value = str(value)
    if value.lower().strip() == "adjustable":
        return {
            "format": "${current}",
            "default": "current",
            "values": {
                "current": ["NaN", "current"]
            }
        }
    if ";" in value:
        values = value.split(value)
        values = [readCurrent(x.strip()) for x in values]
        values = { "current" + (str(i + 1) if i != 0 else ""): [x, "current"] for i, x in enumerate(values)}
        format = ", ".join(values.keys())
        return {
            "format": format,
            "primary": "current",
            "values": values
        }
    else:
        value = erase(value, ["±", "Up to"])
        value = re.sub(r"\(.*?\)", "", value)
        value = value.split("@")[0]
        # Remove multiple current values
        value = value.split("x")[-1]
        value = value.split("/")[-1]
        value = value.split(",")[-1]
        value = value.split("~")[-1]
        value = value.split("or")[-1]
        # Replace V/A typo
        value = value.replace("V", "A")
        value = readCurrent(value)
        return {
            "format": "${current}",
            "primary": "current",
            "values": {
                "current": [value, "current"]
            }
        }

def powerAttribute(value):
    value = str(value)
    value = re.sub(r"\(.*?\)", "", value)
    # Replace V/W typo
    value = value.replace("V", "W")
    # Strip random additional characters (e.g., C108632)
    value = value.replace("S", "")

    p = readPower(value)
    return {
        "format": "${power}",
        "default": "power",
        "values": {
            "power": [p, "power"]
        }
    }

def countAttribute(value):
    value = str(value)
    if value == "-":
        return {
            "format": "${count}",
            "default": "count",
            "values": {
                "count": ["NaN", "count"]
            }
        }
    value = erase(value, [" - Dual"])
    value = re.sub(r"\(.*?\)", "", value)
    # There are expressions like a+b, so let's sum them
    try:
        count = sum(map(int, value.split("+")))
    except ValueError:
        # Sometimes, there are floats in number of pins... God, why?
        # See, e.g., C2836126
        try:
            count = sum(map(float, value.split("+")))
        except ValueError:
            # And sometimes there is garbage...
            count = "NaN"
    return {
        "format": "${count}",
        "default": "count",
        "values": {
            "count": [count, "count"]
        }
    }

def _readChannelCount(value):
    value = str(value).strip()
    if value in ["-", "--", "null"]:
        return "NaN"

    named_counts = {
        "single": 1,
        "single channel": 1,
        "single port": 1,
        "dual": 2,
        "three channels": 3,
        "four channels": 4,
        "quad": 4,
        "hex": 6,
        "seven channels": 7,
    }
    normalized = value.lower()
    if normalized in named_counts:
        return named_counts[normalized]

    value = re.sub(r"\s*channels?$", "", value, flags=re.I).strip()
    channel_match = re.match(r"^(\d+)C(?:\d+A)?$", value, flags=re.I)
    if channel_match:
        return int(channel_match.group(1))
    return int(value)

def channelCountAttribute(value):
    value = str(value)
    parts = [x.strip() for x in re.split(r"[,;/]", value) if x.strip()]
    if len(parts) <= 1:
        return scalarAttribute(value, _readChannelCount, "count", "count")

    values = {}
    for index, part in enumerate(parts, start=1):
        values[f"count {index}"] = [_readChannelCount(part), "count"]
    return {
        "format": ", ".join("${" + f"count {i}" + "}" for i in range(1, len(parts) + 1)),
        "primary": "count 1",
        "values": values
    }

def lsbListAttribute(value, name="linearity"):
    value = str(value)
    parts = [x.strip() for x in re.split(r"[,;]", value) if x.strip()]
    values = {}
    formats = []
    for index, part in enumerate(parts, start=1):
        quantity = name if len(parts) == 1 else f"{name} {index}"
        if part.endswith("%"):
            parsed = scalarAttribute(part, readPercentage, "percentage", quantity)
        else:
            parsed = scalarAttribute(part, readLsb, "lsb", quantity)
        values.update(parsed["values"])
        formats.append(parsed["format"])
    return {
        "format": ", ".join(formats),
        "primary": next(iter(values)),
        "values": values
    }


def capacitanceAttribute(value):
    value = str(value)
    # There are a handful of components, that feature multiple capacitance
    # values, for the sake of the simplicity, take the last one.
    value = readCapacitance(value.split(";")[-1].split("@")[0].strip())
    return {
        "format": "${capacitance}",
        "primary": "capacitance",
        "values": {
            "capacitance": [value, "capacitance"]
        }
    }

def capacitanceListAttribute(value):
    value = str(value).replace(";", ",")
    return scalarListAttribute(value, readCapacitance, "capacitance", "capacitance")

def inductanceAttribute(value):
    value = str(value)
    value = readInductance(value)
    return {
        "format": "${inductance}",
        "primary": "inductance",
        "values": {
            "inductance": [value, "inductance"]
        }
    }

def frequencyAttribute(value):
    value = str(value)
    return rangeOrScalarAttribute(value, readFrequency, "frequency", "frequency")

def frequencyListAttribute(value):
    value = str(value).replace(";", ",")
    return scalarListAttribute(value, readFrequency, "frequency", "frequency")

def frequencyRangeListAttribute(value):
    value = str(value).replace(";", ",")
    parts = [x.strip() for x in value.split(",")]
    values = {}
    formats = []
    for i, part in enumerate(parts, start=1):
        parsed = rangeOrScalarAttribute(part, readFrequency, "frequency", f"frequency {i}")
        values.update(parsed["values"])
        formats.append(parsed["format"])
    return {
        "format": ", ".join(formats),
        "primary": "frequency 1 min" if any(_rangeParts(part) for part in parts) else "frequency 1",
        "values": values
    }

def currentListAttribute(value):
    value = str(value).replace(";", ",")
    return scalarListAttribute(value, readCurrent, "current", "current")

def luminousIntensityAttribute(value):
    value = str(value)
    if "," not in value and ";" not in value and ":" in value:
        value = re.sub(r"\s+([A-Za-z]+:)", r", \1", value)
    separator = ";" if ";" in value else ","
    parts = [x.strip() for x in value.split(separator)]
    values = {}
    formats = []
    for index, part in enumerate(parts, start=1):
        label = str(index)
        if ":" in part:
            label, part = [x.strip() for x in part.split(":", 1)]
        name = f"intensity {label}"
        parsed = rangeOrScalarAttribute(part, readLuminousIntensity, "luminous_intensity", name)
        values.update(parsed["values"])
        formats.append(parsed["format"])
    return {
        "format": ", ".join(formats),
        "primary": next(iter(values)),
        "values": values
    }

def radiantIntensityAttribute(value):
    value = str(value).replace(";", ",")
    parts = [x.strip() for x in value.split(",")]
    values = {}
    formats = []
    for index, part in enumerate(parts, start=1):
        parsed = rangeOrScalarAttribute(
            part,
            readRadiantIntensity,
            "radiant_intensity",
            f"intensity {index}",
        )
        values.update(parsed["values"])
        formats.append(parsed["format"])
    return {
        "format": ", ".join(formats),
        "primary": next(iter(values)),
        "values": values
    }

def voltageNoiseDensityAttribute(value):
    value = str(value).replace(";", ",")
    parts = [
        x.strip()
        for x in re.split(r",(?=\s*[+-]?\d+(?:\.\d+)?\s*[pnumμµ]?V\s*/)", value, flags=re.I)
    ]
    values = {}
    formats = []
    for index, part in enumerate(parts, start=1):
        name = f"density {index}" if len(parts) > 1 else "density"
        parsed = scalarAttribute(part, readVoltageNoiseDensity, "voltage_noise_density", name)
        values.update(parsed["values"])
        formats.append(parsed["format"])
    return {
        "format": ", ".join(formats),
        "primary": next(iter(values)),
        "values": values
    }

def voltageTemperatureDriftAttribute(value):
    value = str(value).replace(";", ",")
    return scalarListAttribute(
        value,
        readVoltageTemperatureDrift,
        "voltage_temperature_drift",
        "drift",
    )

def lowFrequencyNoiseAttribute(value):
    value = str(value).replace(";", ",")
    parts = [x.strip() for x in value.split(",")]
    values = {}
    formats = []
    for index, part in enumerate(parts, start=1):
        suffix = ""
        if part.lower().endswith("p-p"):
            suffix = " p-p"
            part = part[:-3]
        elif part.lower().endswith("rms"):
            suffix = " rms"
            part = part[:-3]
        name = f"noise {index}{suffix}"
        if "ppm" in part.lower():
            parsed = scalarAttribute(part, readPpm, "ppm", name)
        else:
            parsed = scalarAttribute(part, readVoltage, "voltage", name)
        values.update(parsed["values"])
        formats.append(parsed["format"])
    return {
        "format": ", ".join(formats),
        "primary": next(iter(values)),
        "values": values
    }

def _temperatureCoefficientPart(part, name):
    part = part.strip()
    if part in ["-", "--", "null"]:
        return scalarAttribute(part, readTemperatureCoefficient, "temperature_coefficient", name)
    if not re.search(r"pp[mb]", part, flags=re.I):
        return {
            "format": "${" + name + "}",
            "primary": name,
            "values": {
                name: [part, "temperature_coefficient_code"]
            }
        }
    if part.startswith("±"):
        coefficient = readTemperatureCoefficient(part)
        return {
            "format": "${" + name + " min} ~ ${" + name + " max}",
            "primary": name + " min",
            "values": {
                name + " min": [-coefficient, "temperature_coefficient"],
                name + " max": [coefficient, "temperature_coefficient"],
            }
        }
    range_parts = _rangeParts(part)
    if range_parts is not None:
        low, high = range_parts
        return {
            "format": "${" + name + " min} ~ ${" + name + " max}",
            "primary": name + " min",
            "values": {
                name + " min": [readTemperatureCoefficient(low), "temperature_coefficient"],
                name + " max": [readTemperatureCoefficient(high), "temperature_coefficient"],
            }
        }
    return scalarAttribute(part, readTemperatureCoefficient, "temperature_coefficient", name)

def temperatureCoefficientAttribute(value):
    value = str(value).replace(";", ",")
    parts = [x.strip() for x in value.split(",")]
    values = {}
    formats = []
    for index, part in enumerate(parts, start=1):
        name = "coefficient" if len(parts) == 1 else f"coefficient {index}"
        parsed = _temperatureCoefficientPart(part, name)
        values.update(parsed["values"])
        formats.append(parsed["format"])
    return {
        "format": ", ".join(formats),
        "primary": next(iter(values)),
        "values": values
    }

def dataRateAttribute(value):
    value = str(value)
    return rangeOrScalarAttribute(value, readDataRate, "data_rate", "data rate")

def _expandSharedUnitAlternatives(value):
    match = re.fullmatch(
        r"\s*([+-]?\d+(?:\.\d+)?)\s*/\s*([+-]?\d+(?:\.\d+)?)\s*((?:m|u|μ|µ)?V)\s*/\s*(ns|us|μs|µs|ms|s)\s*",
        value,
        re.I,
    )
    if match is None:
        return value
    first, second, voltage_unit, time_unit = match.groups()
    return f"{first}{voltage_unit}/{time_unit}, {second}{voltage_unit}/{time_unit}"

def slewRateAttribute(value):
    value = _expandSharedUnitAlternatives(str(value))
    if "," in value or ";" in value:
        value = value.replace(";", ",")
        return scalarListAttribute(value, readSlewRate, "slew_rate", "slew rate")
    return scalarAttribute(value, readSlewRate, "slew_rate", "slew rate")

def dataSizeAttribute(value):
    return scalarAttribute(value, readDataSize, "data_size", "data size")

def dataSizeListAttribute(value):
    value = str(value).replace(";", ",")
    return scalarListAttribute(value, readDataSize, "data_size", "data size")

def meltingI2tAttribute(value):
    return scalarAttribute(value, readMeltingI2t, "melting_i2t", "melting i2t")

def lengthAttribute(value):
    return rangeOrScalarAttribute(value, readLength, "length", "length")

def pitchAttribute(value):
    value = str(value).strip()
    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?", value):
        value += "mm"
    return lengthAttribute(value)

def lengthRangeListAttribute(value, name="length"):
    value = str(value).replace(";", ",").strip()
    parts = [x.strip() for x in value.split(",")]
    values = {}
    formats = []
    for i, part in enumerate(parts, start=1):
        parsed = rangeOrScalarAttribute(part, readLength, "length", f"{name} {i}")
        values.update(parsed["values"])
        formats.append(parsed["format"])
    return {
        "format": ", ".join(formats),
        "primary": f"{name} 1 min" if any(_rangeParts(part) for part in parts) else f"{name} 1",
        "values": values
    }

def areaMm2RangeListAttribute(value):
    value = str(value).replace(";", ",").strip()
    parts = [x.strip() for x in value.split(",")]
    values = {}
    formats = []
    for index, part in enumerate(parts, start=1):
        parsed = rangeOrScalarAttribute(part, readSquareMillimeter, "area_mm2", f"area {index}")
        values.update(parsed["values"])
        formats.append(parsed["format"])
    return {
        "format": ", ".join(formats),
        "primary": "area 1 min" if any(_rangeParts(part) for part in parts) else "area 1",
        "values": values
    }

def awgRangeListAttribute(value):
    value = str(value).replace(";", ",").strip()
    if value == "~":
        value = "-"
    parts = [x.strip() for x in value.split(",")]
    values = {}
    formats = []
    for index, part in enumerate(parts, start=1):
        parsed = rangeOrScalarAttribute(part, readAwg, "awg", f"awg {index}")
        values.update(parsed["values"])
        formats.append(parsed["format"])
    return {
        "format": ", ".join(formats),
        "primary": "awg 1 min" if any(_rangeParts(part) for part in parts) else "awg 1",
        "values": values
    }

def magneticFluxDensityRangeListAttribute(value):
    value = str(value).replace(";", ",").strip()
    parts = [x.strip() for x in value.split(",")]
    values = {}
    formats = []
    for index, part in enumerate(parts, start=1):
        name = f"field {index}"
        if part.startswith("±"):
            coefficient = readMagneticFluxDensity(part[1:])
            parsed = {
                "format": "${" + name + " min} ~ ${" + name + " max}",
                "primary": name + " min",
                "values": {
                    name + " min": [-coefficient, "magnetic_flux_density"],
                    name + " max": [coefficient, "magnetic_flux_density"],
                }
            }
        else:
            parsed = rangeOrScalarAttribute(
                part,
                readMagneticFluxDensity,
                "magnetic_flux_density",
                name,
            )
        values.update(parsed["values"])
        formats.append(parsed["format"])
    return {
        "format": ", ".join(formats),
        "primary": next(iter(values)),
        "values": values
    }

def opticalLengthRangeListAttribute(value):
    value = str(value).strip()
    parts = [x.strip() for x in re.split(r"[,;]", value)]
    values = {}
    formats = []
    for index, part in enumerate(parts, start=1):
        label = str(index)
        if ":" in part:
            label, part = [x.strip() for x in part.split(":", 1)]
        name = f"wavelength {label}"
        if re.search(r"cd(?:\s*|$)", part, re.I):
            name = f"intensity {label}"
            parsed = scalarAttribute(part, readLuminousIntensity, "luminous_intensity", name)
        else:
            parsed = rangeOrScalarAttribute(part, readLength, "length", name)
        values.update(parsed["values"])
        formats.append(parsed["format"])
    return {
        "format": ", ".join(formats),
        "primary": next(iter(values)),
        "values": values
    }

def wavelengthAttribute(value):
    return rangeOrScalarAttribute(value, readLength, "length", "wavelength")

def timeAttribute(value):
    return rangeOrScalarAttribute(value, readTime, "time", "time")

def timeListAttribute(value):
    value = str(value).replace(";", ",")
    return scalarListAttribute(value, readTime, "time", "time")

def timeAtConditionAttribute(value):
    return scalarAttribute(value, readTime, "time", "time")

def percentageAttribute(value):
    return rangeOrScalarAttribute(value, readPercentage, "percentage", "percentage")

def percentageRangeListAttribute(value):
    value = str(value).replace(";", ",")
    parts = [x.strip() for x in value.split(",")]
    values = {}
    formats = []
    for i, part in enumerate(parts, start=1):
        parsed = rangeOrScalarAttribute(part, readPercentage, "percentage", f"percentage {i}")
        values.update(parsed["values"])
        formats.append(parsed["format"])
    return {
        "format": ", ".join(formats),
        "primary": f"percentage 1 min" if any(_rangeParts(part) for part in parts) else "percentage 1",
        "values": values
    }

def efficiencyPercentageRangeListAttribute(value):
    value = str(value).replace(";", ",")
    parts = [x.strip() for x in value.split(",")]
    values = {}
    formats = []
    for i, part in enumerate(parts, start=1):
        parsed = rangeOrScalarAttribute(part, readEfficiencyPercentage, "percentage", f"percentage {i}")
        values.update(parsed["values"])
        formats.append(parsed["format"])
    return {
        "format": ", ".join(formats),
        "primary": f"percentage 1 min" if any(_rangeParts(part) for part in parts) else "percentage 1",
        "values": values
    }

def temperatureRangeAttribute(value):
    value = str(value).replace("°C", "℃")
    if value.strip() in ["-", "--", "null"]:
        return scalarAttribute("-", lambda x: "NaN", "temperature", "temperature")
    value = erase(value, ["@"])
    value = re.sub(r"\(.*?\)", "", value)
    if _hasCompoundValues(value):
        raise ValueError(f"Compound temperature value cannot be represented as scalar range: {value}")
    if value.strip().startswith("±"):
        value = "-" + value.strip()[1:] + "~+" + value.strip()[1:]
    if "~" in value or ".." in value:
        return rangeOrScalarAttribute(value.replace("℃", ""), lambda x: int(float(x)), "temperature", "temperature")
    value = value.strip()
    if value.endswith("℃"):
        value = value[:-1]
    return scalarAttribute(value, lambda x: int(float(x)), "temperature", "temperature")

def impedanceAtFrequency(value):
    if _hasCompoundValues(str(value)):
        raise ValueError(f"Compound impedance value cannot be represented as scalar tuple: {value}")
    return esr(str(value))

def currentAtConditionAttribute(value, name="current"):
    return scalarAttribute(value, readCurrent, "current", name)

def _withTrailingCurrentUnit(parts):
    unit = None
    for part in parts:
        match = re.search(r"([munpkMKG]?A)\s*$", part)
        if match is not None:
            unit = match.group(1)
            break
    if unit is None:
        return parts
    return [
        part if re.search(r"[A]\s*$", part) else part + unit
        for part in parts
    ]

def currentRangeAttribute(value, name="current"):
    value = str(value).strip()
    if value.startswith("±"):
        value = "-" + value[1:] + "~+" + value[1:]
    return rangeOrScalarAttribute(value, readCurrent, "current", name)

def currentRangeListAttribute(value, name="current"):
    value = str(value).strip()
    if "/" in value and "," not in value and "~" not in value:
        return scalarListAttribute(
            ",".join(_withTrailingCurrentUnit([x.strip() for x in value.split("/")])),
            readCurrent,
            "current",
            name,
        )

    parts = [x.strip() for x in value.split(",")]
    values = {}
    formats = []
    for i, part in enumerate(parts, start=1):
        parsed = currentRangeAttribute(part, f"{name} {i}" if len(parts) > 1 else name)
        values.update(parsed["values"])
        formats.append(parsed["format"])
    primary_name = f"{name} 1" if len(parts) > 1 else name
    return {
        "format": ", ".join(formats),
        "primary": primary_name + " min" if any(_rangeParts(part) or part.startswith("±") for part in parts) else primary_name,
        "values": values
    }

def voltageAtConditionAttribute(value, name="voltage"):
    return scalarAttribute(value, readVoltage, "voltage", name)

def voltageListAttribute(value, name="voltage"):
    value = str(value).replace(";", ",")
    if "/" in value and "," not in value:
        value = re.sub(r"(?<=\dV)/(?=\d)", ",", value)
        value = re.sub(r"(?<=\d)/(?=\d)", ",", value)
    parts = [x.strip() for x in value.split(",")]
    values = {}
    for i, part in enumerate(parts, start=1):
        values[f"{name} {i}"] = [readVoltage(_stripCondition(part)), "voltage"]
    return {
        "format": ", ".join("${" + f"{name} {i}" + "}" for i in range(1, len(parts) + 1)),
        "primary": f"{name} 1",
        "values": values
    }

def voltageRangeAttribute(value, name="voltage"):
    value = str(value).strip()
    if value.startswith("±"):
        value = "-" + value[1:] + "~+" + value[1:]
    return rangeOrScalarAttribute(value, readVoltage, "voltage", name)

def voltageRangeListAttribute(value, name="voltage"):
    value = str(value).strip()
    parts = [x.strip() for x in re.split(r"[,;]", value)]
    values = {}
    formats = []
    for i, part in enumerate(parts, start=1):
        parsed = voltageRangeAttribute(part, f"{name} {i}")
        values.update(parsed["values"])
        formats.append(parsed["format"])
    return {
        "format": ", ".join(formats),
        "primary": f"{name} 1 min" if any(_rangeParts(part) for part in parts) else f"{name} 1",
        "values": values
    }

def labeledVoltageRangeListAttribute(value, name="voltage"):
    value = str(value).strip()
    parts = [x.strip() for x in re.split(r"[,;]", value)]
    values = {}
    formats = []
    range_primary = False
    for index, part in enumerate(parts, start=1):
        label = str(index)
        if ":" in part:
            label, part = [x.strip() for x in part.split(":", 1)]
        parsed = voltageRangeAttribute(part, f"{name} {label}")
        values.update(parsed["values"])
        formats.append(parsed["format"])
        range_primary = range_primary or _rangeParts(part) is not None
    return {
        "format": ", ".join(formats),
        "primary": f"{name} 1 min" if range_primary and "1 min" in values else next(iter(values)),
        "values": values
    }

def powerAtConditionAttribute(value, name="power"):
    return scalarAttribute(value, readPower, "power", name)

def powerListAttribute(value, name="power"):
    value = str(value).replace(";", ",")
    return scalarListAttribute(value, readPower, "power", name)

def energyAttribute(value):
    return scalarAttribute(value, readEnergy, "energy", "energy")

def energyListAttribute(value):
    return scalarListAttribute(value, readEnergy, "energy", "energy")

def decibelListAttribute(value, name="level"):
    value = str(value)
    separator = ";" if ";" in value else ","
    parts = [x.strip() for x in value.split(separator)]
    values = {}
    formats = []
    for i, part in enumerate(parts, start=1):
        signal = part
        frequency = None
        match = re.fullmatch(r"(.*?)@\(?([^)]*)\)?", part)
        if match is not None:
            signal, frequency = match.groups()
        values[f"{name} {i}"] = [readDecibel(signal.strip()), "decibel"]
        formatParts = ["${" + f"{name} {i}" + "}"]
        if frequency:
            try:
                parsedFrequency = rangeOrScalarAttribute(
                    frequency.strip(),
                    readFrequency,
                    "frequency",
                    f"frequency {i}"
                )
                values.update(parsedFrequency["values"])
                formatParts.append("@ " + parsedFrequency["format"])
            except Exception:
                pass
        formats.append(" ".join(formatParts))
    return {
        "format": ", ".join(formats),
        "primary": f"{name} 1",
        "values": values
    }

def decibelTokenListAttribute(value, name="level"):
    value = str(value)
    parts = re.findall(r"[+-]?\d+(?:\.\d+)?\s*dB", value, flags=re.IGNORECASE)
    if not parts and value.strip() in ["-", "--", "null"]:
        parts = [value.strip()]
    values = {}
    for i, part in enumerate(parts, start=1):
        values[f"{name} {i}"] = [readDecibel(part), "decibel"]
    return {
        "format": ", ".join("${" + f"{name} {i}" + "}" for i in range(1, len(parts) + 1)),
        "primary": f"{name} 1",
        "values": values
    }

def decibelMilliwattListAttribute(value, name="level"):
    return scalarListAttribute(value, readDecibelMilliwatt, "decibel_milliwatt", name)

def qAtFrequencyAttribute(value):
    value = str(value)
    parts = [x.strip() for x in value.split(",")]
    values = {}
    formats = []
    for i, part in enumerate(parts, start=1):
        q = part
        frequency = None
        if "@" in part:
            q, frequency = [x.strip() for x in part.split("@", 1)]
        values[f"q {i}"] = [readWithSiPrefix(q), "ratio"]
        formatParts = ["${" + f"q {i}" + "}"]
        if frequency is not None:
            values[f"frequency {i}"] = [readFrequency(frequency), "frequency"]
            formatParts.append("@ ${" + f"frequency {i}" + "}")
        formats.append(" ".join(formatParts))
    return {
        "format": ", ".join(formats),
        "primary": "q 1",
        "values": values
    }

def ratioRangeListAttribute(value, name="ratio"):
    value = str(value).strip()
    if "@" in value:
        value = value.split("@", 1)[0]
    parts = [x.strip() for x in value.split(",")]
    values = {}
    formats = []
    for i, part in enumerate(parts, start=1):
        parsed = rangeOrScalarAttribute(part, readWithSiPrefix, "ratio", f"{name} {i}" if len(parts) > 1 else name)
        values.update(parsed["values"])
        formats.append(parsed["format"])
    primary_name = f"{name} 1" if len(parts) > 1 else name
    return {
        "format": ", ".join(formats),
        "primary": primary_name + " min" if any(_rangeParts(part) for part in parts) else primary_name,
        "values": values
    }

def capacitanceAtConditionAttribute(value, name="capacitance"):
    return scalarAttribute(value, readCapacitance, "capacitance", name)

def capacitanceAtFrequencyAttribute(value):
    value = str(value)
    if "," in value or ";" in value:
        parts = [x.strip() for x in re.split(r"[,;]", value)]
        values = {}
        formats = []
        for i, part in enumerate(parts, start=1):
            parsed = capacitanceAtFrequencyAttribute(part)
            format = parsed["format"]
            for name, parsedValue in parsed["values"].items():
                numberedName = f"{name} {i}"
                values[numberedName] = parsedValue
                format = format.replace("${" + name + "}", "${" + numberedName + "}")
            formats.append(format)
        return {
            "format": ", ".join(formats),
            "primary": "capacitance 1",
            "values": values
        }
    if "@" not in value:
        return scalarAttribute(value, readCapacitance, "capacitance", "capacitance")
    capacitance, frequency = [x.strip() for x in value.split("@", 1)]
    frequency = rangeOrScalarAttribute(frequency, readFrequency, "frequency", "frequency")
    values = {
        "capacitance": [readCapacitance(capacitance), "capacitance"],
    }
    values.update(frequency["values"])
    return {
        "format": "${capacitance} @ " + frequency["format"],
        "primary": "capacitance",
        "values": values
    }

def inductanceAtFrequency(value):
    value = str(value)
    if _hasCompoundValues(value):
        raise ValueError(f"Compound inductance value cannot be represented as scalar tuple: {value}")
    parts = value.split("@", 1)
    inductance = readInductance(parts[0].strip())
    frequency = readFrequency(parts[1].strip()) if len(parts) == 2 else "NaN"
    return {
        "format": "${inductance} @ ${frequency}",
        "primary": "inductance",
        "values": {
            "inductance": [inductance, "inductance"],
            "frequency": [frequency, "frequency"]
        }
    }


def rdsOnMaxAtIdsAtVgs(value):
    """
    Given a string in format "<resistance> @ <current>, <voltage>" parse it and
    return it as structured value
    """
    def readRds(v):
        if v == "-":
            return "NaN", "NaN", "NaN"
        matched = re.fullmatch(r"([\w.]*)\s*[@\s]\s*([-\w.]*)\s*[,，]\s*([-~\w.]*)").groups()
        # There are some transistors with a typo; using "A" instead of "V" or Ω, fix it:
        resistance = matched.group(1).replace("A", "Ω")
        voltage = matched.group(3).replace("A", "V")
        if "~" in voltage:
            voltage = voltage.split("~")[-1]
        return (readResistance(resistance),
                readCurrent(matched.group(2)),
                readVoltage(voltage))
    if value.count(",") == 3 or ";" in value:
        # Double P & N MOSFET
        if ";" in value:
            s = value.split(";")
        else:
            s = value.split(",")
            s = [s[0] + "," + s[1], s[2] + "," + s[3]]
        rds1, id1, vgs1 = readRds(s[0])
        rds2, id2, vgs2 = readRds(s[1])
        return {
            "format": "${Rds 1} @ ${Id 1}, ${Vgs 1}; ${Rds 2} @ ${Id 2}, ${Vgs 2}",
            "primary": "Rds 1",
            "values": {
                "Rds 2": [rds2, "resistance"],
                "Id 2": [id2, "current"],
                "Vgs 2": [vgs2, "voltage"],
                "Rds 1": [rds1, "resistance"],
                "Id 1": [id1, "current"],
                "Vgs 1": [vgs1, "voltage"]
            }
        }
    else:
        rds, ids, vgs = readRds(value)
        return {
            "format": "${Rds} @ ${Id}, ${Vgs}",
            "primary": "Rds",
            "values": {
                "Rds": [rds, "resistance"],
                "Id": [ids, "current"],
                "Vgs": [vgs, "voltage"]
            }
        }

def rdsOnMaxAtVgsAtIds(value):
    """
    Given a string in format "<resistance> @ <voltage>, <current>" parse it and
    return it as structured value
    """
    def readRds(v):
        if v == "-":
            return "NaN", "NaN", "NaN"
        v = v.strip()
        if "@" in v:
            resistance, condition = v.split("@", 1)
            condition = condition.strip().lstrip("=").strip()
            if "," in condition or "，" in condition:
                voltage, current = re.split(r"[,，]", condition, 1)
            else:
                voltage, current = condition, None
        else:
            match = re.fullmatch(
                    r"\s*([\w.Ω]+)\s*(?:\s+([-+~\w.]+?)\s*(?:(?<=\d)([.\w]+)\s*)?)?",
                    v,
                    re.I
                )
            if match is None:
                raise ValueError(f"Cannot parse RDS tuple {v}")
            resistance, voltage, current = match.groups()

        resistance = resistance.strip()
        voltage = voltage.strip() if voltage is not None else "-"
        current = current.strip() if current is not None else "-"
        if current == "" or "·" in current:
            current = "-"

        if not current.endswith("A"):
            if current.endswith("V"):
                if voltage.endswith("A") or voltage.endswith("m"):
                    # There are sometimes swapped values
                    current, voltage = voltage, current
                else:
                    current = current.replace("V", "A")
            else:
                current += "A"
        if voltage.endswith("A"):
            voltage = voltage.replace("A", "V")
        if "~" in voltage:
            voltage = voltage.split("~")[-1]
        return (readResistance(resistance),
                readCurrent(current),
                readVoltage(voltage))
    if value.count(",") == 3 or ";" in value:
        # Double P & N MOSFET
        if ";" in value:
            s = value.split(";")
        else:
            s = value.split(",")
            s = [s[0] + "," + s[1], s[2] + "," + s[3]]
        rds1, id1, vgs1 = readRds(s[0])
        rds2, id2, vgs2 = readRds(s[1])
        return {
            "format": "${Rds 1} @ ${Vgs 1}, ${Id 1}; ${Rds 2} @ ${Vgs 2}, ${Id 2}",
            "primary": "Rds 1",
            "values": {
                "Rds 2": [rds2, "resistance"],
                "Id 2": [id2, "current"],
                "Vgs 2": [vgs2, "voltage"],
                "Rds 1": [rds1, "resistance"],
                "Id 1": [id1, "current"],
                "Vgs 1": [vgs1, "voltage"]
            }
        }
    else:
        rds, ids, vgs = readRds(value)
        return {
            "format": "${Rds} @ ${Vgs}, ${Id}",
            "primary": "Rds",
            "values": {
                "Rds": [rds, "resistance"],
                "Id": [ids, "current"],
                "Vgs": [vgs, "voltage"]
            }
        }


def rdsMeasurementsAtVgs(value):
    """
    Parse one or more RDS(on) measurements in the form "Rds@Vgs" or bare "Rds".
    """
    value = str(value).replace(";", ",")
    parts = [x.strip() for x in value.split(",")]
    values = {}
    formats = []
    for i, part in enumerate(parts, start=1):
        if "@" in part:
            resistance, voltage = part.split("@", 1)
            voltage = voltage.strip().lstrip("=").strip()
        else:
            resistance = part
            voltage = "-"
        values[f"Rds {i}"] = [readResistance(resistance.strip()), "resistance"]
        values[f"Vgs {i}"] = [readVoltage(voltage), "voltage"]
        formats.append("${Rds " + str(i) + "} @ ${Vgs " + str(i) + "}")
    return {
        "format": ", ".join(formats),
        "primary": "Rds 1",
        "values": values
    }


def continuousTransistorCurrent(value, symbol):
    """
    Can parse values like '10A', '10A,12A', '1OA(Tc)'
    """
    value = re.sub(r"\(.*?\)", "", value) # Remove all notes about temperature
    value = erase(value, ["±"])
    value = value.replace("V", "A") # There are some typos - voltage instead of current
    value = value.replace(";", ",") # Sometimes semicolon is used instead of comma
    value = re.sub(r"(?<=\d)/(?=\d)", ",", value) # Slash can separate P/N MOSFET currents
    if "," in value:
        # Double P & N MOSFET
        s = value.split(",")
        i1 = readCurrent(s[0])
        i2 = readCurrent(s[1])
        return {
            "format": "${" + symbol + " 1}, ${" + symbol + " 2}",
            "default": symbol + " 1",
            "values": {
                symbol + " 1": [i1, "current"],
                symbol + " 2": [i2, "current"]
            }
        }
    else:
        i = readCurrent(value)
        return {
            "format": "${" + symbol + "}",
            "default": symbol,
            "values": {
                symbol: [i, "current"]
            }
        }

def drainToSourceVoltage(value):
    """
    Can parse single or double voltage values"
    """
    value = value.replace("A", "V") # There are some typos - current instead of voltage
    if "," in value:
        s = value.split(",")
        v1 = readVoltage(s[0])
        v2 = readVoltage(s[1])
        return {
            "format": "${Vds 1}, ${Vds 2}",
            "default": "Vds 1",
            "values": {
                "Vds 1": [v1, "voltage"],
                "Vds 2": [v2, "voltage"]
            }
        }
    else:
        v = readVoltage(value)
        return {
            "format": "${Vds}",
            "default": "Vds",
            "values": {
                "Vds": [v, "voltage"]
            }
        }

def powerDissipation(value):
    """
    Parse single or double power dissipation into structured value
    """
    value = re.sub(r"\(.*?\)", "", value) # Remove all notes about temperature
    value = value.replace("V", "W") # Common typo
    if "A" in value:
        # The value is a clear nonsense
        return {
            "format": "${power}",
            "default": "power",
            "values": {
                "power": ["NaN", "power"]
            }
        }
    value = value.split("/")[-1] # When there are multiple thermal ratings for
        # transistors, choose the last as it is the most interesting one
    if "," in value:
        s = value.split(",")
        p1 = readPower(s[0])
        p2 = readPower(s[1])
        return {
            "format": "${power 1}, ${power 2}",
            "default": "power 1",
            "values": {
                "power 1": [p1, "power"],
                "power 2": [p2, "power"]
            }
        }
    else:
        p = readPower(value)
        return {
            "format": "${power}",
            "default": "power",
            "values": {
                "power": [p, "power"]
            }
        }

def vgsThreshold(value):
    """
    Parse single or double value in format '<voltage> @ <current>'
    """
    def readVgs(v):
        v = v.strip()
        if value == "-":
            return "NaN", "NaN"
        voltage, current = re.match(r"([-\w.]*)(?:[@| ]([-\w.]*))?", v).groups()
        if current is None:
            current = "-"
        if current.endswith("V"):
            current = "-"
        return readVoltage(voltage), readCurrent(current)

    value = re.sub(r"\(.*?\)", "", value)
    if "," in value or ";" in value:
        splitchar = "," if "," in value else ";"
        s = value.split(splitchar)
        v1, i1 = readVgs(s[0])
        v2, i2 = readVgs(s[1])
        return {
            "format": "${Vgs 1} @ ${Id 1}, ${Vgs 2} @ ${Id 2}",
            "default": "Vgs 1",
            "values": {
                "Vgs 1": [v1, "voltage"],
                "Id 1": [i1, "current"],
                "Vgs 2": [v2, "voltage"],
                "Id 2": [i2, "current"]
            }
        }
    else:
        v, i = readVgs(value)
        return {
            "format": "${Vgs} @ ${Id}",
            "default": "Vgs",
            "values": {
                "Vgs": [v, "voltage"],
                "Id": [i, "current"]
            }
        }

def esr(value):
    """
    Parse equivalent series resistance in the form '<resistance> @ <frequency>'
    """
    if value == "-":
        return {
            "format": "-",
            "default": "esr",
            "values": {
                "esr": ["NaN", "resistance"],
                "frequency": ["NaN", "frequency"]
            }
        }
    value = erase(value, ["(", ")"]) # For resonators, the value is enclosed in parenthesis
    matches = re.fullmatch(r"([\w.]*)\s*(?:[@\s]\s*([~\w.]*))?[.,]?", value)
    res = readResistance(matches.group(1))
    if matches.group(2):
        freq = readFrequency(matches.group(2).split('~')[-1])
        return {
            "format": "${esr} @ ${frequency}",
            "default": "esr",
            "values": {
                "esr": [res, "resistance"],
                "frequency": [freq, "frequency"]
            }
        }
    else:
        return {
            "format": "${esr}",
            "default": "esr",
            "values": {
                "esr": [res, "resistance"]
            }
        }

def rippleCurrent(value):
    if value == "-":
        return {
            "format": "-",
            "default": "current",
            "values": {
                "current": ["NaN", "current"],
                "frequency": ["NaN", "frequency"]
            }
        }
    if value.endswith("-"): # Work around for trailing trash
        value = value[:-1]
    s = value.split("@")
    if len(s) == 1:
        s = value.split(" ")
    i = readCurrent(s[0])
    if len(s) > 1:
        f = readFrequency(s[1].split("~")[-1])
    else:
        f = "NaN"
    return {
        "format": "${current} @ ${frequency}",
        "default": "current",
        "values": {
            "current": [i, "current"],
            "frequency": [f, "frequency"]
        }
    }

def sizeMm(value):
    if value == "-":
        return {
            "format": "-",
            "default": "width",
            "values": {
                "width": ["NaN", "length"],
                "height": ["NaN", "length"]
            }
        }
    value = value.lower()
    s = value.split("x")
    w = float(s[0]) / 1000
    h = float(s[1]) / 1000
    return {
        "format": "${width}×${height}",
        "default": "width",
        "values": {
            "width": [w, "length"],
            "height": [h, "length"]
        }
    }

def forwardVoltage(value):
    if value == "-":
        return {
            "format": "-",
            "default": "Vf",
            "values": {
                "Vf": ["NaN", "voltage"],
                "If": ["NaN", "current"]
            }
        }
    value = erase(value, ["<"])
    value = re.sub(r"\(.*?\)", "", value)
    s = value.split("@")

    vStr = s[0].replace("A", "V") # Common typo
    v = readVoltage(vStr)
    i = readCurrent(s[1].replace("pk", "").replace("PK", "")) if len(s) > 1 else "NaN"
    return {
        "format": "${Vf} @ ${If}",
        "default": "Vf",
        "values": {
            "Vf": [v, "voltage"],
            "If": [i, "current"]
        }
    }

def removeColor(string):
    """
    If there is a color name in the string, remove it
    """
    return erase(string, ["Red", "Green", "Blue", "Orange", "Yellow"])

def voltageRange(value):
    if value == "-":
        return {
            "format": "-",
            "default": "Vmin",
            "values": {
                "Vmin": ["NaN", "voltage"],
                "Vmax": ["NaN", "voltage"]
            }
        }
    value = re.sub(r"\(.*?\)", "", value)
    value = value.replace("A", "V") # Common typo
    value = value.split(",")[0].split(";")[0] # In the case of multivalue range
    if ".." in value:
        s = value.split("..")
    elif "-" in value:
        s = value.split("-")
    else:
        s = value.split("~")
    s = [removeColor(x) for x in s] # Something there is the color in the attributes
    vMin = s[0].split(",")[0].split("/")[0]
    vMin = readVoltage(vMin)
    if len(s) == 2:
        return {
            "format": "${Vmin} ~ ${Vmax}",
            "default": "Vmin",
            "values": {
                "Vmin": [vMin, "voltage"],
                "Vmax": [readVoltage(s[1]), "voltage"]
            }
        }
    return {
            "format": "${Vmin}",
            "default": "Vmin",
            "values": {
                "Vmin": [vMin, "voltage"]
            }
        }

def clampingVoltage(value):
    if value == "-":
        return {
            "format": "-",
            "default": "Vc",
            "values": {
                "Vc": ["NaN", "voltage"],
                "Ic": ["NaN", "current"]
            }
        }
    value = re.sub(r"\(.*?\)", "", value)
    s = value.split("@")
    vC = s[0].split(",")[0].split("/")[0].split(";")[0]
    vC = vC.replace("A", "V") # Common typo
    vC = readVoltage(vC)
    if len(s) == 2 and s[1].strip().lower() not in ["typ", "typ.", "typical"]:
        c = s[1].replace("V", "A") # Common typo
        return {
            "format": "${Vc} @ ${Ic}",
            "default": "Vc",
            "values": {
                "Vc": [vC, "voltage"],
                "Ic": [readCurrent(c), "current"]
            }
        }
    return {
            "format": "${Vc}",
            "default": "Vc",
            "values": {
                "Vc": [vC, "voltage"]
            }
        }

def vceBreakdown(value):
    value = erase(value, "PNP").split(",")[0]
    return voltageAttribute(value)

def vceOnMax(value):
    matched = re.match(r"(.*)@(.*),(.*)", value)
    if matched:
        vce = readVoltage(matched.group(1))
        vge = readVoltage(matched.group(2))
        ic = readCurrent(matched.group(3))
    else:
        vce = "NaN"
        vge = "NaN"
        ic = "NaN"
    return {
        "format": "${Vce} @ ${Vge}, ${Ic}",
        "default": "Vce",
        "values": {
            "Vce": [vce, "voltage"],
            "Vge": [vge, "voltage"],
            "Ic": [ic, "current"]
        }
    }

def temperatureAttribute(value):
    if value == "-":
        return {
            "format": "-",
            "default": "temperature",
            "values": {
                "temperature": ["NaN", "temperature"]
            }
        }
    value = erase(value, ["@"])
    value = re.sub(r"\(.*?\)", "", value)
    value = value.strip()
    assert value.endswith("℃")
    value = erase(value, ["℃"])
    v = int(value)
    return {
        "format": "${temperature}",
        "default": "temperature",
        "values": {
            "temperature": [v, "temperature"]
        }
    }

def kelvinAttribute(value):
    return scalarAttribute(value, readKelvin, "kelvin", "temperature")

def kelvinRangeListAttribute(value):
    value = str(value).replace(";", ",").strip()
    parts = [x.strip() for x in value.split(",")]
    values = {}
    formats = []
    for index, part in enumerate(parts, start=1):
        parsed = rangeOrScalarAttribute(part, readKelvin, "kelvin", f"temperature {index}")
        values.update(parsed["values"])
        formats.append(parsed["format"])
    return {
        "format": ", ".join(formats),
        "primary": "temperature 1 min" if any(_rangeParts(part) for part in parts) else "temperature 1",
        "values": values
    }

def angleListAttribute(value):
    value = str(value).replace(";", ",")
    return scalarListAttribute(value, readAngle, "angle", "angle")

def capacityAtVoltage(value):
    """
    Parses <capacity> @ <voltage>
    """
    if value == "-":
        return {
            "format": "-",
            "default": "capacity",
            "values": {
                "capacity": ["NaN", "capacitance"],
                "voltage": ["NaN", "voltage"]
            }
        }
    def readTheTuple(value):
        value = value.strip()
        try:
            c, v = tuple(value.split("@"))
        except:
            try:
                c, v = tuple(value.split(" "))
            except:
                # Sometimes, we miss voltage
                c = value
                v = None
        c = readCapacitance(c.strip())
        if v is not None:
            v = v.strip()
            if "V" in v or "v" in v:
                rangeParts = _rangeParts(v)
                if rangeParts is not None:
                    v = readVoltage(rangeParts[-1].strip())
                else:
                    v = readVoltage(v)
            else:
                v = "NaN"
        else:
            v = "NaN"
        return c, v
    if ";" in value or ("," in value and "@" not in value):
        separator = ";" if ";" in value else ","
        parsed = [readTheTuple(x) for x in value.split(separator)]
        values = {}
        for i, (c, v) in enumerate(parsed, start=1):
            values[f"capacity {i}"] = [c, "capacitance"]
            values[f"voltage {i}"] = [v, "voltage"]
        return {
            "format": "; ".join(f"${{capacity {i}}} @ ${{voltage {i}}}" for i in range(1, len(parsed) + 1)),
            "default": "capacity 1",
            "values": values
        }
    c, v = readTheTuple(value)
    return {
            "format": "${capacity} @ ${voltage}",
            "default": "capacity",
            "values": {
                "capacity": [c, "capacitance"],
                "voltage": [v, "voltage"]
            }
        }

def chargeAtVoltage(value):
    """
    Parses <charge> @ <voltage>
    """
    if value == "-":
        return {
            "format": "-",
            "default": "charge",
            "values": {
                "charge": ["NaN", "capacitance"],
                "voltage": ["NaN", "voltage"]
            }
        }
    def readTheTuple(value):
        match = re.match(r"(?P<cap>.*?)(\s*[ @](?P<voltage>.*))?", value.strip())
        if match is None:
            raise RuntimeError(f"Cannot parse charge at voltage for {value}")
        q = match.groupdict().get("cap")
        v = match.groupdict().get("voltage")

        if q is not None:
            q = readCharge(q.strip())
        else:
            q = "NaN"

        if v is not None:
            v = readVoltage(re.sub(r'-?\d+~', '', v.strip()))
        else:
            v = "NaN"
        return q, v

    if ";" in value:
        a, b = tuple(value.split(";"))
        q1, v1 = readTheTuple(a)
        q2, v2 = readTheTuple(b)
        return {
            "format": "${charge 1} @ ${voltage 1}; ${charge 2} @ ${voltage 2}",
            "default": "charge 1",
            "values": {
                "charge 1": [q1, "charge"],
                "voltage 1": [v2, "voltage"],
                "charge 2": [q2, "charge"],
                "voltage 2": [v2, "voltage"]
            }
        }

    q, v = readTheTuple(value)
    return {
            "format": "${charge} @ ${voltage}",
            "default": "charge",
            "values": {
                "charge": [q, "charge"],
                "voltage": [v, "voltage"]
            }
        }
