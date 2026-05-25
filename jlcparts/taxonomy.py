import re
import unicodedata
from dataclasses import dataclass


ACRONYMS = {
    "ac", "adc", "afe", "afes", "bjt", "can", "cbb", "cpld", "cmrr", "dac", "dc", "dcr", "dds",
    "ddr", "din", "dp", "dsc", "dsp", "dvi", "emc", "emi", "esd", "esr",
    "ffc", "fet", "fpga", "fpc", "gbp", "gdt", "gnss",
    "hdmi", "hdsc", "ic", "ics", "id", "idc", "ieee", "if", "igbt", "io", "ios", "iq", "ir", "irda",
    "jfet", "lan", "lcd", "lc", "ldo", "led", "lin", "lna",
    "lvds", "mcu", "mcus", "mems", "mlcc", "mos", "mosfet", "mosfets", "mpu",
    "mpus", "ntc", "nxp", "ocxo", "ocxos", "oled", "pcb", "pci", "pcie", "pll", "pmic",
    "poe", "ptc", "qg", "rc", "rf", "rfi", "rfid", "rj11", "rj45", "rlc", "rlcs",
    "rca", "rms", "rgb", "rs", "rtc", "sas", "sata", "saw", "sbr", "scr", "sd", "sim", "smd", "smt", "soc",
    "socs", "spi", "spds", "ta", "tc", "tcr", "tcxo", "tcxos", "tco", "tpd", "tss", "tvs", "uart", "usb",
    "uv", "vbe", "vce", "vceo", "vebo", "vces", "vdss", "vds", "vf", "vga", "vge", "vgs",
    "vih", "vil", "voh", "vol", "vos", "vr", "vrms", "vrwm", "vz", "vco", "vcos", "vcxo", "vcxos", "vfd", "xlr",
    "ciss", "coss", "crss", "ipp", "isat", "zzt",
}

SMALL_WORDS = {"and", "or", "of", "for", "to", "the", "with", "in", "on"}
SPECIAL_WORDS = {
    "ics": "ICs",
    "afes": "AFEs",
    "leds": "LEDs",
    "mcus": "MCUs",
    "mpus": "MPUs",
    "cplds": "CPLDs",
    "dscs": "DSCs",
    "fpgas": "FPGAs",
    "gan": "GaN",
    "hemt": "HEMT",
    "iot": "IoT",
    "lora": "LoRa",
    "ocxos": "OCXOs",
    "opamps": "OpAmps",
    "pcis": "PCIs",
    "pcie": "PCIe",
    "pcies": "PCIes",
    "pd": "Pd",
    "pgas": "PGAs",
    "ppp": "Ppp",
    "rds": "RDS",
    "rlcs": "RLCs",
    "mlcc": "MLCC",
    "socs": "SOCs",
    "spds": "SPDs",
    "ssos": "SSOs",
    "tcxos": "TCXOs",
    "vcxos": "VCXOs",
    "vcos": "VCOs",
    "vgas": "VGAs",
    "wifi": "WiFi",
}


def _split_camel_case(value):
    value = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", value)
    return value


def taxonomy_key(value):
    value = (value or "").strip()
    value = unicodedata.normalize("NFKC", value)
    value = value.replace("（", "(").replace("）", ")")
    value = value.replace("，", ",")
    value = value.replace("?", " ")
    value = _split_camel_case(value)
    value = value.replace("&", " and ")
    value = value.replace("/", " / ")
    value = value.replace(",", " ")
    value = value.replace("-", " ")
    value = re.sub(r"[^\w()+]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.casefold().strip()


def _format_word(word, first=False):
    lower = word.casefold()
    if lower in SPECIAL_WORDS:
        return SPECIAL_WORDS[lower]
    if lower in ACRONYMS:
        return lower.upper()
    if lower in SMALL_WORDS and not first:
        return lower
    if re.match(r"^[a-z]+\d+$", lower):
        return lower.upper()
    return lower[:1].upper() + lower[1:]


def clean_label(value):
    value = (value or "").strip()
    if not value:
        return "Uncategorized"
    value = unicodedata.normalize("NFKC", value)
    value = value.replace("（", "(").replace("）", ")")
    value = value.replace("，", ",")
    value = value.replace("?", " ")
    value = _split_camel_case(value)
    value = value.replace("&", " and ")
    value = re.sub(r"\s*/\s*", " / ", value)
    value = re.sub(r"\s+", " ", value).strip()

    result = []
    word_index = 0
    for part in re.split(r"(\W+)", value):
        if re.match(r"^\w+$", part):
            result.append(_format_word(part, first=word_index == 0))
            word_index += 1
        else:
            result.append(part)
    return "".join(result)


_CATEGORY_ALIASES_RAW = {
    "ADC/DAC/Data Conversion": "Data Converters",
    "Analog ICs": "Data Converters",
    "Data Acquisition": "Data Converters",
    "data converters": "Data Converters",
    "Data Converters": "Data Converters",

    "Amplifiers": "Amplifiers and Comparators",
    "Amplifiers/Comparators": "Amplifiers and Comparators",
    "Operational Amplifier/Comparator": "Amplifiers and Comparators",

    "Audio Components/Vibration Motors": "Audio Products and Motors",
    "Audio Products / Vibration Motors": "Audio Products and Motors",
    "Audio Products/Micromotors": "Audio Products and Motors",
    "audio products/micromotors": "Audio Products and Motors",
    "Audio Products/Motors": "Audio Products and Motors",

    "Bead/Filter/EMI Optimization": "Filters and EMI Optimization",
    "Filters": "Filters and EMI Optimization",
    "Filters/EMI Optimization": "Filters and EMI Optimization",
    "filters/emi optimization": "Filters and EMI Optimization",

    "Circuit Protection": "Circuit Protection",
    "circuit protection": "Circuit Protection",
    "TVS/Fuse/Board Level Protection": "Circuit Protection",

    "Clock And Timing": "Clock and Timing",
    "Clock and Timing": "Clock and Timing",
    "clock and timing": "Clock and Timing",
    "Clock/Timing": "Clock and Timing",
    "RTC/Clock Chip": "Clock and Timing",

    "Communication Interface Chip": "Interface ICs",
    "Communication Interface Chip/UART/485/232": "Interface ICs",
    "Interface": "Interface ICs",
    "Interface ICs": "Interface ICs",

    "IoT/Communication Modules": "IoT / Communication Modules",

    "Crystal Oscillator/Oscillator/Resonator": "Crystals, Oscillators and Resonators",
    "Crystals": "Crystals, Oscillators and Resonators",
    "Crystals, Oscillators, Resonators": "Crystals, Oscillators and Resonators",
    "Crystals/Oscillators/Resonators": "Crystals, Oscillators and Resonators",
    "crystals/oscillators/resonators": "Crystals, Oscillators and Resonators",
    "Resonators/Oscillators": "Crystals, Oscillators and Resonators",

    "Display Modules / LED Drivers / Display Drivers": "Displays and LED Drivers",
    "display modules / led drivers / display drivers": "Displays and LED Drivers",
    "Display Screen": "Displays and LED Drivers",
    "Displays": "Displays and LED Drivers",
    "LED Drivers": "Displays and LED Drivers",
    "Nixie Tube Driver/LED Driver": "Displays and LED Drivers",

    "Embedded Processors & Controllers": "Embedded Processors and Controllers",
    "Single Chip Microcomputer/Microcontroller": "Embedded Processors and Controllers",

    "Gallium Nitride (GaN) Devices": "Gallium Nitride (GaN) Devices",

    "Inductors & Chokes & Transformers": "Inductors, Coils and Transformers",
    "Inductors, Coils, Chokes": "Inductors, Coils and Transformers",
    "Inductors/Coils/Transformers": "Inductors, Coils and Transformers",
    "inductors/coils/transformers": "Inductors, Coils and Transformers",

    "Key/Switch": "Switches",
    "Pushbutton Switches & Relays": "Switches",
    "Switches": "Switches",
    "switches": "Switches",

    "LED/Photoelectric Devices": "Optoelectronics",
    "Optocoupler": "Optoelectronics",
    "Optocoupler/LED/Digital Tube/Photoelectric Device": "Optoelectronics",
    "Optocouplers & LEDs & Infrared": "Optoelectronics",
    "Optoelectronics": "Optoelectronics",
    "optoelectronics": "Optoelectronics",
    "Optoisolators": "Optoelectronics",
    "Photoelectric Devices": "Optoelectronics",

    "Power Management": "Power Management",
    "Power Management (PMIC)": "Power Management",
    "Power Management ICs": "Power Management",
    "Power Supply Chip": "Power Management",

    "Radio Frequency Chip/Antenna": "RF and Wireless",
    "RF & Radio": "RF and Wireless",
    "RF And Wireless": "RF and Wireless",

    "Transistors": "Transistors and Thyristors",
    "Transistors/Thyristors": "Transistors and Thyristors",
    "Triode/MOS Tube/Transistor": "Transistors and Thyristors",
}

_SUBCATEGORY_ALIASES_RAW = {
    "AC-DC Controllers & Regulators": "AC-DC Controllers and Regulators",
    "AC-DC Controllers And Regulators": "AC-DC Controllers and Regulators",
    "Analog To Digital Converters (ADC)": "Analog to Digital Converters (ADCs)",
    "Analog To Digital Converters (ADCs)": "Analog to Digital Converters (ADCs)",
    "Battery Management": "Battery Management ICs",
    "Battery Management ICs": "Battery Management ICs",
    "Bipolar (BJT)": "Bipolar Transistors - BJT",
    "Bipolar Transistors - BJT": "Bipolar Transistors - BJT",
    "Clock Generators / Frequency Synthesizers / PLL": "Clock Generators / Frequency Synthesizers / PLL",
    "Clock Generators, PLLs, Frequency Synthesizers": "Clock Generators / Frequency Synthesizers / PLL",
    "Current Sense Resistors / Shunt Resistors": "Current Sense / Shunt Resistors",
    "Current Sense Resistors/Shunt Resistors": "Current Sense / Shunt Resistors",
    "Current-Sensing Amplifiers": "Current Sense Amplifiers",
    "Current Sense Amplifiers": "Current Sense Amplifiers",
    "DC-DC Converters": "DC-DC Converters",
    "Digital To Analog Converters (DAC)": "Digital to Analog Converters (DACs)",
    "Digital To Analog Converters (DACs)": "Digital to Analog Converters (DACs)",
    "D-Sub / VGA Connector": "D-Sub / VGA Connectors",
    "D-Sub / VGA Connectors": "D-Sub / VGA Connectors",
    "Electrostatic And Surge Protection (TVS/ESD)": "Electrostatic and Surge Protection (TVS/ESD)",
    "ESD And Surge Protection (TVS/ESD)": "Electrostatic and Surge Protection (TVS/ESD)",
    "FET Input Amplifiers": "FET Input Amplifiers",
    "FET InputAmplifiers": "FET Input Amplifiers",
    "Gas Discharge Tube (GDT)": "Gas Discharge Tubes (GDT)",
    "Gas Discharge Tube Arresters (GDT)": "Gas Discharge Tubes (GDT)",
    "GaN Transistors(GaN HEMT)": "GaN Transistors (GaN HEMT)",
    "IGBTs": "IGBT Transistors / Modules",
    "IGBT Transistors / Modules": "IGBT Transistors / Modules",
    "I/O Expanders": "I/O Expanders",
    "Interface -LIN Transceiver": "Interface - LIN Transceiver",
    "Linear Voltage Regulators (LDO)": "Linear Voltage Regulators (LDO)",
    "Dropout Regulators(LDO)": "Linear Voltage Regulators (LDO)",
    "Low Dropout Regulators(LDO)": "Linear Voltage Regulators (LDO)",
    "LoRa Modules": "LoRa Modules",
    "Microcontroller Units (MCUs/MPUs/SOCs)": "Microcontroller Units (MCUs/MPUs/SOCs)",
    "Microcontrollers (MCU/MPU/SOC)": "Microcontroller Units (MCUs/MPUs/SOCs)",
    "MOSFET": "MOSFETs",
    "MOSFETs": "MOSFETs",
    "Operational Amplifier": "Operational Amplifiers",
    "Operational Amplifiers": "Operational Amplifiers",
    "Power Management Specialized - PMIC": "Power Management - Specialized PMIC",
    "Power Management - Specialized": "Power Management - Specialized PMIC",
    "Precision Op Amps": "Precision Op Amps",
    "Precision OpAmps": "Precision Op Amps",
    "Pre-Ordered Chips": "Pre-ordered Chips",
    "Pre-ordered Chips": "Pre-ordered Chips",
    "Pre-Ordered Connectors": "Pre-ordered Connectors",
    "Pre-ordered Connectors": "Pre-ordered Connectors",
    "Pre-Ordered MCUs": "Pre-ordered MCUs",
    "Pre-ordered MCUs": "Pre-ordered MCUs",
    "Pre-Ordered Products": "Pre-ordered Products",
    "Pre-ordered Products": "Pre-ordered Products",
    "Pre-Ordered RLCs": "Pre-ordered RLCs",
    "Pre-ordered RLCs": "Pre-ordered RLCs",
    "Pre-Ordered Transistors": "Pre-ordered Transistors",
    "Pre-ordered transistors": "Pre-ordered Transistors",
    "Pre-programmed Oscillators": "Pre-programmed Oscillators",
    "Pre-Programmed Oscillators": "Pre-programmed Oscillators",
    "Programmable/Variable Gain Amplifiers (PGAs/VGAs)": "Programmable / Variable Gain Amplifiers (PGA/VGA)",
    "Programmable / Variable Gain Amplifiers (PGA/VGA)": "Programmable / Variable Gain Amplifiers (PGA/VGA)",
    "Programmable Logic Device (CPLDs/FPGAs)": "Programmable Logic Devices (CPLDs/FPGAs)",
    "Real Time Clocks": "Real-Time Clocks (RTC)",
    "Real-Time Clocks (RTC)": "Real-Time Clocks (RTC)",
    "Real-time Clocks (RTC)": "Real-Time Clocks (RTC)",
    "RMS To DC Converters": "RMS-to-DC Converters",
    "RMS-To-DC Converters": "RMS-to-DC Converters",
    "RMS-to-DC Converters": "RMS-to-DC Converters",
    "Sample / Hold Amplifiers": "Sample-and-Hold Amplifiers",
    "Sample-And-Hold Amplifiers": "Sample-and-Hold Amplifiers",
    "Sample-and-Hold Amplifiers": "Sample-and-Hold Amplifiers",
    "Temperature And Humidity Sensor": "Temperature and Humidity Sensors",
    "Temperature and Humidity Sensor": "Temperature and Humidity Sensors",
    "Voltage Reference": "Voltage References",
    "Voltage References": "Voltage References",
    "Voltage-To-Frequency / Frequency-To-Voltage Converters": "Voltage-to-Frequency / Frequency-to-Voltage Converters",
    "Voltage-to-Frequency / Frequency-to-Voltage Converters": "Voltage-to-Frequency / Frequency-to-Voltage Converters",
    "Aluminum Electrolytic Capacitors (Can - Screw Terminals)": "Aluminum Electrolytic Capacitors (Can - Screw Terminals)",
    "Analog Front End (AFE)": "Analog Front End (AFEs)",
    "Analog Front End (AFEs)": "Analog Front End (AFEs)",
    "Digital Signal Processors (DSP/DSC)": "Digital Signal Processors (DSP/DSC)",
    "Digital Signal Processors / Controllers (DSPs/DSCs)": "Digital Signal Processors / Controllers (DSPs/DSCs)",
    "EMI Filters (LC, RC Networks)": "EMI Filters (LC, RC Networks)",
    "Interface - PCIs / PCIEs": "Interface - PCIs / PCIes",
    "LIN Transceivers": "LIN Transceivers",
    "Multilayer Ceramic Capacitors MLCC - Leaded": "Multilayer Ceramic Capacitors MLCC - Leaded",
    "Multilayer Ceramic Capacitors MLCC - SMD/SMT": "Multilayer Ceramic Capacitors MLCC - SMD/SMT",
    "Oven Controlled Crystal Oscillators (OCXOs)": "Oven Controlled Crystal Oscillators (OCXOs)",
    "Pulse Transformers(LAN)": "Pulse Transformers (LAN)",
    "RS-485 & RS-422": "RS-485 and RS-422",
    "RS-485 / RS-422 ICs": "RS-485 / RS-422 ICs",
    "RS-485/RS-422 ICs": "RS-485 / RS-422 ICs",
    "Spread Spectrum Oscillators(SSOs)": "Spread Spectrum Oscillators (SSOs)",
    "Polypropylene Film Capacitors (CBB)": "Polypropylene Film Capacitors (CBB)",
}

CATEGORY_ALIASES = {
    taxonomy_key(raw): canonical
    for raw, canonical in _CATEGORY_ALIASES_RAW.items()
}

SUBCATEGORY_ALIASES = {
    taxonomy_key(raw): canonical
    for raw, canonical in _SUBCATEGORY_ALIASES_RAW.items()
}


@dataclass(frozen=True)
class CanonicalCategory:
    category: str
    subcategory: str


def normalize_category(category):
    return CATEGORY_ALIASES.get(taxonomy_key(category), clean_label(category))


def normalize_subcategory(subcategory):
    return SUBCATEGORY_ALIASES.get(taxonomy_key(subcategory), clean_label(subcategory))


def normalize_category_pair(category, subcategory):
    return CanonicalCategory(
        normalize_category(category),
        normalize_subcategory(subcategory),
    )
