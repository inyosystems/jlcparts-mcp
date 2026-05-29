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

def identifierAttribute(value, name="identifier"):
    return {
        "format": "${" + name + "}",
        "primary": name,
        "values": {
            name: [str(value), "identifier"]
        }
    }

def splitIdentifierList(value, separators=",;"):
    tokens = []
    token = []
    depth = 0
    for char in str(value):
        if char in "([{":
            depth += 1
        elif char in ")]}" and depth > 0:
            depth -= 1
        if char in separators and depth == 0:
            item = " ".join("".join(token).split())
            if item:
                tokens.append(item)
            token = []
        else:
            token.append(char)
    item = " ".join("".join(token).split())
    if item:
        tokens.append(item)
    return tokens

def identifierListAttribute(value, name="identifier", separators=",;", aliases=None):
    tokens = splitIdentifierList(value, separators)
    if aliases:
        tokens = [
            aliases.get(token, aliases.get(token.lower(), token))
            for token in tokens
        ]
    if not tokens:
        tokens = ["-"]
    keys = [f"{name} {index}" for index in range(1, len(tokens) + 1)]
    return {
        "format": ", ".join("${" + key + "}" for key in keys),
        "primary": keys[0],
        "values": {
            key: [token, "identifier"]
            for key, token in zip(keys, tokens)
        }
    }

def categoryAttribute(value):
    if not isinstance(value, dict):
        return identifierAttribute(value, "category")
    category = str(value.get("name1", "")).strip() or "-"
    subcategory = str(value.get("name2", "")).strip() or "-"
    values = {
        "category": [category, "identifier"],
        "subcategory": [subcategory, "identifier"],
    }
    if value.get("id1") is not None:
        values["category id"] = [int(value["id1"]), "count"]
    if value.get("id2") is not None:
        values["subcategory id"] = [int(value["id2"]), "count"]
    return {
        "format": "${category} / ${subcategory}",
        "primary": "subcategory",
        "values": values
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

def readRotationalSpeed(value):
    value = value.strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    match = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)\s*rpm", value, flags=re.I)
    if match is None:
        raise ValueError(f"Cannot parse rotational speed {value}")
    return float(match.group(1))

def rotationalSpeedAttribute(value):
    return scalarAttribute(value, readRotationalSpeed, "rotational_speed", "speed")

def accelerationRangeAttribute(value, name="acceleration"):
    value = str(value).strip()
    if value.startswith("±"):
        parsed = readAcceleration(value)
        return {
            "format": "${" + name + " min} ~ ${" + name + " max}",
            "primary": name + " min",
            "values": {
                name + " min": [-parsed, "acceleration"],
                name + " max": [parsed, "acceleration"]
            }
        }
    return scalarAttribute(value, readAcceleration, "acceleration", name)

def readCurrent(value):
    """
    Given a string, try to parse current and return it as Amperes (float)
    """
    value = erase(value, ["PNP"])
    value = erase(value, ["<", ">", "≤", "≥"])
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
    value = re.sub(r"rms$", "", value, flags=re.I)
    value = re.sub(r"\([^)]*\)", "", value)
    value = value.replace("V-", "V")
    value = value.replace("VDC", "V").replace("VAC", "V")
    value = re.sub(r"(?<=\d)(?:AC|DC)$", "V", value, flags=re.I)
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

def readCurrentTemperatureDrift(value):
    value = value.strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    value = re.sub(r"/\s*(?:℃|°C|C)$", "", value, flags=re.I).strip()
    return readCurrent(value)

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
    ppb = re.search(r"ppb$", value, flags=re.I)
    value = re.sub(r"pp[mb](?:p-p)?$", "", value, flags=re.I).strip()
    parsed = float(value)
    return parsed / 1000 if ppb else parsed

def ppmRangeAttribute(value, name="ppm"):
    value = str(value).strip()
    if value.startswith("±"):
        value = "-" + value[1:] + "~+" + value[1:]
    return rangeOrScalarAttribute(value, readPpm, "ppm", name)

def frequencyStabilityAttribute(value, name="stability"):
    value = str(value).strip()
    if "%" in value:
        return percentageRangeAttribute(value, name)
    return ppmRangeAttribute(value, name)

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
    value = re.sub(r"w", "", value, flags=re.I).strip()
    return readWithSiPrefix(value)

def readPowerTemperatureDrift(value):
    value = value.strip()
    if value in ["-", "--"] or "null" in value:
        return "NaN"
    value = re.sub(r"/\s*(?:℃|°C|C)$", "", value, flags=re.I).strip()
    return readPower(value)

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
    if value in ["-", "--", "null", "NaN"]:
        return "NaN"
    value = re.sub(r"(?:bit/s|bps|sps|B/s|Bd)$", "", value, flags=re.IGNORECASE)
    value = erase(value, ["Hz", "HZ", "H"]).strip()
    value = re.sub(r"([0-9.])([kmg])$", lambda m: m.group(1) + m.group(2).upper(), value)
    return readWithSiPrefix(value)

def readSlewRate(value):
    value = value.strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    value = value.replace("µ", "u").replace("μ", "u")
    match = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)\s*((?:m|u|k)?V)\s*/\s*(ns|us|ms|s)", value, re.I)
    if match is None:
        raise ValueError(f"Cannot parse slew rate {value}")
    number = float(match.group(1))
    voltage_unit = match.group(2).lower()
    time_unit = match.group(3).lower()
    voltage_scales = {
        "uv": 1e-6,
        "mv": 1e-3,
        "v": 1,
        "kv": 1e3,
    }
    time_scales = {
        "ns": 1e-9,
        "us": 1e-6,
        "ms": 1e-3,
        "s": 1,
    }
    return number * voltage_scales[voltage_unit] / time_scales[time_unit]

def readFrameRate(value):
    value = value.strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    value = re.sub(r"fps$", "", value, flags=re.I).strip()
    return float(value)

def readAngularVelocity(value):
    value = value.strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    value = value.replace("±", "")
    value = re.sub(r"dps$", "", value, flags=re.I).strip()
    return float(value)

def readAcceleration(value):
    value = value.strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    value = value.replace("±", "")
    value = re.sub(r"g$", "", value, flags=re.I).strip()
    return float(value)

def readForce(value):
    value = value.strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    match = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)\s*(N|gf)", value, flags=re.I)
    if match is None:
        raise ValueError(f"Cannot parse force {value}")
    scales = {
        "n": 1,
        "gf": 0.00980665,
    }
    return float(match.group(1)) * scales[match.group(2).lower()]

def readAirFlow(value):
    value = str(value).strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    match = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)\s*CFM", value, flags=re.I)
    if match is None:
        raise ValueError(f"Cannot parse air flow {value}")
    return float(match.group(1)) * 0.00047194745

def readPercentageTemperatureDrift(value):
    value = str(value).strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    value = value.replace("±", "")
    value = re.sub(r"%\s*/\s*(?:℃|°C|C)$", "", value, flags=re.I).strip()
    return float(value)

def readDecibelMilliwattPerHertz(value):
    value = str(value).strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    value = re.sub(r"dBm\s*/\s*Hz$", "", value, flags=re.I).strip()
    return float(value)

def readRatioTerm(value):
    value = str(value).strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    value = re.sub(r"CT", "", value, flags=re.I)
    value = re.sub(r"±.*$", "", value).strip()
    return readWithSiPrefix(value)

def readInductance(value):
    value = value.replace("H", "").strip()
    return readWithSiPrefix(value)

def readLuminousIntensity(value):
    value = value.strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    value = re.sub(r"cd$", "", value, flags=re.IGNORECASE).strip()
    return readWithSiPrefix(value)

def readLuminousFlux(value):
    value = value.strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    value = re.sub(r"lm$", "", value, flags=re.IGNORECASE).strip()
    return readWithSiPrefix(value)

def readLuminance(value):
    value = value.strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    value = re.sub(r"cd\s*/\s*m2$", "", value, flags=re.IGNORECASE).strip()
    return readWithSiPrefix(value)

def readIlluminance(value):
    value = value.strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    value = re.sub(r"lx$", "", value, flags=re.IGNORECASE).strip()
    return readWithSiPrefix(value)

def readRadiantIntensity(value):
    value = value.strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    value = re.sub(r"/\s*sr$", "", value, flags=re.IGNORECASE).strip()
    return readPower(value)

def readPressure(value):
    value = value.strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    match = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)\s*(pa|hpa|kpa|mpa|mbar|bar)", value, flags=re.I)
    if match is None:
        raise ValueError(f"Cannot parse pressure {value}")
    scales = {
        "pa": 1,
        "hpa": 100,
        "kpa": 1e3,
        "mpa": 1e6,
        "mbar": 100,
        "bar": 1e5,
    }
    return float(match.group(1)) * scales[match.group(2).lower()]

def readPressureTemperatureDrift(value):
    value = value.strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    value = re.sub(r"/\s*K$", "", value, flags=re.I).strip()
    return readPressure(value)

def readLength(value):
    value = value.strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    parenthesizedMetric = re.search(r"\(([^)]*(?:nm|um|mm|cm|km|m|mil|in|inch|inches))\)", value, re.I)
    if parenthesizedMetric is not None:
        value = parenthesizedMetric.group(1)
    elif value.endswith("'"):
        return float(value[:-1]) * 0.3048
    value = value.replace("µ", "u").replace("μ", "u")
    match = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)\s*(nm|um|mm|cm|km|m|mil|in|inch|inches)?", value, re.I)
    if match is None:
        raise ValueError(f"Cannot parse length {value}")
    number = float(match.group(1))
    unit = (match.group(2) or "m").lower()
    scales = {
        "nm": 1e-9,
        "um": 1e-6,
        "mm": 1e-3,
        "cm": 1e-2,
        "km": 1e3,
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
    match = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)\s*(fs|ps|ns|us|ms|s|sec|secs|min|mins|h|hr|hrs|hour|hours)?", value, re.I)
    if match is None:
        raise ValueError(f"Cannot parse time {value}")
    number = float(match.group(1))
    unit = (match.group(2) or "s").lower()
    scales = {
        "fs": 1e-15,
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
    value = re.sub(r"\s*deg$", "", value, flags=re.I)
    value = value.replace("°", "")
    return float(value)

def readDataSize(value):
    value = value.strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    organization = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)\s*([KMGT]?)\s*x\s*(\d+(?:\.\d+)?)", value, re.I)
    if organization is not None:
        words = float(organization.group(1))
        word_unit = organization.group(2).lower()
        width = float(organization.group(3))
        word_scales = {
            "": 1,
            "k": 1024,
            "m": 1024 * 1024,
            "g": 1024 * 1024 * 1024,
            "t": 1024 * 1024 * 1024 * 1024,
        }
        return words * word_scales[word_unit] * width / 8
    match = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)\s*(bit|Kbit|Mbit|Gbit|Tbit|Byte|B|KB|MB|GB|TB)", value, re.I)
    if match is None:
        raise ValueError(f"Cannot parse data size {value}")
    number = float(match.group(1))
    unit = match.group(2).lower()
    scales = {
        "bit": 1 / 8,
        "kbit": 1024 / 8,
        "mbit": 1024 * 1024 / 8,
        "gbit": 1024 * 1024 * 1024 / 8,
        "tbit": 1024 * 1024 * 1024 * 1024 / 8,
        "byte": 1,
        "b": 1,
        "kb": 1024,
        "mb": 1024 * 1024,
        "gb": 1024 * 1024 * 1024,
        "tb": 1024 * 1024 * 1024 * 1024,
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
    if value.endswith("‰"):
        return float(value[:-1]) / 10
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
    value = re.sub(r"dBc\s*/\s*Hz$", "", value, flags=re.IGNORECASE).strip()
    value = re.sub(r"dB(?:i|ic|c)?$", "", value, flags=re.IGNORECASE).strip()
    return float(value)

def readDecibelMilliwatt(value):
    value = value.strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    value = re.sub(r"dBm$", "", value, flags=re.IGNORECASE).strip()
    return float(value)

def readRatio(value):
    value = str(value).strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    value = value.replace("CT", "")
    value = re.sub(r"V\s*/\s*V$", "", value, flags=re.I).strip()
    if ":" in value:
        parts = [x.strip() for x in value.split(":")]
        if len(parts) == 2:
            numerator = readWithSiPrefix(parts[0])
            denominator = readWithSiPrefix(parts[1])
            if numerator == "NaN" or denominator == "NaN":
                return "NaN"
            return numerator / denominator
    return readWithSiPrefix(value)

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

def resistanceRangeAttribute(value):
    return rangeOrScalarAttribute(value, readResistance, "resistance", "resistance")

def resistanceRangeListAttribute(value):
    value = str(value).replace(";", ",")
    parts = [x.strip() for x in value.split(",")]
    values = {}
    formats = []
    for index, part in enumerate(parts, start=1):
        name = f"resistance {index}" if len(parts) > 1 else "resistance"
        parsed = rangeOrScalarAttribute(part, readResistance, "resistance", name)
        values.update(parsed["values"])
        formats.append(parsed["format"])
    primary_name = "resistance 1" if len(parts) > 1 else "resistance"
    return {
        "format": ", ".join(formats),
        "primary": primary_name + " min" if any(_rangeParts(part) for part in parts) else primary_name,
        "values": values
    }

def impedanceAttribute(value):
    value = readResistance(value)
    return {
        "format": "${impedance}",
        "primary": "impedance",
        "values": {
            "impedance": [value, "resistance"]
        }
    }

def impedanceListAttribute(value):
    value = str(value).replace(";", ",")
    return scalarListAttribute(value, readResistance, "resistance", "impedance")

def impedanceRatioAttribute(value):
    value = str(value).strip()
    if ":" not in value:
        return impedanceAttribute(value)
    value = value.replace("Ω", "")
    return colonRatioListAttribute(value, "ratio")


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
        values = value.split(";")
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

def speakerChannelAttribute(value):
    value = str(value).strip()
    if value in ["-", "--", "null"]:
        counts = ["NaN"]
    else:
        parts = [x.strip() for x in value.split(",")]
        counts = []
        for part in parts:
            if part.lower() == "monaural":
                counts.append(1)
            elif part == "双声道":
                counts.append(2)
            else:
                match = re.search(r"\d+", part)
                if match is None:
                    raise ValueError(f"Cannot parse speaker channel count {value}")
                counts.append(float(match.group(0)))
    values = {
        f"channels {i}": [count, "count"]
        for i, count in enumerate(counts, start=1)
    }
    return {
        "format": ", ".join("${" + name + "}" for name in values),
        "primary": "channels 1",
        "values": values
    }

def inputCountAttribute(value):
    value = str(value).strip()
    values = {}
    if value in ["-", "--", "null"]:
        values["inputs"] = ["NaN", "count"]
    elif re.fullmatch(r"\d+", value):
        values["inputs"] = [float(value), "count"]
    else:
        single = re.search(r"(\d+)\s+single-?ended", value, flags=re.I)
        differential = re.search(r"(\d+)\s+(?:pairs?\s+)?differential", value, flags=re.I)
        if single is not None:
            values["single-ended inputs"] = [float(single.group(1)), "count"]
        if differential is not None:
            values["differential input pairs"] = [float(differential.group(1)), "count"]
        if not values:
            raise ValueError(f"Cannot parse input count {value}")
    return {
        "format": ", ".join("${" + name + "}" for name in values),
        "primary": next(iter(values)),
        "values": values
    }

def _countedTermsAttribute(value, terms, default_name="count"):
    value = str(value).strip()
    if value in ["-", "--", "null"]:
        return {
            "format": "${" + default_name + "}",
            "primary": default_name,
            "values": {default_name: ["NaN", "count"]}
        }
    normalized = value.lower()
    normalized = normalized.replace("one", "1").replace("two", "2")
    values = {}
    for name, pattern in terms:
        total = 0
        for match in re.finditer(rf"(\d+)\s*(?:pair\s*)?(?:{pattern})", normalized, flags=re.I):
            count = int(match.group(1))
            if "pair" in match.group(0):
                count *= 2
            total += count
        if total:
            values[name] = [total, "count"]
    if not values:
        values[default_name] = ["NaN", "count"]
    return {
        "format": ", ".join("${" + name + "}" for name in values),
        "primary": next(iter(values)),
        "values": values
    }

def transistorNumberAttribute(value):
    return _countedTermsAttribute(value, [
        ("npn transistors", r"npn"),
        ("pnp transistors", r"pnp"),
        ("n-channel transistors", r"n-?channel"),
        ("p-channel transistors", r"p-?channel"),
    ], "transistors")

def diodeConfigurationAttribute(value):
    value = str(value).strip()
    if value in ["-", "--", "null"]:
        values = {"diodes": ["NaN", "count"]}
    elif re.search(r"\d+\s+series\s*x\s*\d+\s+parallel", value, flags=re.I):
        series, parallel = re.search(r"(\d+)\s+series\s*x\s*(\d+)\s+parallel", value, flags=re.I).groups()
        values = {"series diodes": [float(series), "count"], "parallel strings": [float(parallel), "count"]}
    else:
        values = {}
        independent = re.search(r"(\d+)\s+independent", value, flags=re.I)
        if independent is not None:
            values["independent diodes"] = [float(independent.group(1)), "count"]
        pairs = re.search(r"(\d+)\s+pair", value, flags=re.I)
        if pairs is not None:
            values["diode pairs"] = [float(pairs.group(1)), "count"]
        series = re.search(r"(\d+)\s+(?:in\s+)?series", value, flags=re.I)
        if series is not None:
            values["series diodes"] = [float(series.group(1)), "count"]
        common_anode = re.search(r"(\d+)\s+common anodes?", value, flags=re.I)
        if common_anode is not None:
            values["common anode diodes"] = [float(common_anode.group(1)), "count"]
        common_cathode = re.search(r"(\d+)\s+common cathodes?", value, flags=re.I)
        if common_cathode is not None:
            values["common cathode diodes"] = [float(common_cathode.group(1)), "count"]
        if not values:
            values["diodes"] = ["NaN", "count"]
    return {
        "format": ", ".join("${" + name + "}" for name in values),
        "primary": next(iter(values)),
        "values": values
    }

def scrTypeAttribute(value):
    return _countedTermsAttribute(value, [
        ("triacs", r"triac"),
        ("scrs", r"scr"),
        ("thyristors", r"(?:uni)?directional thyristor|one-way thyristor|two-way thyristor"),
        ("diodes", r"diode"),
    ], "scr devices")

def driverReceiverAttribute(value):
    value = str(value).strip()
    if value in ["-", "--", "null"]:
        values = {"drivers 1": ["NaN", "count"], "receivers 1": ["NaN", "count"]}
        formats = ["${drivers 1}/${receivers 1}"]
    else:
        values = {}
        formats = []
        for i, part in enumerate([x.strip() for x in value.split(";")], start=1):
            drivers, receivers = [float(x.strip()) for x in part.split("/", 1)]
            values[f"drivers {i}"] = [drivers, "count"]
            values[f"receivers {i}"] = [receivers, "count"]
            formats.append("${" + f"drivers {i}" + "}/${" + f"receivers {i}" + "}")
    return {
        "format": ", ".join(formats),
        "primary": "drivers 1",
        "values": values
    }

def detentsPulsesAttribute(value):
    value = str(value).strip()
    if value in ["-", "--", "null"]:
        values = {"detents": ["NaN", "count"], "pulses": ["NaN", "count"]}
    else:
        detents, pulses = [float(x.strip()) for x in value.split("/", 1)]
        values = {"detents": [detents, "count"], "pulses": [pulses, "count"]}
    return {
        "format": "${detents}/${pulses}",
        "primary": "detents",
        "values": values
    }

def metricThreadAttribute(value, name="thread diameter"):
    value = str(value).strip()
    if value in ["-", "--", "null"]:
        return scalarAttribute(value, readLength, "length", name)
    match = re.fullmatch(r"M\s*([0-9]+(?:\.[0-9]+)?)(?:\s*thread)?", value, flags=re.I)
    if match is None:
        raise ValueError(f"Cannot parse metric thread {value}")
    return scalarAttribute(match.group(1) + "mm", readLength, "length", name)

def metricThreadLengthAttribute(value):
    value = str(value).strip()
    match = re.fullmatch(r"M\s*([0-9]+(?:\.[0-9]+)?)\s*[xX]\s*([0-9]+(?:\.[0-9]+)?)", value)
    if match is None:
        return mechanicalDimensionsAttribute(value)
    return {
        "format": "M${thread diameter} x ${length}",
        "primary": "thread diameter",
        "values": {
            "thread diameter": [readLength(match.group(1) + "mm"), "length"],
            "length": [readLength(match.group(2) + "mm"), "length"],
        }
    }

def barrierSideAttribute(value):
    value = str(value).strip()
    if value in ["-", "--", "null"]:
        count = "NaN"
    else:
        match = re.match(r"(\d+)-Side", value, flags=re.I)
        if match is None:
            count = "NaN"
        else:
            count = float(match.group(1))
    return {
        "format": "${sides}",
        "primary": "sides",
        "values": {"sides": [count, "count"]}
    }

def connectorStructureAttribute(value):
    value = str(value).strip()
    if value in ["-", "--", "null"]:
        values = {"rows": ["NaN", "count"], "positions": ["NaN", "count"]}
    else:
        match = re.fullmatch(r"(\d+)\s*x\s*(\d+)\s*P?", value, flags=re.I)
        if match is None:
            raise ValueError(f"Cannot parse connector structure {value}")
        rows, positions_per_row = [float(x) for x in match.groups()]
        values = {
            "rows": [rows, "count"],
            "positions per row": [positions_per_row, "count"],
            "positions": [rows * positions_per_row, "count"],
        }
    return {
        "format": "${rows} x ${positions per row}",
        "primary": "positions",
        "values": values
    }

def pinCountOrPitchAttribute(value):
    value = str(value).strip()
    if re.search(r"mm$", value, flags=re.I):
        return scalarAttribute(value, readLength, "length", "pitch")
    if value in ["-", "--", "null"]:
        count = "NaN"
    else:
        value = re.sub(r"P$", "", value, flags=re.I).strip()
        count = float(value)
    return {
        "format": "${count}",
        "primary": "count",
        "values": {"count": [count, "count"]}
    }

def contactTreatmentThicknessAttribute(value):
    return scalarAttribute(value, readLength, "length", "thickness")

def wireStrandsAttribute(value):
    value = str(value).strip()
    if value in ["-", "--", "null"]:
        values = {"strands": ["NaN", "count"], "strand diameter": ["NaN", "length"]}
    else:
        strands, diameter = [x.strip() for x in value.split("/", 1)]
        diameter = diameter.replace('"', "in")
        values = {
            "strands": [float(strands), "count"],
            "strand diameter": [readLength(diameter), "length"],
        }
    return {
        "format": "${strands} / ${strand diameter}",
        "primary": "strands",
        "values": values
    }

def channelCountTextAttribute(value, name="count"):
    value = str(value).strip()
    if value in ["-", "--", "null"]:
        count = "NaN"
    else:
        match = re.search(r"\d+(?:\.\d+)?", value)
        if match is None:
            raise ValueError(f"Cannot parse count {value}")
        count = float(match.group(0))
    return {
        "format": "${" + name + "}",
        "primary": name,
        "values": {name: [count, "count"]}
    }

def attachmentCountsAttribute(value):
    value = str(value).strip()
    values = {}
    for number, label in re.findall(r"(\d+)\s*(plastic shells?|housings?|terminals?)", value, flags=re.I):
        label = label.lower()
        if label.startswith("plastic shell"):
            name = "plastic shells"
        elif label.startswith("housing"):
            name = "housings"
        else:
            name = "terminals"
        values[name] = [float(number), "count"]
    if not values:
        values["count"] = ["NaN", "count"]
    return {
        "format": ", ".join("${" + name + "}" for name in values),
        "primary": next(iter(values)),
        "values": values
    }

def relayContactFormAttribute(value):
    value = str(value).strip()
    values = {}
    for count, form in re.findall(r"(\d+)\s*(?:Form\s*)?([A-C])\b", value, flags=re.I):
        values[f"form {form.upper()}"] = [int(count), "count"]
    if not values:
        values["contacts"] = ["NaN", "count"]
    return {
        "format": ", ".join("${" + name + "}" for name in values),
        "primary": next(iter(values)),
        "values": values
    }

def relayContactTypeAttribute(value):
    value = str(value).strip()
    co = re.fullmatch(r"(\d+)\s*CO", value, flags=re.I)
    if co is not None:
        return {
            "format": "${changeover contacts}",
            "primary": "changeover contacts",
            "values": {"changeover contacts": [int(co.group(1)), "count"]}
        }
    return relayContactFormAttribute(value)

def segmentDisplayTypeAttribute(value):
    value = str(value).strip()
    match = re.search(r"(\d+)\s*Segment", value, flags=re.I)
    if match is None:
        raise ValueError(f"Cannot parse segment display type {value}")
    return {
        "format": "${segments}",
        "primary": "segments",
        "values": {"segments": [int(match.group(1)), "count"]}
    }

def switchWayAttribute(value):
    value = str(value).strip()
    match = re.search(r"(\d+)\s*-\s*Way", value, flags=re.I)
    if match is None:
        raise ValueError(f"Cannot parse switch way count {value}")
    return {
        "format": "${ways}",
        "primary": "ways",
        "values": {"ways": [int(match.group(1)), "count"]}
    }

def packagePinCountAttribute(value):
    value = str(value).strip()
    match = re.match(r"(\d+)\s*-\s*", value)
    if match is None:
        raise ValueError(f"Cannot parse package pin count {value}")
    return {
        "format": "${pins}",
        "primary": "pins",
        "values": {"pins": [int(match.group(1)), "count"]}
    }

def clockViewingDirectionAttribute(value):
    value = str(value).strip()
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*o'?clock", value, flags=re.I)
    if match is None:
        raise ValueError(f"Cannot parse viewing direction {value}")
    angle = (float(match.group(1)) % 12) * 30
    return {
        "format": "${angle}",
        "primary": "angle",
        "values": {"angle": [angle, "angle"]}
    }

def _readConnectorCount(value):
    value = str(value).strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    base_value = re.sub(r"\(.*?\)", "", value).strip()
    missing = sum(int(x) for x in re.findall(r"missing\s+(\d+)\s*P?", value, flags=re.I))
    subtract_missing = missing and "x" in base_value.lower()
    value = base_value
    total = 0
    for part in value.split("+"):
        part = part.strip()
        part = re.sub(r"(?<=\d)AP$", "P", part, flags=re.I)
        part = re.sub(r"(\d+)\s*-\s*bit$", r"\1bit", part, flags=re.I)
        match = re.fullmatch(r"(\d+)\s*(?:P|b|bits?|digits?)?\s*(?:x\s*(\d+))?", part, flags=re.I)
        if match is None:
            match = re.fullmatch(r"(\d+)\s*x\s*(\d+)\s*P?", part, flags=re.I)
            if match is not None:
                total += int(match.group(1)) * int(match.group(2))
                continue
        if match is None:
            raise ValueError(f"Cannot parse connector count {value}")
        count = int(match.group(1))
        multiplier = int(match.group(2) or 1)
        total += count * multiplier
    return total - missing if subtract_missing else total

def connectorCountAttribute(value):
    return scalarAttribute(value, _readConnectorCount, "count", "count")

def applyConnectorCountAttribute(value):
    value = str(value).strip()
    counts = [int(match) for match in re.findall(r"(\d+)\s*P", value, flags=re.I)]
    if not counts:
        return countAttribute("-")
    if len(counts) == 1:
        return {
            "format": "${count}",
            "primary": "count",
            "values": {"count": [counts[0], "count"]}
        }
    values = {
        f"count {index}": [count, "count"]
        for index, count in enumerate(counts, start=1)
    }
    return {
        "format": ", ".join("${" + f"count {index}" + "}" for index in range(1, len(counts) + 1)),
        "primary": "count 1",
        "values": values
    }

def memoryCompositionAttribute(value):
    value = str(value).strip()
    values = {}
    for count, memory_type in re.findall(r"(\d+)\s*([A-Za-z]+)", value):
        values[memory_type.lower()] = [int(count), "count"]
    if not values:
        values["count"] = ["NaN", "count"]
    return {
        "format": ", ".join("${" + name + "}" for name in values),
        "primary": next(iter(values)),
        "values": values
    }

def generationAttribute(value):
    value = str(value).strip()
    match = re.fullmatch(r"Gen\s+(\d+)", value, flags=re.I)
    if match is None:
        return countAttribute(value)
    return {
        "format": "${generation}",
        "primary": "generation",
        "values": {"generation": [int(match.group(1)), "count"]}
    }

def platingThicknessAttribute(value):
    value = str(value).strip()
    values = {}
    formats = []
    for layer in [x.strip() for x in value.split(",")]:
        match = re.search(r"([A-Za-z ]*?)\s+plating\s+([0-9.]+)(?:\s*~\s*([0-9.]+))?\s*u\"", layer, flags=re.I)
        if match is None:
            raise ValueError(f"Cannot parse plating thickness {value}")
        label = match.group(1).strip().lower()
        label = " ".join(word for word in label.split() if word not in {"bright"})
        low = float(match.group(2)) * 0.0254e-6
        high = float(match.group(3) or match.group(2)) * 0.0254e-6
        values[f"{label} thickness min"] = [low, "length"]
        values[f"{label} thickness max"] = [high, "length"]
        formats.append("${" + f"{label} thickness min" + "} ~ ${" + f"{label} thickness max" + "}")
    return {
        "format": ", ".join(formats),
        "primary": next(iter(values)),
        "values": values
    }

def metricProductDescriptionAttribute(value):
    value = str(value).strip()
    numbers = re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?|(?<=M)\d+(?:\.\d+)?|(?<=L)\d+(?:\.\d+)?", value)
    if not numbers:
        raise ValueError(f"Cannot parse product dimensions {value}")
    values = {
        f"length {index}": [readLength(number + "mm"), "length"]
        for index, number in enumerate(numbers, start=1)
    }
    return {
        "format": " x ".join("${" + f"length {index}" + "}" for index in range(1, len(numbers) + 1)),
        "primary": "length 1",
        "values": values
    }

def specificationsAttribute(value):
    value = str(value).strip()
    if value in ["", "-", "--"]:
        return identifierAttribute("-", "specification")

    pin_match = re.fullmatch(r"(\d+)\s*pin", value, flags=re.I)
    if pin_match:
        return countAttribute(pin_match.group(1))

    metric_match = re.fullmatch(
        r"[PK]?M(\d+(?:\.\d+)?)"
        r"(?:\s*[-xX*]\s*(\d+(?:\.\d+)?))?"
        r"(?:\s*[xX*]\s*(\d+(?:\.\d+)?))?"
        r"(?:\s*\+\s*(\d+(?:\.\d+)?))?"
        r"(?:\s+.*)?",
        value,
        flags=re.I,
    )
    if metric_match:
        diameter, second, third, extra = metric_match.groups()
        values = {"thread diameter": [float(diameter) / 1000, "length"]}
        formats = ["${thread diameter}"]
        if second:
            parsed_second = float(second)
            if parsed_second < 1:
                values["thread pitch"] = [parsed_second / 1000, "length"]
                formats.append("${thread pitch}")
            else:
                values["length 1"] = [parsed_second / 1000, "length"]
                formats.append("${length 1}")
        if third:
            index = 2 if "length 1" in values else 1
            values[f"length {index}"] = [float(third) / 1000, "length"]
            formats.append("${" + f"length {index}" + "}")
        if extra:
            index = 1 + len([name for name in values if name.startswith("length ")])
            values[f"length {index}"] = [float(extra) / 1000, "length"]
            formats.append("${" + f"length {index}" + "}")
        return {
            "format": " x ".join(formats),
            "primary": "thread diameter",
            "values": values
        }

    dimensions = re.fullmatch(
        r"(\d+(?:\.\d+)?)\s*(?:mm)?\s*[*×xX]\s*"
        r"(\d+(?:\.\d+)?)\s*(?:mm)?"
        r"(?:\s*[*×xX]\s*(\d+(?:\.\d+)?)\s*(?:mm)?)?",
        value,
        flags=re.I,
    )
    if dimensions:
        lengths = [float(x) / 1000 for x in dimensions.groups() if x is not None]
        values = {
            f"length {index}": [length, "length"]
            for index, length in enumerate(lengths, start=1)
        }
        return {
            "format": " x ".join("${" + key + "}" for key in values.keys()),
            "primary": "length 1",
            "values": values
        }

    length_match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*mm", value, flags=re.I)
    if length_match:
        return lengthAttribute(value)

    return identifierAttribute(value, "specification")

def sizeAttribute(value):
    value = str(value).strip()
    if value in ["", "-", "--"]:
        return identifierAttribute("-", "size")

    if re.fullmatch(r"\d+(?:\.\d+)?", value):
        return lengthAttribute(value + "mm")

    pin_count = None
    pin_match = re.search(r"-(\d+)\s*pin$", value, flags=re.I)
    if pin_match:
        pin_count = int(pin_match.group(1))
        value = value[:pin_match.start()]

    numbers = re.findall(r"\d+(?:\.\d+)?", value)
    if numbers:
        values = {
            f"length {index}": [float(number) / 1000, "length"]
            for index, number in enumerate(numbers, start=1)
        }
        if pin_count is not None:
            values["pins"] = [pin_count, "count"]
        return {
            "format": " x ".join("${" + key + "}" for key in values.keys()),
            "primary": "length 1",
            "values": values
        }

    return identifierAttribute(value, "size")

def materialGradeAttribute(value):
    value = str(value).strip()
    if value in ["-", "--", "null"]:
        return countAttribute(value)
    values = {}
    grade = re.search(r"\b(\d{3,4})\b", value)
    if grade is not None:
        values["material grade"] = [int(grade.group(1)), "count"]
    temper = re.search(r"\bT(\d+)\b", value, flags=re.I)
    if temper is not None:
        values["temper"] = [int(temper.group(1)), "count"]
    if not values:
        values["material grade"] = ["NaN", "count"]
    return {
        "format": ", ".join("${" + name + "}" for name in values),
        "primary": next(iter(values)),
        "values": values
    }

def _readCycleCount(value):
    value = str(value).strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    normalized = value.replace(",", "").replace("×", "x").lower()
    scientific = re.fullmatch(r"(\d+(?:\.\d+)?)\s*x\s*10\^(\d+)\s*(?:cycles?|times?|cuts?)", normalized)
    if scientific is not None:
        return int(float(scientific.group(1)) * 10 ** int(scientific.group(2)))
    chinese = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(千|万)?\s*次", normalized)
    if chinese is not None:
        multiplier = {
            None: 1,
            "千": 1000,
            "万": 10000,
        }[chinese.group(2)]
        return int(float(chinese.group(1)) * multiplier)
    english = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(thousand|million|trillion)?\s*(?:cycles?|times?|cuts?)", normalized)
    if english is None:
        raise ValueError(f"Cannot parse cycle count {value}")
    multiplier = {
        None: 1,
        "thousand": 1000,
        "million": 1000000,
        "trillion": 1000000000000,
    }[english.group(2)]
    return int(float(english.group(1)) * multiplier)

def cycleCountAttribute(value):
    return scalarAttribute(value, _readCycleCount, "count", "count")

def cycleCountListAttribute(value):
    value = str(value).replace(";", ",")
    tokens = re.findall(
        r"\d+(?:,\d{3})*(?:\.\d+)?\s*(?:[x×]\s*10\^\d+|thousand|million|trillion)?\s*(?:cycles?|times?|cuts?)|"
        r"\d+(?:\.\d+)?\s*(?:千|万)?\s*次|"
        r"-|--|null",
        value,
        flags=re.I,
    )
    if len(tokens) <= 1:
        return cycleCountAttribute(value)
    values = {}
    for i, token in enumerate(tokens, start=1):
        values[f"count {i}"] = [_readCycleCount(token), "count"]
    return {
        "format": ", ".join("${" + f"count {i}" + "}" for i in range(1, len(tokens) + 1)),
        "primary": "count 1",
        "values": values
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
        "dual channel": 2,
        "three channels": 3,
        "four channels": 4,
        "five-way": 5,
        "five channels": 5,
        "quad": 4,
        "triple": 3,
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

def countListAttribute(value):
    value = str(value).replace(";", ",")
    parts = [x.strip() for x in value.split(",") if x.strip()]
    if len(parts) <= 1:
        return countAttribute(value)
    values = {}
    for index, part in enumerate(parts, start=1):
        counts = [_readCount(x) for x in part.split("+")]
        if any(x == "NaN" for x in counts):
            count = "NaN"
        else:
            count = sum(counts)
        values[f"count {index}"] = [count, "count"]
    return {
        "format": ", ".join("${" + f"count {i}" + "}" for i in range(1, len(parts) + 1)),
        "primary": "count 1",
        "values": values
    }

def matrixCountAttribute(value):
    value = str(value).strip()
    if "x" not in value.lower() and "," not in value:
        return countAttribute(value)

    parts = [re.sub(r"\s*bits?$", "", x.strip(), flags=re.I) for x in value.split(",")]
    values = {}
    formats = []
    multiple = len(parts) > 1
    for index, part in enumerate(parts, start=1):
        axes = [x.strip() for x in re.split(r"\s*x\s*", part, flags=re.I) if x.strip()]
        if len(axes) != 2:
            raise ValueError(f"Cannot parse matrix count {value}")
        suffix = f" {index}" if multiple else ""
        columns_name = f"columns{suffix}"
        rows_name = f"rows{suffix}"
        values[columns_name] = [_readCount(axes[0]), "count"]
        values[rows_name] = [_readCount(axes[1]), "count"]
        formats.append("${" + columns_name + "} x ${" + rows_name + "}")
    return {
        "format": ", ".join(formats),
        "primary": "columns 1" if multiple else "columns",
        "values": values
    }

def wordSizeAttribute(value):
    value = str(value).strip()
    parts = [x.strip() for x in value.split(",") if x.strip()]
    if len(parts) == 1 and "x" not in parts[0].lower():
        return countRangeAttribute(value) if _rangeParts(value) else countAttribute(value)

    values = {}
    formats = []

    def add_count_or_range(name, raw):
        range_parts = _rangeParts(raw)
        if range_parts is None:
            values[name] = [_readCount(raw), "count"]
            return "${" + name + "}"
        low, high = range_parts
        values[f"{name} min"] = [_readCount(low), "count"]
        values[f"{name} max"] = [_readCount(high), "count"]
        return "${" + name + " min} ~ ${" + name + " max}"

    for index, part in enumerate(parts, start=1):
        suffix = f" {index}" if len(parts) > 1 else ""
        if "x" in part.lower():
            axes = [x.strip() for x in re.split(r"\s*x\s*", part, flags=re.I) if x.strip()]
            if len(axes) != 2:
                raise ValueError(f"Cannot parse word size {value}")
            columns_name = f"columns{suffix}"
            rows_name = f"rows{suffix}"
            columns_format = add_count_or_range(columns_name, axes[0])
            rows_format = add_count_or_range(rows_name, axes[1])
            formats.append(columns_format + " x " + rows_format)
        else:
            count_name = f"count{suffix}"
            formats.append(add_count_or_range(count_name, part))
    return {
        "format": ", ".join(formats),
        "primary": next(iter(values)),
        "values": values
    }

def pixelArrayAttribute(value):
    value = str(value).strip()
    if value in ["-", "--", "null"]:
        return countAttribute(value)
    match = re.fullmatch(r"(\d+)H\s*x\s*(\d+)V", value, flags=re.I)
    if match is None:
        raise ValueError(f"Cannot parse pixel array {value}")
    return {
        "format": "${horizontal pixels} x ${vertical pixels}",
        "primary": "horizontal pixels",
        "values": {
            "horizontal pixels": [int(match.group(1)), "count"],
            "vertical pixels": [int(match.group(2)), "count"],
        }
    }

def opticalFormatAttribute(value):
    value = str(value).strip()
    if value in ["-", "--", "null"]:
        return scalarAttribute(value, readRatio, "ratio", "optical format")
    if "/" in value:
        numerator, denominator = value.split("/", 1)
        parsed = float(numerator) / float(denominator)
    else:
        parsed = readRatio(value)
    return {
        "format": "${optical format}",
        "primary": "optical format",
        "values": {"optical format": [parsed, "ratio"]}
    }

def _readRowCount(value):
    value = str(value).strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    named_counts = {
        "single row": 1,
        "double row": 2,
    }
    normalized = value.lower()
    if normalized in named_counts:
        return named_counts[normalized]
    value = re.sub(r"\s*rows?$", "", value, flags=re.I).strip()
    return _readCount(value)

def rowCountAttribute(value):
    value = str(value)
    parts = [x.strip() for x in re.split(r"[,;/]", value) if x.strip()]
    if len(parts) <= 1:
        return scalarAttribute(value, _readRowCount, "count", "count")

    values = {}
    for index, part in enumerate(parts, start=1):
        values[f"count {index}"] = [_readRowCount(part), "count"]
    return {
        "format": ", ".join("${" + f"count {i}" + "}" for i in range(1, len(parts) + 1)),
        "primary": "count 1",
        "values": values
    }

def _readResolutionCount(value):
    value = str(value).strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    value = re.sub(r"(\d+)\s*-\s*bit$", r"\1bit", value, flags=re.I)
    value = re.sub(r"\s*(?:bits?|positions?|digits?)$", "", value, flags=re.I).strip()
    number = float(value)
    return int(number) if number.is_integer() else number

def _temperatureResolutionAttribute(value, name):
    value = str(value).replace("°C", "℃").strip()
    if value.startswith("±"):
        value = "-" + value[1:] + "~+" + value[1:]
    value = value.replace("℃", "")
    return rangeOrScalarAttribute(value, float, "temperature", name)

def _resolutionBase(value):
    value = str(value).strip()
    if "℃" in value or "°C" in value:
        return "temperature"
    if "%" in value:
        return "percentage"
    if re.search(r"\d\s*(?:Hz|kHz|MHz|GHz)\s*$", value, flags=re.I):
        return "frequency"
    if re.search(r"\d\s*(?:fs|ps|ns|us|ms|s)\s*$", value, flags=re.I):
        return "time"
    return "resolution"

def _resolutionPartAttribute(value, name):
    value = str(value).strip()
    base = _resolutionBase(value)
    if base == "temperature":
        return _temperatureResolutionAttribute(value, name)
    if base == "percentage":
        return percentageRangeAttribute(re.sub(r"\s*RH$", "", value, flags=re.I), name)
    if base == "frequency":
        return rangeOrScalarAttribute(value, readFrequency, "frequency", name)
    if base == "time":
        return scalarAttribute(value, readTime, "time", name)
    return scalarAttribute(value, _readResolutionCount, "count", name)

def resolutionAttribute(value):
    value = str(value).strip()
    value = re.sub(r"(\d+)\s*/\s*(\d+)\s*[Bb]its?$", r"\1bit,\2bit", value)
    parts = [x.strip() for x in re.split(r"[,;]", value) if x.strip()]
    if len(parts) <= 1:
        return _resolutionPartAttribute(value, "resolution")

    values = {}
    formats = []
    parsed_parts = []
    for part in parts:
        parsed_parts.append((part, _resolutionBase(part)))

    base_counts = {base: sum(1 for _, candidate in parsed_parts if candidate == base) for _, base in parsed_parts}
    base_indexes = {}
    for part, base in parsed_parts:
        base_indexes[base] = base_indexes.get(base, 0) + 1
        name = f"{base} {base_indexes[base]}" if base_counts[base] > 1 else base
        parsed = _resolutionPartAttribute(part, name)
        values.update(parsed["values"])
        formats.append(parsed["format"])

    return {
        "format": ", ".join(formats),
        "primary": next(iter(values)),
        "values": values
    }

def _readCount(value):
    value = str(value).strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    return int(value)

def countRangeAttribute(value):
    return rangeOrScalarAttribute(value, _readCount, "count", "count")

def filterOrderAttribute(value):
    value = re.sub(r"(\d+)(?:st|nd|rd|th)\s+Order", r"\1", str(value), flags=re.I)
    return countListAttribute(value)

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

def capacitanceRangeAttribute(value):
    return rangeOrScalarAttribute(value, readCapacitance, "capacitance", "capacitance")

def capacitanceRangeListAttribute(value):
    value = str(value).replace(";", ",").strip()
    parts = [x.strip() for x in value.split(",")]
    values = {}
    formats = []
    for index, part in enumerate(parts, start=1):
        parsed = rangeOrScalarAttribute(part, readCapacitance, "capacitance", f"capacitance {index}")
        values.update(parsed["values"])
        formats.append(parsed["format"])
    return {
        "format": ", ".join(formats),
        "primary": "capacitance 1 min" if any(_rangeParts(part) for part in parts) else "capacitance 1",
        "values": values
    }

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

def inductanceListAttribute(value):
    value = str(value).replace(";", ",")
    return scalarListAttribute(value, readInductance, "inductance", "inductance")

def frequencyAttribute(value):
    value = str(value)
    return rangeOrScalarAttribute(value, readFrequency, "frequency", "frequency")

def signedFrequencyRangeAttribute(value):
    value = str(value).strip()
    if value.startswith("±"):
        value = "-" + value[1:] + "~+" + value[1:]
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

def frequencyOrBandListAttribute(value):
    value = str(value).strip()
    if re.search(r"hz|mh|gh|kh", value, flags=re.IGNORECASE):
        return frequencyListAttribute(value)

    parts = [x.strip() for x in value.replace(";", ",").split(",") if x.strip()]
    values = {}
    for index, part in enumerate(parts, start=1):
        match = re.fullmatch(r"B\s*(\d+)", part, flags=re.IGNORECASE)
        if match is None:
            raise ValueError(f"Cannot parse communication band {part}")
        values[f"band {index}"] = [int(match.group(1)), "count"]
    return {
        "format": ", ".join("${" + f"band {i}" + "}" for i in range(1, len(parts) + 1)),
        "primary": "band 1",
        "values": values
    }

def currentListAttribute(value):
    value = str(value).replace(";", ",")
    return scalarListAttribute(value, readCurrent, "current", "current")

def labeledCurrentListAttribute(value, name="current"):
    value = str(value).replace(";", ",")
    parts = [x.strip() for x in value.split(",")]
    values = {}
    formats = []
    multiple = len(parts) > 1
    for index, part in enumerate(parts, start=1):
        value_name = f"{name} {index}" if multiple else name
        if ":" in part:
            label, part = [x.strip() for x in part.split(":", 1)]
            value_name = f"{name} {label}"
        values[value_name] = [readCurrent(_stripCondition(part)), "current"]
        formats.append("${" + value_name + "}")
    return {
        "format": ", ".join(formats),
        "primary": next(iter(values)),
        "values": values
    }

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

def luminousFluxAttribute(value):
    value = str(value).replace(";", ",")
    parts = [x.strip() for x in value.split(",")]
    values = {}
    formats = []
    for index, part in enumerate(parts, start=1):
        name = f"flux {index}" if len(parts) > 1 else "flux"
        parsed = rangeOrScalarAttribute(part, readLuminousFlux, "luminous_flux", name)
        values.update(parsed["values"])
        formats.append(parsed["format"])
    primary_name = "flux 1" if len(parts) > 1 else "flux"
    return {
        "format": ", ".join(formats),
        "primary": primary_name + " min" if any(_rangeParts(part) for part in parts) else primary_name,
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
    parts = [x.strip() for x in value.split(",")]
    values = {}
    formats = []
    has_range = False
    for index, part in enumerate(parts, start=1):
        name = f"drift {index}"
        if part.startswith("±"):
            has_range = True
            magnitude = readVoltageTemperatureDrift(part[1:])
            values[f"{name} min"] = [-magnitude, "voltage_temperature_drift"]
            values[f"{name} max"] = [magnitude, "voltage_temperature_drift"]
            formats.append("${" + f"{name} min" + "} ~ ${" + f"{name} max" + "}")
        else:
            values[name] = [readVoltageTemperatureDrift(part), "voltage_temperature_drift"]
            formats.append("${" + name + "}")
    return {
        "format": ", ".join(formats),
        "primary": next(iter(values)),
        "values": values
    }

def currentTemperatureDriftAttribute(value):
    value = str(value).replace(";", ",")
    return scalarListAttribute(
        value,
        readCurrentTemperatureDrift,
        "current_temperature_drift",
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
        elif part.lower().endswith("pp"):
            suffix = " p-p"
            part = part[:-2]
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

def noiseAttribute(value):
    value = str(value).replace(";", ",")
    parts = [x.strip() for x in value.split(",")]
    values = {}
    formats = []
    for index, part in enumerate(parts, start=1):
        if re.search(r"dB\s*\(A\)$", part, flags=re.I):
            name = f"noise {index}"
            parsed = scalarAttribute(re.sub(r"\s*\(A\)$", "", part, flags=re.I), readDecibel, "decibel", name)
        elif re.search(r"%\s*Vout$", part, flags=re.I):
            name = f"noise {index}"
            parsed = scalarAttribute(re.sub(r"\s*Vout$", "", part, flags=re.I), readPercentage, "percentage", name)
        else:
            parsed = lowFrequencyNoiseAttribute(part)
            if len(parts) > 1:
                parsed_values = {}
                parsed_format = parsed["format"]
                for quantity, parsed_value in parsed["values"].items():
                    renamed = re.sub(r"^noise 1", f"noise {index}", quantity)
                    parsed_values[renamed] = parsed_value
                    parsed_format = parsed_format.replace("${" + quantity + "}", "${" + renamed + "}")
                parsed = {**parsed, "format": parsed_format, "values": parsed_values}
        values.update(parsed["values"])
        formats.append(parsed["format"])
    return {
        "format": ", ".join(formats),
        "primary": next(iter(values)),
        "values": values
    }

def luminanceAttribute(value):
    return scalarAttribute(value, readLuminance, "luminance", "luminance")

def _readSensitivityRatio(value):
    value = str(value).strip()
    match = re.fullmatch(
        r"([+-]?\d+(?:\.\d+)?)\s*([munpμµ]?V|[munpμµ]?A)\s*/\s*(A|mT|Gs|g)",
        value,
        flags=re.I,
    )
    if match is None:
        raise ValueError(f"Cannot parse sensitivity {value}")
    number, numerator_unit, denominator_unit = match.groups()
    numerator_unit = numerator_unit.replace("μ", "u").replace("µ", "u")
    denominator_unit = denominator_unit.lower()
    if numerator_unit.lower().endswith("v"):
        numerator = readVoltage(f"{number}{numerator_unit}")
        if denominator_unit == "a":
            return numerator, "voltage_per_current"
        if denominator_unit == "mt":
            return numerator / 1e-3, "voltage_per_magnetic_flux_density"
        if denominator_unit == "gs":
            return numerator / 1e-4, "voltage_per_magnetic_flux_density"
        if denominator_unit == "g":
            return numerator, "voltage_per_g"
    numerator = readCurrent(f"{number}{numerator_unit}")
    if denominator_unit == "a":
        return numerator, "current_per_current"
    raise ValueError(f"Cannot parse sensitivity {value}")

def sensitivityAttribute(value):
    value = str(value).replace(";", ",")
    parts = [x.strip() for x in value.split(",")]
    values = {}
    formats = []
    for index, part in enumerate(parts, start=1):
        name = f"sensitivity {index}" if len(parts) > 1 else "sensitivity"
        if part in ["-", "--", "null"]:
            values[name] = ["NaN", "decibel"]
            formats.append("${" + name + "}")
        elif "dbm" in part.lower():
            values[name] = [readDecibelMilliwatt(part), "decibel_milliwatt"]
            formats.append("${" + name + "}")
        elif "db" in part.lower():
            signal = part
            tolerance = None
            if "@" in part:
                signal, tolerance = [x.strip() for x in part.split("@", 1)]
            values[name] = [readDecibel(signal), "decibel"]
            format_parts = ["${" + name + "}"]
            if tolerance:
                tolerance_name = f"{name} tolerance"
                tolerance = tolerance.replace("±", "")
                values[tolerance_name] = [readDecibel(tolerance), "decibel"]
                format_parts.append("± ${" + tolerance_name + "}")
            formats.append(" ".join(format_parts))
        else:
            parsed_value, unit = _readSensitivityRatio(part)
            values[name] = [parsed_value, unit]
            formats.append("${" + name + "}")
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

def dataRateListAttribute(value):
    value = str(value).replace(";", ",")
    return scalarListAttribute(value, readDataRate, "data_rate", "data rate")

def readWriteDataRateAttribute(value):
    value = str(value).strip()
    read, write = [x.strip() for x in value.split("/", 1)]
    unit_match = re.search(r"([A-Za-z/]+)$", write)
    if unit_match is not None and re.search(r"[A-Za-z]", read) is None:
        read += unit_match.group(1)
    return {
        "format": "${read data rate}/${write data rate}",
        "primary": "read data rate",
        "values": {
            "read data rate": [readDataRate(read), "data_rate"],
            "write data rate": [readDataRate(write), "data_rate"],
        }
    }

def readIops(value):
    value = value.strip()
    if value in ["-", "--", "null", "NaN"]:
        return "NaN"
    value = re.sub(r"iops$", "", value, flags=re.IGNORECASE).strip()
    return readWithSiPrefix(value)

def iopsAttribute(value, name="iops"):
    return scalarAttribute(value, readIops, "frequency", name)

def readWriteIopsAttribute(value):
    value = str(value).strip()
    read, write = [x.strip() for x in value.split("/", 1)]
    return {
        "format": "${read iops}/${write iops}",
        "primary": "read iops",
        "values": {
            "read iops": [readIops(read), "frequency"],
            "write iops": [readIops(write), "frequency"],
        }
    }

def frameRateListAttribute(value):
    value = str(value).replace(";", ",")
    return scalarListAttribute(value, readFrameRate, "frequency", "frame rate")

def angularVelocityAttribute(value):
    value = str(value).strip()
    if value.startswith("±"):
        value = "-" + value[1:] + "~+" + value[1:]
    return rangeOrScalarAttribute(value, readAngularVelocity, "angular_velocity", "angular velocity")

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

def slewRateAttribute(value, name="slew rate"):
    value = _expandSharedUnitAlternatives(str(value))
    if "," in value or ";" in value:
        value = value.replace(";", ",")
        return scalarListAttribute(value, readSlewRate, "slew_rate", name)
    return scalarAttribute(value, readSlewRate, "slew_rate", name)

def dataSizeAttribute(value):
    return scalarAttribute(value, readDataSize, "data_size", "data size")

def dataSizeListAttribute(value):
    value = str(value).replace(";", ",")
    return scalarListAttribute(value, readDataSize, "data_size", "data size")

def meltingI2tAttribute(value):
    return scalarAttribute(value, readMeltingI2t, "melting_i2t", "melting i2t")

def lengthAttribute(value):
    return rangeOrScalarAttribute(value, readLength, "length", "length")

def pressureAttribute(value):
    value = str(value).strip()
    if value.startswith("±"):
        value = "-" + value[1:] + "~+" + value[1:]
    return rangeOrScalarAttribute(value, readPressure, "pressure", "pressure")

def pressureRangeListAttribute(value):
    value = str(value).replace(";", ",").strip()
    parts = [x.strip() for x in value.split(",")]
    values = {}
    formats = []
    for i, part in enumerate(parts, start=1):
        parsed = pressureAttribute(part)
        name_map = {
            name: name.replace("pressure", f"pressure {i}", 1)
            for name in parsed["values"]
        }
        for name, parsed_value in parsed["values"].items():
            values[name_map[name]] = parsed_value
        format = parsed["format"]
        for old, new in name_map.items():
            format = format.replace("${" + old + "}", "${" + new + "}")
        formats.append(format)
    return {
        "format": ", ".join(formats),
        "primary": "pressure 1 min" if any(_rangeParts(part) or part.startswith("±") for part in parts) else "pressure 1",
        "values": values
    }

def pressureTemperatureDriftAttribute(value):
    return scalarAttribute(value, readPressureTemperatureDrift, "pressure_temperature_drift", "pressure drift")

def illuminanceAttribute(value):
    return scalarAttribute(value, readIlluminance, "illuminance", "illuminance")

def _readMechanicalLength(value):
    value = str(value).strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    labeled = re.search(r"([+-]?\d+(?:\.\d+)?)\s*(nm|um|mm|cm|m|mil|in|inch|inches)\s*$", value, flags=re.I)
    if labeled is not None and labeled.group(0).strip() != value:
        value = labeled.group(0)
    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?", value):
        value += "mm"
    elif re.fullmatch(r"[+-]?\d+(?:\.\d+)?\s*m", value, flags=re.I):
        value += "m"
    return readLength(value)

def mechanicalLengthAttribute(value):
    return rangeOrScalarAttribute(value, _readMechanicalLength, "length", "length")

def inchLengthAttribute(value):
    value = str(value).strip()
    if value not in ["-", "--", "null"] and not re.search(r"[a-z\"]\s*$", value, flags=re.I):
        value += "in"
    return lengthAttribute(value)

def mechanicalLengthRangeListAttribute(value, name="length"):
    value = str(value).replace(";", ",").strip()
    parts = [x.strip() for x in value.split(",")]
    values = {}
    formats = []
    for i, part in enumerate(parts, start=1):
        parsed = rangeOrScalarAttribute(part, _readMechanicalLength, "length", f"{name} {i}")
        values.update(parsed["values"])
        formats.append(parsed["format"])
    return {
        "format": ", ".join(formats),
        "primary": f"{name} 1 min" if any(_rangeParts(part) for part in parts) else f"{name} 1",
        "values": values
    }

def boardSpaceAttribute(value):
    value = str(value).strip()
    if "x" not in value.lower():
        return mechanicalLengthAttribute(value)
    parts = [x.strip() for x in re.split(r"\s*x\s*", value, flags=re.I) if x.strip()]
    unit = next((re.search(r"(nm|um|mm|cm|m|mil|in|inch|inches)\s*$", part, flags=re.I).group(1) for part in parts if re.search(r"(nm|um|mm|cm|m|mil|in|inch|inches)\s*$", part, flags=re.I)), "mm")
    values = {}
    for index, part in enumerate(parts, start=1):
        if re.search(r"(nm|um|mm|cm|m|mil|in|inch|inches)\s*$", part, flags=re.I) is None:
            part += unit
        values[f"length {index}"] = [_readMechanicalLength(part), "length"]
    return {
        "format": " x ".join("${" + f"length {i}" + "}" for i in range(1, len(parts) + 1)),
        "primary": "length 1",
        "values": values
    }

def mechanicalDimensionsAttribute(value):
    value = str(value).strip()
    if value in ["-", "--", "null"]:
        return mechanicalLengthAttribute(value)
    value = value.replace("×", "x").replace("*", "x").replace("φ", "")
    parts = [x.strip() for x in re.split(r"\s*x\s*", value, flags=re.I) if x.strip()]
    if len(parts) == 1:
        return mechanicalLengthAttribute(parts[0])
    unit = next(
        (
            re.search(r"(nm|um|mm|cm|m|mil|in|inch|inches)\s*$", part, flags=re.I).group(1)
            for part in parts
            if re.search(r"(nm|um|mm|cm|m|mil|in|inch|inches)\s*$", part, flags=re.I)
        ),
        "mm",
    )
    values = {}
    for index, part in enumerate(parts, start=1):
        if re.search(r"(nm|um|mm|cm|m|mil|in|inch|inches)\s*$", part, flags=re.I) is None:
            part += unit
        values[f"length {index}"] = [_readMechanicalLength(part), "length"]
    return {
        "format": " x ".join("${" + f"length {i}" + "}" for i in range(1, len(parts) + 1)),
        "primary": "length 1",
        "values": values
    }

def parenthesizedMetricDimensionsAttribute(value):
    value = str(value)
    match = re.search(r"\(([^)]*mm[^)]*)\)", value, flags=re.I)
    if match is None:
        return mechanicalDimensionsAttribute(value)
    return mechanicalDimensionsAttribute(match.group(1))

def tolerancedLengthAttribute(value):
    value = str(value).strip()
    value = value.replace("≤", "")
    value = re.sub(r"\((mm|cm|m|um|µm|μm|nm|in|inch|inches|mil)\)$", r"\1", value, flags=re.I)
    if "±" not in value:
        return lengthAttribute(value)
    nominal, tolerance = [x.strip() for x in value.split("±", 1)]
    if nominal == "":
        nominal = "0"
    nominal_unit = re.search(r"(nm|um|mm|cm|m|mil|in|inch|inches)\s*$", nominal, flags=re.I)
    tolerance_unit = re.search(r"(nm|um|mm|cm|m|mil|in|inch|inches)\s*$", tolerance, flags=re.I)
    if nominal_unit is None and tolerance_unit is not None:
        nominal += tolerance_unit.group(1)
    elif tolerance_unit is None and nominal_unit is not None:
        tolerance += nominal_unit.group(1)
    length = readLength(nominal)
    tolerance_value = readLength(tolerance)
    return {
        "format": "${length} ± ${length tolerance}",
        "primary": "length",
        "values": {
            "length": [length, "length"],
            "length tolerance": [tolerance_value, "length"],
            "length min": [length - tolerance_value, "length"],
            "length max": [length + tolerance_value, "length"],
        }
    }

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
    value = re.sub(r"\s*AWG$", "", value, flags=re.I)
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

def wireRodAwgAttribute(value):
    value = str(value).strip()
    match = re.search(r"([0-9]+(?:/[0-9]+)?(?:\s*~\s*[0-9]+(?:/[0-9]+)?)?)\s*AWG", value, flags=re.I)
    if match is None:
        raise ValueError(f"Cannot parse wire rod AWG {value}")
    return awgRangeListAttribute(match.group(1))

def coreWireGaugeAttribute(value):
    value = str(value).strip()
    awg = re.search(r"(?:AWG\s*|\b)([0-9]+(?:/[0-9]+)?(?:\s*~\s*[0-9]+(?:/[0-9]+)?)?)\s*AWG\b|AWG\s*([0-9]+)", value, flags=re.I)
    if awg is not None:
        gauge = next(group for group in awg.groups() if group is not None)
        parsed = awgRangeListAttribute(gauge)
        return {
            **parsed,
            "primary": parsed["primary"],
        }

    diameter = re.search(r"(?:Diameter|OD)\s*:?\s*([0-9]+(?:\.[0-9]+)?)\s*(mm)?", value, flags=re.I)
    if diameter is None:
        raise ValueError(f"Cannot parse core wire gauge {value}")
    return scalarAttribute(diameter.group(1) + "mm", readLength, "length", "diameter")

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

def trailingTimeAttribute(value):
    value = str(value).split(",")[-1].strip()
    return timeAttribute(value)

def readYearDuration(value):
    value = str(value).strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    value = re.sub(r"\s*years?$", "", value, flags=re.I).strip()
    return float(value) * 365 * 24 * 3600

def yearDurationAttribute(value):
    return rangeOrScalarAttribute(value, readYearDuration, "time", "time")

def percentageAttribute(value):
    return rangeOrScalarAttribute(value, readPercentage, "percentage", "percentage")

def percentageRangeAttribute(value, name="percentage"):
    value = str(value).strip()
    if value.startswith("±"):
        value = "-" + value[1:] + "~+" + value[1:]
    return rangeOrScalarAttribute(value, readPercentage, "percentage", name)

def percentageRangeListAttribute(value):
    value = str(value).replace(";", ",")
    parts = [x.strip() for x in value.split(",")]
    values = {}
    formats = []
    for i, part in enumerate(parts, start=1):
        parsed = percentageRangeAttribute(part, f"percentage {i}")
        values.update(parsed["values"])
        formats.append(parsed["format"])
    return {
        "format": ", ".join(formats),
        "primary": f"percentage 1 min" if any(_rangeParts(part) or part.startswith("±") for part in parts) else "percentage 1",
        "values": values
    }

def flexiblePercentageAttribute(value):
    value = str(value).strip()
    signed_range = re.fullmatch(r"([+-]?\d+(?:\.\d+)?%)\s*[;~]\s*([+-]?\d+(?:\.\d+)?%)", value)
    if signed_range:
        return percentageRangeAttribute("~".join(signed_range.groups()))
    return percentageRangeListAttribute(value) if _hasCompoundValues(value) else percentageRangeAttribute(value)

def powerTemperatureDriftListAttribute(value, name="power drift"):
    value = str(value).replace(";", ",")
    return scalarListAttribute(value, readPowerTemperatureDrift, "power_temperature_drift", name)

def dissipationFactorAttribute(value):
    value = str(value).strip()
    if "%" in value or value in ["-", "--", "null"]:
        return flexiblePercentageAttribute(value)
    return powerTemperatureDriftListAttribute(value) if _hasCompoundValues(value) else scalarAttribute(
        value,
        readPowerTemperatureDrift,
        "power_temperature_drift",
        "power drift",
    )

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

def _normalizeTemperatureValue(value):
    value = str(value).replace("°C", "℃")
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"\(.*?\)", "", value)
    value = re.sub(r"\s+to\s+", "~", value, flags=re.I)
    value = re.sub(r"^~(?=\d)", "-", value)
    value = re.sub(r"(?<=\d)℃?\s*-\s*(?=[+]?\d)", "~", value)
    return value.strip()

def _readCelsius(value):
    value = str(value).replace("°C", "℃").strip()
    if value in ["-", "--", "null"]:
        return "NaN"
    value = value.rstrip("℃").strip()
    return float(value)

def temperatureRangeAttribute(value):
    value = str(value).replace("°C", "℃")
    if value.strip() in ["-", "--", "null"]:
        return scalarAttribute("-", lambda x: "NaN", "temperature", "temperature")
    value = erase(value, ["@"])
    value = _normalizeTemperatureValue(value)
    if _hasCompoundValues(value):
        raise ValueError(f"Compound temperature value cannot be represented as scalar range: {value}")
    if value.strip().startswith("±"):
        value = "-" + value.strip()[1:] + "~+" + value.strip()[1:]
    if "~" in value or ".." in value:
        return rangeOrScalarAttribute(value, _readCelsius, "temperature", "temperature")
    return scalarAttribute(value, _readCelsius, "temperature", "temperature")

def solderingTemperatureAttribute(value):
    value = _normalizeTemperatureValue(value)
    if value.strip() in ["-", "--", "null"]:
        return scalarAttribute("-", lambda x: "NaN", "temperature", "temperature")

    if "@" not in value:
        return temperatureRangeAttribute(value)

    temperature, duration = [x.strip() for x in value.split("@", 1)]
    parsed = temperatureRangeAttribute(temperature)
    parsed_duration = rangeOrScalarAttribute(duration, readTime, "time", "time")

    values = dict(parsed["values"])
    values.update(parsed_duration["values"])
    return {
        "format": f'{parsed["format"]} @ {parsed_duration["format"]}',
        "primary": parsed["primary"],
        "values": values,
    }

def temperatureListAttribute(value):
    value = str(value).replace("°C", "℃")
    parts = [x.strip() for x in re.split(r"[,;/]", value) if x.strip()]
    unit = next((re.search(r"℃", part).group(0) for part in parts if "℃" in part), "℃")
    parts = [part if "℃" in part else part + unit for part in parts]
    values = {}
    formats = []
    for index, part in enumerate(parts, start=1):
        parsed = temperatureRangeAttribute(part)
        for name, parsed_value in parsed["values"].items():
            values[f"{name} {index}"] = parsed_value
        formats.append(parsed["format"].replace("${temperature", "${temperature " + str(index)))
    return {
        "format": ", ".join(formats),
        "primary": "temperature 1",
        "values": values,
    }

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

def voltageAtElectricalConditionsAttribute(value, name="voltage"):
    value = str(value).strip()
    if "@" not in value:
        return voltageListAttribute(value, name)

    voltage_part, condition_part = [x.strip() for x in value.split("@", 1)]
    values = {name: [readVoltage(voltage_part), "voltage"]}
    formats = ["${" + name + "}"]
    current_count = 0
    voltage_count = 0
    unknown_count = 0
    for condition in [x.strip() for x in condition_part.split(",") if x.strip()]:
        if re.search(r"v", condition, flags=re.I):
            voltage_count += 1
            key = f"condition voltage {voltage_count}"
            values[key] = [readVoltage(condition), "voltage"]
        elif re.search(r"a", condition, flags=re.I):
            current_count += 1
            key = f"condition current {current_count}"
            values[key] = [readCurrent(condition), "current"]
        else:
            unknown_count += 1
            key = f"condition {unknown_count}"
            values[key] = [condition, "identifier"]
        formats.append("${" + key + "}")
    return {
        "format": " @ ".join([formats[0], ", ".join(formats[1:])]) if len(formats) > 1 else formats[0],
        "primary": name,
        "values": values
    }

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

def readVoltageAmplitude(value):
    value = str(value).strip()
    value = re.sub(r"(?:p-p|pp|rms)$", "", value, flags=re.I).strip()
    return readVoltage(value)

def voltageAmplitudeListAttribute(value, name="voltage"):
    value = str(value).replace(";", ",")
    return scalarListAttribute(value, readVoltageAmplitude, "voltage", name)

def voltageOrDecibelListAttribute(value, name="ripple"):
    value = str(value).replace(";", ",")
    parts = [x.strip() for x in value.split(",")]
    values = {}
    formats = []
    for index, part in enumerate(parts, start=1):
        value_name = name if len(parts) == 1 else f"{name} {index}"
        if "db" in part.lower():
            values[value_name] = [readDecibel(part), "decibel"]
        else:
            values[value_name] = [readVoltageAmplitude(part), "voltage"]
        formats.append("${" + value_name + "}")
    return {
        "format": ", ".join(formats),
        "primary": next(iter(values)),
        "values": values
    }

def powerOrDecibelMilliwattListAttribute(value, name="power"):
    value = str(value).replace(";", ",")
    parts = [x.strip() for x in value.split(",")]
    values = {}
    formats = []
    for index, part in enumerate(parts, start=1):
        value_name = name if len(parts) == 1 else f"{name} {index}"
        if "dbm" in part.lower():
            values[value_name] = [readDecibelMilliwatt(part), "decibel_milliwatt"]
        else:
            values[value_name] = [readPower(part), "power"]
        formats.append("${" + value_name + "}")
    return {
        "format": ", ".join(formats),
        "primary": next(iter(values)),
        "values": values
    }

def labeledPowerListAttribute(value, name="power"):
    value = str(value).replace(";", ",")
    parts = [x.strip() for x in value.split(",") if x.strip()]
    values = {}
    formats = []
    for index, part in enumerate(parts, start=1):
        label = None
        value_part = part
        if ":" in part:
            label, value_part = [x.strip() for x in part.split(":", 1)]
        value_name = f"{name} {label}" if label else f"{name} {index}"
        values[value_name] = [readPower(value_part), "power"]
        formats.append("${" + value_name + "}")
    return {
        "format": ", ".join(formats),
        "primary": next(iter(values)),
        "values": values
    }

def voltageOrCurrentListAttribute(value):
    value = str(value).replace(";", ",")
    parts = [x.strip() for x in value.split(",")]
    values = {}
    formats = []
    for index, part in enumerate(parts, start=1):
        value_part = _stripCondition(part)
        is_current = bool(re.search(r"\d\s*(?:[fpnumkKMGT]?A)\b", value_part))
        unit = "current" if is_current else "voltage"
        name = unit if len(parts) == 1 else f"{unit} {index}"
        reader = readCurrent if is_current else readVoltage
        values[name] = [reader(value_part), unit]
        formats.append("${" + name + "}")
    first_unit = "current" if next(iter(values)).startswith("current") else "voltage"
    primary = first_unit if len(parts) == 1 else f"{first_unit} 1"
    return {
        "format": ", ".join(formats),
        "primary": primary,
        "values": values
    }

def voltageSemicolonListAttribute(value, name="voltage"):
    value = str(value)
    parts = [x.strip() for x in value.split(";")]
    if len(parts) <= 1:
        parsed = readVoltage(_stripCondition(value))
        return {
            "format": "${" + name + "}",
            "primary": name,
            "values": {
                name: [parsed, "voltage"]
            }
        }
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

def powerRangeListAttribute(value, name="power"):
    value = str(value).replace(";", ",").strip()
    value = re.sub(r"(?<=W)\s*-\s*(?=\d)", "~", value, flags=re.I)
    parts = [x.strip() for x in value.split(",")]
    values = {}
    formats = []
    for i, part in enumerate(parts, start=1):
        parsed = rangeOrScalarAttribute(part, readPower, "power", f"{name} {i}")
        values.update(parsed["values"])
        formats.append(parsed["format"])
    return {
        "format": ", ".join(formats),
        "primary": f"{name} 1 min" if any(_rangeParts(part) for part in parts) else f"{name} 1",
        "values": values
    }

def outputPowerListAttribute(value):
    value = str(value).replace("×", "x")
    parts = []
    for part in [x.strip() for x in value.split(",")]:
        signal, load = [x.strip() for x in part.split("@", 1)] if "@" in part else (part, None)
        if "+" in signal:
            parts.extend(
                f"{subpart.strip()}@{load}" if load is not None else subpart.strip()
                for subpart in signal.split("+")
            )
        else:
            parts.append(part)
    values = {}
    formats = []
    for i, part in enumerate(parts, start=1):
        if part in ["-", "--", "null"]:
            values[f"power {i}"] = ["NaN", "power"]
            formats.append("${" + f"power {i}" + "}")
            continue
        signal, load = [x.strip() for x in part.split("@", 1)] if "@" in part else (part, None)
        signal = re.sub(r"\([^)]*\)", "", signal).strip()
        prefix_match = re.fullmatch(r"(\d+)\s*x\s*(.+)", signal, flags=re.I)
        if prefix_match is not None and re.search(r"w", prefix_match.group(2), flags=re.I):
            channels, power = prefix_match.groups()
        else:
            match = re.fullmatch(r"(.+?)(?:x\s*(\d+))?", signal, flags=re.I)
            if match is None:
                raise ValueError(f"Cannot parse output power {value}")
            power, channels = match.groups()
        power = power.strip()
        if re.search(r"dBm$", power, flags=re.I):
            values[f"power {i}"] = [readDecibelMilliwatt(power), "decibel_milliwatt"]
        else:
            values[f"power {i}"] = [readPower(power), "power"]
        format_parts = ["${" + f"power {i}" + "}"]
        if channels is not None:
            values[f"channels {i}"] = [float(channels), "count"]
            format_parts.append("x ${" + f"channels {i}" + "}")
        if load is not None:
            values[f"load {i}"] = [readResistance(load), "resistance"]
            format_parts.append("@ ${" + f"load {i}" + "}")
        formats.append(" ".join(format_parts))
    return {
        "format": ", ".join(formats),
        "primary": "power 1",
        "values": values
    }

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

def decibelRangeListAttribute(value, name="level"):
    value = str(value)
    separator = ";" if ";" in value else ","
    parts = [x.strip() for x in value.split(separator)]
    values = {}
    formats = []
    has_range = False
    for i, part in enumerate(parts, start=1):
        signal = part
        frequency = None
        match = re.fullmatch(r"(.*?)@\(?([^)]*)\)?", part)
        if match is not None:
            signal, frequency = match.groups()
        parsed = rangeOrScalarAttribute(signal.strip(), readDecibel, "decibel", f"{name} {i}")
        has_range = has_range or bool(_rangeParts(signal))
        values.update(parsed["values"])
        formatParts = [parsed["format"]]
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
        "primary": f"{name} 1 min" if has_range else f"{name} 1",
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

def ratioAtCurrentVoltageAttribute(value, name="gain"):
    value = str(value).strip()
    values = {}
    formats = []
    for i, part in enumerate([x.strip() for x in value.split(";")], start=1):
        signal = part
        current = None
        voltage = None
        if "@" in part:
            signal, condition = [x.strip() for x in part.split("@", 1)]
            condition = re.sub(r"([munpkKMGT]?A)\.(?=\d)", r"\1,", condition)
            pieces = [x.strip() for x in condition.split(",")]
            if pieces:
                if re.search(r"v", pieces[0], flags=re.I):
                    voltage = pieces[0]
                else:
                    current = pieces[0]
            if len(pieces) > 1:
                if re.search(r"a", pieces[1], flags=re.I):
                    current = pieces[1]
                else:
                    voltage = pieces[1]
        parsed_signal = rangeOrScalarAttribute(signal, readWithSiPrefix, "ratio", f"{name} {i}")
        values.update(parsed_signal["values"])
        format_parts = [parsed_signal["format"]]
        if current is not None:
            values[f"current {i}"] = [readCurrent(current), "current"]
            format_parts.append("@ ${" + f"current {i}" + "}")
        if voltage is not None:
            values[f"voltage {i}"] = [readVoltage(voltage), "voltage"]
            format_parts.append("${" + f"voltage {i}" + "}")
        formats.append(" ".join(format_parts))
    return {
        "format": ", ".join(formats),
        "primary": f"{name} 1",
        "values": values
    }

def ratioAtFrequencyAttribute(value, name="ratio"):
    value = str(value).strip()
    values = {}
    formats = []
    for i, part in enumerate([x.strip() for x in value.split(",")], start=1):
        signal = part
        frequency = None
        if "@" in part:
            signal, frequency = [x.strip() for x in part.split("@", 1)]
        values[f"{name} {i}"] = [readWithSiPrefix(signal), "ratio"]
        format_parts = ["${" + f"{name} {i}" + "}"]
        if frequency is not None:
            values[f"frequency {i}"] = [readFrequency(frequency), "frequency"]
            format_parts.append("@ ${" + f"frequency {i}" + "}")
        formats.append(" ".join(format_parts))
    return {
        "format": ", ".join(formats),
        "primary": f"{name} 1",
        "values": values
    }

def turnsRatioAttribute(value):
    value = str(value).replace(";", ",").strip()
    parts = [x.strip() for x in value.split(",")]
    values = {}
    formats = []
    for i, part in enumerate(parts, start=1):
        terms = [x.strip() for x in part.split(":")]
        for j, term in enumerate(terms, start=1):
            values[f"ratio {i}.{j}"] = [readRatioTerm(term), "ratio"]
        formats.append(":".join("${" + f"ratio {i}.{j}" + "}" for j in range(1, len(terms) + 1)))
    return {
        "format": ", ".join(formats),
        "primary": "ratio 1.1",
        "values": values
    }

def ethernetRateAttribute(value):
    value = str(value).strip()
    if value in ["-", "--", "null"]:
        values = {"data rate 1": ["NaN", "data_rate"]}
    else:
        rates = []
        for number, suffix in re.findall(r"(\d+(?:\.\d+)?)\s*(G|M)?(?=\s*Base|-|/|\b)", value, flags=re.I):
            scale = 1e9 if suffix.lower() == "g" else 1e6
            rates.append(float(number) * scale)
        if not rates:
            raise ValueError(f"Cannot parse Ethernet rate {value}")
        values = {
            f"data rate {i}": [rate, "data_rate"]
            for i, rate in enumerate(rates, start=1)
        }
    return {
        "format": ", ".join("${" + name + "}" for name in values),
        "primary": "data rate 1",
        "values": values
    }

def contactRatingAttribute(value):
    value = str(value).replace(";", ",").strip()
    parts = [x.strip() for x in value.split(",")]
    values = {}
    formats = []
    for i, part in enumerate(parts, start=1):
        if part in ["-", "--", "null"]:
            values[f"current {i}"] = ["NaN", "current"]
            formats.append("${" + f"current {i}" + "}")
            continue
        if "@" in part:
            current, voltage = [x.strip() for x in part.split("@", 1)]
            values[f"current {i}"] = [readCurrent(current), "current"]
            values[f"voltage {i}"] = [readVoltage(voltage), "voltage"]
            formats.append("${" + f"current {i}" + "} @ ${" + f"voltage {i}" + "}")
        else:
            values[f"current {i}"] = [readCurrent(part), "current"]
            formats.append("${" + f"current {i}" + "}")
    return {
        "format": ", ".join(formats),
        "primary": "current 1",
        "values": values
    }

def shrinkageRatioAttribute(value):
    value = str(value).strip()
    values = {}
    if ":" in value:
        parts = [x.strip() for x in value.replace(";", ",").split(",")]
        for i, part in enumerate(parts, start=1):
            if part in ["-", "--", "null"]:
                values[f"ratio {i}"] = ["NaN", "ratio"]
            else:
                numerator, denominator = [readRatioTerm(x) for x in part.split(":", 1)]
                values[f"ratio {i}"] = [numerator / denominator, "ratio"]
    else:
        for label, sign, number in re.findall(r"(Lateral|Longitudinal)\s+Shrinkage\s*([≥≤])\s*([0-9.]+)%", value, flags=re.I):
            name = f"{label.lower()} shrinkage {'min' if sign == '≥' else 'max'}"
            values[name] = [float(number), "percentage"]
    if not values:
        values["ratio"] = ["NaN", "ratio"]
    return {
        "format": ", ".join("${" + name + "}" for name in values),
        "primary": next(iter(values)),
        "values": values
    }

def fractionListAttribute(value, name="ratio"):
    value = str(value).replace(";", ",").strip()
    values = {}
    for i, part in enumerate([x.strip() for x in value.split(",")], start=1):
        part = part.split("@", 1)[0].strip()
        if part in ["-", "--", "null"]:
            ratio = "NaN"
        elif "/" in part:
            numerator, denominator = [float(x.strip()) for x in part.split("/", 1)]
            ratio = numerator / denominator
        else:
            ratio = readWithSiPrefix(part)
        values[f"{name} {i}"] = [ratio, "ratio"]
    return {
        "format": ", ".join("${" + key + "}" for key in values),
        "primary": f"{name} 1",
        "values": values
    }

def voltageRatioAttribute(value):
    value = str(value).replace(";", ",").strip()
    values = {}
    formats = []
    for i, part in enumerate([x.strip() for x in value.split(",")], start=1):
        if "/" in part:
            numerator, denominator = [x.strip() for x in part.split("/", 1)]
            values[f"voltage {i}.1"] = [readVoltage(numerator), "voltage"]
            values[f"voltage {i}.2"] = [readVoltage(denominator), "voltage"]
            formats.append("${" + f"voltage {i}.1" + "}/${" + f"voltage {i}.2" + "}")
        else:
            parsed = voltageRangeAttribute(part, f"voltage {i}")
            values.update(parsed["values"])
            formats.append(parsed["format"])
    return {
        "format": ", ".join(formats),
        "primary": next(iter(values)),
        "values": values
    }

def frequencyOrVoltageRangeAttribute(value):
    value = str(value).strip()
    if re.search(r"Hz", value, flags=re.I):
        value = re.sub(r"(?<=\d)-(?=\d)", "~", value)
        return frequencyRangeListAttribute(value)
    return voltageRatioAttribute(value)

def decibelMilliwattRangeAttribute(value, name="level"):
    value = str(value).strip()
    return rangeOrScalarAttribute(value, readDecibelMilliwatt, "decibel_milliwatt", name)

def decibelMilliwattPerHertzListAttribute(value, name="noise"):
    value = str(value).replace(";", ",")
    return scalarListAttribute(value, readDecibelMilliwattPerHertz, "decibel_milliwatt_per_hertz", name)

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

def gainListAttribute(value):
    value = str(value).strip()
    parts = [x.strip() for x in value.split(",")]
    values = {}
    formats = []
    has_range = False
    for i, part in enumerate(parts, start=1):
        name = f"gain {i}" if len(parts) > 1 else "gain"
        if "db" in part.lower():
            parsed = rangeOrScalarAttribute(part, readDecibel, "decibel", name)
        else:
            parsed = rangeOrScalarAttribute(part, readRatio, "ratio", name)
        has_range = has_range or bool(_rangeParts(part))
        values.update(parsed["values"])
        formats.append(parsed["format"])
    primary_name = "gain 1" if len(parts) > 1 else "gain"
    return {
        "format": ", ".join(formats),
        "primary": primary_name + " min" if has_range else primary_name,
        "values": values
    }

def colonRatioListAttribute(value, name="ratio"):
    value = str(value).strip()
    parts = [x.strip() for x in value.split(",")]
    values = {}
    for i, part in enumerate(parts, start=1):
        value_name = f"{name} {i}" if len(parts) > 1 else name
        values[value_name] = [readRatio(part), "ratio"]
    primary_name = f"{name} 1" if len(parts) > 1 else name
    return {
        "format": ", ".join("${" + (f"{name} {i}" if len(parts) > 1 else name) + "}" for i in range(1, len(parts) + 1)),
        "primary": primary_name,
        "values": values
    }

def dynamicRangeAttribute(value):
    value = str(value).strip()
    if "db" in value.lower():
        return decibelTokenListAttribute(value, "dynamic range")
    return colonRatioListAttribute(value, "dynamic range")

def switchCircuitAttribute(value):
    value = str(value).strip()
    if value in ["-", "--", "null"] or re.fullmatch(r"\d+(?:\.\d+)?\s*:\s*\d+(?:\.\d+)?", value):
        return colonRatioListAttribute(value, "ratio")
    return stringAttribute(value)

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

def diodeCapacitanceAttribute(value):
    value = str(value).strip()
    if value in ["-", "--", "null"]:
        return scalarAttribute(value, readCapacitance, "capacitance", "capacitance")

    measurement_re = re.compile(
        r"(?P<cap>[+-]?\d+(?:\.\d+)?\s*[fpnumkKMGT]?F)"
        r"(?:\s*@\s*(?P<conditions>.*?))?"
        r"(?=,\s*[+-]?\d+(?:\.\d+)?\s*[fpnumkKMGT]?F|$)",
        flags=re.I,
    )
    matches = list(measurement_re.finditer(value))
    if not matches:
        raise ValueError(f"Cannot parse diode capacitance {value}")

    values = {}
    formats = []
    multiple = len(matches) > 1
    for index, match in enumerate(matches, start=1):
        suffix = f" {index}" if multiple else ""
        cap_name = f"capacitance{suffix}"
        values[cap_name] = [readCapacitance(match.group("cap")), "capacitance"]
        format_parts = ["${" + cap_name + "}"]

        conditions = match.group("conditions")
        if conditions:
            for condition in [x.strip() for x in conditions.split(",") if x.strip()]:
                if re.search(r"V\s*$", condition, flags=re.I):
                    voltage_name = f"voltage{suffix}"
                    values[voltage_name] = [readVoltage(condition), "voltage"]
                    format_parts.append("@ ${" + voltage_name + "}")
                elif re.search(r"Hz\s*$", condition, flags=re.I):
                    frequency_name = f"frequency{suffix}"
                    values[frequency_name] = [readFrequency(condition), "frequency"]
                    format_parts.append("@ ${" + frequency_name + "}")
        formats.append(" ".join(format_parts))

    return {
        "format": ", ".join(formats),
        "primary": "capacitance 1" if multiple else "capacitance",
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
    def hasCurrentUnit(v):
        return bool(re.search(r"a\b", v.strip(), re.I))

    def hasVoltageUnit(v):
        return bool(re.search(r"v\b", v.strip(), re.I))

    def splitResistanceValues(resistance):
        resistance = resistance.strip()
        ratio = re.fullmatch(
            r"([+-]?\d+(?:\.\d+)?)\s*/\s*([+-]?\d+(?:\.\d+)?)([a-zA-ZμµΩ]*)",
            resistance,
        )
        if ratio:
            first, second, unit = ratio.groups()
            return [first + unit, second + unit]
        return [resistance]

    def splitConditions(condition):
        condition = condition.strip().lstrip("=").strip()
        if "," in condition or "，" in condition:
            first, second = [x.strip() for x in re.split(r"[,，]", condition, 1)]
        else:
            first, second = condition, "-"

        first_is_current = hasCurrentUnit(first)
        first_is_voltage = hasVoltageUnit(first)
        second_is_current = hasCurrentUnit(second)
        second_is_voltage = hasVoltageUnit(second)

        if first_is_current or second_is_voltage:
            current, voltage = first, second
        elif first_is_voltage or second_is_current:
            voltage, current = first, second
        else:
            voltage, current = first, second

        if current == "" or "·" in current:
            current = "-"
        if voltage == "":
            voltage = "-"
        return voltage, current

    def readRds(v):
        if v == "-":
            return [("NaN", "NaN", "NaN")]
        v = v.strip()
        if "@" in v:
            resistance, condition = v.split("@", 1)
            voltage, current = splitConditions(condition)
        else:
            match = re.fullmatch(
                    r"\s*([\w.Ω]+)\s*(?:\s+([-+~\w.]+?)\s*(?:(?<=\d)([.\w]+)\s*)?)?",
                    v,
                    re.I
                )
            if match is None:
                raise ValueError(f"Cannot parse RDS tuple {v}")
            resistance, voltage, current = match.groups()

        voltage = voltage.strip() if voltage is not None else "-"
        current = current.strip() if current is not None else "-"
        if current == "" or "·" in current:
            current = "-"
        if current != "-" and "Ω" in current and not hasCurrentUnit(current):
            current = current.replace("Ω", "A")

        if current != "-" and not hasCurrentUnit(current):
            current += "A"
        if voltage != "-" and not hasVoltageUnit(voltage):
            voltage += "V"
        if "~" in voltage:
            voltage = voltage.split("~")[-1]

        return [
            (readResistance(resistance), readCurrent(current), readVoltage(voltage))
            for resistance in splitResistanceValues(resistance)
        ]

    if ";" in value:
        s = value.split(";")
    elif value.count(",") == 3:
        # Double P & N MOSFET without semicolon separator.
        s = value.split(",")
        s = [s[0] + "," + s[1], s[2] + "," + s[3]]
    else:
        s = [value]

    measurements = []
    for part in s:
        measurements.extend(readRds(part))

    if len(measurements) > 1:
        if ";" in value:
            separator = "; "
        else:
            separator = ", "
        values = {}
        formats = []
        for index, (rds, ids, vgs) in enumerate(measurements, start=1):
            values[f"Rds {index}"] = [rds, "resistance"]
            values[f"Id {index}"] = [ids, "current"]
            values[f"Vgs {index}"] = [vgs, "voltage"]
            formats.append("${Rds " + str(index) + "} @ ${Vgs " + str(index) + "}, ${Id " + str(index) + "}")
        return {
            "format": separator.join(formats),
            "primary": "Rds 1",
            "values": values
        }

    rds, ids, vgs = measurements[0]
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

def labeledAngleListAttribute(value):
    value = str(value).replace(";", ",")
    parts = [x.strip() for x in value.split(",")]
    values = {}
    formats = []
    for index, part in enumerate(parts, start=1):
        label = str(index)
        if ":" in part:
            label, part = [x.strip() for x in part.split(":", 1)]
        name = f"angle {label}"
        values[name] = [readAngle(part), "angle"]
        formats.append("${" + name + "}")
    return {
        "format": ", ".join(formats),
        "primary": next(iter(values)),
        "values": values
    }

def angleRangeListAttribute(value):
    value = str(value).replace(";", ",").strip()
    parts = [x.strip() for x in value.split(",")]
    values = {}
    formats = []
    for index, part in enumerate(parts, start=1):
        if part.startswith("±"):
            part = "-" + part[1:] + "~+" + part[1:]
        parsed = rangeOrScalarAttribute(part, readAngle, "angle", f"angle {index}")
        values.update(parsed["values"])
        formats.append(parsed["format"])
    return {
        "format": ", ".join(formats),
        "primary": "angle 1 min" if any(_rangeParts(part) or part.startswith("±") for part in parts) else "angle 1",
        "values": values
    }

def angleOrDecibelListAttribute(value, name="angle"):
    value = str(value).replace(";", ",")
    parts = [x.strip() for x in value.split(",")]
    values = {}
    formats = []
    for index, part in enumerate(parts, start=1):
        value_name = name if len(parts) == 1 else f"{name} {index}"
        if "db" in part.lower():
            values[value_name] = [readDecibel(part), "decibel"]
        else:
            values[value_name] = [readAngle(part), "angle"]
        formats.append("${" + value_name + "}")
    return {
        "format": ", ".join(formats),
        "primary": next(iter(values)),
        "values": values
    }

def forceAttribute(value):
    return scalarAttribute(value, readForce, "force", "force")

def forceRangeListAttribute(value):
    value = str(value).replace(";", ",").strip()
    parts = [x.strip() for x in value.split(",")]
    values = {}
    formats = []
    for i, part in enumerate(parts, start=1):
        signal = part.split("@", 1)[0].strip()
        if signal.startswith("±"):
            signal = "-" + signal[1:] + "~+" + signal[1:]
        parsed = rangeOrScalarAttribute(signal, readForce, "force", f"force {i}")
        values.update(parsed["values"])
        formats.append(parsed["format"])
    return {
        "format": ", ".join(formats),
        "primary": "force 1 min" if any(_rangeParts(part.split("@", 1)[0]) or part.startswith("±") for part in parts) else "force 1",
        "values": values
    }

def airFlowAttribute(value):
    return scalarAttribute(value, readAirFlow, "air_flow", "air flow")

def percentageTemperatureDriftAttribute(value):
    value = str(value).strip()
    if value.startswith("±"):
        parsed = readPercentageTemperatureDrift(value)
        return {
            "format": "${drift min} ~ ${drift max}",
            "primary": "drift min",
            "values": {
                "drift min": [-parsed, "percentage_per_temperature"],
                "drift max": [parsed, "percentage_per_temperature"],
            }
        }
    return scalarAttribute(value, readPercentageTemperatureDrift, "percentage_per_temperature", "drift")

def humidityAttribute(value):
    value = str(value).strip()
    value = re.sub(r"%\s*RH", "%", value, flags=re.I)
    return flexiblePercentageAttribute(value)

def accuracyAttribute(value):
    value = str(value).strip()
    if value in ["-", "--", "null"]:
        return scalarAttribute(value, readLength, "length", "accuracy")
    if "db" in value.lower():
        parsed = percentageRangeAttribute(value.replace("dB", "%").replace("db", "%"), "accuracy")
        values = {
            name: [amount, "decibel"]
            for name, (amount, _unit) in parsed["values"].items()
        }
        return {
            "format": parsed["format"],
            "primary": parsed["primary"],
            "values": values
        }
    grade = re.fullmatch(r"(?:Grade|Level)\s+(\d+(?:\.\d+)?)", value, flags=re.I)
    if grade is not None:
        return {
            "format": "${accuracy grade}",
            "primary": "accuracy grade",
            "values": {"accuracy grade": [float(grade.group(1)), "ratio"]}
        }
    return scalarAttribute(value, readLength, "length", "accuracy")

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
        value = value.strip()
        if "@" in value:
            q, v = [x.strip() for x in value.split("@", 1)]
        else:
            q = value
            v = None

        if q:
            q = readCharge(q.strip())
        else:
            q = "NaN"

        if v is not None:
            v = v.strip().split(",")[-1]
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
