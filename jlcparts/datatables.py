import hashlib
import re
import os
import shutil
import json
import datetime
import gzip
from collections import OrderedDict, defaultdict
from pathlib import Path

import click
from jlcparts.partLib import PartLibraryDb
from jlcparts.common import sha256file
from jlcparts import attributes, descriptionAttributes
from jlcparts.taxonomy import clean_label, normalize_category_pair, taxonomy_key

def saveJson(object, filename, hash=False, pretty=False, compress=False):
    openFn = gzip.open if compress else open
    with openFn(filename, "wt", encoding="utf-8") as f:
        if pretty:
            json.dump(object, f, indent=4, sort_keys=True)
        else:
            json.dump(object, f, separators=(',', ':'), sort_keys=True)
    if hash:
        with open(filename + ".sha256", "w") as f:
            hash = sha256file(filename)
            f.write(hash)
        return hash

def weakUpdateParameters(attrs, newParameters):
    for attr, value in newParameters.items():
        if attr in attrs and attrs[attr] not in ["", "-"]:
            continue
        attrs[attr] = value

def extractAttributesFromDescription(description):
    if description.startswith("Chip Resistor - Surface Mount"):
        return descriptionAttributes.chipResistor(description)
    if (description.startswith("Multilayer Ceramic Capacitors MLCC") or
       description.startswith("Aluminum Electrolytic Capacitors")):
        return descriptionAttributes.capacitor(description)
    return {}

def normalizeUnicode(value):
    """
    Replace unexpected unicode sequence with a resonable ones
    """
    value = value.replace("（", " (").replace("）", ")")
    value = value.replace("，", ",")
    return value

def multiScalarValue(value):
    return isinstance(value, str) and ("," in value or "~" in value)

def compoundValue(value):
    return isinstance(value, str) and any(separator in value for separator in [",", ";"])

def normalizeAttribute(key, value):
    """
    Takes a name of attribute and its value (usually a string) and returns a
    normalized attribute name and its value as a tuple. Normalized value is a
    dictionary in the format:
        {
            "format": <format string, e.g., "${Resistance} ${Power}",
            "primary": <name of primary value>,
            "values": <dictionary of values with units, e.g, { "resistance": [10, "resistance"] }>
        }
    The fallback is unit "string"
    """
    larr = lambda arr : map(lambda str : str.lower(), arr)
    normkey = normalizeAttributeKey(key)
    key = normkey.lower()
    if isinstance(value, str):
        value = normalizeUnicode(value)

    try:
        if key in ["resistance @ 25°c"] and compoundValue(value):
            value = attributes.resistanceListAttribute(value)
        elif key in larr(["Resistance Value", "Output Impedance", "Rated Impeance"]):
            value = attributes.resistanceListAttribute(value) if compoundValue(value) else attributes.resistanceAttribute(value)
        elif key in larr(["Resistance", "Resistance in Ohms @ 25°C", "Resistance @ 25°C",
                "DC Resistance", "Insulation Resistance", "Insulation Resistance(Ir)",
                "Insulation Resistance (Min)",
                "Nominal Cold Resistance"]):
            value = attributes.stringAttribute(value) if multiScalarValue(value) else attributes.resistanceAttribute(value)
        elif key in larr(["Coil Resistance", "Ron", "Resistor on-State", "On-State Resistance (Max)", "Zener Impedance (ZZT)",
                "Resistance - Initial (Ri) (Min)"]):
            value = attributes.resistanceListAttribute(value) if compoundValue(value) else attributes.resistanceAttribute(value)
        elif key in larr(["Balance Port Impedence", "Unbalance Port Impedence", "Impedance(Zzk)", "Impedance"]):
            value = attributes.impedanceListAttribute(value) if compoundValue(value) else attributes.impedanceAttribute(value)
        elif key in larr(["Voltage - Rated", "Voltage Rating - DC", "Allowable Voltage", "Allowable Voltage (DC)",
                "Allowable Voltage (AC)",
                "Rated Voltage", "Rated Voltage (Max)", "Rated Voltage (AC)", "Rated Voltage (DC)",
                "AC Voltage (Max)", "DC Voltage (Max)",
                "Supply Voltage", "Supply Voltage (Max)", "Supply Voltage (Min)",
                "Varistor Voltage(Max)", "Varistor Voltage(Typ)",
                "Varistor Voltage(Min)", "Voltage - DC Reverse (Vr) (Max)",
                "Reverse Voltage (Vr)",
                "Voltage - DC Spark Over (Nom)", "Voltage - Peak Reverse (Max)",
                "Voltage - Reverse Standoff (Typ)", "Voltage - Gate Trigger (Vgt) (Max)",
                "Voltage - Off State (Max)", "Voltage - Input", "Voltage - Input (Max)", "Voltage - Output (Max)",
                "Input Voltage (Max)", "Input Voltage (Min)",
                "Voltage - Output (Fixed)", "Voltage - Output (Min/Fixed)",
                "Supply Voltage (Max)", "Supply Voltage (Min)", "Output Voltage",
                "Voltage - Input (Min)", "Drain Source Voltage (Vdss)",
                "Drain-Source Voltage (Vdss)", "Voltage - Input Offset(VOS)",
                "Charging Saturation Voltage", "Isolation Voltage(VRMS)",
                "Maximum Power Supply Range (Vdd-Vss)",
                "Collector-Emitter Breakdown Voltage (VCEO)",
                "Collector-Emitter Voltage (VCEO)", "Emitter-Base Voltage (VEBO)",
                "Input Offset Voltage (VOS)", "Input Hysteresis Voltage (Vhys)",
                "Gate-Source Breakdown Voltage (Vgss)",
                "Gate-Source Cutoff Voltage (Vgs(Off))",
                "Impulse Breakdown Voltage(Vimp)", "DC Rated Voltage",
                "Voltage(AC)", "Overload Voltage (Max)", "Voltage Drop",
                "Voltage Withstand", "Withstanding Voltage",
                "On - State Voltage(Vt)", "Switching Voltage(Vs)",
                "Peak Off - State Voltage(Vdrm)", "On State Voltage",
                "Trigger Voltage", "Operating Voltage (Max)", "Switching Voltage (Vs)",
                "Peak Off-State Voltage", "Reset Voltage", "Peak Impulse Voltage"]):
            if key == "charging saturation voltage" and compoundValue(value):
                value = attributes.voltageListAttribute(value)
            elif key == "isolation voltage(vrms)" and compoundValue(value):
                value = attributes.voltageListAttribute(value)
            elif key == "maximum power supply range (vdd-vss)" and compoundValue(value):
                value = attributes.voltageListAttribute(value)
            elif key == "withstanding voltage":
                value = attributes.voltageSemicolonListAttribute(value)
            elif key in [
                    "collector-emitter breakdown voltage (vceo)",
                    "collector-emitter voltage (vceo)",
                    "emitter-base voltage (vebo)",
                    "input offset voltage (vos)",
                    "input hysteresis voltage (vhys)",
                    "gate-source breakdown voltage (vgss)",
                    "gate-source cutoff voltage (vgs(off))",
                    "voltage(ac)",
                    "voltage withstand",
                    "operating voltage (max)",
                ] and compoundValue(value):
                value = attributes.voltageListAttribute(value)
            else:
                value = attributes.voltageAttribute(value)
        elif key in ["input voltage(dc)", "motor drive voltage(vm)", "control voltage",
                "vcm - common mode voltage", "low voltage detection threshold",
                "differential input voltage", "differential voltage",
                "operating voltage range", "load voltage", "input voltage (vin)",
                "tripping voltage",
                "voltage - supply(input)", "voltage - supply(output)",
                "input voltage range", "common mode voltage",
                "voltage - supply(vcca)", "voltage - supply(vccb)",
                "voltage - supply (driver)", "dc spark-over voltage"]:
            value = attributes.voltageRangeListAttribute(value) if compoundValue(value) else attributes.voltageRangeAttribute(value, "voltage")
        elif key in larr(["Human Body Model", "Contact Discharge Vesd"]):
            value = attributes.voltageRangeAttribute(value, "voltage")
        elif key in larr(["Input Voltage", "Frequency Input Voltage", "Zener Voltage (Range)",
                "Single Supply", "Dual Supply", "Operating Voltage", "Voltage - Input(DC)",
                "Low Level Range (VIL)"]):
            complexVoltageAlternatives = isinstance(value, str) and ("/" in value or "、" in value)
            if key in larr(["Dual Supply", "Operating Voltage"]) and isinstance(value, str) and ("," in value or ";" in value):
                value = attributes.voltageRangeListAttribute(value, "voltage")
            else:
                value = attributes.stringAttribute(value) if compoundValue(value) or complexVoltageAlternatives else attributes.voltageRangeAttribute(value, "voltage")
        elif key in larr(["Input Logic Level - High", "Input Logic Level - Low",
                "Output Logic Level - High", "Output Logic Level - Low",
                "Output Low Voltage", "Output High Voltage", "Input Low Voltage",
                "Intput High Voltage"]):
            value = attributes.voltageRangeListAttribute(value, "voltage")
        elif key in larr(["Reverse Stand-Off Voltage (VRWM)", "Threshold Voltage",
                "Varistor Voltage", "VOS - Input Offset Voltage"]):
            value = attributes.voltageRangeListAttribute(value, "voltage")
        elif key in larr(["Clamping Voltage@IPP"]):
            value = attributes.voltageListAttribute(value, "voltage") if isinstance(value, str) and ("," in value or ";" in value) else attributes.voltageAtConditionAttribute(value, "voltage")
        elif key in larr(["Breakdown Voltage", "Breakdown Voltage (Vbr)", "VCE Saturation(VCE(sat))",
                "Voltage Dropout", "Dropout Voltage"]):
            if key in larr(["Breakdown Voltage", "Breakdown Voltage (Vbr)"]) and isinstance(value, str) and ("," in value or ";" in value or "/" in value):
                value = attributes.voltageListAttribute(value, "voltage")
            else:
                value = attributes.stringAttribute(value) if compoundValue(value) else attributes.voltageAtConditionAttribute(value, "voltage")
        elif key in larr(["Voltage - Forward(Vf)", "Forward Voltage (Vf)"]):
            value = attributes.labeledVoltageRangeListAttribute(value, "voltage") if compoundValue(value) else attributes.voltageRangeAttribute(value, "voltage")
        elif key in larr(["Collector-Emitter Saturation Voltage (VCE(sat) @ Ic, Ib)"]):
            value = attributes.voltageAtConditionAttribute(value, "voltage")
        elif key in larr(["Rated current", "Rated Current", "surge current", "Current - Average Rectified (Io)",
                    "Average Rectified Current (IO)",
                    "Current - Breakover", "Current - Peak Output", "Current - Peak Pulse (10/1000μs)",
                    "Impulse Discharge Current (8/20us)", "Current - Gate Trigger (Igt) (Max)",
                    "Current - On State (It (AV)) (Max)", "Current - On State (It (RMS)) (Max)",
                    "Current - Supply (Max)", "Supply Current", "Supply Current (Max)",
                    "Output Current", "Output Current (Max)", "Rectified Current",
                    "Output / Channel Current", "Current - Output", "Current Range",
                    "Trip Current", "Maximum Continuous Current", "Operating Current",
                    "Collector Current (Ic)", "Charge Current - Max",
                    "Saturation Current (Isat)", "Reverse Leakage Current", "Reverse Leakage Current (Ir)",
                    "Peak Pulse Current (Ipp)", "Peak Pulse Current (Ipp) @ 10/1000us",
                    "Peak Pulse Current(Ipp)@8/20us",
                    "Quiescent Current", "Quiescent Current (Iq)", "Quiescent Current(Iq)",
                    "Quiescent Current (Ground Current)", "Quiescent Current Per Amplifier",
                    "Ib - Input Bias Current", "Input Bias Current (Ib)", "Standby Current",
                    "Non-Repetitive Peak Forward Surge Current", "Quiescent Supply Current",
                    "Input Offset Current(IOS)", "Receive Current", "Current - Collector(Ic)",
                    "Supply Current (Iq)", "Current - Input Bias(Ib)", "Current - Output Low(Iol)",
                    "Current - Output High(Ioh)", "Current - Surge(Itsm@F)", "Send Current",
                    "Current of Transmitting", "Current Consumption", "Current - Leakage",
                    "Peak Current", "Peak Non-Repetitive Surge Current (Itsm@F)",
                    "Hold Current", "Peak Output Current(Sink)",
                    "Peak Output Current(Source)", "Working Current",
                    "Collector Cut-Off Current (Icbo)",
                    "Current - Collector Cutoff",
                    "Load Current",
                    "Steady State Current (Max)",
                    "Minimum Cathode Current for Regulation",
                    "Holding Current (Ih)",
                    "Current - Max",
                    "Supply Current Per Channel",
                    "Standby Supply Current",
                    "Standby Current (Iq)",
                    "Current - on State(It(RMS))",
                    "Current - Gate Trigger(Igt)",
                    "Leakage Current(Dcl)", "Balance Current", "Leakage Current",
                    "Reverse Leakage Current (Ir)", "Hold Current(Ih)",
                    "On - State Current(It)", "Trigger Current",
                    "Nominal Impulse Discharge Current", "Impulse Discharge Current",
                    "Surge Current Capacity (8/20us)", "Off State Current",
                    "Off-State Current", "On-State Current (It)",
                    "Supply Current (Icc)", "Standby Current (Max)"]):
            currentListKeys = [
                "non-repetitive peak forward surge current",
                "quiescent current",
                "quiescent current (iq)",
                "quiescent current(iq)",
                "quiescent supply current",
                "input offset current(ios)",
                "receive current",
                "current - collector(ic)",
                "supply current (iq)",
                "current - input bias(ib)",
                "current - output low(iol)",
                "current - output high(ioh)",
                "current - surge(itsm@f)",
                "send current",
                "current of transmitting",
                "maximum continuous current",
                "operating current",
                "collector current (ic)",
                "current consumption",
                "peak pulse current(ipp)@8/20us",
                "output current",
                "peak output current(sink)",
                "current - collector cutoff",
                "load current",
                "steady state current (max)",
                "minimum cathode current for regulation",
                "holding current (ih)",
                "current - max",
                "standby current (iq)",
                "current - gate trigger(igt)",
                "balance current",
                "leakage current",
                "reverse leakage current (ir)",
                "hold current(ih)",
                "supply current (icc)",
            ]
            if key in ["current - leakage", "leakage current(dcl)"]:
                value = attributes.currentAttribute(value)
            elif key in ["current range", "current consumption", "trigger current"]:
                value = attributes.currentRangeListAttribute(value)
            elif key in currentListKeys and isinstance(value, str) and ("," in value or ";" in value):
                value = attributes.currentListAttribute(value)
            elif isinstance(value, str) and ("," in value or re.search(r"\d\s*-\s*\d", value)):
                value = attributes.stringAttribute(value)
            else:
                value = attributes.currentAttribute(value)
        elif key in larr(["Power", "Power (Max)", "Power Per Element", "Power Dissipation (Pd)",
                          "Dissipation Power (Max)", "Switching Power (Max)",
                          "Power Dissipation", "Peak Pulse Power Dissipation (Ppp)",
                          "Peak Pulse Power Dissipation (Ppp)@10/1000us",
                          "Peak Pulse Power(Ppp)@8/20us", "Rated Power",
                          "Coil Rated Power"]):
            if key == "peak pulse power(ppp)@8/20us" and isinstance(value, str) and ("," in value or ";" in value):
                value = attributes.powerListAttribute(value, "power")
            elif key in ["power dissipation (pd)", "coil rated power"] and compoundValue(value):
                value = attributes.powerListAttribute(value, "power")
            else:
                value = attributes.stringAttribute(value) if multiScalarValue(value) else attributes.powerAtConditionAttribute(value, "power")
        elif key in larr(["Energy", "Energy (Max)", "Turn-on Energy (Eon)",
                "Switching Energy(Eoff)"]):
            if key in ["turn-on energy (eon)", "switching energy(eoff)"] and compoundValue(value):
                value = attributes.energyListAttribute(value)
            else:
                value = attributes.energyAttribute(value)
        elif key in larr(["Melting I2t"]):
            value = attributes.meltingI2tAttribute(value)
        elif key in larr(["Attenuation", "Power Supply Rejection Ratio (Psrr)",
                "Insertion Loss", "Signal-to-Noise Ratio", "Noise Figure",
                "S/N Ratio", "Common Mode Rejection Ratio(CMRR)", "Common Mode Rejection Ratio (CMRR)",
                "Return Loss (Min)", "Sound Pressure Level(Spl)", "Peak Gain",
                "Snr(Signal to Noise Ratio)", "Signal to Noise Ratio",
                "Output Return Loss", "Input Return Loss"]):
            if key == "sound pressure level(spl)":
                value = attributes.decibelTokenListAttribute(value, "level")
            elif key == "peak gain":
                value = attributes.decibelListAttribute(value, "gain")
            else:
                value = attributes.decibelListAttribute(value, "level")
        elif key in larr(["IP3", "P1d B"]):
            value = attributes.decibelMilliwattListAttribute(value, "level")
        elif key in larr(["Q @ Frequency"]):
            value = attributes.qAtFrequencyAttribute(value)
        elif key in larr(["DC Current Gain"]):
            value = attributes.ratioRangeListAttribute(value, "gain")
        elif key in larr(["Voltage Reference Value", "Full-Scale Range(Fsr)"]):
            value = attributes.voltageListAttribute(value)
        elif key in larr(["Integral Non - Linearity", "Integral Nonlinearity", "Inl/Dnl(Lsb)", "Gain Error"]):
            value = attributes.lsbListAttribute(value, "gain error" if key == "gain error" else "linearity")
        elif key in larr(["Number of Channels", "Number of Elements"]):
            value = attributes.channelCountAttribute(value)
        elif key in larr(["Resolution", "Resolution (Bits)", "Resolution(Bits)"]):
            value = attributes.resolutionAttribute(value)
        elif key in larr(["Filter Order"]):
            value = attributes.filterOrderAttribute(value)
        elif key in larr(["Number of Bits Per Element", "Timer Number", "Numberof Drivers",
                "Numberof Receivers", "Number of Receivers", "Number of Drivers",
                "Number of Ports", "Number of Supporting Devices"]):
            value = attributes.countListAttribute(value)
        elif key in larr(["Number of Pins", "Number of Resistors", "Number of Loop",
                    "Number of Regulators", "Number of Outputs", "Number of Capacitors",
                    "Number of I/O", "Gpio Ports Number", "Number of Logic Elements/Blocks",
                    "Number of Differential Input Channels", "Number of Taps",
                    "Number of Voltages Monitored", "Number of Amplifiers",
                    "Attrition", "Minimum Order Quantity", "Minimum Placement Quantity",
                    "Minimum Purchase Quantity", "Order Multiple", "Packaging Quantity",
                    "Warehouse Stock - Jiangsu", "Warehouse Stock - Shenzhen",
                    "Warehouse Stock - Hong Kong",
                    "Logic Array Blocks", "Number of Circuits", "Number of Filters",
                    "Circuits", "Number of Poles", "Number of Nodes", "Unidirectional Channels",
                    "Bidirectional Channels"]):
            value = attributes.countAttribute(value)
        elif key in larr(["Number of Cells"]):
            value = attributes.countRangeAttribute(value)
        elif key in larr(["Number of Contacts", "Number of Holes", "Number of Positions",
                "Number of Positions or Pins"]):
            value = attributes.connectorCountAttribute(value)
        elif key in larr(["Frequency Registers(Bit)", "Tuning Word Width(Bits)",
                "Tuning Word Width (Max)"]):
            value = attributes.connectorCountAttribute(value)
        elif key in larr(["Life", "Mechanical Life"]):
            value = attributes.cycleCountAttribute(value)
        elif key in larr(["Capacitance", "Junction Capacitance", "Input Capacitance", "Input Capacitance(Cies)",
                "CISS-Input Capacitance", "Output Capacitance(Coes)",
                "Reverse Transfer Capacitance (Cres)", "Reverse Transfer Capacitance (Crss)",
                "Con", "Capacitive Load (Max)", "Nominal Capacitance",
                "Capacitance @ VR, F", "Off-State Capacitance (Co)",
                "Maximum Capacitance @ 1mhz", "Inter-Electrode Capacitance",
                "Electrostatic Capacitance"]):
            if key in ["junction capacitance", "capacitive load (max)"] and compoundValue(value):
                value = attributes.capacitanceListAttribute(value)
            elif multiScalarValue(value):
                value = attributes.stringAttribute(value)
            else:
                value = attributes.capacitanceAttribute(value)
        elif key in larr(["Electrostatic Capacity"]):
            value = attributes.capacitanceRangeListAttribute(value) if compoundValue(value) else attributes.capacitanceRangeAttribute(value)
        elif key in larr(["Inductance", "Equivalent Series Inductance"]):
            value = attributes.stringAttribute(value) if multiScalarValue(value) else attributes.inductanceAttribute(value)
        elif key in larr(["Length", "Width", "Height", "Diameter", "Switch Height", "Overall Length",
                "Height Above Board", "X-Length of Bottom Edge on Board (Spacing Line)",
                "Y-Width of Bottom Edge on Board", "Z-Height of the Board", "Diameter (Φd)", "Insulation Od",
                "Insulation Height", "Switch Length", "Switch Width", "Interface Length/Height", "Interface Diameter",
                "Height - Seated (Max)", "Length of Mating Pin", "Operating Height", "Operational Height", "L", "Row Spacing",
                "System Fit Height", "Overall Length/Height", "Head Width", "Center Height",
                "Outside Contact Diameter", "Length of End Connection Pin", "Diameter of Bolt Mouth",
                "Pin Length", "Diameter(Φd)", "Lead Pitch", "Inner Diameter Φ/Inner Width D",
                "Lead Spacing", "Φd", "Pin Spacing", "Capacitor Length", "Pin Spaceing",
                "Capacitor Diameter", "Size/Dimension", "Body Thickness", "Body Height",
                "Body Length", "Body Width", "Thickness", "Fuse Length",
                "Fuse Diameter (Φd)", "Fuse Width"]):
            if key == "diameter" and isinstance(value, str) and re.fullmatch(r"M\s*\d+(?:\.\d+)?", value, re.I):
                value = re.sub(r"^M\s*", "", value, flags=re.I) + "mm"
            if key in larr(["Insulation Od", "Interface Length/Height", "Interface Diameter",
                    "System Fit Height", "Fuse Length", "Fuse Diameter (Φd)",
                    "Fuse Width"]) and isinstance(value, str) and ("," in value or ";" in value):
                value = attributes.lengthRangeListAttribute(value, "length")
            elif key == "thickness" and isinstance(value, str) and "±" in value:
                value = attributes.tolerancedLengthAttribute(value)
            else:
                value = attributes.stringAttribute(value) if compoundValue(value) else attributes.lengthAttribute(value)
        elif key in larr(["Pitch"]):
            value = attributes.pitchAttribute(value)
        elif key in larr(["Luminous Intensity", "Light Intensity"]):
            value = attributes.luminousIntensityAttribute(value)
        elif key in larr(["Radiant Intensity"]):
            value = attributes.radiantIntensityAttribute(value)
        elif key in larr(["Input Voltage Noise Density", "Noise Density(E N)"]):
            value = attributes.voltageNoiseDensityAttribute(value)
        elif key in larr(["Input Offset Voltage Drift(VOS TC)"]):
            value = attributes.voltageTemperatureDriftAttribute(value)
        elif key in larr(["Input Offset Current Drift (IOS TC)", "Input Offset Current Drift(IOS TC)"]):
            value = attributes.currentTemperatureDriftAttribute(value)
        elif key in larr(["Noise - 1/10hz to 10hz"]):
            value = attributes.lowFrequencyNoiseAttribute(value)
        elif key in larr(["Temperature Coefficient", "Voltage Reference Drift", "Gain Drift",
                "Temperature Stability"]):
            value = attributes.temperatureCoefficientAttribute(value)
        elif key in larr(["Wavelength - Dominant", "Dominant Wavelength", "Peak Wavelength"]):
            value = attributes.opticalLengthRangeListAttribute(value) if compoundValue(value) else attributes.wavelengthAttribute(value)
        elif key in larr(["Tolerance"]):
            value = attributes.percentageAttribute(value) if isinstance(value, str) and "%" in value and not compoundValue(value) else attributes.stringAttribute(value)
        elif key in larr(["Precision", "Linearity", "Error", "Degree of Linearity",
                "Total Harmonic Distortion + Noise (Thd+N)", "Total Harmonic Distortion(Thd)",
                "Total Harmonic Distortion", "Differential Gain", "Capacitance Tolerance"]):
            value = attributes.flexiblePercentageAttribute(value)
        elif key in larr(["Dissipation Factor"]):
            value = attributes.dissipationFactorAttribute(value)
        elif key in larr(["Duty Cycle", "Conversion Efficiency", "Efficiency"]):
            if key == "efficiency":
                value = attributes.efficiencyPercentageRangeListAttribute(value)
            elif key == "conversion efficiency" and compoundValue(value):
                value = attributes.percentageRangeListAttribute(value)
            else:
                value = attributes.stringAttribute(value) if compoundValue(value) else attributes.percentageAttribute(value)
        elif key == "Rds On (Max) @ Id, Vgs".lower():
            value = attributes.rdsOnMaxAtIdsAtVgs(value)
        elif key in larr(["Operating Junction Temperature Range"]):
            value = attributes.temperatureRangeAttribute(value)
        elif key in larr(["Operating Temperature", "Operating Temperature (Max)", "Operating Temperature (Min)",
                "Holding Temperature", "Detection Temperature Range",
                "Maximum Temperature Limit", "Holding Temperature Limit",
                "Rated Functioning Temperature"]):
            if key in larr(["Holding Temperature Limit"]) and isinstance(value, str) and ("/" in value or "," in value or ";" in value):
                value = attributes.temperatureListAttribute(value)
            else:
                value = attributes.stringAttribute(value) if compoundValue(value) else attributes.temperatureRangeAttribute(value)
        elif key in larr(["B Constant (25°C/85°C)", "B Constant (25°C/50°C)"]):
            value = attributes.kelvinRangeListAttribute(value) if isinstance(value, str) and ("," in value or ";" in value) else attributes.kelvinAttribute(value)
        elif key in larr(["Color Temperature"]):
            value = attributes.kelvinRangeListAttribute(value)
        elif key in larr(["Wire Gauge - MM2", "Wire Gauge - Sqmm"]):
            value = attributes.areaMm2RangeListAttribute(value)
        elif key in larr(["Wire Gauge - Awg"]):
            value = attributes.awgRangeListAttribute(value)
        elif key in larr(["Operation Points", "Release Points"]):
            value = attributes.magneticFluxDensityRangeListAttribute(value)
        elif key in larr(["Viewing Angle", "Differential Phase"]):
            value = attributes.angleListAttribute(value)
        elif key.startswith("continuous drain current"):
            value = attributes.continuousTransistorCurrent(value, "Id")
        elif key == "Current - Collector (Ic) (Max)".lower():
            value = attributes.continuousTransistorCurrent(value, "Ic")
        elif key in larr(["Vgs(th) (Max) @ Id", "Gate Threshold Voltage (Vgs(th)@Id)",
                          "Gate Threshold Voltage (Vgs(th) @ Id)"]):
            malformedThresholdCurrent = isinstance(value, str) and "@" in value and not re.search(r"\d", value.split("@", 1)[1])
            value = attributes.stringAttribute(value) if malformedThresholdCurrent else attributes.vgsThreshold(value)
        elif key.startswith("drain to source voltage"):
            value = attributes.drainToSourceVoltage(value)
        elif key in larr(["Drain Source On Resistance (RDS(on)@Vgs,Id)",
                          "Drain-Source On Resistance (RDS(on))",
                          "Drain-Source On Resistance (RDS(on) @ Vgs, Id)"]):
            if key == "drain-source on resistance (rds(on))" and isinstance(value, str) and ("," in value or ";" in value):
                value = attributes.rdsMeasurementsAtVgs(value)
            else:
                if isinstance(value, str) and value.count("@") == 1 and ";" in value:
                    value = value.replace(";", ",")
                malformedRdsValue = isinstance(value, str) and ("/" in value.split("@", 1)[0] or re.search(r",[^,]*Ω", value))
                if isinstance(value, str):
                    value = re.sub(r"@VGS\s*", "@", value, flags=re.IGNORECASE)
                value = attributes.stringAttribute(value) if isinstance(value, str) and (malformedRdsValue or value.count("@") > 1 or ("," in value and value.count("@") != 1)) else attributes.rdsOnMaxAtVgsAtIds(value)
        elif key == "Power Dissipation-Max (Ta=25°C)".lower():
            value = attributes.powerDissipation(value)
        elif key in larr(["Equivalent Series Resistance", "Equivalent Series Resistance (ESR)", "ESR"]):
            value = attributes.esr(value)
        elif key in larr(["Resistance - Post Trip (R1) (Max)"]):
            value = attributes.stringAttribute(value) if multiScalarValue(value) else attributes.resistanceAttribute(value)
        elif key in larr(["Impedance @ Frequency"]):
            value = attributes.stringAttribute(value) if compoundValue(value) else attributes.impedanceAtFrequency(value)
        elif key == "Ripple Current".lower():
            value = attributes.rippleCurrent(value)
        elif key == "Size(mm)".lower():
            value = attributes.sizeMm(value)
        elif key in larr(["Voltage - Forward (Vf) (Max) @ If", "Forward Voltage (Vf @ If)"]):
            invalidForwardCurrent = isinstance(value, str) and "@" in value and "A" not in value.split("@", 1)[1]
            value = attributes.stringAttribute(value) if isinstance(value, str) and (";" in value or value.count("@") > 1 or invalidForwardCurrent) else attributes.forwardVoltage(value)
        elif key in larr(["Voltage - Breakdown (Min)", "Voltage - Zener (Nom) (Vz)",
            "Breakdown Voltage (Min)", "Zener Voltage (Nom)", "Vf - Forward Voltage"]):
            value = attributes.voltageRange(value)
        elif key in larr(["Voltage - Clamping (Max) @ Ipp", "Clamping Voltage (Max) @ Ipp", "Clamping Voltage (Max)"]):
            value = attributes.clampingVoltage(value)
        elif key == "Voltage - Collector Emitter Breakdown (Max)".lower():
            value = attributes.vceBreakdown(value)
        elif key == "Vce(on) (Max) @ Vge, Ic".lower():
            value = attributes.vceOnMax(value)
        elif key in larr(["Input Capacitance (Ciss@Vds)", "Input Capacitance (Ciss @ Vds)",
                   "Output Capacitance (Coss @ Vds)",
                   "Reverse Transfer Capacitance (Crss@Vds)", "Reverse Transfer Capacitance (Crss @ Vds)"]):
            value = attributes.capacityAtVoltage(value)
        elif key in larr(["Total Gate Charge (Qg@Vgs)", "Total Gate Charge (Qg @ Vgs)"]):
            value = attributes.stringAttribute(value) if isinstance(value, str) and value.count(";") != 0 else attributes.chargeAtVoltage(value)
        elif key in larr(["Data Rate", "Data Rate (Max)"]):
            value = attributes.dataRateListAttribute(value) if compoundValue(value) else attributes.dataRateAttribute(value)
        elif key in larr(["Slew Rate", "Slew Rate(Sr)", "Cmti(K V/Us)"]):
            value = attributes.slewRateAttribute(value, "cmti" if key == "cmti(k v/us)" else "slew rate")
        elif key in larr(["Program Storage Size", "Ram Size", "Embedded Block Ram", "Memory Size", "Memory Space"]):
            value = attributes.dataSizeListAttribute(value) if key in ["ram size", "memory size"] and isinstance(value, str) and ("," in value or ";" in value) else attributes.dataSizeAttribute(value)
        elif key in larr(["Frequency - self resonant", "Output frequency (max)",
                "Frequency - Switching", "Frequency Range", "Frequency", "Clock Frequency",
                "Switching Frequency", "Bandwidth", "Gain Bandwidth Product",
                "Gain Bandwidth Product(GBP)", "Frequency - Center", "Sampling Rate",
                "-3d B Bandwidth", "Cut-Off Frequency", "Transition Frequency (F T)",
                "Sampling Frequency", "Center Frequency", "CPU Maximum Speed",
                "Frequency(Center/Band)", "Switch Frequency", "Absolute Bandwidth",
                "Throughput Rate", "Update Rate", "Frequency Output",
                "Gain Bandwidth Product (GBP)", "Resonant Frequency", "Count Rate",
                "The Main Fclk", "Bandwidth (-3d B)", "-3db Bandwidth(G=1)",
                "Frequency - Cutoff or Center"]):
            if isinstance(value, str) and re.search(r"(?:bit/s|bps)\s*$", value, flags=re.IGNORECASE):
                value = attributes.dataRateAttribute(value)
            else:
                if key == "sampling rate" and isinstance(value, str) and re.search(r"\d\s*[munp]?s\b", value, flags=re.IGNORECASE):
                    value = attributes.timeAttribute(value)
                elif key in ["sampling rate", "frequency - switching", "clock frequency", "transition frequency (f t)", "sampling frequency", "center frequency", "cpu maximum speed", "frequency(center/band)", "switch frequency", "absolute bandwidth", "throughput rate", "update rate", "frequency output", "gain bandwidth product", "count rate", "the main fclk", "bandwidth (-3d b)", "-3db bandwidth(g=1)", "frequency - cutoff or center"] and isinstance(value, str) and ("," in value or ";" in value) and "~" in value:
                    value = attributes.frequencyRangeListAttribute(value)
                elif key in ["sampling rate", "frequency - switching", "clock frequency", "transition frequency (f t)", "sampling frequency", "center frequency", "cpu maximum speed", "frequency(center/band)", "switch frequency", "absolute bandwidth", "throughput rate", "update rate", "frequency output", "gain bandwidth product", "count rate", "the main fclk", "bandwidth (-3d b)", "-3db bandwidth(g=1)", "frequency - cutoff or center"] and isinstance(value, str) and ("," in value or ";" in value):
                    value = attributes.frequencyListAttribute(value)
                else:
                    value = attributes.stringAttribute(value) if compoundValue(value) else attributes.frequencyAttribute(value)
        elif key in larr(["Rated Speed"]):
            value = attributes.rotationalSpeedAttribute(value)
        elif key in larr(["Typical Capatitance", "Junction Capacitance(Cj)@1mhz"]):
            value = attributes.capacitanceAtFrequencyAttribute(value)
        elif key in larr(["Inductance @ Frequency"]):
            value = attributes.stringAttribute(value) if compoundValue(value) else attributes.inductanceAtFrequency(value)
        elif key in larr(["Propagation Delay", "Propagation Delay (TPD)", "Propagation Delay Time", "Turn-On Time",
                "Turn-Off Time", "Rise Time", "Fall Time", "Reverse Recovery Time (Trr)",
                "Reset Timeout", "Settling Time", "Response Time (Tr)", "Time to Trip (Max)", "Td(Off)",
                "Propagation Delay Tp Hl", "Propagation Delay Tp Lh", "Max Propagation Delay",
                "Maximum Propagation Delay", "Td(on)", "Block Erase Time(T Be)",
                "Temperature Conversion Time", "Setup Time", "Acquisition Time",
                "Hold Settling Time", "High Level Delay Time", "Low Level Delay Time",
                "Diode Reverse Recovery Time (Trr)", "Page Programming Time (Tpp)",
                "Turn Off Delay Time (Td(Off))", "Thermal Time Constant",
                "Hold Time", "Phase Jitter", "Lifetime", "Lifetime @ Temperature",
                "Load Life", "Action Time (Ton)", "Cycle-to-Cycle Jitter",
                "Period Jitter", "Available Total Delays", "Output Skew",
                "Continuous Adjustable Delay Range", "Time Intervals", "Access Time",
                "Delay Time", "Switch Time(Toff)"]):
            if compoundValue(value) and "@" not in value:
                if key in larr(["Propagation Delay (TPD)", "Propagation Delay Time", "Reset Timeout", "Settling Time", "Response Time (Tr)", "Time to Trip (Max)", "Td(Off)",
                        "Propagation Delay Tp Hl", "Propagation Delay Tp Lh", "Td(on)", "Block Erase Time(T Be)",
                        "Temperature Conversion Time", "Setup Time", "Page Programming Time (Tpp)",
                        "Thermal Time Constant", "Hold Time", "Phase Jitter",
                        "Action Time (Ton)", "Cycle-to-Cycle Jitter",
                        "Period Jitter"]) and isinstance(value, str) and ("," in value or ";" in value):
                    value = attributes.timeListAttribute(value)
                else:
                    value = attributes.stringAttribute(value)
            elif key == "block erase time(t be)" and isinstance(value, str) and ("," in value or ";" in value):
                value = attributes.timeListAttribute(value)
            else:
                value = attributes.timeAtConditionAttribute(value) if isinstance(value, str) and "@" in value else attributes.timeAttribute(value)
        else:
            value = attributes.stringAttribute(value)
    except: 
        print(f"Could not process key {normkey}; obj {value}")
        value = attributes.stringAttribute(value)   # fall back to string -- these values should have their patterns updated

    assert isinstance(value, dict)
    return normkey, value

_ATTRIBUTE_ALIASES_RAW = {
    # Casing, spacing, and punctuation variants.
    "OperatingTemperature": "Operating Temperature",
    "Operating Temperature\t-": "Operating Temperature",
    "Operating Temperature Range": "Operating Temperature",
    "Temperature   Coefficient": "Temperature Coefficient",
    "Temperature Coefficient(Typ)": "Temperature Coefficient",
    "Temperature Coefficient (Typ)": "Temperature Coefficient",
    "Output_ type": "Output Type",
    "Number of PINs": "Number of Pins",
    "Number Of Channels": "Number of Channels",
    "Number of  Channels": "Number of Channels",
    "NumberOfHoles": "Number of Holes",
    "InterfaceType": "Interface Type",
    "ContactResistance": "Contact Resistance",
    "InsulationResistance": "Insulation Resistance",
    "moq": "Minimum Order Quantity",
    "order_multiple": "Order Multiple",
    "packaging_num": "Packaging Quantity",
    "whs-js": "Warehouse Stock - Jiangsu",
    "whs-zh": "Warehouse Stock - Shenzhen",
    "whs-hk": "Warehouse Stock - Hong Kong",

    # Common electrical names.
    "Power(Watts)": "Power",
    "Power (Watts)": "Power",
    "Power - Max": "Power",
    "Max Power": "Power (Max)",
    "Maximum Power": "Power (Max)",
    "Pd - Power Dissipation": "Power Dissipation (Pd)",
    "Power Dissipation(Pd)": "Power Dissipation (Pd)",
    "Equivalent Series Resistance": "Equivalent Series Resistance (ESR)",
    "Equivalent Series Resistance(ESR)": "Equivalent Series Resistance (ESR)",
    "Equivalent Series Resistance (ESR)": "Equivalent Series Resistance (ESR)",
    "ESR (Equivalent Series Resistance)": "Equivalent Series Resistance (ESR)",
    "Equivalent Series   Resistance(ESR)": "Equivalent Series Resistance (ESR)",
    "DC Resistance(DCR)": "DC Resistance",
    "DC Resistance (DCR)": "DC Resistance",
    "DC Resistance (DCR) (Max)": "DC Resistance",
    "DCR( Ω Max )": "DC Resistance",
    "RDS(on)": "Drain-Source On Resistance (RDS(on))",
    "RDS(On)": "Drain-Source On Resistance (RDS(on))",
    "Rds(on)": "Drain-Source On Resistance (RDS(on))",
    "Drain Source On Resistance (RDS(on)@Vgs,Id)": "Drain-Source On Resistance (RDS(on) @ Vgs, Id)",
    "Drain Source On Resistance (RDS(on)@Vgs,ID)": "Drain-Source On Resistance (RDS(on) @ Vgs, Id)",
    "Gate Charge(Qg)": "Total Gate Charge (Qg @ Vgs)",
    "Total Gate Charge (Qg@Vgs)": "Total Gate Charge (Qg @ Vgs)",
    "Input Capacitance(Ciss)": "Input Capacitance (Ciss @ Vds)",
    "Input Capacitance(Ciss@Vds)": "Input Capacitance (Ciss @ Vds)",
    "Input Capacitance (Ciss@Vds)": "Input Capacitance (Ciss @ Vds)",
    "Output Capacitance(Coss)": "Output Capacitance (Coss @ Vds)",
    "Output Capacitance(Coss@Vds)": "Output Capacitance (Coss @ Vds)",
    "Reverse Transfer Capacitance(Crss)": "Reverse Transfer Capacitance (Crss @ Vds)",
    "Reverse Transfer Capacitance (Crss@Vds)": "Reverse Transfer Capacitance (Crss @ Vds)",
    "Reverse Transfer Capacitance(Crss@Vds)": "Reverse Transfer Capacitance (Crss @ Vds)",

    # Voltage, current, and power rating families.
    "Voltage Rated": "Rated Voltage",
    "RatedVoltage": "Rated Voltage",
    "Voltage Rating": "Rated Voltage",
    "Voltage Rating (Max)": "Rated Voltage (Max)",
    "Rated Voltage (Max)": "Rated Voltage (Max)",
    "Allowable Voltage(Vdc)": "Rated Voltage (DC)",
    "Voltage Rating - DC": "Rated Voltage (DC)",
    "Voltage Rating (DC)": "Rated Voltage (DC)",
    "Voltage Rating(AC)": "Rated Voltage (AC)",
    "Voltage Rating (AC)": "Rated Voltage (AC)",
    "Voltage Rating  (AC)": "Rated Voltage (AC)",
    "Voltage - Supply": "Supply Voltage",
    "Supply - Voltage": "Supply Voltage",
    "Voltage-Supply(Max)": "Supply Voltage (Max)",
    "Supply Voltage(Max)": "Supply Voltage (Max)",
    "Supply Voltage (Max)": "Supply Voltage (Max)",
    "Maximum Input Voltage": "Input Voltage (Max)",
    "Voltage - Input(Max)": "Input Voltage (Max)",
    "Voltage - Input (Max)": "Input Voltage (Max)",
    "Voltage - Input (minimum value)": "Input Voltage (Min)",
    "Voltage - Input (maximum value)": "Input Voltage (Max)",
    "Output Current(Max)": "Output Current (Max)",
    "MAX Output Current": "Output Current (Max)",
    "Output Power(Max)": "Output Power (Max)",
    "Output Power  (Max)": "Output Power (Max)",
    "Maximum AC Volts": "AC Voltage (Max)",
    "Maximum DC Volts": "DC Voltage (Max)",
    "Maximum Energy": "Energy (Max)",
    "Current Rating": "Rated Current",
    "Current Rating (Max)": "Rated Current",
    "RatedCurrent": "Rated Current",
    "Current - Supply": "Supply Current",
    "Current - Supply(Max)": "Supply Current (Max)",
    "Current - Supply (Max)": "Supply Current (Max)",
    "Supply Current(Max)": "Supply Current (Max)",
    "Current - Saturation(Isat)": "Saturation Current (Isat)",
    "Current - Saturation (Isat)": "Saturation Current (Isat)",
    "Current - Rectified": "Rectified Current",
    "Clamping Voltage": "Clamping Voltage (Max)",
    "Maximum Clamping Voltage": "Clamping Voltage (Max)",
    "Voltage - Clamping (Max) @ Ipp": "Clamping Voltage (Max) @ Ipp",
    "Voltage - Forward(Vf@If)": "Forward Voltage (Vf @ If)",
    "Voltage - Forward (Vf)@ If": "Forward Voltage (Vf @ If)",
    "Voltage - Forward (Vf) (Max) @ If": "Forward Voltage (Vf @ If)",
    "Forward Voltage (Vf@If)": "Forward Voltage (Vf @ If)",
    "Forward Voltage (Vf) @ If": "Forward Voltage (Vf @ If)",
    "Forward Voltage(Vf)": "Forward Voltage (Vf)",
    "Forward Voltage (VF)": "Forward Voltage (Vf)",
    "Voltage - DC Reverse(Vr)": "Reverse Voltage (Vr)",
    "Voltage - DC Reverse (Vr) (Max)": "Reverse Voltage (Vr)",
    "Voltage - Breakdown": "Breakdown Voltage",
    "Voltage - Breakover": "Breakdown Voltage (Min)",
    "Voltage - Breakdown (Min)": "Breakdown Voltage (Min)",
    "Voltage - Zener (Nom) (Vz)": "Zener Voltage (Nom)",

    # Zener, TVS, and RF details.
    "Impedance(Zzt)": "Zener Impedance (Zzt)",
    "Zener Voltage(Nom)": "Zener Voltage (Nom)",
    "Zener Voltage(Range)": "Zener Voltage (Range)",
    "Peak Pulse Current-Ipp (10/1000us)": "Peak Pulse Current (Ipp) @ 10/1000us",
    "Peak Pulse Current (Ipp)@10/1000us": "Peak Pulse Current (Ipp) @ 10/1000us",
    "Peak Pulse Power Dissipation (Ppp)": "Peak Pulse Power Dissipation (Ppp)",
    "Insertion Loss ( dB Max )": "Insertion Loss (dB Max)",
    "Insertion Loss (Max)": "Insertion Loss (dB Max)",
    "-3db Bandwidth": "-3dB Bandwidth",

    # Transistor names.
    "Current - Continuous Drain(Id)": "Continuous Drain Current (Id)",
    "Drain Source Voltage (Vdss)": "Drain-Source Voltage (Vdss)",
    "Drain to Source Voltage (Vdss)": "Drain-Source Voltage (Vdss)",
    "Gate Threshold Voltage-VGE(th)": "Vgs(th) (Max) @ Id",
    "Gate Threshold Voltage (Vgs(th))": "Gate Threshold Voltage (Vgs(th) @ Id)",
    "Gate Threshold Voltage (Vgs(th)@Id)": "Gate Threshold Voltage (Vgs(th) @ Id)",
    "Collector - Emitter Voltage VCEO": "Collector-Emitter Voltage (VCEO)",
    "Collector-emitter voltage (Vceo)": "Collector-Emitter Voltage (VCEO)",
    "Maximum collector Emitter Voltage (Vceo)": "Collector-Emitter Voltage (VCEO)",
    "Collector-Emitter Breakdown Voltage (Vceo)": "Collector-Emitter Breakdown Voltage (VCEO)",
    "Collector Emitter Breakdown Voltage(Vceo)": "Collector-Emitter Breakdown Voltage (VCEO)",
    "Emitter-Base Voltage(Vebo)": "Emitter-Base Voltage (VEBO)",
    "Emitter-Base Voltage VEBO": "Emitter-Base Voltage (VEBO)",
    "Collector-Emitter Saturation Voltage (VCE(sat)@Ic,Ib)": "Collector-Emitter Saturation Voltage (VCE(sat) @ Ic, Ib)",
    "Collector-emitter saturation voltage (VCE(sat)@Ic,Ib)": "Collector-Emitter Saturation Voltage (VCE(sat) @ Ic, Ib)",
    "Vce(on) (Max) @ Vge, Ic": "VCE(on) (Max) @ Vge, Ic",

    # Mechanical and connector names.
    "Pins Structure": "Pin Structure",
    "Height-Seated": "Height - Seated (Max)",
    "Height - Seated(Max)": "Height - Seated (Max)",
    "Current Rating-Signal": "Signal Current Rating",
    "Current Rating-Signal (Max)": "Signal Current Rating (Max)",
    "Current Rating-Power": "Power Current Rating",
    "Current Rating-Power (Max)": "Power Current Rating (Max)",
    "Current Rating - Power (Max)": "Power Current Rating (Max)",

    # Timing and frequency.
    "Output Frequency(Max)": "Output Frequency (Max)",
    "Clock Frequency(Max)": "Clock Frequency (Max)",
    "Data Rate(Max)": "Data Rate (Max)",
    "Switching Current(Max)": "Switching Current (Max)",
    "Maximum Switching Current": "Switching Current (Max)",
    "Switching Voltage(Max)": "Switching Voltage (Max)",
    "Maximum Switching Voltage": "Switching Voltage (Max)",
    "Capacitive Load(Max)": "Capacitive Load (Max)",
    "Maximum Capacitive Load": "Capacitive Load (Max)",
    "Time to Trip(Max)": "Time to Trip (Max)",
    "Maximum Time to Trip": "Time to Trip (Max)",
    "Duty Cycle(Max)": "Duty Cycle (Max)",
    "Soldering Temperature(Max)": "Soldering Temperature (Max)",
    "Return Loss(Min)": "Return Loss (Min)",
    "Dissipation Power(Max)": "Dissipation Power (Max)",
    "Switching Power(Max)": "Switching Power (Max)",
    "Load Current(Max)": "Load Current (Max)",
    "Tuning  Word Width(Max)": "Tuning Word Width (Max)",
    "Tuning Word Width(Max)": "Tuning Word Width (Max)",
    "Maximum frequency": "Frequency (Max)",
    "Frequency-Max": "Frequency (Max)",
    "Frequency - Maximum": "Frequency (Max)",
    "Transition frequency(fT)": "Transition Frequency (fT)",
    "Transition frequency (fT)": "Transition Frequency (fT)",
    "Reverse Recovery Time(trr)": "Reverse Recovery Time (trr)",
    "Propagation Delay(tpd)": "Propagation Delay (tpd)",
    "Turn-on time": "Turn-On Time",
    "Turn-off time": "Turn-Off Time",
    "Rise time": "Rise Time",
    "Fall time": "Fall Time",
    "Q @ Freq": "Q @ Frequency",

    # Spelling and plain English variants.
    "Colour": "Color",
    "Rail To Rail": "Rail to Rail",
    "Rail-to-Rail": "Rail to Rail",
    "With lamp": "With Lamp",
    "level of protection": "Level of Protection",
    "Single supply": "Single Supply",
    "Standby current": "Standby Current",
    "standby current": "Standby Current",
}

ATTRIBUTE_ALIASES = {
    taxonomy_key(raw): canonical
    for raw, canonical in _ATTRIBUTE_ALIASES_RAW.items()
}


def normalizeCapitalization(key):
    """
    Given a category name, normalize capitalization. We turn everything
    lowercase, but some known substring (such as MOQ or MHz) replace back to the
    correct capitalization
    """
    key = re.sub(r"(?<! )\((Max|Min|Typ|Nom)\)", r" (\1)", key, flags=re.IGNORECASE)
    key = clean_label(key)
    key = key.replace(" / ", "/")
    key = re.sub(r"\s+@\s+", " @ ", key)
    key = re.sub(r"\s+", " ", key)
    replacements = {
        "D B": "dB",
        "I2c": "I2C",
        "Po E": "PoE",
        "Smbus": "SMBus",
        "Pmbus": "PMBus",
        "(IPP)": "(Ipp)",
        "(ID)": "(Id)",
        "(IC)": "(Ic)",
        "(IF)": "(If)",
        "(IR)": "(Ir)",
        "(IQ)": "(Iq)",
        "(ISAT)": "(Isat)",
        "(QG": "(Qg",
        "(CISS": "(Ciss",
        "(COSS": "(Coss",
        "(CRSS": "(Crss",
        "(VDS": "(Vds",
        "(VGS": "(Vgs",
        "(VF": "(Vf",
        "(VR)": "(Vr)",
        "(VZ": "(Vz",
        "@ VGS": "@ Vgs",
        "@ VDS": "@ Vds",
        "@ ID": "@ Id",
        "@ IF": "@ If",
        ", ID": ", Id",
        ", IB": ", Ib",
        "RDS(ON)": "RDS(on)",
        "VCE(Sat)": "VCE(sat)",
        "Vgs(Th)": "Vgs(th)",
        "VDD": "Vdd",
        "VSS": "Vss",
        "Cpu": "CPU",
        "Drain-Source on": "Drain-Source On",
    }
    for old, new in replacements.items():
        key = key.replace(old, new)
    return key.strip()

def normalizeAttributeKey(key):
    """
    Takes a name of attribute and its value and returns a normalized key
    (e.g., strip unit name).
    """
    key = normalizeUnicode(str(key)).strip()
    key = re.sub(r"\s+", " ", key)
    key = ATTRIBUTE_ALIASES.get(taxonomy_key(key), key)
    if "(Watts)" in key:
        key = key.replace("(Watts)", "").strip()
    if "(Ohms)" in key:
        key = key.replace("(Ohms)", "").strip()
    if key == "aristor Voltage(Min)":
        key = "Varistor Voltage(Min)"
    if key in ["ESR (Equivalent Series Resistance)", "Equivalent Series   Resistance(ESR)",
            "Equivalent Series Resistance(ESR)"] or key.startswith("Equivalent Series Resistance"):
        key = "Equivalent Series Resistance (ESR)"
    if key in ["Allowable Voltage(Vdc)", "Voltage - Max", "Rated Voltage",
            "Voltage Rating"] or key.startswith("Voltage Rated"):
        key = "Rated Voltage"
    if key in ["DC Resistance (DCR)", "DC Resistance (DCR) (Max)", "DCR( Ω Max )",
            "DC Resistance(DCR)"]:
        key = "DC Resistance"
    if key in ["Insertion Loss ( dB Max )", "Insertion Loss (Max)"]:
        key = "Insertion Loss (dB Max)"
    if key in ["Current Rating (Max)", "Rated Current", "Current Rating"]:
        key = "Rated Current"
    if key == "Current - Saturation (Isat)":
        key = "Saturation Current (Isat)"
    if key == "Power - Max":
        key = "Power"
    if key == "Pd - Power Dissipation":
        key = "Power Dissipation (Pd)"
    if key == "Voltage - Breakover":
        key = "Voltage - Breakdown (Min)"
    if key == "Gate Threshold Voltage-VGE(th)":
        key = "Vgs(th) (Max) @ Id"
    if key in ["Gate Threshold Voltage (Vgs(th))", "Gate Threshold Voltage (Vgs(th)@Id)"]:
        key = "Gate Threshold Voltage (Vgs(th)@Id)"
    if key == "Current - Continuous Drain(Id)":
        key = "Continuous Drain Current (Id)"
    if key == "Rds(on)":
        key = "Drain-Source On Resistance (RDS(on) @ Vgs, Id)"
    if key == "Input Capacitance(Ciss)":
        key = "Input Capacitance (Ciss @ Vds)"
    if key == "Output Capacitance(Coss)":
        key = "Output Capacitance (Coss @ Vds)"
    if key == "Gate Charge(Qg)":
        key = "Total Gate Charge (Qg @ Vgs)"
    if key == "Voltage - DC Reverse(Vr)":
        key = "Reverse Voltage (Vr)"
    if key == "Voltage - Forward(Vf@If)":
        key = "Forward Voltage (Vf @ If)"
    if key == "Current - Rectified":
        key = "Rectified Current"
    if key == "Impedance(Zzt)":
        key = "Zener Impedance (Zzt)"
    if key == "Zener Voltage(Nom)":
        key = "Zener Voltage (Nom)"
    if key == "Zener Voltage(Range)":
        key = "Zener Voltage (Range)"
    if key == "Pins Structure":
        key = "Pin Structure"
    if key.startswith("Lifetime @ Temp"):
        key = "Lifetime @ Temperature"
    if key.startswith("Q @ Freq"):
        key = "Q @ Frequency"
    return normalizeCapitalization(key)

def pullExtraAttributes(component):
    """
    Turn common properties (e.g., base/extended) into attributes. Return them as
    a dictionary
    """
    status = "Discontinued" if component["extra"] == {} and component.get("jlc_extra", {}) == {} else "Active"
    type = "Extended"
    if component["basic"]:
        type = "Basic"
    if component["preferred"]:
        type = "Preferred"
    return {
        "Basic/Extended": type,
        "Package": component["package"],
        "Status": status
    }

def crushImages(images):
    if not images:
        return None
    firstImg = images[0]
    imageUrls = [value for value in firstImg.values() if isinstance(value, str)]
    if not imageUrls:
        return None
    img = imageUrls[0].rsplit("/", 1)[1]
    # make sure every url ends the same
    assert all(i.rsplit("/", 1)[1] == img for i in imageUrls)
    return img

def trimLcscUrl(url, lcsc):
    if url is None:
        return None
    slug = url[url.rindex("/") + 1 : url.rindex("_")]
    if url.startswith("http"):
        assert url.endswith(f"/product-detail/{slug}_{lcsc}.html")
    return slug

def _extraAttributes(extra):
    if "attributes" in extra:
        attr = extra.get("attributes", {})
    else:
        attr = extra
    if isinstance(attr, list):
        return {}
    return attr or {}

def _jlcAttributes(jlcExtra):
    if not isinstance(jlcExtra, dict):
        return {}
    attr = jlcExtra.get("attributes", {})
    if isinstance(attr, list):
        return {}
    return attr or {}

def _mergeAttributes(component):
    attr = dict(_extraAttributes(component.get("extra", {})))
    for key, value in _jlcAttributes(component.get("jlc_extra", {})).items():
        if value in ["", "-"]:
            continue
        attr[key] = value
    return attr

def extractComponent(component, schema):
    try:
        propertyList = []
        for schItem in schema:
            if schItem == "attributes":
                attr = _mergeAttributes(component)
                attr.update(pullExtraAttributes(component))
                weakUpdateParameters(attr, extractAttributesFromDescription(component["description"]))

                # Remove extra attributes that are either not useful, misleading
                # or overridden by data from JLC
                attr.pop("url", None)
                attr.pop("images", None)
                attr.pop("prices", None)
                attr.pop("datasheet", None)
                attr.pop("id", None)
                attr.pop("manufacturer", None)
                attr.pop("number", None)
                attr.pop("title", None)
                attr.pop("quantity", None)
                for i in range(10):
                    attr.pop(f"quantity{i}", None)

                attr["Manufacturer"] = component.get("manufacturer", None)

                attr = dict([normalizeAttribute(key, val) for key, val in attr.items()])
                propertyList.append(attr)
            elif schItem == "img":
                images = component.get("extra", {}).get("images", None)
                propertyList.append(crushImages(images))
            elif schItem == "url":
                url = component.get("extra", {}).get("url", None)
                propertyList.append(trimLcscUrl(url, component["lcsc"]))
            elif schItem in component:
                item = component[schItem]
                if isinstance(item, str):
                    item = item.strip()
                propertyList.append(item)
            else:
                propertyList.append(None)
        return propertyList
    except Exception as e:
        raise RuntimeError(f"Cannot extract {component['lcsc']}").with_traceback(e.__traceback__)

def buildDatatable(components):
    schema = ["lcsc", "mfr", "joints", "description",
              "datasheet", "price", "img", "url", "attributes"]
    return {
        "schema": schema,
        "components": [extractComponent(x, schema) for x in components]
    }

def buildStocktable(components):
    return {component["lcsc"]: component["stock"] for component in components }

def clearDir(directory):
    """
    Delete everything inside a directory
    """
    for filename in os.listdir(directory):
        file_path = os.path.join(directory, filename)
        if os.path.isfile(file_path) or os.path.islink(file_path):
            os.unlink(file_path)
        elif os.path.isdir(file_path):
            shutil.rmtree(file_path)


WEB_FILE_FORMAT_VERSION = 4
LOOKUP_BUCKET_SIZE_DEFAULT = 100000
MAX_COMPONENTS_PER_SHARD_DEFAULT = 1000
BROWSE_COMPONENTS_PER_SHARD_DEFAULT = 20000
TRIGRAM_SIZE = 3
MAX_TRIGRAM_BUCKET_ROWS = 100000
TRIGRAM_GROUP_PREFIX_SIZE = 2
SEARCH_GRAM_RE = re.compile(r"^[a-z0-9-]{3}$")
COMPONENT_ROW_SCHEMA = {
    "lcsc": 0,
    "mfr": 1,
    "joints": 2,
    "description": 3,
    "datasheet": 4,
    "price": 5,
    "img": 6,
    "url": 7,
    "attributes": 8,
    "stock": 9,
    "subcategory": 10,
}
SEARCH_INDEX_ROW_SCHEMA = {
    "lcsc": 0,
    "text": 1,
    "shard": 2,
}
COMPONENT_SOURCE_SCHEMA = [
    "lcsc",
    "mfr",
    "joints",
    "description",
    "datasheet",
    "price",
    "img",
    "url",
    "attributes",
    "stock",
]


def _stableComponentFilebase(catName, subcatName):
    base = f"{catName}__{subcatName}"
    base = base.replace("&", "and").replace("/", "aka")
    base = re.sub(r"[^A-Za-z0-9]+", "_", base).strip("_")
    digest = hashlib.sha1(f"{catName}\0{subcatName}".encode("utf-8")).hexdigest()[:8]
    return f"{base}__{digest}".lower()


def _writeJsonArtifact(data, filename, compress=False):
    openFn = gzip.open if compress else open
    with openFn(filename, "wt", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"), sort_keys=True)
    return sha256file(filename)


def _writeJsonLinesArtifact(rows, filename):
    with gzip.open(filename, "wt", encoding="utf-8") as f:
        for row in rows:
            json.dump(row, f, separators=(",", ":"), sort_keys=False)
            f.write("\n")
    return sha256file(filename)


def _lookupBucketForLcsc(lcsc, bucketSize):
    return int(lcsc[1:]) // bucketSize


def _isUsableCategory(catName, subcatName):
    return catName.strip() != "" and subcatName.strip() != ""


def _componentRows(components, subcategoryId, attributeLut):
    rows = [COMPONENT_ROW_SCHEMA]
    for component in components:
        values = extractComponent(component, COMPONENT_SOURCE_SCHEMA)
        attrIds = [
            updateLut(attributeLut, [name, value])
            for name, value in values[COMPONENT_ROW_SCHEMA["attributes"]].items()
        ]
        rows.append([
            values[COMPONENT_ROW_SCHEMA["lcsc"]],
            values[COMPONENT_ROW_SCHEMA["mfr"]],
            values[COMPONENT_ROW_SCHEMA["joints"]],
            values[COMPONENT_ROW_SCHEMA["description"]],
            values[COMPONENT_ROW_SCHEMA["datasheet"]],
            values[COMPONENT_ROW_SCHEMA["price"]],
            values[COMPONENT_ROW_SCHEMA["img"]],
            values[COMPONENT_ROW_SCHEMA["url"]],
            attrIds,
            values[COMPONENT_ROW_SCHEMA["stock"]],
            subcategoryId,
        ])
    return rows


def _componentSearchText(component):
    return " ".join([
        str(component.get("lcsc", "")),
        str(component.get("mfr", "")),
        str(component.get("description", "")),
    ]).lower()


def _cleanSearchText(text):
    return text.replace("\t", " ").replace("\r", " ").replace("\n", " ")


def _searchTrigrams(text):
    if len(text) < TRIGRAM_SIZE:
        return set()
    return {
        gram
        for i in range(len(text) - TRIGRAM_SIZE + 1)
        for gram in [text[i:i + TRIGRAM_SIZE]]
        if SEARCH_GRAM_RE.match(gram)
    }


def _trigramGroup(gram):
    return gram[:TRIGRAM_GROUP_PREFIX_SIZE]


def _trigramGroupFileName(group):
    encoded = group.encode("utf-8").hex()
    return f"search-trigrams-{encoded}.tsv.gz"


def _writeSearchIndexRows(searchIndexFile, components, shardName):
    for component in components:
        searchText = _cleanSearchText(_componentSearchText(component))
        searchIndexFile.write(f"{component['lcsc']}\t{shardName}\t{searchText}\n")


def _flushComponentShard(chunk, shardName, outdir, subcategoryId, attributeLut,
                         files, lookupBuckets=None, lookupBucketSize=None,
                         searchIndexFile=None, trigramCounts=None,
                         kind="components"):
    shardRows = _componentRows(chunk, subcategoryId, attributeLut)
    shardPath = os.path.join(outdir, shardName)
    shardHash = _writeJsonLinesArtifact(shardRows, shardPath)
    files[shardName] = {
        "name": shardName,
        "kind": kind,
        "sha256": shardHash,
        "componentCount": len(chunk),
        "subcategoryId": subcategoryId,
    }
    if lookupBuckets is not None:
        for component in chunk:
            bucket = _lookupBucketForLcsc(component["lcsc"], lookupBucketSize)
            lookupBuckets.setdefault(bucket, {})[component["lcsc"]] = shardName
    if trigramCounts is not None:
        for component in chunk:
            for gram in _searchTrigrams(_cleanSearchText(_componentSearchText(component))):
                trigramCounts[gram] += 1
    if searchIndexFile is not None:
        _writeSearchIndexRows(searchIndexFile, chunk, shardName)


class _LruTextWriters:
    def __init__(self, maxOpen):
        self.maxOpen = maxOpen
        self.writers = OrderedDict()

    def write(self, filename, text):
        writer = self.writers.get(filename)
        if writer is None:
            if len(self.writers) >= self.maxOpen:
                _, oldWriter = self.writers.popitem(last=False)
                oldWriter.close()
            writer = open(filename, "a", encoding="utf-8")
            self.writers[filename] = writer
        else:
            self.writers.move_to_end(filename)
        writer.write(text)

    def close(self):
        for writer in self.writers.values():
            writer.close()
        self.writers.clear()


def _writeTrigramIndexes(searchIndexPath, outdir, files, totalComponents, trigramCounts):
    if totalComponents == 0:
        return {}

    selectedGrams = {
        gram: count
        for gram, count in trigramCounts.items()
        if count <= MAX_TRIGRAM_BUCKET_ROWS
    }
    if not selectedGrams:
        return {}

    tempDir = os.path.join(outdir, ".trigram-tmp")
    Path(tempDir).mkdir(parents=True, exist_ok=True)
    writers = _LruTextWriters(maxOpen=64)
    groupTempFiles = {}
    groupRows = defaultdict(int)
    try:
        with gzip.open(searchIndexPath, "rt", encoding="utf-8") as searchIndexFile:
            for line in searchIndexFile:
                line = line.rstrip("\n")
                if not line:
                    continue
                textStart = line.find("\t", line.find("\t") + 1)
                if textStart == -1:
                    continue
                text = line[textStart + 1:]
                for gram in _searchTrigrams(text):
                    if gram not in selectedGrams:
                        continue
                    group = _trigramGroup(gram)
                    tempPath = groupTempFiles.get(group)
                    if tempPath is None:
                        tempPath = os.path.join(tempDir, _trigramGroupFileName(group)[:-3])
                        groupTempFiles[group] = tempPath
                    writers.write(tempPath, f"{gram}\t{line}\n")
                    groupRows[group] += 1
    finally:
        writers.close()

    groupFiles = {}
    for group, tempPath in sorted(groupTempFiles.items()):
        filename = _trigramGroupFileName(group)
        outPath = os.path.join(outdir, filename)
        with open(tempPath, "rt", encoding="utf-8") as src, gzip.open(outPath, "wt", encoding="utf-8") as dst:
            shutil.copyfileobj(src, dst)
        fileHash = sha256file(outPath)
        files[filename] = {
            "name": filename,
            "kind": "search-trigram-group",
            "sha256": fileHash,
            "group": group,
            "entryCount": groupRows[group],
        }
        groupFiles[group] = {
            "file": filename,
            "rows": groupRows[group],
        }

    buckets = {}
    for gram in sorted(selectedGrams):
        group = _trigramGroup(gram)
        if group not in groupFiles:
            continue
        rows = selectedGrams[gram]
        buckets[gram] = {
            "file": groupFiles[group]["file"],
            "rows": rows,
            "group": group,
        }

    shutil.rmtree(tempDir)
    return {
        "gramSize": TRIGRAM_SIZE,
        "groupPrefixSize": TRIGRAM_GROUP_PREFIX_SIZE,
        "maxBucketRows": MAX_TRIGRAM_BUCKET_ROWS,
        "groups": groupFiles,
        "buckets": buckets,
    }


def _lutToEntries(lutMap):
    entries = [None] * len(lutMap)
    for key, value in lutMap.items():
        entries[value] = json.loads(key)
    return entries


def updateLut(lutMap, item):
    key = json.dumps(item, separators=(",", ":"), sort_keys=True)
    if key not in lutMap:
        lutMap[key] = len(lutMap)
    return lutMap[key]

@click.command()
@click.argument("library", type=click.Path(dir_okay=False))
@click.argument("outdir", type=click.Path(file_okay=False))
@click.option("--ignoreoldstock", type=int, default=None,
    help="Ignore components that weren't on stock for more than n days")
@click.option("--jobs", type=int, default=1,
    help="Number of parallel processes. Defaults to 1, set to 0 to use all cores")
@click.option("--max-components-per-shard", type=int, default=MAX_COMPONENTS_PER_SHARD_DEFAULT,
    show_default=True,
    help="Maximum number of components stored in a search/lookup frontend shard")
@click.option("--browse-components-per-shard", type=int, default=BROWSE_COMPONENTS_PER_SHARD_DEFAULT,
    show_default=True,
    help="Maximum number of components stored in a category browsing frontend shard")
@click.option("--lookup-bucket-size", type=int, default=LOOKUP_BUCKET_SIZE_DEFAULT,
    show_default=True,
    help="Number of LCSC numeric codes stored in a single lookup shard")
def buildtables(library, outdir, ignoreoldstock, jobs, max_components_per_shard, browse_components_per_shard, lookup_bucket_size):
    """
    Build datatables out of the LIBRARY and save them in OUTDIR
    """
    lib = PartLibraryDb(library)
    Path(outdir).mkdir(parents=True, exist_ok=True)
    clearDir(outdir)
    del jobs  # kept for CLI compatibility with the previous builder

    categories = lib.categories()
    sortedCategories = [
        (catName, sorted(subcategories))
        for catName, subcategories in sorted(categories.items())
    ]
    total = sum(
        1
        for catName, subcategories in sortedCategories
        for subcatName in subcategories
        if _isUsableCategory(catName, subcatName)
    )
    processed = 0

    files = {}
    categoryEntries = []
    categoryEntriesByPair = {}
    attributeLut = {}
    lookupBuckets = {}
    trigramCounts = defaultdict(int)
    totalComponents = 0
    categoryId = 0
    searchIndexFilename = "search-index.tsv.gz"
    searchIndexPath = os.path.join(outdir, searchIndexFilename)
    searchIndexFile = gzip.open(searchIndexPath, "wt", encoding="utf-8")

    try:
        for catName, subcategories in sortedCategories:
            for subcatName in subcategories:
                if not _isUsableCategory(catName, subcatName):
                    continue
                processed += 1
                componentCount = lib.countCategoryComponents(
                    catName,
                    subcatName,
                    stockNewerThan=ignoreoldstock
                )
                if componentCount == 0:
                    continue

                canonical = normalize_category_pair(catName, subcatName)
                categoryPair = (canonical.category, canonical.subcategory)
                categoryEntry = categoryEntriesByPair.get(categoryPair)
                if categoryEntry is None:
                    categoryId += 1
                    categoryEntry = {
                        "id": categoryId,
                        "category": canonical.category,
                        "subcategory": canonical.subcategory,
                        "componentCount": 0,
                        "shards": [],
                        "browseShards": [],
                        "rawCategories": [],
                    }
                    categoryEntriesByPair[categoryPair] = categoryEntry
                    categoryEntries.append(categoryEntry)

                canonicalCategoryId = categoryEntry["id"]
                rawCategoryId = lib.getCategoryId(catName, subcatName)
                categoryKey = _stableComponentFilebase(catName, subcatName)
                shardNames = []
                browseShardNames = []
                totalComponents += componentCount
                categoryEntry["componentCount"] += componentCount
                categoryEntry["rawCategories"].append({
                    "id": rawCategoryId,
                    "category": catName,
                    "subcategory": subcatName,
                    "componentCount": componentCount,
                })
                print(
                    f"{((processed - 1) / max(total, 1) * 100):.2f} % "
                    f"{catName}: {subcatName} -> "
                    f"{canonical.category}: {canonical.subcategory} ({componentCount})"
                )

                chunk = []
                browseChunk = []
                shardIndex = 0
                browseShardIndex = 0
                for component in lib.iterCategoryComponents(
                        catName, subcatName, stockNewerThan=ignoreoldstock,
                        fetchSize=max(1000, min(max_components_per_shard, 5000))):
                    chunk.append(component)
                    browseChunk.append(component)
                    if len(chunk) >= max_components_per_shard:
                        shardIndex += 1
                        shardName = f"components-{categoryKey}-{shardIndex:03d}.jsonl.gz"
                        _flushComponentShard(
                            chunk, shardName, outdir, canonicalCategoryId, attributeLut,
                            files, lookupBuckets, lookup_bucket_size, searchIndexFile,
                            trigramCounts
                        )
                        shardNames.append(shardName)
                        chunk = []
                    if len(browseChunk) >= browse_components_per_shard:
                        browseShardIndex += 1
                        browseShardName = f"browse-components-{categoryKey}-{browseShardIndex:03d}.jsonl.gz"
                        _flushComponentShard(
                            browseChunk, browseShardName, outdir, canonicalCategoryId, attributeLut,
                            files, kind="browse-components"
                        )
                        browseShardNames.append(browseShardName)
                        browseChunk = []

                if chunk:
                    shardIndex += 1
                    shardName = f"components-{categoryKey}-{shardIndex:03d}.jsonl.gz"
                    _flushComponentShard(
                        chunk, shardName, outdir, canonicalCategoryId, attributeLut,
                        files, lookupBuckets, lookup_bucket_size, searchIndexFile,
                        trigramCounts
                    )
                    shardNames.append(shardName)
                if browseChunk:
                    browseShardIndex += 1
                    browseShardName = f"browse-components-{categoryKey}-{browseShardIndex:03d}.jsonl.gz"
                    _flushComponentShard(
                        browseChunk, browseShardName, outdir, canonicalCategoryId, attributeLut,
                        files, kind="browse-components"
                    )
                    browseShardNames.append(browseShardName)

                categoryEntry["shards"].extend(shardNames)
                categoryEntry["browseShards"].extend(browseShardNames)
    finally:
        searchIndexFile.close()

    searchIndexHash = sha256file(searchIndexPath)
    files[searchIndexFilename] = {
        "name": searchIndexFilename,
        "kind": "search-index",
        "sha256": searchIndexHash,
        "entryCount": totalComponents,
        "format": "tsv-v1",
    }

    searchTrigrams = _writeTrigramIndexes(
        searchIndexPath, outdir, files, totalComponents, trigramCounts
    )

    attributesLutFilename = "attributes-lut.json.gz"
    attributesLutPath = os.path.join(outdir, attributesLutFilename)
    attributesLutHash = _writeJsonArtifact(_lutToEntries(attributeLut), attributesLutPath, compress=True)
    files[attributesLutFilename] = {
        "name": attributesLutFilename,
        "kind": "attributes-lut",
        "sha256": attributesLutHash,
        "entryCount": len(attributeLut),
    }

    lookupFiles = {}
    for bucket, mapping in sorted(lookupBuckets.items()):
        lookupName = f"lookup-{bucket:05d}.json.gz"
        lookupPath = os.path.join(outdir, lookupName)
        lookupHash = _writeJsonArtifact(mapping, lookupPath, compress=True)
        files[lookupName] = {
            "name": lookupName,
            "kind": "lookup",
            "sha256": lookupHash,
            "bucket": bucket,
            "entryCount": len(mapping),
        }
        lookupFiles[str(bucket)] = lookupName

    manifest = {
        "version": WEB_FILE_FORMAT_VERSION,
        "created": datetime.datetime.now().astimezone().replace(microsecond=0).isoformat(),
        "totalComponents": totalComponents,
        "lookupBucketSize": lookup_bucket_size,
        "attributesLut": attributesLutFilename,
        "searchIndex": searchIndexFilename,
        "searchIndexFormat": "tsv-v1",
        "searchTrigrams": searchTrigrams,
        "categories": categoryEntries,
        "lookupBuckets": lookupFiles,
        "files": files,
    }
    _writeJsonArtifact(manifest, os.path.join(outdir, "manifest.json"), compress=False)
