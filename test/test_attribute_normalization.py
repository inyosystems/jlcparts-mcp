import math

import pytest

from jlcparts.datatables import normalizeAttribute


def normalized_values(key, value, capsys):
    normalized_key, normalized = normalizeAttribute(key, value)
    captured = capsys.readouterr()
    assert "Could not process key" not in captured.out
    assert normalized_key == key
    assert all(v[1] != "string" for v in normalized["values"].values())
    return normalized["values"]


def assert_quantity(actual, expected, unit):
    assert actual[1] == unit
    if expected == "NaN":
        assert actual[0] == "NaN"
    else:
        assert math.isclose(actual[0], expected)


@pytest.mark.parametrize(
    ("value", "rds", "vgs", "current"),
    [
        ("500mΩ@+5V,0.5A", 0.5, 5.0, 0.5),
        ("4.2Ω@=10V", 4.2, 10.0, "NaN"),
        ("120mΩ@10V,0.5·52A", 0.12, 10.0, "NaN"),
        ("11mΩ@10V,", 0.011, 10.0, "NaN"),
        ("0.0051Ω@10V,", 0.0051, 10.0, "NaN"),
    ],
)
def test_rds_on_at_vgs_id_malformed_tuples(value, rds, vgs, current, capsys):
    values = normalized_values(
        "Drain-Source On Resistance (RDS(on) @ Vgs, Id)",
        value,
        capsys,
    )

    assert_quantity(values["Rds"], rds, "resistance")
    assert_quantity(values["Vgs"], vgs, "voltage")
    assert_quantity(values["Id"], current, "current")


@pytest.mark.parametrize(
    ("value", "measurements"),
    [
        (
            "990mΩ@100mA,4.5V;1.9Ω@100mA,4.5V",
            [(0.99, 4.5, 0.1), (1.9, 4.5, 0.1)],
        ),
        (
            "400mΩ@4.5V,540mA;700mΩ@4.5V,430mA",
            [(0.4, 4.5, 0.54), (0.7, 4.5, 0.43)],
        ),
        (
            "170mΩ@4.5V;380mΩ@4.5V",
            [(0.17, 4.5, "NaN"), (0.38, 4.5, "NaN")],
        ),
        (
            "60mΩ@3.1A,10;95mΩ@2.7A,10V",
            [(0.06, 10.0, 3.1), (0.095, 10.0, 2.7)],
        ),
        (
            "9.2mΩ@9.8A,10V;60mΩ@5A,10V;30mΩ@6A,10V",
            [(0.0092, 10.0, 9.8), (0.06, 10.0, 5.0), (0.03, 10.0, 6.0)],
        ),
        (
            "26/55mΩ@10V",
            [(0.026, 10.0, "NaN"), (0.055, 10.0, "NaN")],
        ),
        (
            "900mΩ@10V,500mΩ",
            [(0.9, 10.0, 0.5)],
        ),
    ],
)
def test_rds_on_at_vgs_id_measurement_lists(value, measurements, capsys):
    values = normalized_values(
        "Drain-Source On Resistance (RDS(on) @ Vgs, Id)",
        value,
        capsys,
    )

    for index, (rds, vgs, current) in enumerate(measurements, start=1):
        suffix = f" {index}" if len(measurements) > 1 else ""
        assert_quantity(values[f"Rds{suffix}"], rds, "resistance")
        assert_quantity(values[f"Vgs{suffix}"], vgs, "voltage")
        assert_quantity(values[f"Id{suffix}"], current, "current")


@pytest.mark.parametrize(
    ("value", "measurements"),
    [
        (
            "1.5mΩ@10V, 2mΩ@4.5V",
            [(0.0015, 10.0), (0.002, 4.5)],
        ),
        (
            "47mΩ@10V, 60mΩ@4.5V, 85mΩ@2.5V",
            [(0.047, 10.0), (0.06, 4.5), (0.085, 2.5)],
        ),
        (
            "1Ω, 750mΩ",
            [(1.0, "NaN"), (0.75, "NaN")],
        ),
    ],
)
def test_rds_on_multiple_measurements(value, measurements, capsys):
    values = normalized_values(
        "Drain-Source On Resistance (RDS(on))",
        value,
        capsys,
    )

    for index, (rds, vgs) in enumerate(measurements, start=1):
        assert_quantity(values[f"Rds {index}"], rds, "resistance")
        assert_quantity(values[f"Vgs {index}"], vgs, "voltage")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("60Ω", 60.0),
        ("12Ω", 12.0),
        ("-", "NaN"),
    ],
)
def test_static_rds_on_values(value, expected, capsys):
    values = normalized_values("Static Drain-Source On Resistance (RDS(on))", value, capsys)

    assert_quantity(values["Rds"], expected, "resistance")
    assert_quantity(values["Vgs"], "NaN", "voltage")
    assert_quantity(values["Id"], "NaN", "current")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Coil Resistance", "1.44kΩ", {"resistance": 1440.0}),
        ("Coil Resistance", "540Ω, 400Ω, 220Ω", {
            "resistance 1": 540.0,
            "resistance 2": 400.0,
            "resistance 3": 220.0,
        }),
        ("Ron", "500mΩ", {"resistance": 0.5}),
        ("Ron", "245Ω@9V, 2.5kΩ@5V", {
            "resistance 1": 245.0,
            "resistance 2": 2500.0,
        }),
        ("Zener Impedance (ZZT)", "30Ω", {"resistance": 30.0}),
        ("Zener Impedance (ZZT)", "1.2kΩ", {"resistance": 1200.0}),
        ("Resistance - Initial (Ri) (Min)", "40mΩ", {"resistance": 0.04}),
        ("Resistance - Initial (Ri) (Min)", "2.5Ω", {"resistance": 2.5}),
        ("Resistance @ 25°C", "70mΩ", {"resistance": 0.07}),
        ("Resistance @ 25°C", "10kΩ", {"resistance": 10000.0}),
        ("Resistance @ 25°C", "60Ω, 30Ω", {"resistance 1": 60.0, "resistance 2": 30.0}),
        ("Resistance", "100Ω, 47Ω", {"resistance 1": 100.0, "resistance 2": 47.0}),
        ("Resistance", "5kΩ, 1.25kΩ", {"resistance 1": 5000.0, "resistance 2": 1250.0}),
        ("DC Resistance", "85mΩ, 340Ω", {"resistance 1": 0.085, "resistance 2": 340.0}),
        ("Resistance Value", "100kΩ", {"resistance": 100000.0}),
        ("Resistance Value", "1.45kΩ, 2.54kΩ", {"resistance 1": 1450.0, "resistance 2": 2540.0}),
        ("Output Impedance", "2.2kΩ", {"resistance": 2200.0}),
        ("Rated Impeance", "8Ω", {"resistance": 8.0}),
        ("Resistor on-State", "34mΩ", {"resistance": 0.034}),
        ("Resistor on-State", "10mΩ;30mΩ", {"resistance 1": 0.01, "resistance 2": 0.03}),
        ("On-State Resistance (Max)", "3.5kΩ", {"resistance": 3500.0}),
        ("On-State Resistance (Max)", "4.6Ω;5.7Ω", {"resistance 1": 4.6, "resistance 2": 5.7}),
        ("Series Resistance (RS)", "650mΩ", {"resistance": 0.65}),
        ("Input Resistor", "10kΩ", {"resistance": 10000.0}),
        ("Input Resistor", "-", {"resistance": "NaN"}),
        ("Contact Resistance", "30mΩ", {"resistance": 30e-3}),
        ("Contact Resistance", "100MΩ", {"resistance": 100e6}),
        ("Contact Resistance", "-", {"resistance": "NaN"}),
        ("Current Terminal Resistance", "1mΩ", {"resistance": 0.001}),
        ("Output Resistance", "2Ω, 1.5Ω", {"resistance 1": 2.0, "resistance 2": 1.5}),
        ("On Resistance", "750mΩ", {"resistance": 0.75}),
        ("On-Resistance", "28mΩ", {"resistance": 0.028}),
        ("Total Resistance", "5kΩ", {"resistance": 5000.0}),
    ],
)
def test_resistance_list_attributes(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, resistance in expected.items():
        assert_quantity(values[quantity], resistance, "resistance")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Insulation Resistance", "100MΩ", 100e6),
        ("Insulation Resistance", "1.011kΩ", 1011.0),
        ("Insulation Resistance", "-", "NaN"),
        ("Insulation Resistance(Ir)", "10MΩ", 10e6),
        ("Insulation Resistance(Ir)", "10mΩ", 0.01),
        ("Insulation Resistance (Min)", "100MΩ", 100e6),
        ("Nominal Cold Resistance", "2.52mΩ", 0.00252),
    ],
)
def test_insulation_resistance_values(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    assert_quantity(values["resistance"], expected, "resistance")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("27mΩ@100kHz", {"esr": (0.027, "resistance"), "frequency": (100e3, "frequency")}),
        ("20mΩ", {"esr": (0.02, "resistance")}),
        ("-", {"esr": ("NaN", "resistance"), "frequency": ("NaN", "frequency")}),
    ],
)
def test_esr_values(value, expected, capsys):
    values = normalized_values("ESR", value, capsys)

    for quantity, (amount, unit) in expected.items():
        assert_quantity(values[quantity], amount, unit)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("500Ω", 500.0),
        ("1.75kΩ", 1750.0),
        ("-", "NaN"),
    ],
)
def test_impedance_zzk(value, expected, capsys):
    values = normalized_values("Impedance(Zzk)", value, capsys)

    assert_quantity(values["impedance"], expected, "resistance")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("400kΩ", {"impedance": 400e3}),
        ("80mΩ", {"impedance": 0.08}),
        ("113kΩ;256kΩ;7.8MΩ", {
            "impedance 1": 113e3,
            "impedance 2": 256e3,
            "impedance 3": 7.8e6,
        }),
        ("50Ω, 80Ω", {"impedance 1": 50.0, "impedance 2": 80.0}),
        ("-", {"impedance": "NaN"}),
    ],
)
def test_impedance_values(value, expected, capsys):
    values = normalized_values("Impedance", value, capsys)

    for quantity, resistance in expected.items():
        assert_quantity(values[quantity], resistance, "resistance")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0.2Ω", 0.2),
        ("150mΩ", 0.15),
        ("-", "NaN"),
    ],
)
def test_dynamic_impedance_values(value, expected, capsys):
    values = normalized_values("Dynamic Impedance", value, capsys)

    assert_quantity(values["impedance"], expected, "resistance")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("DCR Secondary Side (Max)", "5.04Ω", 5.04),
        ("DCR Secondary Side (Max)", "0.75mΩ", 0.00075),
        ("DCR Primary Side (Max)", "1.5mΩ", 0.0015),
    ],
)
def test_dcr_resistance_values(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    assert_quantity(values["resistance"], expected, "resistance")


@pytest.mark.parametrize("key", ["Characteristic Impedance", "Resonant Impedance"])
def test_impedance_alias_values(key, capsys):
    values = normalized_values(key, "50Ω", capsys)

    assert_quantity(values["impedance"], 50.0, "resistance")


@pytest.mark.parametrize("key", ["Impedance Ratio-Unbalanced/Balanced", "Impedance - Unbalanced/Balanced"])
def test_impedance_ratio_aliases(key, capsys):
    values = normalized_values(key, "50Ω:100Ω", capsys)

    assert_quantity(values["ratio"], 0.5, "ratio")


@pytest.mark.parametrize(
    ("value", "measurements"),
    [
        ("300Ω@100MHz, 250Ω@100MHz", [(300.0, 100e6), (250.0, 100e6)]),
        ("2.8kΩ@10MHz, 1kΩ@10MHz", [(2800.0, 10e6), (1000.0, 10e6)]),
        ("1.2kΩ@100MHz, 900Ω@1GHz", [(1200.0, 100e6), (900.0, 1e9)]),
    ],
)
def test_impedance_at_frequency_lists(value, measurements, capsys):
    values = normalized_values("Impedance @ Frequency", value, capsys)

    for index, (impedance, frequency) in enumerate(measurements, start=1):
        assert_quantity(values[f"impedance {index}"], impedance, "resistance")
        assert_quantity(values[f"frequency {index}"], frequency, "frequency")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Single Supply", "2V~36V", (2.0, 36.0)),
        ("Dual Supply", "±18V", (-18.0, 18.0)),
        ("Operating Voltage", "±15V", (-15.0, 15.0)),
        ("Operating Voltage", "-15V~15V", (-15.0, 15.0)),
        ("Voltage - Input(DC)", "900mV~5.5V", (0.9, 5.5)),
        ("Voltage - Input(DC)", "45V", 45.0),
        ("Input Voltage(DC)", "6V~58V", (6.0, 58.0)),
        ("Input Voltage(DC)", "24V", 24.0),
        ("Motor Drive Voltage(Vm)", "8V~45V", (8.0, 45.0)),
        ("Control Voltage", "2.5V~21V", (2.5, 21.0)),
        ("Vcm - Common Mode Voltage", "-300mV~26V", (-0.3, 26.0)),
        ("Vcm - Common Mode Voltage", "48V", 48.0),
        ("Low Voltage Detection Threshold", "1.71V~5.5V", (1.71, 5.5)),
        ("Low Voltage Detection Threshold", "3.3V", 3.3),
        ("Operating Voltage Range", "1.71V~5.5V", (1.71, 5.5)),
        ("Operating Voltage Range", "1.2V", 1.2),
        ("Low Level Range (VIL)", "700mV~800mV", (0.7, 0.8)),
        ("Low Level Range (VIL)", "0.8V", 0.8),
        ("Low Level Range (VOL)", "100mV~260mV", (0.1, 0.26)),
        ("Low Level Range (VOL)", "0.05V", 0.05),
        ("Operating Voltage", "-", "NaN"),
    ],
)
def test_supply_voltage_ranges(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    if isinstance(expected, tuple):
        assert_quantity(values["voltage min"], expected[0], "voltage")
        assert_quantity(values["voltage max"], expected[1], "voltage")
    else:
        assert_quantity(values["voltage"], expected, "voltage")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("385V", 385.0),
        ("1.465kV", 1465.0),
        ("-", "NaN"),
    ],
)
def test_allowable_voltage_dc(value, expected, capsys):
    values = normalized_values("Allowable Voltage (DC)", value, capsys)

    assert_quantity(values["voltage"], expected, "voltage")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("300V", 300.0),
        ("1kV", 1000.0),
        ("1.1kV", 1100.0),
    ],
)
def test_allowable_voltage_ac(value, expected, capsys):
    values = normalized_values("Allowable Voltage (AC)", value, capsys)

    assert_quantity(values["voltage"], expected, "voltage")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("35V", {"voltage": 35.0}),
        ("0V~600V", {"voltage min": 0.0, "voltage max": 600.0}),
        ("220V, 110V", {"voltage 1": 220.0, "voltage 2": 110.0}),
        ("1.8kV", {"voltage": 1800.0}),
    ],
)
def test_load_voltage(value, expected, capsys):
    values = normalized_values("Load Voltage", value, capsys)

    for quantity, voltage in expected.items():
        assert_quantity(values[quantity], voltage, "voltage")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2.7V~5.5V", {"voltage min": 2.7, "voltage max": 5.5}),
        ("900mV", {"voltage": 0.9}),
        ("2.5V, 3.3V", {"voltage 1": 2.5, "voltage 2": 3.3}),
        ("2.25V~5.5V, 1.71V~1.89V", {
            "voltage 1 min": 2.25,
            "voltage 1 max": 5.5,
            "voltage 2 min": 1.71,
            "voltage 2 max": 1.89,
        }),
    ],
)
def test_supply_voltage_vcca(value, expected, capsys):
    values = normalized_values("Voltage - Supply(Vcca)", value, capsys)

    for quantity, voltage in expected.items():
        assert_quantity(values[quantity], voltage, "voltage")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2.7V~5.5V", {"voltage min": 2.7, "voltage max": 5.5}),
        ("-5V~-3.3V", {"voltage min": -5.0, "voltage max": -3.3}),
        ("900mV", {"voltage": 0.9}),
    ],
)
def test_supply_voltage_vccb(value, expected, capsys):
    values = normalized_values("Voltage - Supply(Vccb)", value, capsys)

    for quantity, voltage in expected.items():
        assert_quantity(values[quantity], voltage, "voltage")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("14V~30V", {"voltage min": 14.0, "voltage max": 30.0}),
        ("-500mV~35V", {"voltage min": -0.5, "voltage max": 35.0}),
        ("30V", {"voltage": 30.0}),
    ],
)
def test_supply_voltage_driver(value, expected, capsys):
    values = normalized_values("Voltage - Supply (Driver)", value, capsys)

    for quantity, voltage in expected.items():
        assert_quantity(values[quantity], voltage, "voltage")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("700V", 700.0),
        ("4.2kV", 4200.0),
        ("1.05kV", 1050.0),
    ],
)
def test_impulse_breakdown_voltage(value, expected, capsys):
    values = normalized_values("Impulse Breakdown Voltage(Vimp)", value, capsys)

    assert_quantity(values["voltage"], expected, "voltage")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("230V", {"voltage": 230.0}),
        ("72V~108V", {"voltage min": 72.0, "voltage max": 108.0}),
        ("2.5kV", {"voltage": 2500.0}),
    ],
)
def test_dc_spark_over_voltage(value, expected, capsys):
    values = normalized_values("DC Spark-Over Voltage", value, capsys)

    for quantity, voltage in expected.items():
        assert_quantity(values[quantity], voltage, "voltage")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Input Voltage (Vin)", "2.7V~5.5V", {"voltage min": 2.7, "voltage max": 5.5}),
        ("Voltage - Supply(Input)", "±18V", {"voltage min": -18.0, "voltage max": 18.0}),
        ("Voltage - Supply(Output)", "3V~20V", {"voltage min": 3.0, "voltage max": 20.0}),
        ("Reverse Voltage", "6V", {"voltage": 6.0}),
        ("On-State Voltage (Vt)", "3.5V", {"voltage": 3.5}),
        ("Lag of Receiver", "120mV", {"voltage": 0.12}),
        ("End-Off Voltage", "750mV", {"voltage": 0.75}),
        ("End-Off Voltage", "-", {"voltage": "NaN"}),
        ("Voltage - Supply (Bus)", "2.9V~5.5V", {"voltage min": 2.9, "voltage max": 5.5}),
        ("Voltage - Supply (Logic)", "10V~30V", {"voltage min": 10.0, "voltage max": 30.0}),
        ("Integrated Power Output Voltage", "3V~3.5V", {"voltage min": 3.0, "voltage max": 3.5}),
        ("Supply Voltage(Vcc)", "4.5V~5.5V", {"voltage min": 4.5, "voltage max": 5.5}),
        ("ESD Protect", "±15000V", {"voltage min": -15000.0, "voltage max": 15000.0}),
        ("Supply Voltage(Single)", "2V~5.5V", {"voltage min": 2.0, "voltage max": 5.5}),
        ("Mains Input", "3V~3.6V;4.5V~5.5V", {
            "voltage 1 min": 3.0,
            "voltage 1 max": 3.6,
            "voltage 2 min": 4.5,
            "voltage 2 max": 5.5,
        }),
        ("Receiver Hysteresis", "50mV", {"voltage": 0.05}),
        ("High Level Range (VIH)", "1.75V~3.5V", {"voltage min": 1.75, "voltage max": 3.5}),
        ("High Level Range (VOH)", "1.9V~5.34V", {"voltage min": 1.9, "voltage max": 5.34}),
        ("Input Logic Level -Low", "750mV~1.5V", {"voltage min": 0.75, "voltage max": 1.5}),
        ("Input Logic Level -Low", "900mV, 300mV, 600mV, 1.1V", {
            "voltage 1": 0.9,
            "voltage 2": 0.3,
            "voltage 3": 0.6,
            "voltage 4": 1.1,
        }),
        ("Input Voltage Range", "-3V~3V, 0.06V~10V", {
            "voltage 1 min": -3.0,
            "voltage 1 max": 3.0,
            "voltage 2 min": 0.06,
            "voltage 2 max": 10.0,
        }),
        ("Common Mode Voltage", "0V~76V", {"voltage min": 0.0, "voltage max": 76.0}),
        ("Voltage - Input", "250V", {"voltage": 250.0}),
        ("Control Voltage Range/Center", "0V~3.3V", {"voltage min": 0.0, "voltage max": 3.3}),
    ],
)
def test_extra_voltage_ranges(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, voltage in expected.items():
        assert_quantity(values[quantity], voltage, "voltage")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("On - State Voltage(Vt)", "4V", {"voltage": 4.0}),
        ("Switching Voltage(Vs)", "1kV", {"voltage": 1000.0}),
        ("Peak Off - State Voltage(Vdrm)", "1.2kV", {"voltage": 1200.0}),
        ("Human Body Model", "±30kV", {"voltage min": -30000.0, "voltage max": 30000.0}),
        ("Human Body Model", "-", {"voltage": "NaN"}),
        ("Contact Discharge Vesd", "±8kV", {"voltage min": -8000.0, "voltage max": 8000.0}),
        ("Contact Discharge Vesd", "30kV", {"voltage": 30000.0}),
        ("On State Voltage", "1V", {"voltage": 1.0}),
        ("Trigger Voltage", "7.5V", {"voltage": 7.5}),
        ("Operating Voltage (Max)", "250V;60V", {"voltage 1": 250.0, "voltage 2": 60.0}),
        ("Switching Voltage (Vs)", "25V", {"voltage": 25.0}),
        ("Peak Off-State Voltage", "6V", {"voltage": 6.0}),
        ("Reset Voltage", "620mV", {"voltage": 0.62}),
        ("Peak Impulse Voltage", "650V", {"voltage": 650.0}),
        ("Vbo (Typ)", "40V", {"voltage": 40.0}),
        ("Breakover Voltage Vbo (Typ)", "110V", {"voltage": 110.0}),
        ("Breakover Voltage Symmetry", "3V", {"voltage": 3.0}),
        ("Dynamic Breakover Voltage", "5V", {"voltage": 5.0}),
        ("Forward Voltage", "3.2V(UVA), 6V(UVC)", {"voltage 1": 3.2, "voltage 2": 6.0}),
        ("Forward Voltage", "R:1.8V~2.4V;G:2.8V~3.4V;B:2.8V~3.4V", {
            "voltage R min": 1.8,
            "voltage R max": 2.4,
            "voltage G min": 2.8,
            "voltage G max": 3.4,
            "voltage B min": 2.8,
            "voltage B max": 3.4,
        }),
        ("Peak Repetitive Off State Voltage (Vdrm)", "1.2kV", {"voltage": 1200.0}),
        ("Gate Trigger Voltage (Vgt)", "1.1V, 1.7V", {"voltage 1": 1.1, "voltage 2": 1.7}),
        ("Collector-Emitter Breakdown Voltage (VCES)", "1.2kV", {"voltage": 1200.0}),
        ("Gate-Emitter Threshold Voltage (VGE(Th)@IC)", "2V@5V,10A", {"voltage": 2.0}),
        ("Gate-Emitter Threshold Voltage (VGE(Th)@IC)", "3.75V, 5.75V", {"voltage 1": 3.75, "voltage 2": 5.75}),
        ("Voltage - on State(Vtm)", "1.6V", {"voltage": 1.6}),
        ("Repetitive Peak Off-State Voltage", "30V", {"voltage": 30.0}),
        ("Collector Emitter Voltage", "20V", {"voltage": 20.0}),
        ("Antistatic Capacity", "R:3000V, G:450V, B:250V", {
            "voltage R": 3000.0,
            "voltage G": 450.0,
            "voltage B": 250.0,
        }),
        ("DC Reverse Voltage(Vr)", "20V", {"voltage": 20.0}),
        ("Voltage - Input (Max)(Vi(Off))", "300mV@100uA,5V", {"voltage": 0.3}),
        ("Input Voltage (Vi(on)@IC,VCE)", "1.4V@1mA,0.3V", {"voltage": 1.4}),
        ("Output Voltage(Vo(on))", "300mV@5mA,0.25mA", {"voltage": 0.3}),
        ("Voltage - Isolation", "1.6 kV", {"voltage": 1600.0}),
        ("Forward Voltage Drop", "1.8V, 1.7V, 1.6V", {
            "voltage 1": 1.8,
            "voltage 2": 1.7,
            "voltage 3": 1.6,
        }),
        ("Switching Voltage", "180V", {"voltage": 180.0}),
        ("DC Reverse Voltage", "24.7V", {"voltage": 24.7}),
        ("Peak Off-State Voltage(Vdrm)", "400V", {"voltage": 400.0}),
        ("Collector-Emitter Saturation Voltage (VCE(sat)@IC,IF)", "0.4V@2.5mA,10mA", {"voltage": 0.4}),
        ("Receiving End Voltage", "70V", {"voltage": 70.0}),
        ("Voltage - Load", "1500V", {"voltage": 1500.0}),
        ("Input Forward Voltage", "1.25V", {"voltage": 1.25}),
        ("Reverse Pressure (Typ)", "60V", {"voltage": 60.0}),
        ("ESD Protection Voltage", "7.5kV", {"voltage": 7500.0}),
        ("MOS Breakdown Voltage", "230V", {"voltage": 230.0}),
        ("Insulated Voltage", "3.5kV@AC;6kV", {"voltage 1": 3500.0, "voltage 2": 6000.0}),
        ("Input Offset Voltage", "4mV", {"voltage": 0.004}),
        ("VBE Saturation(VBE(Sat))", "0.86V", {"voltage": 0.86}),
        ("VBE on(VBE(on))", "2.8V, 3V, 2V", {"voltage 1": 2.8, "voltage 2": 3.0, "voltage 3": 2.0}),
        ("Rated Output Voltage", "954mV", {"voltage": 0.954}),
        ("Vmax", "32V", {"voltage": 32.0}),
        ("Forward Voltage (Typ)", "1.2V", {"voltage": 1.2}),
        ("Applied Voltage", "150V", {"voltage": 150.0}),
        ("Withstand Voltage - Output", "80V", {"voltage": 80.0}),
        ("Gate-Source Breakdown Voltage (V(Br)Gss)", "40V", {"voltage": 40.0}),
        ("Gate-Source Cutoff Voltage (Vgs(Off)@ID)", "1.5V@0.1uA", {"voltage": 1.5}),
        ("Output Voltage (Vo(on)@IO/Ii)", "100mV@5mA,0.25mA", {"voltage": 0.1}),
        ("Input Voltage (Vi(Off)@IC,VCE)", "300mV@100uA,5V", {"voltage": 0.3}),
        ("Diode Forward Voltage (Vf@IF)", "2.7V@30A", {"voltage": 2.7}),
        ("Collector-Emitter Saturation Voltage (VCE(sat)@IC,VGE)", "1.6V@60A,15V", {"voltage": 1.6}),
        ("Peak Forward on State Voltage (Vtm)", "1.9V", {"voltage": 1.9}),
        ("Voltage - on State (Vtm)", "1.55V", {"voltage": 1.55}),
        ("Output Low Voltage", "0.2V~0.5V", {"voltage 1 min": 0.2, "voltage 1 max": 0.5}),
        ("Output High Voltage", "700mV", {"voltage 1": 0.7}),
        ("Input Low Voltage", "500mV~800mV", {"voltage 1 min": 0.5, "voltage 1 max": 0.8}),
        ("Intput High Voltage", "2V~5.5V", {"voltage 1 min": 2.0, "voltage 1 max": 5.5}),
        ("Dielectric Withstand Voltage", "500V", {"voltage": 500.0}),
    ],
)
def test_additional_voltage_aliases(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, voltage in expected.items():
        assert_quantity(values[quantity], voltage, "voltage")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Coil Voltage", "DC12V", {"voltage": (12.0, "voltage")}),
        ("Coil Voltage", "220V, 240V", {
            "voltage 1": (220.0, "voltage"),
            "voltage 2": (240.0, "voltage"),
        }),
        ("Switching Voltage (Max)", "400V@AC", {"voltage": (400.0, "voltage")}),
        ("Switching Voltage (Max)", "250V@AC, 220V@DC", {
            "voltage 1": (250.0, "voltage"),
            "voltage 2": (220.0, "voltage"),
        }),
        ("Switching Voltage (Max)", "50A", {"current": (50.0, "current")}),
        ("Switching Voltage (Max)", "-", {"voltage": ("NaN", "voltage")}),
    ],
)
def test_additional_voltage_or_current_values(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, expected_value in expected.items():
        value, unit = expected_value
        assert_quantity(values[quantity], value, unit)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("±0.5V", {"voltage min": -0.5, "voltage max": 0.5}),
        ("-40V~2V", {"voltage min": -40.0, "voltage max": 2.0}),
        ("±500mV", {"voltage min": -0.5, "voltage max": 0.5}),
    ],
)
def test_differential_voltage(value, expected, capsys):
    values = normalized_values("Differential Voltage", value, capsys)

    for quantity, voltage in expected.items():
        assert_quantity(values[quantity], voltage, "voltage")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("16mV", {"voltage": 0.016}),
        ("11.5mV~13.86mV", {"voltage min": 0.0115, "voltage max": 0.01386}),
        ("2.8V", {"voltage": 2.8}),
    ],
)
def test_tripping_voltage(value, expected, capsys):
    values = normalized_values("Tripping Voltage", value, capsys)

    for quantity, voltage in expected.items():
        assert_quantity(values[quantity], voltage, "voltage")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("DC Rated Voltage", "50V", {"voltage": 50.0}),
        ("Voltage(AC)", "275V, 310V", {"voltage 1": 275.0, "voltage 2": 310.0}),
        ("Overload Voltage (Max)", "2kV", {"voltage": 2000.0}),
        ("Voltage Drop", "92mV", {"voltage": 0.092}),
        ("Voltage Withstand", "15kV, 8kV", {"voltage 1": 15000.0, "voltage 2": 8000.0}),
        ("Withstanding Voltage", "600V@AC,3secs", {"voltage": 600.0}),
        ("Withstanding Voltage", "2000V@AC,1mins;2400V@AC,1secs", {"voltage 1": 2000.0, "voltage 2": 2400.0}),
    ],
)
def test_extra_scalar_voltages(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, voltage in expected.items():
        assert_quantity(values[quantity], voltage, "voltage")


def test_charging_saturation_voltage(capsys):
    values = normalized_values("Charging Saturation Voltage", "4.2V", capsys)

    assert_quantity(values["voltage"], 4.2, "voltage")


def test_charging_saturation_voltage_list(capsys):
    values = normalized_values("Charging Saturation Voltage", "4.2V, 4.35V, 4.3V", capsys)

    assert_quantity(values["voltage 1"], 4.2, "voltage")
    assert_quantity(values["voltage 2"], 4.35, "voltage")
    assert_quantity(values["voltage 3"], 4.3, "voltage")


def test_operating_voltage_multiple_ranges(capsys):
    values = normalized_values(
        "Operating Voltage",
        "1.71V~1.89V;3.135V~3.465V",
        capsys,
    )

    assert_quantity(values["voltage 1 min"], 1.71, "voltage")
    assert_quantity(values["voltage 1 max"], 1.89, "voltage")
    assert_quantity(values["voltage 2 min"], 3.135, "voltage")
    assert_quantity(values["voltage 2 max"], 3.465, "voltage")


def test_input_voltage_dc_multiple_ranges(capsys):
    values = normalized_values("Input Voltage(DC)", "7V~31V;6.5V~36V", capsys)

    assert_quantity(values["voltage 1 min"], 7.0, "voltage")
    assert_quantity(values["voltage 1 max"], 31.0, "voltage")
    assert_quantity(values["voltage 2 min"], 6.5, "voltage")
    assert_quantity(values["voltage 2 max"], 36.0, "voltage")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("125V;250V", {"voltage 1": 125.0, "voltage 2": 250.0}),
        ("80~305VAC、113~431VDC", {
            "voltage 1 min": 80.0,
            "voltage 1 max": 305.0,
            "voltage 2 min": 113.0,
            "voltage 2 max": 431.0,
        }),
        ("85~264VAC/100~370VDC", {
            "voltage 1 min": 85.0,
            "voltage 1 max": 264.0,
            "voltage 2 min": 100.0,
            "voltage 2 max": 370.0,
        }),
        ("85-305VAC、120-430VDC", {
            "voltage 1 min": 85.0,
            "voltage 1 max": 305.0,
            "voltage 2 min": 120.0,
            "voltage 2 max": 430.0,
        }),
    ],
)
def test_input_voltage_lists(value, expected, capsys):
    values = normalized_values("Input Voltage", value, capsys)

    for quantity, voltage in expected.items():
        assert_quantity(values[quantity], voltage, "voltage")


def test_common_mode_voltage_multiple_ranges(capsys):
    values = normalized_values("Vcm - Common Mode Voltage", "-2V~76V, -2V~42V", capsys)

    assert_quantity(values["voltage 1 min"], -2.0, "voltage")
    assert_quantity(values["voltage 1 max"], 76.0, "voltage")
    assert_quantity(values["voltage 2 min"], -2.0, "voltage")
    assert_quantity(values["voltage 2 max"], 42.0, "voltage")


def test_low_voltage_detection_threshold_multiple_ranges(capsys):
    values = normalized_values("Low Voltage Detection Threshold", "1.14V~1.26V;3V~5.5V", capsys)

    assert_quantity(values["voltage 1 min"], 1.14, "voltage")
    assert_quantity(values["voltage 1 max"], 1.26, "voltage")
    assert_quantity(values["voltage 2 min"], 3.0, "voltage")
    assert_quantity(values["voltage 2 max"], 5.5, "voltage")


def test_operating_voltage_range_multiple_values(capsys):
    values = normalized_values("Operating Voltage Range", "3.3V;5V", capsys)

    assert_quantity(values["voltage 1"], 3.3, "voltage")
    assert_quantity(values["voltage 2"], 5.0, "voltage")


def test_dual_supply_multiple_ranges(capsys):
    values = normalized_values(
        "Dual Supply",
        "1V~18V, -18V~-1V",
        capsys,
    )

    assert_quantity(values["voltage 1 min"], 1.0, "voltage")
    assert_quantity(values["voltage 1 max"], 18.0, "voltage")
    assert_quantity(values["voltage 2 min"], -18.0, "voltage")
    assert_quantity(values["voltage 2 max"], -1.0, "voltage")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("30mA", {"current": 0.03}),
        ("860uA~1.1mA", {"current min": 860e-6, "current max": 1.1e-3}),
        (
            "620uA, 980uA, 800uA, 300uA",
            {
                "current 1": 620e-6,
                "current 2": 980e-6,
                "current 3": 800e-6,
                "current 4": 300e-6,
            },
        ),
        ("-", {"current": "NaN"}),
    ],
)
def test_current_consumption(value, expected, capsys):
    values = normalized_values("Current Consumption", value, capsys)

    for quantity, current in expected.items():
        assert_quantity(values[quantity], current, "current")


def test_output_current_list(capsys):
    values = normalized_values("Output Current", "46mA, 42mA, 48mA, 38mA", capsys)

    assert_quantity(values["current 1"], 46e-3, "current")
    assert_quantity(values["current 2"], 42e-3, "current")
    assert_quantity(values["current 3"], 48e-3, "current")
    assert_quantity(values["current 4"], 38e-3, "current")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("6V", {"voltage": 6.0}),
        ("13.3V;7.5V", {"voltage 1": 13.3, "voltage 2": 7.5}),
    ],
)
def test_breakdown_voltage_vbr(value, expected, capsys):
    values = normalized_values("Breakdown Voltage (Vbr)", value, capsys)

    for quantity, voltage in expected.items():
        assert_quantity(values[quantity], voltage, "voltage")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1.2kV", {"Vds": 1200.0}),
        ("600V, 650V", {"Vds 1": 600.0, "Vds 2": 650.0}),
    ],
)
def test_drain_to_source_voltage(value, expected, capsys):
    values = normalized_values("Drain to Source Voltage", value, capsys)

    for quantity, voltage in expected.items():
        assert_quantity(values[quantity], voltage, "voltage")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("17V", {"voltage": 17.0}),
        ("26V;12V", {"voltage 1": 26.0, "voltage 2": 12.0}),
    ],
)
def test_clamping_voltage_ipp(value, expected, capsys):
    values = normalized_values("Clamping Voltage@IPP", value, capsys)

    for quantity, voltage in expected.items():
        assert_quantity(values[quantity], voltage, "voltage")


@pytest.mark.parametrize(
    ("key", "value", "measurements"),
    [
        (
            "Voltage Dropout",
            "235mV@(500mA), 260mV@(500mA)",
            [(0.235, 0.5), (0.26, 0.5)],
        ),
        (
            "Voltage Dropout",
            "1V@(100mA), 1.1V@(800mA), 1.05V@(500mA)",
            [(1.0, 0.1), (1.1, 0.8), (1.05, 0.5)],
        ),
        (
            "Dropout Voltage",
            "-;200mV@(200mA)",
            [("NaN", "NaN"), (0.2, 0.2)],
        ),
    ],
)
def test_dropout_voltage_at_current_lists(key, value, measurements, capsys):
    values = normalized_values(key, value, capsys)

    for index, (voltage, current) in enumerate(measurements, start=1):
        suffix = f" {index}" if len(measurements) > 1 else ""
        assert_quantity(values[f"voltage{suffix}"], voltage, "voltage")
        assert_quantity(values[f"current{suffix}"], current, "current")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("3pF", {"capacitance": 3e-12}),
        (
            "3pF, 1.5pF, 5pF",
            {
                "capacitance 1": 3e-12,
                "capacitance 2": 1.5e-12,
                "capacitance 3": 5e-12,
            },
        ),
        ("0.5pF, 2.5nF", {"capacitance 1": 0.5e-12, "capacitance 2": 2.5e-9}),
    ],
)
def test_junction_capacitance_list(value, expected, capsys):
    values = normalized_values("Junction Capacitance", value, capsys)

    for quantity, capacitance in expected.items():
        assert_quantity(values[quantity], capacitance, "capacitance")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1000uF", {"capacitance": 1000e-6}),
        ("3300uF, 300uF", {"capacitance 1": 3300e-6, "capacitance 2": 300e-6}),
    ],
)
def test_capacitive_load_max(value, expected, capsys):
    values = normalized_values("Capacitive Load (Max)", value, capsys)

    for quantity, capacitance in expected.items():
        assert_quantity(values[quantity], capacitance, "capacitance")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Nominal Capacitance", "1uF", {"capacitance": 1e-6}),
        ("Capacitance @ VR, F", "120pF", {"capacitance": 120e-12}),
        ("Off-State Capacitance (Co)", "100pF", {"capacitance": 100e-12}),
        ("Maximum Capacitance @ 1mhz", "1pF", {"capacitance": 1e-12}),
        ("Maximum Capacitance @ 1mhz", "680nF", {"capacitance": 680e-9}),
        ("Maximum Capacitance @ 1mhz", "-", {"capacitance": "NaN"}),
        ("Inter-Electrode Capacitance", "0.45pF", {"capacitance": 0.45e-12}),
        ("Electrostatic Capacitance", "0.8pF", {"capacitance": 0.8e-12}),
        ("Input Capacitance", "1.8pF", {"capacitance": 1.8e-12}),
        ("Input Capacitance", "-", {"capacitance": "NaN"}),
        ("Input Capacitance (Cies@VCE)", "3.29nF@25V", {"capacitance": 3.29e-9, "Vce": 25.0}),
        ("Input Capacitance (Cies@VCE)", "-", {"capacitance": "NaN", "Vce": "NaN"}),
        ("Capacitance-Input", "1.5pF", {"capacitance": 1.5e-12}),
        ("Input Capacitiance(Ci)", "15pF", {"capacitance": 15e-12}),
        ("Capacitance", "0.35pF, 0.45pF", {"capacitance 1": 0.35e-12, "capacitance 2": 0.45e-12}),
        ("Capacitance", "30pF~60pF", {"capacitance 1 min": 30e-12, "capacitance 1 max": 60e-12}),
        ("Capacitance", "1pF~100uF", {"capacitance 1 min": 1e-12, "capacitance 1 max": 100e-6}),
        ("Capacitance", "180pF@1kHz,1V", {"capacitance": 180e-12}),
        ("Electrostatic Capacity", "30pF~60pF", {"capacitance min": 30e-12, "capacitance max": 60e-12}),
        ("Built-in Load Capacitance", "10pF", {"capacitance": 10e-12}),
        ("Built - in Load Capacitance", "47pF", {"capacitance": 47e-12}),
        ("Load Capacitor", "12.5pF", {"capacitance": 12.5e-12}),
        ("Load Capacitance", "7.36pF", {"capacitance": 7.36e-12}),
        ("External Load Capacitor", "10pF", {"capacitance": 10e-12}),
        ("Static Capacitance", "3.2pF", {"capacitance": 3.2e-12}),
        ("Sensor Capacitance Range", "0pF~119pF", {"capacitance min": 0, "capacitance max": 119e-12}),
    ],
)
def test_extra_capacitance_attributes(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, amount in expected.items():
        unit = "voltage" if quantity == "Vce" else "capacitance"
        assert_quantity(values[quantity], amount, unit)


def test_equivalent_series_inductance_values(capsys):
    values = normalized_values("Equivalent Series Inductance", "0.1nH", capsys)

    assert_quantity(values["inductance"], 0.1e-9, "inductance")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Secondary Side Inductance", "652uH", {"inductance": 652e-6}),
        ("Leakage Inductance", "300nH", {"inductance": 300e-9}),
        ("Inductance", "150uH, 450uH", {"inductance 1": 150e-6, "inductance 2": 450e-6}),
    ],
)
def test_inductance_values(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, inductance in expected.items():
        assert_quantity(values[quantity], inductance, "inductance")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Inductor", "350uH", {"inductance": 350e-6}),
        ("Inductor", "150uH;450uH", {"inductance 1": 150e-6, "inductance 2": 450e-6}),
        ("Inductor(100khz,1/10v/8m A) (Min)", "325uH", {"inductance": 325e-6}),
    ],
)
def test_inductor_aliases(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, inductance in expected.items():
        assert_quantity(values[quantity], inductance, "inductance")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("240uV", 240e-6),
        ("250nV", 250e-9),
        ("1.6V", 1.6),
    ],
)
def test_input_offset_voltage_vos(value, expected, capsys):
    values = normalized_values("Voltage - Input Offset(VOS)", value, capsys)

    assert_quantity(values["voltage"], expected, "voltage")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Output Logic Level - High", "8.3V", {"voltage 1": 8.3}),
        ("Output Logic Level - Low", "400mV", {"voltage 1": 0.4}),
        ("Input Logic Level - High", "1.75V~3.5V", {"voltage 1 min": 1.75, "voltage 1 max": 3.5}),
        ("Input Logic Level - Low", "500mV, 850mV, 750mV", {
            "voltage 1": 0.5,
            "voltage 2": 0.85,
            "voltage 3": 0.75,
        }),
        ("Output Logic Level - High", "1.62V~1.65V, 2.34V~2.7V, 4.47V~4.5V", {
            "voltage 1 min": 1.62,
            "voltage 1 max": 1.65,
            "voltage 2 min": 2.34,
            "voltage 2 max": 2.7,
            "voltage 3 min": 4.47,
            "voltage 3 max": 4.5,
        }),
    ],
)
def test_logic_level_voltage_lists(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, voltage in expected.items():
        assert_quantity(values[quantity], voltage, "voltage")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Varistor Voltage", "423V~517V", {"voltage 1 min": 423.0, "voltage 1 max": 517.0}),
        ("Varistor Voltage", "1.08kV~1.32kV", {"voltage 1 min": 1080.0, "voltage 1 max": 1320.0}),
        ("Reverse Stand-Off Voltage (VRWM)", "7V, 12V", {"voltage 1": 7.0, "voltage 2": 12.0}),
        ("VOS - Input Offset Voltage", "800uV, 100uV", {"voltage 1": 800e-6, "voltage 2": 100e-6}),
        ("Threshold Voltage", "100mV, 325mV", {"voltage 1": 0.1, "voltage 2": 0.325}),
        ("Threshold Voltage", "-", {"voltage 1": "NaN"}),
        ("Input Voltage(AC)", "85VAC~264VAC", {"voltage min": 85.0, "voltage max": 264.0}),
        ("Triping Voltage", "4.75mV~5.25mV", {"voltage min": 0.00475, "voltage max": 0.00525}),
    ],
)
def test_voltage_range_list_attributes(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, voltage in expected.items():
        assert_quantity(values[quantity], voltage, "voltage")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2V, 3.3V", {"voltage 1": 2.0, "voltage 2": 3.3}),
        ("1.3V~2V, 2.8V~3.4V", {
            "voltage 1 min": 1.3,
            "voltage 1 max": 2.0,
            "voltage 2 min": 2.8,
            "voltage 2 max": 3.4,
        }),
        ("R:1.9V~2.5V;G:2.8V~3.4V;B:2.8V~3.4V", {
            "voltage R min": 1.9,
            "voltage R max": 2.5,
            "voltage G min": 2.8,
            "voltage G max": 3.4,
            "voltage B min": 2.8,
            "voltage B max": 3.4,
        }),
        ("3.2V@UVA, 6.5V@UVC", {"voltage 1": 3.2, "voltage 2": 6.5}),
    ],
)
@pytest.mark.parametrize("key", ["Voltage - Forward(Vf)", "Forward Voltage (Vf)"])
def test_forward_voltage_vf_lists(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, voltage in expected.items():
        assert_quantity(values[quantity], voltage, "voltage")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1.25V@150mA, 1V@50mA", {
            "Vf 1": (1.25, "voltage"),
            "current 1": (0.15, "current"),
            "Vf 2": (1.0, "voltage"),
            "current 2": (0.05, "current"),
        }),
        ("885mV@10mA, 715mV@1mA", {
            "Vf 1": (0.885, "voltage"),
            "current 1": (0.01, "current"),
            "Vf 2": (0.715, "voltage"),
            "current 2": (0.001, "current"),
        }),
        ("500mV@60V", {
            "Vf": (0.5, "voltage"),
            "current": ("NaN", "current"),
        }),
    ],
)
def test_forward_voltage_vf_at_if_lists(value, expected, capsys):
    values = normalized_values("Forward Voltage (Vf @ If)", value, capsys)

    for quantity, expected_value in expected.items():
        amount, unit = expected_value
        assert_quantity(values[quantity], amount, unit)


@pytest.mark.parametrize(
    ("key", "value", "quantity", "expected", "unit"),
    [
        ("Sampling Rate", "352800Hz", "frequency", 352800.0, "frequency"),
        ("Resonant Frequency", "1.2kHz", "frequency", 1200.0, "frequency"),
        ("Count Rate", "8MHz", "frequency", 8e6, "frequency"),
        ("-3d B Bandwidth", "14kHz", "frequency", 14000.0, "frequency"),
        ("-3d B Bandwidth", "1.7GHz", "frequency", 1.7e9, "frequency"),
        ("Non-Repetitive Peak Forward Surge Current", "1.95kA", "current", 1950.0, "current"),
        ("Quiescent Supply Current", "50nA", "current", 50e-9, "current"),
        ("Input Offset Current(IOS)", "8nA", "current", 8e-9, "current"),
        ("Receive Current", "46mA", "current", 0.046, "current"),
        ("Current - Collector(Ic)", "4A", "current", 4.0, "current"),
        ("Supply Current (Iq)", "1uA", "current", 1e-6, "current"),
        ("Current - Input Bias(Ib)", "1.2pA", "current", 1.2e-12, "current"),
        ("Input Bias Current (Ib)", "0.25uA", "current", 0.25e-6, "current"),
        ("Current - Output Low(Iol)", "2.5mA", "current", 0.0025, "current"),
        ("Current - Output High(Ioh)", "-6mA", "current", -0.006, "current"),
        ("Current - Surge(Itsm@F)", "284A@60Hz", "current", 284.0, "current"),
        ("Send Current", "266mA", "current", 0.266, "current"),
        ("Current of Transmitting", "21mA", "current", 0.021, "current"),
        ("Current - Leakage", "47uA@25℃,5min", "current", 47e-6, "current"),
        ("Peak Current", "2.5kA", "current", 2500.0, "current"),
        ("Peak Non-Repetitive Surge Current (Itsm@F)", "160A@50Hz", "current", 160.0, "current"),
        ("Quiescent Current (Ground Current)", "800nA", "current", 800e-9, "current"),
        ("Quiescent Current Per Amplifier", "1.14mA", "current", 0.00114, "current"),
        ("Controller Stand-By Current", "130uA", "current", 130e-6, "current"),
        ("Controller Stand-By Current", "-", "current", "NaN", "current"),
        ("Nand Stand-By Current", "40uA", "current", 40e-6, "current"),
        ("Nand Stand-By Current", "-", "current", "NaN", "current"),
        ("Peak Output Current(Sink)", "2mA", "current", 0.002, "current"),
        ("Peak Output Current(Source)", "400uA", "current", 400e-6, "current"),
        ("Hold Current", "750mA", "current", 0.75, "current"),
        ("Working Current", "500uA", "current", 500e-6, "current"),
        ("Supply Current Per Channel", "3.6mA", "current", 0.0036, "current"),
        ("Collector Cut-Off Current (Icbo)", "100nA", "current", 100e-9, "current"),
        ("Current - Collector Cutoff", "50uA", "current", 50e-6, "current"),
        ("Load Current", "130mA", "current", 0.13, "current"),
        ("Steady State Current (Max)", "100uA", "current", 100e-6, "current"),
        ("Minimum Cathode Current for Regulation", "400uA", "current", 400e-6, "current"),
        ("Holding Current (Ih)", "40mA", "current", 0.04, "current"),
        ("Current - Max", "100A", "current", 100.0, "current"),
        ("Forward Current(If)", "50mA", "current", 0.05, "current"),
        ("Output Source Current", "10mA", "current", 0.01, "current"),
        ("Output Sink Current", "25mA", "current", 0.025, "current"),
        ("Output Leakage Current(Icex)", "50uA", "current", 50e-6, "current"),
        ("Input Current(Off)", "100uA", "current", 100e-6, "current"),
        ("Input Current(on)", "1.35mA", "current", 0.00135, "current"),
        ("Source Current", "12mA", "current", 0.012, "current"),
        ("Sink Current", "12mA", "current", 0.012, "current"),
        ("Refresh Current", "8mA", "current", 0.008, "current"),
        ("Frequency (Max)", "6GHz", "frequency", 6e9, "frequency"),
        ("Clock Frequency (Max)", "166MHz", "frequency", 166e6, "frequency"),
        ("Band Width", "45Hz~2kHz", "frequency min", 45.0, "frequency"),
        ("Band Width", "80kHz, 20kHz", "frequency 1", 80000.0, "frequency"),
        ("Clock Frequency(Fc)", "100MHz", "frequency", 100e6, "frequency"),
        ("Maximum Speed", "200MHz, 180MHz", "frequency 1", 200e6, "frequency"),
        ("Pass Bandwidth", "7.5kHz", "frequency", 7500.0, "frequency"),
        ("Stop Bandwidth", "50kHz", "frequency", 50000.0, "frequency"),
        ("Passband Bandwidth", "20.46MHz;48MHz", "frequency 1", 20.46e6, "frequency"),
        ("Response Frequency", "20Hz~20kHz", "frequency 1 min", 20.0, "frequency"),
        ("Central Frequency", "2.4GHz;5.4GHz", "frequency 1", 2.4e9, "frequency"),
        ("Lo Frequency Range", "400MHz~2.5GHz", "frequency 1 min", 400e6, "frequency"),
        ("IF Frequency Range", "10MHz~500MHz", "frequency 1 min", 10e6, "frequency"),
        ("RF Frequency Range", "400MHz~2.5GHz", "frequency 1 min", 400e6, "frequency"),
        ("Frequency Range", "2.4GHz~2.5GHz, 4.9GHz~5.845GHz", "frequency 1 min", 2.4e9, "frequency"),
        ("Frequency Range", "50Hz, 60Hz", "frequency 1", 50.0, "frequency"),
        ("Voltage", "600 V", "voltage", 600.0, "voltage"),
        ("Control Voltage Range/Center", "0V~3.3V", "voltage min", 0.0, "voltage"),
        ("Vbo (Range Value)", "35V~45V", "voltage min", 35.0, "voltage"),
        ("Breakover Voltage Vbo(Range Value)", "95V~110V", "voltage min", 95.0, "voltage"),
        ("High-Side Bias Voltage(Vbs)", "13.5V~16.5V", "voltage min", 13.5, "voltage"),
        ("Voltage - Input(AC)", "85VAC~265VAC", "voltage min", 85.0, "voltage"),
        ("Input Voltage(Vac)", "85VAC~305VAC", "voltage min", 85.0, "voltage"),
        ("Voltage - Supply for Logic", "1.65V~3.3V", "voltage min", 1.65, "voltage"),
        ("The Power Supply Voltage", "4.75V~5.25V", "voltage min", 4.75, "voltage"),
        ("Rated Speed", "8500RPM", "speed", 8500.0, "rotational_speed"),
        ("Rated Speed", "-", "speed", "NaN", "rotational_speed"),
    ],
)
def test_scalar_frequency_and_current_attributes(key, value, quantity, expected, unit, capsys):
    values = normalized_values(key, value, capsys)
    assert_quantity(values[quantity], expected, unit)


def test_peak_output_current_sink_list(capsys):
    values = normalized_values("Peak Output Current(Sink)", "200uA, 16mA", capsys)

    assert_quantity(values["current 1"], 200e-6, "current")
    assert_quantity(values["current 2"], 0.016, "current")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Balance Current", "100mA", {"current": 0.1}),
        ("Leakage Current", "400uA, 700uA", {"current 1": 400e-6, "current 2": 700e-6}),
        ("Reverse Leakage Current (Ir)", "10uA@6kV, 10uA@1.7kV", {"current 1": 10e-6, "current 2": 10e-6}),
        ("Hold Current(Ih)", "350mA, 125mA", {"current 1": 0.35, "current 2": 0.125}),
        ("On - State Current(It)", "2.2A", {"current": 2.2}),
        ("Nominal Impulse Discharge Current", "5kA", {"current": 5000.0}),
        ("Nominal Impulse Discharge Current", "-", {"current": "NaN"}),
        ("Impulse Discharge Current", "1.2kA", {"current": 1200.0}),
        ("Surge Current Capacity (8/20us)", "300A", {"current": 300.0}),
        ("Off State Current", "100uA", {"current": 100e-6}),
        ("Off-State Current", "300pA", {"current": 300e-12}),
        ("On-State Current (It)", "800mA", {"current": 0.8}),
        ("Supply Current (Icc)", "20mA, 6mA", {"current 1": 0.02, "current 2": 0.006}),
        ("Standby Current (Max)", "150nA", {"current": 150e-9}),
        ("Trigger Current", "5A~15A", {"current min": 5.0, "current max": 15.0}),
        ("Trigger Current", "650mA", {"current": 0.65}),
        ("Contact Current", "3A, 6A", {"current 1": 3.0, "current 2": 6.0}),
        ("Contact Current", "-", {"current": "NaN"}),
        ("Signal Current Rating", "500mA", {"current": 0.5}),
        ("Signal Current Rating (Max)", "1.25A", {"current": 1.25}),
        ("Signal Current Rating (Max)", "-", {"current": "NaN"}),
        ("Breaking Capacity", "50A;300A", {"current 1": 50.0, "current 2": 300.0}),
        ("Breaking Capacity", "50A@125V", {"current": 50.0}),
        ("Interrupt Rating", "1kA@32V", {"current": 1000.0}),
        ("Interrupt Rating", "100A@125VDC, 200A@250VAC", {
            "current 1": 100.0,
            "current 2": 200.0,
        }),
        ("Interrupting Rating", "2000A@32V", {"current": 2000.0}),
        ("Rated Ripple Curren", "2.3A@100kHz", {"current": 2.3}),
        ("Drain Current (Idss)", "57mA", {"current": 0.057}),
        ("Current Rating (AC)", "3A", {"current": 3.0}),
        ("Current Rating (DC)", "50mA", {"current": 0.05}),
        ("IR - Reverse Current", "1.5A", {"current": 1.5}),
        ("Peak Forward Surge Current", "1.95kA", {"current": 1950.0}),
        ("Breakover Current (Ibo)", "50uA", {"current": 50e-6}),
        ("Repetitive Peak on-State Current (Itrm)", "2A", {"current": 2.0}),
        ("Leak Current", "10uA", {"current": 10e-6}),
        ("Continuous Current (Imax)", "4A", {"current": 4.0}),
        ("Segment Drive Current", "45mA, 60mA", {"current 1": 0.045, "current 2": 0.06}),
        ("Digit Drive Current", "320mA", {"current": 0.32}),
        ("Forward Current", "R:20mA, G:20mA, B:10mA", {
            "current R": 0.02,
            "current G": 0.02,
            "current B": 0.01,
        }),
        ("Forward Current", "200mA@UVA, 30mA@UVC", {"current 1": 0.2, "current 2": 0.03}),
        ("Output Current(It(RMS))", "100mA", {"current": 0.1}),
        ("Current - Surge(Itsm)", "120A, 115A", {"current 1": 120.0, "current 2": 115.0}),
        ("Quiescent Current (Max)", "2uA", {"current": 2e-6}),
        ("Sleep Mode Current (Izz)", "3uA", {"current": 3e-6}),
        ("Standby Current(Isb)", "5uA, 15uA", {"current 1": 5e-6, "current 2": 15e-6}),
        ("Iout", "300mA, 400mA", {"current 1": 0.3, "current 2": 0.4}),
        ("Maximum Charge Current", "1.1A", {"current": 1.1}),
        ("RMS on-State Current(It (RMS))", "25A", {"current": 25.0}),
        ("Gate Trigger Current(Igt)", "15mA;25mA", {"current 1": 0.015, "current 2": 0.025}),
        ("Collector Cut-Off Current (Ices)", "7uA", {"current": 7e-6}),
        ("Limiting Current", "840mA", {"current": 0.84}),
        ("Contact Current (DC)", "1mA", {"current": 0.001}),
        ("Current - DC Forward(If)", "350mA, 250mA", {"current 1": 0.35, "current 2": 0.25}),
        ("Dark Current", "100pA", {"current": 100e-12}),
        ("Switching Current", "500mA", {"current": 0.5}),
        ("Maximum Load Current", "1.25A", {"current": 1.25}),
        ("Standby Supply Current (Isb)", "90uA", {"current": 90e-6}),
        ("Battery Current", "50nA, 150nA", {"current 1": 50e-9, "current 2": 150e-9}),
        ("Supply Current (Program)", "30mA", {"current": 0.03}),
        ("Supply Current (Erase)", "5mA", {"current": 0.005}),
        ("Supply Current (Read)", "140uA", {"current": 140e-6}),
        ("Idle Current", "75uA", {"current": 75e-6}),
        ("RMS on-State Current(It(RMS))", "70mA", {"current": 0.07}),
        ("Current Dark", "5pA", {"current": 5e-12}),
        ("Continuous Load Current", "1400mA", {"current": 1.4}),
        ("Threshold Current", "4.9mA", {"current": 0.0049}),
        ("Collector Current (Max)", "920uA", {"current": 920e-6}),
        ("Bias Current", "4mA~200mA", {"current min": 0.004, "current max": 0.2}),
        ("Peak Output Current", "15A", {"current": 15.0}),
        ("Input Current", "<0.2A (Average Current 0.03~0.1A)", {"current": 0.2}),
        ("Load Current (Max)", "1.5A", {"current": 1.5}),
        ("Collector Cut-Off Current (Icbo@Vcb)", "100nA@30V", {"current": 100e-9}),
        ("Current - Collector Pulsed (Icm)", "60A, 70A", {"current 1": 60.0, "current 2": 70.0}),
        ("Collector Current(Ic)", "500mA", {"current": 0.5}),
        ("Pulsed Collector Current (Icm)", "200A", {"current": 200.0}),
    ],
)
def test_additional_current_values(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, current in expected.items():
        assert_quantity(values[quantity], current, "current")


def test_additional_current_aliases(capsys):
    values = normalized_values("Rated Output Current", "2mA", capsys)
    assert_quantity(values["current"], 0.002, "current")

    values = normalized_values("Setting Current", "0.63-1A", capsys)
    assert_quantity(values["current min"], 0.63, "current")
    assert_quantity(values["current max"], 1.0, "current")


def test_switching_current_max(capsys):
    values = normalized_values("Switching Current (Max)", "2A, 5A", capsys)

    assert_quantity(values["current 1"], 2.0, "current")
    assert_quantity(values["current 2"], 5.0, "current")


def test_sampling_rate_lists(capsys):
    values = normalized_values("Sampling Rate", "48000Hz, 32000Hz, 44100Hz", capsys)

    assert_quantity(values["frequency 1"], 48000.0, "frequency")
    assert_quantity(values["frequency 2"], 32000.0, "frequency")
    assert_quantity(values["frequency 3"], 44100.0, "frequency")


def test_diode_capacitance_conditions(capsys):
    values = normalized_values(
        "Diode Capacitance",
        "2.85pF@25V,1MHz, 2.6pF@28V,1MHz",
        capsys,
    )

    assert_quantity(values["capacitance 1"], 2.85e-12, "capacitance")
    assert_quantity(values["voltage 1"], 25.0, "voltage")
    assert_quantity(values["frequency 1"], 1e6, "frequency")
    assert_quantity(values["capacitance 2"], 2.6e-12, "capacitance")
    assert_quantity(values["voltage 2"], 28.0, "voltage")
    assert_quantity(values["frequency 2"], 1e6, "frequency")


def test_sampling_rate_range_lists(capsys):
    values = normalized_values("Sampling Rate", "16kHz~96kHz, 16kHz~192kHz", capsys)

    assert_quantity(values["frequency 1 min"], 16000.0, "frequency")
    assert_quantity(values["frequency 1 max"], 96000.0, "frequency")
    assert_quantity(values["frequency 2 min"], 16000.0, "frequency")
    assert_quantity(values["frequency 2 max"], 192000.0, "frequency")


def test_switching_frequency_lists(capsys):
    values = normalized_values("Frequency - Switching", "2.5MHz, 1.25MHz", capsys)

    assert_quantity(values["frequency 1"], 2.5e6, "frequency")
    assert_quantity(values["frequency 2"], 1.25e6, "frequency")

    values = normalized_values("Frequency - Switching", "100kHz~1MHz, 340kHz~520kHz", capsys)

    assert_quantity(values["frequency 1 min"], 100e3, "frequency")
    assert_quantity(values["frequency 1 max"], 1e6, "frequency")
    assert_quantity(values["frequency 2 min"], 340e3, "frequency")
    assert_quantity(values["frequency 2 max"], 520e3, "frequency")


def test_switch_frequency_values(capsys):
    values = normalized_values("Switch Frequency", "25kHz;100kHz", capsys)

    assert_quantity(values["frequency 1"], 25e3, "frequency")
    assert_quantity(values["frequency 2"], 100e3, "frequency")

    values = normalized_values("Switch Frequency", "233kHz~1MHz", capsys)

    assert_quantity(values["frequency min"], 233e3, "frequency")
    assert_quantity(values["frequency max"], 1e6, "frequency")

def test_throughput_rate_values(capsys):
    values = normalized_values("Throughput Rate", "10kHz", capsys)

    assert_quantity(values["frequency"], 10e3, "frequency")

    values = normalized_values("Throughput Rate", "10kHz, 20kHz", capsys)

    assert_quantity(values["frequency 1"], 10e3, "frequency")
    assert_quantity(values["frequency 2"], 20e3, "frequency")

def test_update_rate_values(capsys):
    values = normalized_values("Update Rate", "2.7MHz", capsys)

    assert_quantity(values["frequency"], 2.7e6, "frequency")

    values = normalized_values("Update Rate", "33MHz, 22MHz", capsys)

    assert_quantity(values["frequency 1"], 33e6, "frequency")
    assert_quantity(values["frequency 2"], 22e6, "frequency")

def test_frequency_output_values(capsys):
    values = normalized_values("Frequency Output", "450MHz", capsys)

    assert_quantity(values["frequency"], 450e6, "frequency")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("16GHz, 6.4GHz", [16e9, 6.4e9]),
        ("24.576MHz, 24MHz, 22.579MHz", [24.576e6, 24e6, 22.579e6]),
    ],
)
def test_output_frequency_max_lists(value, expected, capsys):
    values = normalized_values("Output Frequency (Max)", value, capsys)

    for index, frequency in enumerate(expected, start=1):
        assert_quantity(values[f"frequency {index}"], frequency, "frequency")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1GHz", 1e9),
        ("16.776MHz", 16.776e6),
        ("-", "NaN"),
    ],
)
def test_main_fclk_values(value, expected, capsys):
    values = normalized_values("The Main Fclk", value, capsys)

    assert_quantity(values["frequency"], expected, "frequency")


def test_count_rate_list(capsys):
    values = normalized_values("Count Rate", "16MHz, 32MHz", capsys)

    assert_quantity(values["frequency 1"], 16e6, "frequency")
    assert_quantity(values["frequency 2"], 32e6, "frequency")


def test_gain_bandwidth_product_values(capsys):
    values = normalized_values("Gain Bandwidth Product", "85MHz, 115MHz", capsys)

    assert_quantity(values["frequency 1"], 85e6, "frequency")
    assert_quantity(values["frequency 2"], 115e6, "frequency")

    values = normalized_values("Gain Bandwidth Product (GBP)", "1MHz", capsys)

    assert_quantity(values["frequency"], 1e6, "frequency")


def test_absolute_bandwidth_values(capsys):
    values = normalized_values("Absolute Bandwidth", "863MHz~876MHz", capsys)

    assert_quantity(values["frequency min"], 863e6, "frequency")
    assert_quantity(values["frequency max"], 876e6, "frequency")

    values = normalized_values("Absolute Bandwidth", "2.4GHz~2.5GHz, 4.9GHz~5.95GHz", capsys)

    assert_quantity(values["frequency 1 min"], 2.4e9, "frequency")
    assert_quantity(values["frequency 1 max"], 2.5e9, "frequency")
    assert_quantity(values["frequency 2 min"], 4.9e9, "frequency")
    assert_quantity(values["frequency 2 max"], 5.95e9, "frequency")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Bandwidth (-3d B)", "85MHz", {"frequency": 85e6}),
        ("Bandwidth", "140kHz, 200kHz", {"frequency 1": 140e3, "frequency 2": 200e3}),
        ("-3db Bandwidth(G=1)", "60kHz", {"frequency": 60e3}),
        ("Frequency - Cutoff or Center", "1MHz", {"frequency": 1e6}),
        ("Frequency - Cutoff or Center", "900MHz~2GHz", {
            "frequency min": 900e6,
            "frequency max": 2e9,
        }),
        ("Typical Application Frequency", "5GHz", {"frequency": 5e9}),
        ("Typical Application Frequency", "433MHz, 868MHz, 915MHz", {
            "frequency 1": 433e6,
            "frequency 2": 868e6,
            "frequency 3": 915e6,
        }),
        ("Frequency", "100kHz, 1Hz", {"frequency 1": 100e3, "frequency 2": 1.0}),
        ("Frequency", "42kHz~900kHz, 4.2kHz~90kHz", {
            "frequency 1 min": 42e3,
            "frequency 1 max": 900e3,
            "frequency 2 min": 4.2e3,
            "frequency 2 max": 90e3,
        }),
        ("Clock Frequency (Fc)", "166MHz", {"frequency": 166e6}),
        ("Clock Frequency (Fc)", "400kHz~1MHz", {
            "frequency min": 400e3,
            "frequency max": 1e6,
        }),
        ("Fixed-Frequency Pwm Mode", "27kHz", {"frequency": 27e3}),
        ("Communication Frequency", "850MHz, 1800MHz, 1900MHz", {
            "frequency 1": 850e6,
            "frequency 2": 1800e6,
            "frequency 3": 1900e6,
        }),
    ],
)
def test_additional_frequency_aliases(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, frequency in expected.items():
        assert_quantity(values[quantity], frequency, "frequency")


def test_communication_frequency_bands(capsys):
    values = normalized_values("Communication Frequency", "B2, B3, B1", capsys)

    assert_quantity(values["band 1"], 2, "count")
    assert_quantity(values["band 2"], 3, "count")
    assert_quantity(values["band 3"], 1, "count")


def test_clock_frequency_lists(capsys):
    values = normalized_values("Clock Frequency", "32MHz, 32kHz, 1MHz", capsys)

    assert_quantity(values["frequency 1"], 32e6, "frequency")
    assert_quantity(values["frequency 2"], 32e3, "frequency")
    assert_quantity(values["frequency 3"], 1e6, "frequency")

    values = normalized_values("Clock Frequency", "100MHz~310MHz, 0.1MHz~200MHz", capsys)

    assert_quantity(values["frequency 1 min"], 100e6, "frequency")
    assert_quantity(values["frequency 1 max"], 310e6, "frequency")
    assert_quantity(values["frequency 2 min"], 0.1e6, "frequency")
    assert_quantity(values["frequency 2 max"], 200e6, "frequency")


def test_cpu_maximum_speed_lists(capsys):
    values = normalized_values("CPU Maximum Speed", "400MHz, 800MHz, 1GHz", capsys)

    assert_quantity(values["frequency 1"], 400e6, "frequency")
    assert_quantity(values["frequency 2"], 800e6, "frequency")
    assert_quantity(values["frequency 3"], 1e9, "frequency")

    values = normalized_values("CPU Maximum Speed", "-", capsys)

    assert_quantity(values["frequency"], "NaN", "frequency")


def test_frequency_center_band_lists(capsys):
    values = normalized_values("Frequency(Center/Band)", "2.4GHz, 5.4GHz", capsys)

    assert_quantity(values["frequency 1"], 2.4e9, "frequency")
    assert_quantity(values["frequency 2"], 5.4e9, "frequency")


def test_sampling_rate_time_range(capsys):
    values = normalized_values("Sampling Rate", "0.1ms~23.5ms", capsys)

    assert_quantity(values["time min"], 0.0001, "time")
    assert_quantity(values["time max"], 0.0235, "time")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("490MHz", 490e6),
        ("16GHz", 16e9),
        ("-", "NaN"),
    ],
)
def test_cut_off_frequency(value, expected, capsys):
    values = normalized_values("Cut-Off Frequency", value, capsys)

    assert_quantity(values["frequency"], expected, "frequency")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("40MHz", [40e6]),
        ("25GHz", [25e9]),
        ("250MHz, 200MHz", [250e6, 200e6]),
        ("-", ["NaN"]),
    ],
)
def test_transition_frequency(value, expected, capsys):
    values = normalized_values("Transition Frequency (F T)", value, capsys)

    if len(expected) == 1:
        assert_quantity(values["frequency"], expected[0], "frequency")
    else:
        for index, frequency in enumerate(expected, start=1):
            assert_quantity(values[f"frequency {index}"], frequency, "frequency")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("3kHz", {"frequency": 3e3}),
        ("4kHz~12kHz", {"frequency min": 4e3, "frequency max": 12e3}),
        ("3.75Hz;15Hz;60Hz", {"frequency 1": 3.75, "frequency 2": 15.0, "frequency 3": 60.0}),
    ],
)
def test_sampling_frequency(value, expected, capsys):
    values = normalized_values("Sampling Frequency", value, capsys)

    for quantity, frequency in expected.items():
        assert_quantity(values[quantity], frequency, "frequency")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("3.6GHz", {"frequency": 3.6e9}),
        ("455kHz", {"frequency": 455e3}),
        ("1.17645GHz;1.583GHz", {"frequency 1": 1.17645e9, "frequency 2": 1.583e9}),
    ],
)
def test_center_frequency(value, expected, capsys):
    values = normalized_values("Center Frequency", value, capsys)

    for quantity, frequency in expected.items():
        assert_quantity(values[quantity], frequency, "frequency")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("40kHz, 37.9kHz, 36.7kHz, 32.7kHz", [40e3, 37.9e3, 36.7e3, 32.7e3]),
        ("1.57542GHz, 1.5611GHz, 1.602GHz", [1.57542e9, 1.5611e9, 1.602e9]),
    ],
)
def test_frequency_center_lists(value, expected, capsys):
    values = normalized_values("Frequency - Center", value, capsys)

    for index, frequency in enumerate(expected, start=1):
        assert_quantity(values[f"frequency {index}"], frequency, "frequency")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Non-Repetitive Peak Forward Surge Current", "120A, 240A", [120.0, 240.0]),
        ("Quiescent Current", "8mA, 10mA, 16mA", [0.008, 0.01, 0.016]),
        ("Quiescent Current (Iq)", "7.3mA, 4.5mA", [0.0073, 0.0045]),
        ("Quiescent Current(Iq)", "2uA, 5uA, 500nA", [2e-6, 5e-6, 500e-9]),
        ("Quiescent Supply Current", "2mA, 1mA, 600uA", [0.002, 0.001, 0.0006]),
        ("Input Offset Current(IOS)", "2nA, 5nA", [2e-9, 5e-9]),
        ("Receive Current", "3.5mA, 5mA", [0.0035, 0.005]),
        ("Current - Collector(Ic)", "5A, 4.45A", [5.0, 4.45]),
        ("Ib - Input Bias Current", "2.5uA, 1.2uA", [2.5e-6, 1.2e-6]),
        ("Current - Output Low(Iol)", "2.6mA, 6.8mA, 1mA", [0.0026, 0.0068, 0.001]),
        ("Current - Output High(Ioh)", "1mA, 2.6mA, 6.8mA", [0.001, 0.0026, 0.0068]),
        ("Saturation Current (Isat)", "75A, 85A", [75.0, 85.0]),
        ("Saturation Current (Isat)", "900mA, 1.02A", [0.9, 1.02]),
        ("Current - Surge(Itsm@F)", "170A@60Hz, 155A@50Hz", [170.0, 155.0]),
        ("Send Current", "9.5mA, 16mA", [0.0095, 0.016]),
        ("Current of Transmitting", "7.1mA, 3.5mA", [0.0071, 0.0035]),
        ("Current - Collector Cutoff", "100uA, 500uA", [100e-6, 500e-6]),
        ("Load Current", "900mA, 1.2A", [0.9, 1.2]),
        ("Steady State Current (Max)", "440uA, 400uA", [440e-6, 400e-6]),
        ("Minimum Cathode Current for Regulation", "80uA, 55uA", [80e-6, 55e-6]),
        ("Holding Current (Ih)", "60mA, 30mA, 45mA", [0.06, 0.03, 0.045]),
        ("Current - Max", "60A, 125A, 40A", [60.0, 125.0, 40.0]),
        ("Source Current", "3mA;15mA", [0.003, 0.015]),
        ("Sink Current", "24mA;64mA", [0.024, 0.064]),
        ("Refresh Current", "1mA, 2.7mA, 400uA", [0.001, 0.0027, 400e-6]),
        ("Power Current Rating", "5A, 250mA, 1.25A", [5.0, 0.25, 1.25]),
        ("Supply Current", "1.2mA, 300uA", [0.0012, 300e-6]),
        ("Rated Current", "15A, 16A", [15.0, 16.0]),
    ],
)
def test_current_lists(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for index, current in enumerate(expected, start=1):
        assert_quantity(values[f"current {index}"], current, "current")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("20A", {"current": 20.0}),
        ("0A~200A", {"current min": 0.0, "current max": 200.0}),
        ("±5.75A", {"current min": -5.75, "current max": 5.75}),
        ("400/5A", {"current 1": 400.0, "current 2": 5.0}),
        ("±20A, ±10A", {
            "current 1 min": -20.0,
            "current 1 max": 20.0,
            "current 2 min": -10.0,
            "current 2 max": 10.0,
        }),
    ],
)
def test_current_range(value, expected, capsys):
    values = normalized_values("Current Range", value, capsys)

    for quantity, current in expected.items():
        assert_quantity(values[quantity], current, "current")


def test_drain_current_idss_at_vds(capsys):
    values = normalized_values("Drain Current (Idss@VDS,VGS=0)", "14mA@10V", capsys)

    assert_quantity(values["Idss"], 0.014, "current")
    assert_quantity(values["Vds"], 10.0, "voltage")


def test_supply_current_range_list(capsys):
    values = normalized_values("Supply Current", "150uA~230uA, 130uA~250uA", capsys)

    assert_quantity(values["current 1 min"], 150e-6, "current")
    assert_quantity(values["current 1 max"], 230e-6, "current")
    assert_quantity(values["current 2 min"], 130e-6, "current")
    assert_quantity(values["current 2 max"], 250e-6, "current")


def test_rated_current_dash_range(capsys):
    values = normalized_values("Rated Current", "40-50A", capsys)

    assert_quantity(values["current min"], 40.0, "current")
    assert_quantity(values["current max"], 50.0, "current")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2.2A", 2.2),
        ("100mA", 0.1),
        ("200uA", 0.0002),
        ("-", "NaN"),
    ],
)
def test_trip_current(value, expected, capsys):
    values = normalized_values("Trip Current", value, capsys)

    assert_quantity(values["current"], expected, "current")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("5A", [5.0]),
        ("400mA", [0.4]),
        ("10uA", [10e-6]),
        ("25A, 55A", [25.0, 55.0]),
    ],
)
def test_maximum_continuous_current(value, expected, capsys):
    values = normalized_values("Maximum Continuous Current", value, capsys)

    if len(expected) == 1:
        assert_quantity(values["current"], expected[0], "current")
    else:
        for index, current in enumerate(expected, start=1):
            assert_quantity(values[f"current {index}"], current, "current")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("800uA", [800e-6]),
        ("40nA", [40e-9]),
        ("3uA, 5uA", [3e-6, 5e-6]),
    ],
)
def test_operating_current(value, expected, capsys):
    values = normalized_values("Operating Current", value, capsys)

    if len(expected) == 1:
        assert_quantity(values["current"], expected[0], "current")
    else:
        for index, current in enumerate(expected, start=1):
            assert_quantity(values[f"current {index}"], current, "current")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("200nA", 200e-9),
        ("8uA", 8e-6),
        ("0.2mA", 0.0002),
    ],
)
def test_standby_supply_current(value, expected, capsys):
    values = normalized_values("Standby Supply Current", value, capsys)

    assert_quantity(values["current"], expected, "current")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("3mA", [0.003]),
        ("330uA, 360uA", [330e-6, 360e-6]),
        ("600nA", [600e-9]),
    ],
)
def test_standby_current_iq(value, expected, capsys):
    values = normalized_values("Standby Current (Iq)", value, capsys)

    if len(expected) == 1:
        assert_quantity(values["current"], expected[0], "current")
    else:
        for index, current in enumerate(expected, start=1):
            assert_quantity(values[f"current {index}"], current, "current")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1A", 1.0),
        ("700mA", 0.7),
        ("1.25A", 1.25),
    ],
)
def test_on_state_rms_current(value, expected, capsys):
    values = normalized_values("Current - on State(It(RMS))", value, capsys)

    assert_quantity(values["current"], expected, "current")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("50mA", [0.05]),
        ("50uA", [50e-6]),
        ("2mA, 1mA, 4mA", [0.002, 0.001, 0.004]),
    ],
)
def test_gate_trigger_current(value, expected, capsys):
    values = normalized_values("Current - Gate Trigger(Igt)", value, capsys)

    if len(expected) == 1:
        assert_quantity(values["current"], expected[0], "current")
    else:
        for index, current in enumerate(expected, start=1):
            assert_quantity(values[f"current {index}"], current, "current")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1270", 1270),
        ("2", 2),
        ("56480", 56480),
    ],
)
def test_logic_array_blocks(value, expected, capsys):
    values = normalized_values("Logic Array Blocks", value, capsys)

    assert_quantity(values["count"], expected, "count")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Number of Circuits", "16", {"count": 16}),
        ("Number of Filters", "4", {"count": 4}),
        ("Circuits", "2", {"count": 2}),
        ("Number of Poles", "3", {"count": 3}),
        ("Number of Poles", "-", {"count": "NaN"}),
        ("Number of Nodes", "256", {"count": 256}),
        ("Node Number", "128", {"count": 128}),
        ("Unidirectional Channels", "8", {"count": 8}),
        ("Bidirectional Channels", "0", {"count": 0}),
        ("Mac Address Support", "4096", {"count": 4096}),
        ("Vlan Support", "128", {"count": 128}),
        ("Forward Channel", "0", {"count": 0}),
        ("Reverse Channel", "4", {"count": 4}),
        ("Number of Forward Channels", "8", {"count": 8}),
        ("Number of Reverse Channels", "4", {"count": 4}),
        ("Number of Forward Channels Groups", "1", {"count": 1}),
        ("Number of Reverse Channels Groups", "1", {"count": 1}),
        ("Number of Input Channels", "1", {"count": 1}),
        ("Number of Non-Differential Input Channels", "0", {"count": 0}),
        ("Numberof Channels", "6", {"count": 6}),
        ("Number of Cells", "3~16", {"count min": 3, "count max": 16}),
        ("Number of Cells", "12", {"count": 12}),
        ("Pin Number Per Port", "3", {"count": 3}),
        ("Number of Inserts", "2", {"count": 2}),
        ("Number of Leg", "-", {"count": "NaN"}),
        ("Connection Number (Max)", "8", {"count": 8}),
        ("Connectable Bits", "-", {"count": "NaN"}),
        ("Pin Number in Each Row", "18", {"count": 18}),
        ("Needle Number", "12", {"count": 12}),
        ("Channels", "16", {"count": 16}),
        ("Number of Characters", "4", {"count": 4}),
        ("Number of Terminals", "4", {"count": 4}),
        ("Turns", "11", {"count": 11}),
        ("Number of Turns", "25", {"count": 25}),
        ("Number of Coded Gears", "10", {"count": 10}),
        ("SPI", "5", {"count": 5}),
        ("UART/Usart", "4", {"count": 4}),
        ("I2C", "3", {"count": 3}),
        ("I2s", "4", {"count": 4}),
        ("16bit Timer", "8", {"count": 8}),
        ("CAN", "1", {"count": 1}),
        ("Number of Half Bridges", "3", {"count": 3}),
        ("Order", "2", {"count": 2}),
        ("Number of LED Drivers", "3", {"count": 3}),
        ("Output Channel", "2", {"count": 2}),
        ("Pin Number", "8", {"count": 8}),
        ("Number of Sensitive Elements", "4", {"count": 4}),
        ("The Channel Number", "24", {"count": 24}),
        ("Channels Per Circuit", "12", {"count": 12}),
        ("Battery Count", "-", {"count": "NaN"}),
    ],
)
def test_extra_count_attributes(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, count in expected.items():
        assert_quantity(values[quantity], count, "count")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Dot Matrix Number", "8x8", {"columns": 8, "rows": 8}),
        ("Number of Digits", "9", {"count": 9}),
        ("Number of Digits", "5x7", {"columns": 5, "rows": 7}),
        ("Display Configurations(Bit)", "20x4 bit, 16x8 bit", {
            "columns 1": 20,
            "rows 1": 4,
            "columns 2": 16,
            "rows 2": 8,
        }),
    ],
)
def test_matrix_count_attributes(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, count in expected.items():
        assert_quantity(values[quantity], count, "count")


def test_active_pixel_array(capsys):
    values = normalized_values("Active Pixel Array", "1280Hx1080V", capsys)

    assert_quantity(values["horizontal pixels"], 1280, "count")
    assert_quantity(values["vertical pixels"], 1080, "count")


def test_optical_format(capsys):
    values = normalized_values("Optical Format(Inch)", "1/2.09", capsys)

    assert_quantity(values["optical format"], 1 / 2.09, "ratio")

    values = normalized_values("Optical Format (Inch)", "1/4", capsys)
    assert_quantity(values["optical format"], 0.25, "ratio")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Number of Pins Per Row", "4", {"count": 4}),
        ("Number of Pins Per Row", "1, 3", {"count 1": 1, "count 2": 3}),
        ("Number of Pins Per Row", "-", {"count": "NaN"}),
        ("Number of Rows", "Double Row", {"count": 2}),
        ("Number of Rows", "Single Row", {"count": 1}),
        ("Number of Rows", "3, 2", {"count 1": 3, "count 2": 2}),
        ("Rows", "1, -", {"count 1": 1, "count 2": "NaN"}),
    ],
)
def test_row_count_attributes(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, count in expected.items():
        assert_quantity(values[quantity], count, "count")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Number of Data Pins", "36P", {"count": 36}),
        ("Number of Data Pins", "-", {"count": "NaN"}),
        ("Number of Conductors", "4P", {"count": 4}),
        ("Number of Conductors", "22", {"count": 22}),
        ("Parallel Bit Count Per Channel", "12, 10", {"count 1": 12, "count 2": 10}),
    ],
)
def test_connector_count_attributes(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, count in expected.items():
        assert_quantity(values[quantity], count, "count")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("16", {"resolution": (16, "count")}),
        ("12Bit", {"resolution": (12, "count")}),
        ("16-bit", {"resolution": (16, "count")}),
        ("10;12;14;16", {
            "resolution 1": (10, "count"),
            "resolution 2": (12, "count"),
            "resolution 3": (14, "count"),
            "resolution 4": (16, "count"),
        }),
        ("12bit, 15bit", {"resolution 1": (12, "count"), "resolution 2": (15, "count")}),
        ("12, 16, 10, 14", {
            "resolution 1": (12, "count"),
            "resolution 2": (16, "count"),
            "resolution 3": (10, "count"),
            "resolution 4": (14, "count"),
        }),
        ("16/32 Bit", {"resolution 1": (16, "count"), "resolution 2": (32, "count")}),
        ("6 digits", {"resolution": (6, "count")}),
        ("13.8", {"resolution": (13.8, "count")}),
        ("19ps", {"resolution": (19e-12, "time")}),
        ("44.1kHz;48kHz;96kHz;192kHz", {
            "frequency 1": (44.1e3, "frequency"),
            "frequency 2": (48e3, "frequency"),
            "frequency 3": (96e3, "frequency"),
            "frequency 4": (192e3, "frequency"),
        }),
        ("1MHz;14", {"frequency": (1e6, "frequency"), "resolution": (14, "count")}),
        ("10Hz;24;80Hz", {
            "frequency 1": (10.0, "frequency"),
            "resolution": (24, "count"),
            "frequency 2": (80.0, "frequency"),
        }),
        ("±0.5℃", {"resolution min": (-0.5, "temperature"), "resolution max": (0.5, "temperature")}),
        ("±2%RH", {"resolution min": (-2.0, "percentage"), "resolution max": (2.0, "percentage")}),
        ("±5%RH;±1℃", {
            "percentage min": (-5.0, "percentage"),
            "percentage max": (5.0, "percentage"),
            "temperature min": (-1.0, "temperature"),
            "temperature max": (1.0, "temperature"),
        }),
    ],
)
def test_resolution_values(value, expected, capsys):
    values = normalized_values("Resolution", value, capsys)

    for quantity, (amount, unit) in expected.items():
        assert_quantity(values[quantity], amount, unit)


def test_resolution_bits_values(capsys):
    values = normalized_values("Resolution (Bits)", "16", capsys)

    assert_quantity(values["resolution"], 16, "count")

    values = normalized_values("Resolution(Bits)", "16-Bit", capsys)

    assert_quantity(values["resolution"], 16, "count")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Output Bits", "8bit", {"resolution": (8, "count")}),
        ("Output Bits", "12bit, 14bit, 10bit, 8bit", {
            "resolution 1": (12, "count"),
            "resolution 2": (14, "count"),
            "resolution 3": (10, "count"),
            "resolution 4": (8, "count"),
        }),
        ("DAC (Bit)", "12bit;7bit", {"resolution 1": (12, "count"), "resolution 2": (7, "count")}),
        ("ADC (Bit)", "24bit", {"resolution": (24, "count")}),
        ("Pwm (Bit)", "8bit;32bit", {"resolution 1": (8, "count"), "resolution 2": (32, "count")}),
        ("Core Size", "16/32 Bit", {"resolution 1": (16, "count"), "resolution 2": (32, "count")}),
        ("Temperature Resolution", "12bit", {"resolution": (12, "count")}),
        ("Effective Number of Bits", "12bit", {"resolution": (12, "count")}),
    ],
)
def test_resolution_alias_values(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, (amount, unit) in expected.items():
        assert_quantity(values[quantity], amount, unit)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("51P", 51),
        ("8P+16P", 24),
        ("4Px2", 8),
        ("9Px2+12P", 30),
    ],
)
def test_number_of_contacts(value, expected, capsys):
    values = normalized_values("Number of Contacts", value, capsys)

    assert_quantity(values["count"], expected, "count")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("80P", 80),
        ("14", 14),
        ("3AP", 3),
    ],
)
def test_number_of_holes(value, expected, capsys):
    values = normalized_values("Number of Holes", value, capsys)

    assert_quantity(values["count"], expected, "count")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2x7P", 14),
        ("1x5P", 5),
        ("2x10P (missing 1P)", 19),
        ("1x3P (Missing 1P)", 2),
        ("2x4", 8),
    ],
)
def test_number_of_positions_or_pins(value, expected, capsys):
    values = normalized_values("Number of Positions or Pins", value, capsys)

    assert_quantity(values["count"], expected, "count")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("34P", 34),
        ("3P (4P with 1 missing)", 3),
        ("36P (40P Missing 4P)", 36),
        ("16Bit", 16),
        ("6 digits", 6),
        ("8-bit", 8),
    ],
)
def test_number_of_positions(value, expected, capsys):
    values = normalized_values("Number of Positions", value, capsys)

    assert_quantity(values["count"], expected, "count")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("10P MIL", {"count": 10}),
        ("34P/40P MIL", {"count 1": 34, "count 2": 40}),
        ("50P/MDR", {"count": 50}),
        ("Universal form", {"count": "NaN"}),
    ],
)
def test_apply_connector_count(value, expected, capsys):
    values = normalized_values("Apply", value, capsys)

    for quantity, count in expected.items():
        assert_quantity(values[quantity], count, "count")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Frequency Registers(Bit)", "48", 48),
        ("Tuning Word Width(Bits)", "24b", 24),
        ("Tuning Word Width (Max)", "48b", 48),
    ],
)
def test_bit_width_counts(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    assert_quantity(values["count"], expected, "count")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1-Channel", {"channels 1": 1}),
        ("2-Channel", {"channels 1": 2}),
        ("1-Channel, 2-Channel", {"channels 1": 1, "channels 2": 2}),
        ("Monaural", {"channels 1": 1}),
        ("双声道", {"channels 1": 2}),
    ],
)
def test_speaker_channels(value, expected, capsys):
    values = normalized_values("Speaker Channels", value, capsys)

    for quantity, count in expected.items():
        assert_quantity(values[quantity], count, "count")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2 Pairs Differential Inputs", {"differential input pairs": 2}),
        ("2 Single-Ended Inputs", {"single-ended inputs": 2}),
        ("1 single-ended input + 1 differential pair input", {
            "single-ended inputs": 1,
            "differential input pairs": 1,
        }),
        ("8", {"inputs": 8}),
    ],
)
def test_number_of_inputs(value, expected, capsys):
    values = normalized_values("Number of Inputs", value, capsys)

    for quantity, count in expected.items():
        assert_quantity(values[quantity], count, "count")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1 NPN", {"npn transistors": 1}),
        ("1 N-Channel + 1 P-Channel", {"n-channel transistors": 1, "p-channel transistors": 1}),
        ("2 NPN + 2 PNP", {"npn transistors": 2, "pnp transistors": 2}),
    ],
)
def test_semiconductor_number(value, expected, capsys):
    values = normalized_values("Number", value, capsys)

    for quantity, count in expected.items():
        assert_quantity(values[quantity], count, "count")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1 Independent", {"independent diodes": 1}),
        ("1 Pair Common Anode", {"diode pairs": 1}),
        ("3 series x 2 parallel", {"series diodes": 3, "parallel strings": 2}),
        ("6 in series", {"series diodes": 6}),
    ],
)
def test_diode_configuration_counts(value, expected, capsys):
    values = normalized_values("Diode Configuration", value, capsys)

    for quantity, count in expected.items():
        assert_quantity(values[quantity], count, "count")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1 TRIAC", {"triacs": 1}),
        ("1 Unidirectional Thyristor and 1 Diode", {"thyristors": 1, "diodes": 1}),
        ("3 SCR and 3 Diode", {"scrs": 3, "diodes": 3}),
    ],
)
def test_scr_type_counts(value, expected, capsys):
    values = normalized_values("SCR Type", value, capsys)

    for quantity, count in expected.items():
        assert_quantity(values[quantity], count, "count")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("NPN", ["NPN"]),
        ("1 NPN Pre-biased, 1 PNP Pre-biased", ["1 NPN Pre-biased", "1 PNP Pre-biased"]),
        ("NPN+PNP", ["NPN+PNP"]),
    ],
)
def test_transistor_type_identifiers(value, expected, capsys):
    values = normalized_values("Transistor Type", value, capsys)

    assert {
        name: quantity
        for name, (quantity, unit) in values.items()
        if unit == "identifier"
    } == {
        f"type {index}": token
        for index, token in enumerate(expected, start=1)
    }


def test_driver_receiver(capsys):
    values = normalized_values("Driver/Receiver", "1/1;2/2", capsys)

    assert_quantity(values["drivers 1"], 1, "count")
    assert_quantity(values["receivers 1"], 1, "count")
    assert_quantity(values["drivers 2"], 2, "count")
    assert_quantity(values["receivers 2"], 2, "count")


def test_detents_pulses(capsys):
    values = normalized_values("Number of Detents/Pulses (Incremental)", "24/12", capsys)

    assert_quantity(values["detents"], 24, "count")
    assert_quantity(values["pulses"], 12, "count")


@pytest.mark.parametrize("key", ["Screw Specification", "Socket Specification", "Screw Hole Size"])
def test_metric_thread_attributes(key, capsys):
    values = normalized_values(key, "M3.5", capsys)

    assert_quantity(values["thread diameter"], 0.0035, "length")


def test_size_specifications_metric_thread_length(capsys):
    values = normalized_values("Size Specifications", "M3X13", capsys)

    assert_quantity(values["thread diameter"], 0.003, "length")
    assert_quantity(values["length"], 0.013, "length")

    values = normalized_values("Size Specifications", "3.2X6", capsys)
    assert_quantity(values["length 1"], 0.0032, "length")
    assert_quantity(values["length 2"], 0.006, "length")


def test_barrier_type_sides(capsys):
    values = normalized_values("Barrier Type", "2-Side", capsys)

    assert_quantity(values["sides"], 2, "count")


def test_connector_structure(capsys):
    values = normalized_values("Structure", "2x24P", capsys)

    assert_quantity(values["rows"], 2, "count")
    assert_quantity(values["positions per row"], 24, "count")
    assert_quantity(values["positions"], 48, "count")


def test_pin_and_stitch_counts(capsys):
    values = normalized_values("Pin", "12", capsys)
    assert_quantity(values["count"], 12, "count")

    values = normalized_values("Number of Stitches", "28P", capsys)
    assert_quantity(values["count"], 28, "count")

    values = normalized_values("Number of Stitches", "2.54mm", capsys)
    assert_quantity(values["pitch"], 0.00254, "length")


def test_additional_text_counts(capsys):
    values = normalized_values("Number of Incoming Lines Per Route", "2", capsys)
    assert_quantity(values["count"], 2, "count")

    values = normalized_values("Number of Independent Circuits", "1 channel", capsys)
    assert_quantity(values["circuits"], 1, "count")

    values = normalized_values("Line Number", "4.0", capsys)
    assert_quantity(values["count"], 4, "count")

    values = normalized_values("Work Score/Number of Work Combinations", "3 way", capsys)
    assert_quantity(values["count"], 3, "count")


def test_attachment_counts(capsys):
    values = normalized_values("Attachment", "1 plastic shell, 4 terminals", capsys)

    assert_quantity(values["plastic shells"], 1, "count")
    assert_quantity(values["terminals"], 4, "count")


def test_relay_contact_form_counts(capsys):
    values = normalized_values("Contact Form", "1 Form A + 1 Form B: 1A + 1B (SPST-NO + SPST-NC)", capsys)

    assert_quantity(values["form A"], 1, "count")
    assert_quantity(values["form B"], 1, "count")

    values = normalized_values("Relay Contact Form", "1 Form A(SPST-NO)", capsys)
    assert_quantity(values["form A"], 1, "count")

    values = normalized_values("Contact Types", "2CO", capsys)
    assert_quantity(values["changeover contacts"], 2, "count")


def test_display_switch_package_counts(capsys):
    values = normalized_values("Display Type", "7 Segment", capsys)
    assert_quantity(values["segments"], 7, "count")

    values = normalized_values("Switch Type", "Square Tilt 5-Way", capsys)
    assert_quantity(values["ways"], 5, "count")

    values = normalized_values("Packaging/Housing", "3-SIP Module", capsys)
    assert_quantity(values["pins"], 3, "count")


def test_memory_generation_and_material_attributes(capsys):
    values = normalized_values("Type of Memory", "1 FLASH +1 RAM", capsys)
    assert_quantity(values["flash"], 1, "count")
    assert_quantity(values["ram"], 1, "count")

    values = normalized_values("Ipex Algebra", "Gen 3", capsys)
    assert_quantity(values["generation"], 3, "count")

    values = normalized_values("Texture of Material", "6063-T5 aluminum", capsys)
    assert_quantity(values["material grade"], 6063, "count")
    assert_quantity(values["temper"], 5, "count")

    values = normalized_values("Shield Clip", "301 stainless steel", capsys)
    assert_quantity(values["material grade"], 301, "count")


@pytest.mark.parametrize(
    "value",
    ["H62 brass", "304 stainless steel", "SUS304-1/2H,T0.15", "-"],
)
def test_material_quality_identifier(value, capsys):
    values = normalized_values("Material Quality", value, capsys)

    assert values["identifier"] == [value, "identifier"]


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("Battery Type", "CR2032"),
        ("Applicable Battery Specifications", "CR2032"),
        ("DDR Sdram Standard", "DDR3"),
        ("Protocol Standard", "USB 2.0"),
        ("Usoc Codes", "RJ45"),
        ("Grade", "UL style 21215"),
        ("WiFi Protocols", "WIFI 802.11b/g/n"),
        ("CPU", "ESP8266"),
        ("Controller Type", "ST7789V"),
        ("Model", "XT60U-M"),
        ("Support Interface", "I2C;SPI;UART"),
        ("Utilized IC/Part", "ATWILC1000B-MU"),
        ("Wireless Standard", "Bluetooth5.0"),
        ("Core Processor", "ESP8266 chip"),
        ("Core IC", "nRF52832 chip"),
        ("Support PoE Standard", "IEEE 802.3 at(PoE+), IEEE 802.3 af(PoE)"),
        ("Character Set", "GB2312"),
        ("With Relay/Socket Model", "HF-157F"),
        ("Package", "SOIC-16-300mil"),
        ("Mpn", "DRV411AIRGPR"),
        ("Description", "VQFN-20 ADC/DAC - Specialized ROHS"),
        ("Display Configurations", "7段"),
        ("Display Configurations(Segment)", "7 Segment"),
        ("Touch Screen Type", "4、5Or8Wire Resistive Type"),
        ("Logic Family", "STLD1"),
        ("Type of Battery", "Lithium Battery, LiFePO4 Battery"),
        ("Ratings", "AEC-Q200"),
        ("Subclass", "X1,Y1"),
        ("Level of Protection", "IEC 61000-4-2"),
        ("Ethernet Speed Standards", "10BASE-T, 100BASE-TX, 100BASE-FX"),
        ("Versions", "PCI-E 3.0"),
        ("Algorithm", "SHA-256"),
        ("Input Type", "2-Wire Bus"),
        ("USB Protocol", "USB 2.0"),
        ("Application", "I2C"),
        ("Memory Format", "DDR3 SDRAM"),
        ("Agreement", "FeliCa,ISO 14443A,ISO 14443B,ISO 15693,MIFARE,NFC"),
        ("CPU Core", "ARM Cortex-M0"),
        ("Standard", "IEC 320-C8"),
        ("Pin Structure", "2x4P"),
        ("Interface Form", "M.2-B Key"),
        ("Flame Retardant Rating", "UL94V-0"),
        ("Plastic Material", "PA46"),
        ("Specification", "6.35"),
        ("Holes Structure", "1x13P"),
        ("Manufacturer", "Analog Devices Inc./Maxim Integrated"),
        ("Series", "74HC Series"),
        ("Lamp Holder Type", "2.0mm x 1.25mm square LED"),
        ("Ip Rating", "IP67"),
        ("Ip Rating", "-"),
    ],
)
def test_identifier_attributes(key, value, capsys):
    values = normalized_values(key, value, capsys)

    assert values["identifier"] == [value, "identifier"]


@pytest.mark.parametrize("value", ["FLASH", "Gold", "Tin"])
def test_finish_thickness_identifier(value, capsys):
    values = normalized_values("Finish Thickness", value, capsys)

    assert values["finish"] == [value, "identifier"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2um", 2e-6),
        ('15u"', 15 * 25.4e-6),
        ("-", "NaN"),
    ],
)
def test_finish_thickness_length(value, expected, capsys):
    values = normalized_values("Finish Thickness", value, capsys)

    assert_quantity(values["thickness"], expected, "length")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Mini-SPOX(5264)", ["Mini-SPOX(5264)"]),
        ("XA, XAD, XM, XAG", ["XA", "XAD", "XM", "XAG"]),
        ("-;-", ["-", "-"]),
    ],
)
def test_reference_series_identifiers(value, expected, capsys):
    values = normalized_values("Reference Series", value, capsys)

    assert {
        name: quantity
        for name, (quantity, unit) in values.items()
        if unit == "identifier"
    } == {
        f"series {index}": token
        for index, token in enumerate(expected, start=1)
    }


def test_safety_certification_identifiers(capsys):
    values = normalized_values("Safety Certification", "UL;CUL;VDE;ENEC10;CQC;KC", capsys)

    assert values["certification 1"] == ["UL", "identifier"]
    assert values["certification 4"] == ["ENEC10", "identifier"]
    assert values["certification 6"] == ["KC", "identifier"]


@pytest.mark.parametrize("value", ["SP3T", "Double pole triple throw", "2P2T", "-"])
def test_circuit_identifier(value, capsys):
    values = normalized_values("Circuit", value, capsys)

    assert values["circuit"] == [value, "identifier"]


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        (
            "Features",
            "Programmable gain, Built-in reference source",
            ["Programmable gain", "Built-in reference source"],
        ),
        (
            "Feature",
            "Low ESR;Overcurrent Protection(OCP);Short-Circuit  Protection",
            ["Low ESR", "Overcurrent Protection(OCP)", "Short-Circuit Protection"],
        ),
        (
            "Function",
            "Power-on reset, Power-down mode, Integrated buffer",
            ["Power-on reset", "Power-down mode", "Integrated buffer"],
        ),
    ],
)
def test_feature_list_attributes(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    assert {
        name: quantity
        for name, (quantity, unit) in values.items()
        if unit == "identifier"
    } == {
        f"feature {index}": token
        for index, token in enumerate(expected, start=1)
    }


def test_characteristic_list_attribute(capsys):
    values = normalized_values("Characteristic", "Remote on/off, OCP, OVP, SCP", capsys)

    assert values["characteristic 1"] == ["Remote on/off", "identifier"]
    assert values["characteristic 2"] == ["OCP", "identifier"]
    assert values["characteristic 3"] == ["OVP", "identifier"]
    assert values["characteristic 4"] == ["SCP", "identifier"]


def test_category_attribute(capsys):
    values = normalized_values(
        "Category",
        {
            "id1": 601,
            "id2": 11295,
            "name1": "ADC/DAC/Data Conversion",
            "name2": "ADC/DAC - Specialized",
        },
        capsys,
    )

    assert values["category"] == ["ADC/DAC/Data Conversion", "identifier"]
    assert values["subcategory"] == ["ADC/DAC - Specialized", "identifier"]
    assert values["category id"] == [601, "count"]
    assert values["subcategory id"] == [11295, "count"]


def test_configuration_display_counts(capsys):
    values = normalized_values("Configuration", "8 Segment x 2 Digit, 7 Segment x 3 Digit", capsys)

    assert_quantity(values["segments 1"], 8, "count")
    assert_quantity(values["digits 1"], 2, "count")
    assert_quantity(values["segments 2"], 7, "count")
    assert_quantity(values["digits 2"], 3, "count")


def test_configuration_identifiers(capsys):
    values = normalized_values("Configuration", "Common Drain, Common source", capsys)

    assert values["configuration 1"] == ["Common Drain", "identifier"]
    assert values["configuration 2"] == ["Common source", "identifier"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1.1V@250uA,100mA", {
            "Vce": (1.1, "voltage"),
            "condition current 1": (250e-6, "current"),
            "condition current 2": (0.1, "current"),
        }),
        ("2V@20A,4.5V", {
            "Vce": (2.0, "voltage"),
            "condition current 1": (20.0, "current"),
            "condition voltage 1": (4.5, "voltage"),
        }),
        ("150mV, 400mV", {
            "Vce 1": (0.15, "voltage"),
            "Vce 2": (0.4, "voltage"),
        }),
        ("400mV@0.04mA,0.5mA,1.6mA", {
            "Vce": (0.4, "voltage"),
            "condition current 1": (40e-6, "current"),
            "condition current 2": (0.5e-3, "current"),
            "condition current 3": (1.6e-3, "current"),
        }),
    ],
)
def test_vce_saturation_values(value, expected, capsys):
    values = normalized_values("VCE Saturation(VCE(sat))", value, capsys)

    for quantity, expected_value in expected.items():
        assert_quantity(values[quantity], expected_value[0], expected_value[1])


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("SPI, I2C", ["SPI", "I2C"]),
        ("SPI;DSP", ["SPI", "DSP"]),
        ("I2C, S/PDIF", ["I2C", "S/PDIF"]),
        ("U/D", ["U/D"]),
    ],
)
def test_interface_attribute(value, expected, capsys):
    values = normalized_values("Interface", value, capsys)

    assert {
        name: quantity
        for name, (quantity, unit) in values.items()
        if unit == "identifier"
    } == {
        f"interface {index}": token
        for index, token in enumerate(expected, start=1)
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("SPI, I2C", ["SPI", "I2C"]),
        ("CMOS;serial", ["CMOS", "serial"]),
        ("Up/Down(U/D,CS)", ["Up/Down(U/D,CS)"]),
        ("PWM, SPI, ADC, USB, I2C, ISP, JTAG, DMA",
            ["PWM", "SPI", "ADC", "USB", "I2C", "ISP", "JTAG", "DMA"]),
    ],
)
def test_interface_type_attribute(value, expected, capsys):
    values = normalized_values("Interface Type", value, capsys)

    assert {
        name: quantity
        for name, (quantity, unit) in values.items()
        if unit == "identifier"
    } == {
        f"interface {index}": token
        for index, token in enumerate(expected, start=1)
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("SPI, I2C, UART", ["SPI", "I2C", "UART"]),
        ("I2C;SPI;UART", ["I2C", "SPI", "UART"]),
        ("serial", ["serial"]),
    ],
)
def test_control_interface_attribute(value, expected, capsys):
    values = normalized_values("Control Interface", value, capsys)

    assert {
        name: quantity
        for name, (quantity, unit) in values.items()
        if unit == "identifier"
    } == {
        f"interface {index}": token
        for index, token in enumerate(expected, start=1)
    }


def test_communication_interface_attribute(capsys):
    values = normalized_values("Communication Interface", "SPI, JTAG, I2C", capsys)

    assert values["interface 1"] == ["SPI", "identifier"]
    assert values["interface 2"] == ["JTAG", "identifier"]
    assert values["interface 3"] == ["I2C", "identifier"]


def test_protocol_identifier_list(capsys):
    values = normalized_values("Protocol", "USB 3.1;DP 1.3", capsys)

    assert values["protocol 1"] == ["USB 3.1", "identifier"]
    assert values["protocol 2"] == ["DP 1.3", "identifier"]

    values = normalized_values("Interface Protocol", "I2C;SPI;UART", capsys)

    assert values["protocol 1"] == ["I2C", "identifier"]
    assert values["protocol 2"] == ["SPI", "identifier"]
    assert values["protocol 3"] == ["UART", "identifier"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Encoder/decoder", ["Encoder/decoder"]),
        ("Driver, Buffer", ["Driver", "Buffer"]),
        ("Transceiver;隔离器", ["Transceiver", "隔离器"]),
        ("NPN+PNP", ["NPN+PNP"]),
    ],
)
def test_type_attribute(value, expected, capsys):
    values = normalized_values("Type", value, capsys)

    assert {
        name: quantity
        for name, (quantity, unit) in values.items()
        if unit == "identifier"
    } == {
        f"type {index}": token
        for index, token in enumerate(expected, start=1)
    }


def test_logic_type_attribute(capsys):
    values = normalized_values("Logic Type", "Divide-by-2, Divide-by-10", capsys)

    assert values["logic type 1"] == ["Divide-by-2", "identifier"]
    assert values["logic type 2"] == ["Divide-by-10", "identifier"]


def test_antenna_type_attribute(capsys):
    values = normalized_values("Antenna Type", "Stamp Hole Antenna, IPEX interface", capsys)

    assert values["antenna type 1"] == ["Stamp Hole Antenna", "identifier"]
    assert values["antenna type 2"] == ["IPEX interface", "identifier"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Cellular,CATV,DBS,PCS,WLAN", ["Cellular", "CATV", "DBS", "PCS", "WLAN"]),
        ("RS422;RS485", ["RS422", "RS485"]),
        ("802.11a/b/g/WiFi;802.16/WiMax;WLAN",
            ["802.11a/b/g/WiFi", "802.16/WiMax", "WLAN"]),
        ("2G/3G/4G", ["2G/3G/4G"]),
    ],
)
def test_applications_attribute(value, expected, capsys):
    values = normalized_values("Applications", value, capsys)

    assert {
        name: quantity
        for name, (quantity, unit) in values.items()
        if unit == "identifier"
    } == {
        f"application {index}": token
        for index, token in enumerate(expected, start=1)
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("USB to UART, USB to SPI, USB to I2C", ["USB to UART", "USB to SPI", "USB to I2C"]),
        ("Buffers;Driver", ["Buffers", "Driver"]),
        ("USB to HUB; USB to SD/MMC", ["USB to HUB", "USB to SD/MMC"]),
        ("-", ["-"]),
    ],
)
def test_applications_function_attribute(value, expected, capsys):
    values = normalized_values("Applications Function", value, capsys)

    assert {
        name: quantity
        for name, (quantity, unit) in values.items()
        if unit == "identifier"
    } == {
        f"application {index}": token
        for index, token in enumerate(expected, start=1)
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("DC Power Jack", ["DC Power Jack"]),
        ("Type-A, Type-C", ["Type-A", "Type-C"]),
        ("DDR1;DDR2", ["DDR1", "DDR2"]),
        ("Blade/Shrapnel Connector", ["Blade/Shrapnel Connector"]),
        ("Ferrite Ring (SMD)", ["Ferrite Ring (SMD)"]),
    ],
)
def test_connector_type_attribute(value, expected, capsys):
    values = normalized_values("Connector Type", value, capsys)

    assert {
        name: quantity
        for name, (quantity, unit) in values.items()
        if unit == "identifier"
    } == {
        f"connector type {index}": token
        for index, token in enumerate(expected, start=1)
    }


def test_connection_type_identifier(capsys):
    values = normalized_values("Connection Type", "Screw Connection (M2.5)", capsys)

    assert values["connection type"] == ["Screw Connection (M2.5)", "identifier"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Current-缓冲", ["Current Buffered"]),
        ("Voltage-缓冲;Current-非缓冲", ["Voltage Buffered", "Current Unbuffered"]),
        ("Open-drain, Open Collector", ["Open Drain", "Open Collector"]),
        ("漏极开路;Push-pull", ["Open Drain", "Push-Pull"]),
        ("CMOS;互补;轨到轨;TTL", ["CMOS", "Complementary", "Rail-to-Rail", "TTL"]),
        ("Clipped sine wave", ["Clipped Sine Wave"]),
    ],
)
def test_output_type_attribute(value, expected, capsys):
    values = normalized_values("Output Type", value, capsys)

    assert {
        name: quantity
        for name, (quantity, unit) in values.items()
        if unit == "identifier"
    } == {
        f"output type {index}": token
        for index, token in enumerate(expected, start=1)
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("PWM;Watchdog", ["PWM", "Watchdog"]),
        ("Low-VoltageDetect;WDT;PWM;CCP capture/compare",
            ["Low-Voltage Detection", "Watchdog", "PWM", "CCP Capture/Compare"]),
        ("RTC Real-time Clock;Watchdog;Ethernet protocol stack",
            ["RTC", "Watchdog", "Ethernet Protocol Stack"]),
        ("Temperature transducer;TRNG;硬件加密",
            ["Temperature Sensor", "TRNG", "Hardware Encryption"]),
        ("触摸按键;安全加密", ["Touch Button", "Hardware Encryption"]),
        ("LCD/LED Driver;WDT", ["LCD/LED Driver", "Watchdog"]),
    ],
)
def test_peripheral_function_attribute(value, expected, capsys):
    values = normalized_values("Peripheral/Function", value, capsys)

    assert {
        name: quantity
        for name, (quantity, unit) in values.items()
        if unit == "identifier"
    } == {
        f"peripheral {index}": token
        for index, token in enumerate(expected, start=1)
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("SEPIC, Buck, Boost, Buck-Boost", ["SEPIC", "Buck", "Boost", "Buck-Boost"]),
        ("Boost;Cuk;Flyback;SEPIC", ["Boost", "Cuk", "Flyback", "SEPIC"]),
        ("Step-down;Boost;Step-down-Boost", ["Buck", "Boost", "Buck-Boost"]),
        ("Full Bridge;Half-bridge;Push-pull type", ["Full-Bridge", "Half-Bridge", "Push-Pull"]),
        ("Switched capacitor(充电泵)", ["Charge Pump"]),
        ("boost converter", ["Boost"]),
    ],
)
def test_topology_attribute(value, expected, capsys):
    values = normalized_values("Topology", value, capsys)

    assert {
        name: quantity
        for name, (quantity, unit) in values.items()
        if unit == "identifier"
    } == {
        f"topology {index}": token
        for index, token in enumerate(expected, start=1)
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("R:75mW, G:120mW, B:120mW", {
            "power R": 0.075,
            "power G": 0.12,
            "power B": 0.12,
        }),
        ("75mW, 62.5mW", {
            "power 1": 0.075,
            "power 2": 0.0625,
        }),
        ("R:120mW, G:60mW, B:60mW", {
            "power R": 0.12,
            "power G": 0.06,
            "power B": 0.06,
        }),
    ],
)
def test_power_attribute(value, expected, capsys):
    values = normalized_values("Power", value, capsys)

    for quantity, expected_value in expected.items():
        assert_quantity(values[quantity], expected_value, "power")


def test_remarks_voltage_power(capsys):
    values = normalized_values("Remarks", "24V/60W", capsys)

    assert_quantity(values["voltage"], 24.0, "voltage")
    assert_quantity(values["power"], 60.0, "power")

    values = normalized_values("Remarks", "Output Voltage + Output Current (Max)", capsys)

    assert values["remark"] == ["Output Voltage + Output Current (Max)", "identifier"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("3pin", {"count": (3, "count")}),
        ("M3X8", {"thread diameter": (0.003, "length"), "length 1": (0.008, "length")}),
        ("M2.5X0.45", {"thread diameter": (0.0025, "length"), "thread pitch": (0.00045, "length")}),
        ("M3-0.5X10", {
            "thread diameter": (0.003, "length"),
            "thread pitch": (0.0005, "length"),
            "length 1": (0.01, "length"),
        }),
        ("M3X11+6", {
            "thread diameter": (0.003, "length"),
            "length 1": (0.011, "length"),
            "length 2": (0.006, "length"),
        }),
        ("30*1.5*1mm", {
            "length 1": (0.03, "length"),
            "length 2": (0.0015, "length"),
            "length 3": (0.001, "length"),
        }),
        ("6.5mm", {"length": (0.0065, "length")}),
    ],
)
def test_specifications_attribute(value, expected, capsys):
    values = normalized_values("Specifications", value, capsys)

    for quantity, expected_value in expected.items():
        assert_quantity(values[quantity], expected_value[0], expected_value[1])


def test_specifications_identifier_fallback(capsys):
    values = normalized_values(
        "Specifications",
        "Coil Voltage: 230 VAC; Coil Current: 14.2mA",
        capsys,
    )

    assert values["specification"] == [
        "Coil Voltage: 230 VAC; Coil Current: 14.2mA",
        "identifier",
    ]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("29mm×12.7mm×15.7mm", {
            "length 1": (0.029, "length"),
            "length 2": (0.0127, "length"),
            "length 3": (0.0157, "length"),
        }),
        ("L2.9*W1.5*H1.2 mm", {
            "length 1": (0.0029, "length"),
            "length 2": (0.0015, "length"),
            "length 3": (0.0012, "length"),
        }),
        ("M3x7x9.5-6pin", {
            "length 1": (0.003, "length"),
            "length 2": (0.007, "length"),
            "length 3": (0.0095, "length"),
            "pins": (6, "count"),
        }),
        ("2.8", {"length": (0.0028, "length")}),
    ],
)
def test_size_attribute(value, expected, capsys):
    values = normalized_values("Size", value, capsys)

    for quantity, expected_value in expected.items():
        assert_quantity(values[quantity], expected_value[0], expected_value[1])


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Brass;Copper Alloy", ["Brass", "Copper Alloy"]),
        ("Brass, Phosphor bronze", ["Brass", "Phosphor Bronze"]),
        ("phosphor bronze", ["Phosphor Bronze"]),
        ("锡磷青铜", ["Tin Phosphor Bronze"]),
        ("AgSnO2+W", ["AgSnO2+W"]),
    ],
)
def test_contact_material_attribute(value, expected, capsys):
    values = normalized_values("Contact Material", value, capsys)

    assert {
        name: quantity
        for name, (quantity, unit) in values.items()
        if unit == "identifier"
    } == {
        f"material {index}": token
        for index, token in enumerate(expected, start=1)
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Red", ["Red"]),
        ("Red, green, blue", ["Red", "Green", "Blue"]),
        ("Blue(RGB)", ["Blue"]),
        ("Green-yellow,Yellow", ["Yellow Green", "Yellow"]),
        ("Amber Color,Blue", ["Amber", "Blue"]),
        ("Cold White", ["Cool White"]),
    ],
)
def test_illumination_color_attribute(value, expected, capsys):
    values = normalized_values("Illumination Color", value, capsys)

    assert {
        name: quantity
        for name, (quantity, unit) in values.items()
        if unit == "identifier"
    } == {
        f"color {index}": token
        for index, token in enumerate(expected, start=1)
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("600kHz, 1MHz, 800kHz", {
            "frequency 1": 600e3,
            "frequency 2": 1e6,
            "frequency 3": 800e3,
        }),
        ("1.2MHz;2.4MHz", {
            "frequency 1": 1.2e6,
            "frequency 2": 2.4e6,
        }),
        ("18kHz~40kHz;55kHz~75kHz", {
            "frequency 1 min": 18e3,
            "frequency 1 max": 40e3,
            "frequency 2 min": 55e3,
            "frequency 2 max": 75e3,
        }),
    ],
)
def test_switching_frequency_attribute(value, expected, capsys):
    values = normalized_values("Switching Frequency", value, capsys)

    for quantity, expected_value in expected.items():
        assert_quantity(values[quantity], expected_value, "frequency")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("500mA, 315mA", [0.5, 0.315]),
        ("3A, -3A", [3.0, -3.0]),
        ("4A, 8A, -3A, -1.25A", [4.0, 8.0, -3.0, -1.25]),
    ],
)
def test_output_current_max_attribute(value, expected, capsys):
    values = normalized_values("Output Current (Max)", value, capsys)

    for index, expected_value in enumerate(expected, start=1):
        assert_quantity(values[f"current {index}"], expected_value, "current")


def test_plating_and_product_description_dimensions(capsys):
    values = normalized_values("Electroplate", 'Bright tin plating 80~150u", nickel plating 50u"', capsys)
    assert_quantity(values["tin thickness min"], 80 * 0.0254e-6, "length")
    assert_quantity(values["tin thickness max"], 150 * 0.0254e-6, "length")
    assert_quantity(values["nickel thickness min"], 50 * 0.0254e-6, "length")
    assert_quantity(values["nickel thickness max"], 50 * 0.0254e-6, "length")

    values = normalized_values("Product Description", "M3*6*L4+1.4", capsys)
    assert_quantity(values["length 1"], 0.003, "length")
    assert_quantity(values["length 2"], 0.006, "length")
    assert_quantity(values["length 3"], 0.004, "length")
    assert_quantity(values["length 4"], 0.0014, "length")


def test_viewing_direction_clock_angle(capsys):
    values = normalized_values("Viewing Direction", "6 o'clock", capsys)

    assert_quantity(values["angle"], 180, "angle")


def test_wire_strands(capsys):
    values = normalized_values("Number of Wire Strands", "42/0.0039\"", capsys)

    assert_quantity(values["strands"], 42, "count")
    assert_quantity(values["strand diameter"], 0.0039 * 0.0254, "length")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Life", "100,000 cycles", 100000),
        ("Life", "4 million cycles", 4000000),
        ("Mechanical Life", "1万次", 10000),
        ("Mechanical Life", "5千次", 5000),
        ("Mechanical Life", "5 Million Times", 5000000),
        ("Elastic Life", "10000 times", 10000),
        ("Operating Life", "2万次", 20000),
        ("Program/Erase Cycles", "1×10^15 Cycles", 1000000000000000),
        ("Program/Erase Cycles", "1 Trillion Cycles", 1000000000000),
        ("Switching Life", "10000 times", 10000),
        ("Switch Life", "100,000 Times", 100000),
        ("Switch Life", "1万次", 10000),
    ],
)
def test_cycle_life_counts(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    assert_quantity(values["count"], expected, "count")


def test_write_cycle_endurance(capsys):
    values = normalized_values("Write Cycle Endurance", "1,000,000 cycles", capsys)

    assert_quantity(values["count"], 1000000, "count")


def test_store_cycles(capsys):
    values = normalized_values("Store Cycles", "1,000,000 cycles", capsys)

    assert_quantity(values["count"], 1000000, "count")


def test_cycle_life_count_lists(capsys):
    values = normalized_values("Connect-Disconnect Life", "5,000 cycles, 1,500 Cycles", capsys)

    assert_quantity(values["count 1"], 5000, "count")
    assert_quantity(values["count 2"], 1500, "count")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1.2uA", 1.2e-6),
        ("20.8uA@25℃,5min", 20.8e-6),
        ("500nA@25°C,5min", 500e-9),
    ],
)
def test_leakage_current_dcl(value, expected, capsys):
    values = normalized_values("Leakage Current(Dcl)", value, capsys)

    assert_quantity(values["current"], expected, "current")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("11A", 11.0),
        ("250mA", 0.25),
        ("null", "NaN"),
    ],
)
def test_average_rectified_current(value, expected, capsys):
    values = normalized_values("Average Rectified Current (IO)", value, capsys)

    assert_quantity(values["current"], expected, "current")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("4A", [4.0]),
        ("500uA", [500e-6]),
        ("870mA;770mA", [0.87, 0.77]),
    ],
)
def test_collector_current(value, expected, capsys):
    values = normalized_values("Collector Current (Ic)", value, capsys)

    if len(expected) == 1:
        assert_quantity(values["current"], expected[0], "current")
    else:
        for index, current in enumerate(expected, start=1):
            assert_quantity(values[f"current {index}"], current, "current")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("800mA", 0.8),
        ("6uA", 6e-6),
        ("-", "NaN"),
    ],
)
def test_charge_current_max(value, expected, capsys):
    values = normalized_values("Charge Current - Max", value, capsys)

    assert_quantity(values["current"], expected, "current")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Power Current Rating (Max)", "5A", 5.0),
        ("Contact Current (AC)", "100mA", 0.1),
    ],
)
def test_additional_scalar_current_values(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    assert_quantity(values["current"], expected, "current")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("5A", {"current": 5.0}),
        ("10A@(8/20us)", {"current": 10.0}),
        ("870mA", {"current": 0.87}),
        ("15A;37.5A", {"current 1": 15.0, "current 2": 37.5}),
    ],
)
def test_peak_pulse_current_8_20us(value, expected, capsys):
    values = normalized_values("Peak Pulse Current(Ipp)@8/20us", value, capsys)

    for quantity, current in expected.items():
        assert_quantity(values[quantity], current, "current")


def test_peak_pulse_current_waveform_list(capsys):
    values = normalized_values(
        "Peak Pulse Current (Ipp)",
        "57.5A@10/1000us, 431.3A@8/20us",
        capsys,
    )

    assert_quantity(values["current 1"], 57.5, "current")
    assert_quantity(values["pulse rise time 1"], 10e-6, "time")
    assert_quantity(values["pulse duration 1"], 1000e-6, "time")
    assert_quantity(values["current 2"], 431.3, "current")
    assert_quantity(values["pulse rise time 2"], 8e-6, "time")
    assert_quantity(values["pulse duration 2"], 20e-6, "time")


def test_peak_pulse_current_mixed_condition_list(capsys):
    values = normalized_values(
        "Peak Pulse Current (Ipp)",
        "30A, 60A, 120A@10/1000us",
        capsys,
    )

    assert_quantity(values["current 1"], 30.0, "current")
    assert_quantity(values["current 2"], 60.0, "current")
    assert_quantity(values["current 3"], 120.0, "current")
    assert_quantity(values["pulse rise time 3"], 10e-6, "time")
    assert_quantity(values["pulse duration 3"], 1000e-6, "time")


def test_peak_pulse_current_time_range(capsys):
    values = normalized_values("Peak Pulse Current (Ipp)", "35.6A@10-15ms", capsys)

    assert_quantity(values["current"], 35.6, "current")
    assert_quantity(values["pulse time min"], 10e-3, "time")
    assert_quantity(values["pulse time max"], 15e-3, "time")


def test_number_of_io_count(capsys):
    values = normalized_values("Number of I/O", "8", capsys)

    assert_quantity(values["count"], 8, "count")

def test_number_of_differential_input_channels_count(capsys):
    values = normalized_values("Number of Differential Input Channels", "3", capsys)

    assert_quantity(values["count"], 3, "count")

def test_number_of_taps_count(capsys):
    values = normalized_values("Number of Taps", "256", capsys)

    assert_quantity(values["count"], 256, "count")

def test_number_of_voltages_monitored_count(capsys):
    values = normalized_values("Number of Voltages Monitored", "12", capsys)

    assert_quantity(values["count"], 12, "count")

def test_number_of_amplifiers_count(capsys):
    values = normalized_values("Number of Amplifiers", "1", capsys)

    assert_quantity(values["count"], 1, "count")

def test_filter_order_count(capsys):
    values = normalized_values("Filter Order", "5th Order, 4th Order", capsys)

    assert_quantity(values["count 1"], 5, "count")
    assert_quantity(values["count 2"], 4, "count")

def test_number_of_bits_per_element_count(capsys):
    values = normalized_values("Number of Bits Per Element", "4, 2", capsys)

    assert_quantity(values["count 1"], 4, "count")
    assert_quantity(values["count 2"], 2, "count")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Timer Number", "3", {"count": 3}),
        ("Timer Number", "-", {"count": "NaN"}),
        ("Numberof Drivers", "24", {"count": 24}),
        ("Numberof Receivers", "5", {"count": 5}),
        ("Number of Receivers", "2, 1", {"count 1": 2, "count 2": 1}),
        ("Number of Drivers", "2, 1", {"count 1": 2, "count 2": 1}),
        ("Number of Ports", "28", {"count": 28}),
        ("Number of Supporting Devices", "126", {"count": 126}),
        ("Number of Receiver", "5", {"count": 5}),
        ("Number of Driver", "4", {"count": 4}),
        ("Input Number", "2, 1", {"count 1": 2, "count 2": 1}),
    ],
)
def test_driver_receiver_count_values(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, count in expected.items():
        assert_quantity(values[quantity], count, "count")


def test_word_size_counts(capsys):
    values = normalized_values("Word Size", "12, 16", capsys)
    assert_quantity(values["count 1"], 12, "count")
    assert_quantity(values["count 2"], 16, "count")

    values = normalized_values("Word Size", "16x16, 16, 8x16", capsys)
    assert_quantity(values["columns 1"], 16, "count")
    assert_quantity(values["rows 1"], 16, "count")
    assert_quantity(values["count 2"], 16, "count")
    assert_quantity(values["columns 3"], 8, "count")
    assert_quantity(values["rows 3"], 16, "count")

    values = normalized_values("Word Size", "5x7~24", capsys)
    assert_quantity(values["columns"], 5, "count")
    assert_quantity(values["rows min"], 7, "count")
    assert_quantity(values["rows max"], 24, "count")

    values = normalized_values("Word Size", "16~192", capsys)
    assert_quantity(values["count min"], 16, "count")
    assert_quantity(values["count max"], 192, "count")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("4", {"count": 4}),
        ("Dual", {"count": 2}),
        ("Four channels", {"count": 4}),
        ("QUAD", {"count": 4}),
        ("Hex", {"count": 6}),
        ("4;8", {"count 1": 4, "count 2": 8}),
        ("4, 3", {"count 1": 4, "count 2": 3}),
        ("3/8", {"count 1": 3, "count 2": 8}),
        ("Five Channels", {"count": 5}),
        ("4/7", {"count 1": 4, "count 2": 7}),
        ("1C2A", {"count": 1}),
        ("-", {"count": "NaN"}),
    ],
)
def test_channel_count(value, expected, capsys):
    values = normalized_values("Number of Channels", value, capsys)

    for quantity, count in expected.items():
        assert_quantity(values[quantity], count, "count")

@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2", 2),
        ("Dual channel", 2),
        ("Four Channels", 4),
        ("-", "NaN"),
    ],
)
def test_number_of_elements_count(value, expected, capsys):
    values = normalized_values("Number of Elements", value, capsys)

    assert_quantity(values["count"], expected, "count")

@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Integral Non - Linearity", "1LSB", {"linearity": [1, "lsb"]}),
        ("Integral Non - Linearity", "1/2LSB", {"linearity": [0.5, "lsb"]}),
        ("Integral Non - Linearity", "2LSB, 1LSB, 4LSB", {
            "linearity 1": [2, "lsb"],
            "linearity 2": [1, "lsb"],
            "linearity 3": [4, "lsb"],
        }),
        ("Integral Nonlinearity", "±8LSB;±1LSB", {
            "linearity 1": [8, "lsb"],
            "linearity 2": [1, "lsb"],
        }),
        ("Integral Nonlinearity", "±0.001%", {"linearity": [0.001, "percentage"]}),
        ("Inl/Dnl(Lsb)", "-", {"linearity": ["NaN", "lsb"]}),
        ("Gain Error", "±0.7LSB", {"gain error": [0.7, "lsb"]}),
    ],
)
def test_lsb_linearity(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, expected_value in expected.items():
        assert_quantity(values[quantity], expected_value[0], expected_value[1])

@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2.5V", {"voltage 1": 2.5}),
        ("625mV", {"voltage 1": 0.625}),
        ("2.5V, 1.25V", {"voltage 1": 2.5, "voltage 2": 1.25}),
        ("-", {"voltage 1": "NaN"}),
    ],
)
def test_voltage_reference_value(value, expected, capsys):
    values = normalized_values("Voltage Reference Value", value, capsys)

    for quantity, voltage in expected.items():
        assert_quantity(values[quantity], voltage, "voltage")

@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("10V", {"voltage 1": 10.0}),
        ("625mV", {"voltage 1": 0.625}),
        ("2.5V, 1.25V, 625mV", {
            "voltage 1": 2.5,
            "voltage 2": 1.25,
            "voltage 3": 0.625,
        }),
    ],
)
def test_full_scale_range(value, expected, capsys):
    values = normalized_values("Full-Scale Range(Fsr)", value, capsys)

    for quantity, voltage in expected.items():
        assert_quantity(values[quantity], voltage, "voltage")

@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("±280mV", {"voltage min": -0.28, "voltage max": 0.28}),
        ("2V", {"voltage": 2.0}),
        ("±31.25mV, ±5mV", {
            "voltage 1 min": -0.03125,
            "voltage 1 max": 0.03125,
            "voltage 2 min": -0.005,
            "voltage 2 max": 0.005,
        }),
    ],
)
def test_differential_input_voltage(value, expected, capsys):
    values = normalized_values("Differential Input Voltage", value, capsys)

    for quantity, voltage in expected.items():
        assert_quantity(values[quantity], voltage, "voltage")

@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("5000", {"voltage": 5000.0}),
        ("4.8kVrms", {"voltage": 4800.0}),
        ("4kV@AC", {"voltage": 4000.0}),
        ("6kV, 3.5kV", {"voltage 1": 6000.0, "voltage 2": 3500.0}),
        ("-", {"voltage": "NaN"}),
    ],
)
def test_isolation_voltage(value, expected, capsys):
    values = normalized_values("Isolation Voltage(VRMS)", value, capsys)

    for quantity, voltage in expected.items():
        assert_quantity(values[quantity], voltage, "voltage")

@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("36V", {"voltage": 36.0}),
        ("10V, 12V", {"voltage 1": 10.0, "voltage 2": 12.0}),
    ],
)
def test_maximum_power_supply_range(value, expected, capsys):
    values = normalized_values("Maximum Power Supply Range (Vdd-Vss)", value, capsys)

    for quantity, voltage in expected.items():
        assert_quantity(values[quantity], voltage, "voltage")

@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Collector-Emitter Breakdown Voltage (VCEO)", "100V", {"voltage": 100.0}),
        ("Collector-Emitter Breakdown Voltage (VCEO)", "160V;150V", {
            "voltage 1": 160.0,
            "voltage 2": 150.0,
        }),
        ("Collector-Emitter Voltage (VCEO)", "12V, 15V", {
            "voltage 1": 12.0,
            "voltage 2": 15.0,
        }),
        ("Emitter-Base Voltage (VEBO)", "5V, 6V", {
            "voltage 1": 5.0,
            "voltage 2": 6.0,
        }),
        ("Input Offset Voltage (VOS)", "200uV", {"voltage": 200e-6}),
        ("Input Offset Voltage (VOS)", "5mV;-5mV", {
            "voltage 1": 0.005,
            "voltage 2": -0.005,
        }),
        ("Input Hysteresis Voltage (Vhys)", "1mV, 10mV", {
            "voltage 1": 0.001,
            "voltage 2": 0.01,
        }),
        ("Gate-Source Breakdown Voltage (Vgss)", "40V", {"voltage": 40.0}),
        ("Gate-Source Cutoff Voltage (Vgs(Off))", "300mV, 1.5V, 700mV", {
            "voltage 1": 0.3,
            "voltage 2": 1.5,
            "voltage 3": 0.7,
        }),
        ("Controller Operating Voltage (Vccq)", "1.7V~1.95V, 2.7V~3.6V", {
            "voltage 1 min": 1.7,
            "voltage 1 max": 1.95,
            "voltage 2 min": 2.7,
            "voltage 2 max": 3.6,
        }),
        ("Nand Operating Voltage (Vccf)", "3.3V, 1.8V", {
            "voltage 1": 3.3,
            "voltage 2": 1.8,
        }),
        ("Upply Voltage (Vcc)", "2.2V~3.6V;4.5V~5.5V", {
            "voltage 1 min": 2.2,
            "voltage 1 max": 3.6,
            "voltage 2 min": 4.5,
            "voltage 2 max": 5.5,
        }),
        ("Vin", "3V~36V", {"voltage min": 3.0, "voltage max": 36.0}),
        ("Vout", "5V, -5V", {"voltage 1": 5.0, "voltage 2": -5.0}),
        ("Supply Voltage Range", "3V~3.6V", {"voltage min": 3.0, "voltage max": 3.6}),
        ("Supply Voltage Range - Vccio", "2.5V;3.3V", {"voltage 1": 2.5, "voltage 2": 3.3}),
        ("Voltage - Supply(Vccio)", "2.5V, 3.3V", {"voltage 1": 2.5, "voltage 2": 3.3}),
        ("Voltage - Supply (Ic)", "40V~57V", {"voltage min": 40.0, "voltage max": 57.0}),
        ("Voltage - Supply (Power)", "50V~57V", {"voltage min": 50.0, "voltage max": 57.0}),
        ("VGS", "±30V", {"voltage min": -30.0, "voltage max": 30.0}),
        ("Hi-Pot", "1.5kV", {"voltage": 1500.0}),
        ("Isolation Voltage(RMS)", "3.75kV;5kV", {"voltage 1": 3750.0, "voltage 2": 5000.0}),
        ("Isolation Voltage", "5kV", {"voltage": 5000.0}),
    ],
)
def test_voltage_alias_values(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, voltage in expected.items():
        assert_quantity(values[quantity], voltage, "voltage")


def test_gpio_ports_number_count(capsys):
    values = normalized_values("Gpio Ports Number", "34", capsys)

    assert_quantity(values["count"], 34, "count")

    values = normalized_values("Gpio Ports Number", "-", capsys)

    assert_quantity(values["count"], "NaN", "count")


def test_logic_elements_blocks_count(capsys):
    values = normalized_values("Number of Logic Elements/Blocks", "2160", capsys)

    assert_quantity(values["count"], 2160, "count")

    values = normalized_values("Number of Logic Elements/Blocks", "-", capsys)

    assert_quantity(values["count"], "NaN", "count")


def test_logic_elements_cells_count(capsys):
    values = normalized_values("Logic Elements/Cells", "10320", capsys)

    assert_quantity(values["count"], 10320, "count")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("10Mbit/s", {"data rate": 10e6}),
        ("8kHz, 32kHz", {"data rate 1": 8e3, "data rate 2": 32e3}),
        ("2Mbps;50Mbps", {"data rate 1": 2e6, "data rate 2": 50e6}),
        ("3.75Gbps, 1Gbps", {"data rate 1": 3.75e9, "data rate 2": 1e9}),
        (("Data Rate (Max)", "24Mbps"), {"data rate": 24e6}),
        (("Data Rate (Max)", "40ksps, 100ksps"), {"data rate 1": 40e3, "data rate 2": 100e3}),
        (("Reading Speed in Sequence", "330MB/S"), {"data rate": 330e6}),
        (("Writing Speed in Sequence", "27.3MB/S"), {"data rate": 27.3e6}),
        (("Transmission Rate", "106Kbit/s, 848Kbit/s"), {"data rate 1": 106e3, "data rate 2": 848e3}),
        (("Sequential Read/Write (Mb/S)", "256/119MB/s"), {"read data rate": 256e6, "write data rate": 119e6}),
        ("NaN", {"data rate": "NaN"}),
    ],
)
def test_data_rate(value, expected, capsys):
    if isinstance(value, tuple):
        key, value = value
    else:
        key = "Data Rate"
    values = normalized_values(key, value, capsys)

    for quantity, rate in expected.items():
        assert_quantity(values[quantity], rate, "data_rate")


def test_random_read_write_iops(capsys):
    values = normalized_values("Random Read/Write (Iops)", "3200/1800iops", capsys)

    assert_quantity(values["read iops"], 3200, "frequency")
    assert_quantity(values["write iops"], 1800, "frequency")

    values = normalized_values("Random Write (Iops)", "65Kiops", capsys)
    assert_quantity(values["write iops"], 65000, "frequency")

    values = normalized_values("Random Read (Iops)", "70Kiops", capsys)
    assert_quantity(values["read iops"], 70000, "frequency")


def test_frame_rate(capsys):
    values = normalized_values("Frame Rate(Fps)", "30, 60", capsys)

    assert_quantity(values["frame rate 1"], 30.0, "frequency")
    assert_quantity(values["frame rate 2"], 60.0, "frequency")


def test_gyroscope_measurement_range(capsys):
    values = normalized_values("Gyroscope Measurement Range (Max)", "±2000dps", capsys)

    assert_quantity(values["angular velocity min"], -2000.0, "angular_velocity")
    assert_quantity(values["angular velocity max"], 2000.0, "angular_velocity")


def test_relative_bandwidth(capsys):
    values = normalized_values("Relative Bandwidth", "±6.5MHz", capsys)

    assert_quantity(values["frequency min"], -6.5e6, "frequency")
    assert_quantity(values["frequency max"], 6.5e6, "frequency")


def test_b_constant_kelvin(capsys):
    values = normalized_values("B Constant (25°C/85°C)", "3434K", capsys)

    assert_quantity(values["temperature"], 3434.0, "kelvin")

    values = normalized_values("B Constant (25°C/85°C)", "-", capsys)

    assert_quantity(values["temperature"], "NaN", "kelvin")

    values = normalized_values("B Constant (25°C/50°C)", "3450K, 3950K", capsys)

    assert_quantity(values["temperature 1"], 3450.0, "kelvin")
    assert_quantity(values["temperature 2"], 3950.0, "kelvin")

    values = normalized_values("B Constant (25°C/100°C)", "3455K", capsys)

    assert_quantity(values["temperature"], 3455.0, "kelvin")

    values = normalized_values("B Constant (25°C/75°C)", "3477K", capsys)

    assert_quantity(values["temperature"], 3477.0, "kelvin")


def test_holding_temperature(capsys):
    values = normalized_values("Holding Temperature", "76℃", capsys)

    assert_quantity(values["temperature"], 76, "temperature")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Maximum Temperature Limit", "180℃", {"temperature": 180}),
        ("Maximum Temperature Limit", "-", {"temperature": "NaN"}),
        ("Holding Temperature Limit", "76℃", {"temperature": 76}),
        ("Holding Temperature Limit", "72/61℃", {"temperature 1": 72, "temperature 2": 61}),
        ("Rated Functioning Temperature", "102℃", {"temperature": 102}),
        ("Shrinkage Temperature", "90°C (initial)", {"temperature": 90}),
        ("Operating Temperatue", "-40℃~+85℃", {"temperature min": -40, "temperature max": 85}),
        ("Operating Temperatue", "-", {"temperature": "NaN"}),
    ],
)
def test_temperature_limit_values(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, temperature in expected.items():
        assert_quantity(values[quantity], temperature, "temperature")


def test_temperature_range_alias(capsys):
    values = normalized_values("Temperature Range", "-40℃~+85℃", capsys)

    assert_quantity(values["temperature min"], -40, "temperature")
    assert_quantity(values["temperature max"], 85, "temperature")


def test_operating_temperature_list(capsys):
    values = normalized_values("Operating Temperature", "-40℃~+85℃, 0℃~+70℃", capsys)

    assert_quantity(values["temperature min 1"], -40, "temperature")
    assert_quantity(values["temperature max 1"], 85, "temperature")
    assert_quantity(values["temperature min 2"], 0, "temperature")
    assert_quantity(values["temperature max 2"], 70, "temperature")


def test_operating_temperature_conditional_list(capsys):
    values = normalized_values(
        "Operating Temperature",
        "-40℃~+85℃@(TA), -40℃~+125℃@(TJ)",
        capsys,
    )

    assert_quantity(values["temperature min 1"], -40, "temperature")
    assert_quantity(values["temperature max 1"], 85, "temperature")
    assert_quantity(values["temperature min 2"], -40, "temperature")
    assert_quantity(values["temperature max 2"], 125, "temperature")


def test_operating_temperature_scalar_list(capsys):
    values = normalized_values("Operating Temperature", "65℃, 60℃, 50℃, 55℃", capsys)

    assert_quantity(values["temperature 1"], 65, "temperature")
    assert_quantity(values["temperature 2"], 60, "temperature")
    assert_quantity(values["temperature 3"], 50, "temperature")
    assert_quantity(values["temperature 4"], 55, "temperature")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Temperature", "0℃~+85℃", {"temperature min": 0, "temperature max": 85}),
        ("Temperature Hysteresis Configuration", "2℃, 10℃", {"temperature 1": 2, "temperature 2": 10}),
        ("Programmable Action Temperature Range", "-55℃~+125℃", {"temperature min": -55, "temperature max": 125}),
        ("Accuracy of Operating Temperature", "±0.5℃", {"temperature min": -0.5, "temperature max": 0.5}),
        ("Reset Temperature", "86℃", {"temperature": 86}),
        ("Temperature Resistance", "-20℃~+80℃", {"temperature min": -20, "temperature max": 80}),
        ("Temperature Resistance", "120℃", {"temperature": 120}),
    ],
)
def test_additional_temperature_aliases(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, temperature in expected.items():
        assert_quantity(values[quantity], temperature, "temperature")


def test_misc_numeric_aliases(capsys):
    values = normalized_values("Air Volume", "1.01CFM", capsys)
    assert_quantity(values["air flow"], 1.01 * 0.00047194745, "air_flow")

    values = normalized_values("Sensitivity Temperature Bleaching", "±3%/℃", capsys)
    assert_quantity(values["drift min"], -3.0, "percentage_per_temperature")
    assert_quantity(values["drift max"], 3.0, "percentage_per_temperature")

    values = normalized_values("Aperture Jitter", "25ns", capsys)
    assert_quantity(values["time"], 25e-9, "time")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Working Temperature", "-20℃~+70℃", {
            "temperature min": -20,
            "temperature max": 70,
        }),
        ("Working Temperature", "-20℃-+65℃", {
            "temperature min": -20,
            "temperature max": 65,
        }),
        ("Working Temperature", "-30℃ to +85℃", {
            "temperature min": -30,
            "temperature max": 85,
        }),
        ("Working Temperature", "~15℃~+50℃", {
            "temperature min": -15,
            "temperature max": 50,
        }),
        ("Storage Temperature", "~20℃~+85℃", {
            "temperature min": -20,
            "temperature max": 85,
        }),
    ],
)
def test_additional_temperature_range_attributes(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, temperature in expected.items():
        assert_quantity(values[quantity], temperature, "temperature")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Soldering Temperature (Max)", "260℃", {"temperature": (260, "temperature")}),
        ("Soldering Temperature (Max)", "260℃@3S", {"temperature": (260, "temperature"), "time": (3, "time")}),
        ("Soldering Temperature (Max)", "260℃@3~5S", {
            "temperature": (260, "temperature"),
            "time min": (3, "time"),
            "time max": (5, "time"),
        }),
        ("Soldering Temperature (Max)", "-", {"temperature": ("NaN", "temperature")}),
        ("Welding Temperature (Max)", "250℃@5S", {"temperature": (250, "temperature"), "time": (5, "time")}),
        ("Welding Temperature (Max)", "265℃@2~3S", {
            "temperature": (265, "temperature"),
            "time min": (2, "time"),
            "time max": (3, "time"),
        }),
        ("Welding Temperature (Max)", "260℃@", {"temperature": (260, "temperature")}),
    ],
)
def test_soldering_temperature_max_attribute(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, expected_value in expected.items():
        value, unit = expected_value
        assert_quantity(values[quantity], value, unit)


def test_detection_temperature_range(capsys):
    values = normalized_values("Detection Temperature Range", "-55℃~+125℃", capsys)

    assert_quantity(values["temperature min"], -55, "temperature")
    assert_quantity(values["temperature max"], 125, "temperature")


def test_operating_junction_temperature_range(capsys):
    values = normalized_values("Operating Junction Temperature Range", "-55℃~+150℃@(Tj)", capsys)

    assert_quantity(values["temperature min"], -55, "temperature")
    assert_quantity(values["temperature max"], 150, "temperature")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("130°", {"angle 1": 130.0}),
        ("±45°", {"angle 1": 45.0}),
        ("150°, 120°", {"angle 1": 150.0, "angle 2": 120.0}),
        ("±45°@Horizontal, ±45°@Vertical", {"angle 1": 45.0, "angle 2": 45.0}),
        ("100°;40°", {"angle 1": 100.0, "angle 2": 40.0}),
        ("0.05deg", {"angle 1": 0.05}),
        ("-", {"angle 1": "NaN"}),
    ],
)
@pytest.mark.parametrize("key", ["Viewing Angle", "Differential Phase", "Reception Angle", "Operating Angle in Each Direction", "Angle"])
def test_angle_values(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, angle in expected.items():
        assert_quantity(values[quantity], angle, "angle")


@pytest.mark.parametrize("value", ["Bent tip", "Straight Header"])
def test_angle_identifiers(value, capsys):
    values = normalized_values("Angle", value, capsys)

    assert values["angle"] == [value, "identifier"]


@pytest.mark.parametrize("key", ["Phase Balance", "Phase Difference"])
def test_phase_angle_aliases(key, capsys):
    values = normalized_values(key, "180°@±10°, 180°@±15°", capsys)

    assert_quantity(values["angle 1"], 180.0, "angle")
    assert_quantity(values["angle 2"], 180.0, "angle")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0.7deg", {"phase": (0.7, "angle")}),
        ("0.5deg, 0.7deg", {"phase 1": (0.5, "angle"), "phase 2": (0.7, "angle")}),
        ("5dB", {"phase": (5.0, "decibel")}),
    ],
)
def test_phase_unbalance(value, expected, capsys):
    values = normalized_values("Phase Unbalance", value, capsys)

    for quantity, expected_value in expected.items():
        value, unit = expected_value
        assert_quantity(values[quantity], value, unit)


def test_rotation_angle(capsys):
    values = normalized_values("Rotation Angle", "0°~360°", capsys)

    assert_quantity(values["angle 1 min"], 0.0, "angle")
    assert_quantity(values["angle 1 max"], 360.0, "angle")


def test_half_angle_alias(capsys):
    values = normalized_values("Half Angle", "±60°", capsys)

    assert_quantity(values["angle 1 min"], -60.0, "angle")
    assert_quantity(values["angle 1 max"], 60.0, "angle")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1.6N", 1.6),
        ("70gf", 70 * 0.00980665),
    ],
)
def test_press_force(value, expected, capsys):
    values = normalized_values("Press Force", value, capsys)

    assert_quantity(values["force 1"], expected, "force")


def test_operating_force(capsys):
    values = normalized_values("Operating Force", "0N~15N", capsys)

    assert_quantity(values["force 1 min"], 0.0, "force")
    assert_quantity(values["force 1 max"], 15.0, "force")

    values = normalized_values("Operating Force", "260gf@±50gf", capsys)
    assert_quantity(values["force 1"], 260 * 0.00980665, "force")

    values = normalized_values("Operation Force", "50gf@±10gf", capsys)
    assert_quantity(values["force 1"], 50 * 0.00980665, "force")


def test_under_pressure(capsys):
    values = normalized_values("Under Pressure", "0.3N.Min", capsys)

    assert_quantity(values["force 1"], 0.3, "force")

    values = normalized_values("Under Pressure", "Twist 45°/1000mm, arch 5mm/1000mm", capsys)

    assert values["under pressure 1"] == ["Twist 45°/1000mm", "identifier"]
    assert values["under pressure 2"] == ["arch 5mm/1000mm", "identifier"]


def test_acceleration_measurement_range(capsys):
    values = normalized_values("Acceleration Measurement Range (Max)", "±16g", capsys)

    assert_quantity(values["acceleration min"], -16, "acceleration")
    assert_quantity(values["acceleration max"], 16, "acceleration")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("83%", {"percentage": 83.0}),
        ("82%~90%", {"percentage min": 82.0, "percentage max": 90.0}),
        ("89%, 92%", {"percentage 1": 89.0, "percentage 2": 92.0}),
        ("88.5%, 85.5%, 88.2%, 85.2%", {
            "percentage 1": 88.5,
            "percentage 2": 85.5,
            "percentage 3": 88.2,
            "percentage 4": 85.2,
        }),
    ],
)
def test_conversion_efficiency_values(value, expected, capsys):
    values = normalized_values("Conversion Efficiency", value, capsys)

    for quantity, percentage in expected.items():
        assert_quantity(values[quantity], percentage, "percentage")

@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Precision", "±20%", {"percentage min": -20.0, "percentage max": 20.0}),
        ("Precision", "-20%;+55%", {"percentage min": -20.0, "percentage max": 55.0}),
        ("Precision", "-40%~+20%", {"percentage min": -40.0, "percentage max": 20.0}),
        ("Linearity", "1%, 0.3%", {"percentage 1": 1.0, "percentage 2": 0.3}),
        ("Linearity", "-0.7%", {"percentage": -0.7}),
        ("Error", "0.25%", {"percentage": 0.25}),
        ("Degree of Linearity", "±0.012%", {"percentage min": -0.012, "percentage max": 0.012}),
        ("Degree of Linearity", "-", {"percentage": "NaN"}),
        ("Total Harmonic Distortion + Noise (Thd+N)", "0.15%, 0.11%", {
            "percentage 1": 0.15,
            "percentage 2": 0.11,
        }),
        ("Total Harmonic Distortion(Thd)", "10%", {"percentage": 10.0}),
        ("Total Harmonic Distortion", "10%", {"percentage": 10.0}),
        ("Total Harmonic Distortion", "-", {"percentage": "NaN"}),
        ("Differential Gain", "0.01%", {"percentage": 0.01}),
        ("Capacitance Tolerance", "±20%", {"percentage min": -20.0, "percentage max": 20.0}),
        ("Capacitance Tolerance", "-20%~+50%", {"percentage min": -20.0, "percentage max": 50.0}),
        ("Constant Current Accuracy", "3‰", {"percentage": 0.3}),
        ("Constant Current Accuracy", "5%, 15%", {"percentage 1": 5.0, "percentage 2": 15.0}),
        ("Output Voltage Accuracy", "±1.5%", {"percentage min": -1.5, "percentage max": 1.5}),
        ("Output Voltage Accuracy", "±5‰", {"percentage min": -0.5, "percentage max": 0.5}),
        ("Duty Cycle", "1/4,1/3", {"percentage 1": 25.0, "percentage 2": 100 / 3}),
        ("Duty Cycle (Max)", "85%, 90%", {"percentage 1": 85.0, "percentage 2": 90.0}),
        ("Current Transfer Ratio (Ctr) Maximum/Saturation Value", "400%", {"percentage": 400.0}),
        ("Current Transfer Ratio (Ctr) Minimum", "0.25%", {"percentage": 0.25}),
        ("B Constant Tolerance", "±1%", {"percentage min": -1.0, "percentage max": 1.0}),
        ("Resistance Tolerance", "±5%, ±0.5%", {
            "percentage 1 min": -5.0,
            "percentage 1 max": 5.0,
            "percentage 2 min": -0.5,
            "percentage 2 max": 0.5,
        }),
    ],
)
def test_flexible_percentage_values(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, percentage in expected.items():
        assert_quantity(values[quantity], percentage, "percentage")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0.1%, 0.5%", {
            "tolerance 1": (0.1, "percentage"),
            "tolerance 2": (0.5, "percentage"),
        }),
        ("-0.6%;+0.4%", {
            "tolerance min": (-0.6, "percentage"),
            "tolerance max": (0.4, "percentage"),
        }),
        ("±1℃", {
            "tolerance min": (-1.0, "temperature"),
            "tolerance max": (1.0, "temperature"),
        }),
        ("±1.5", {
            "tolerance min": (-1.5, "ratio"),
            "tolerance max": (1.5, "ratio"),
        }),
        ("-", {"tolerance": ("NaN", "ratio")}),
    ],
)
def test_mixed_tolerance_values(value, expected, capsys):
    values = normalized_values("Tolerance", value, capsys)

    for quantity, (amount, unit) in expected.items():
        assert_quantity(values[quantity], amount, unit)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("6%", {"percentage": [6.0, "percentage"]}),
        ("16%", {"percentage": [16.0, "percentage"]}),
        ("1mW/℃", {"power drift": [0.001, "power_temperature_drift"]}),
        ("0.212mW/℃", {"power drift": [0.000212, "power_temperature_drift"]}),
        ("7mW/℃, 8.5mW/℃", {
            "power drift 1": [0.007, "power_temperature_drift"],
            "power drift 2": [0.0085, "power_temperature_drift"],
        }),
    ],
)
def test_dissipation_factor_values(value, expected, capsys):
    values = normalized_values("Dissipation Factor", value, capsys)

    for quantity, expected_value in expected.items():
        assert_quantity(values[quantity], expected_value[0], expected_value[1])


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("47.6%", {"percentage 1": 47.6}),
        ("87%, 83%", {"percentage 1": 87.0, "percentage 2": 83.0}),
        ("0.89", {"percentage 1": 89.0}),
        ("-", {"percentage 1": "NaN"}),
    ],
)
def test_efficiency_values(value, expected, capsys):
    values = normalized_values("Efficiency", value, capsys)

    for quantity, percentage in expected.items():
        assert_quantity(values[quantity], percentage, "percentage")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("32KB", 32 * 1024),
        ("1MB", 1024 * 1024),
        ("384Byte", 384),
        ("1.75KB", 1.75 * 1024),
        ("-", "NaN"),
    ],
)
def test_program_storage_size(value, expected, capsys):
    values = normalized_values("Program Storage Size", value, capsys)

    assert_quantity(values["data size"], expected, "data_size")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("288KB", {"data size": 288 * 1024}),
        ("8.5MB", {"data size": 8.5 * 1024 * 1024}),
        ("64KB, 32KB, 16KB", {
            "data size 1": 64 * 1024,
            "data size 2": 32 * 1024,
            "data size 3": 16 * 1024,
        }),
        ("-", {"data size": "NaN"}),
    ],
)
def test_ram_size(value, expected, capsys):
    values = normalized_values("Ram Size", value, capsys)

    for quantity, data_size in expected.items():
        assert_quantity(values[quantity], data_size, "data_size")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("423936bit", 423936 / 8),
        ("2396160bit", 2396160 / 8),
        ("13455360bit", 13455360 / 8),
    ],
)
def test_embedded_block_ram(value, expected, capsys):
    values = normalized_values("Embedded Block Ram", value, capsys)

    assert_quantity(values["data size"], expected, "data_size")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Eeprom", "2KB", 2 * 1024),
        ("Flash Size", "12KB", 12 * 1024),
        ("Flash Size", "2MB", 2 * 1024 * 1024),
        ("Flash Size", "-", "NaN"),
        ("Memory Size of Flash", "256Mbit", 256 * 1024 * 1024 / 8),
        ("Memory Size of Ram", "64Mbit", 64 * 1024 * 1024 / 8),
        ("Density", "32GB", 32 * 1024 * 1024 * 1024),
        ("Otp Memory Size", "256Byte@-", 256),
    ],
)
def test_additional_memory_size_aliases(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    assert_quantity(values["data size"], expected, "data_size")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("64Kbit", {"data size": 64 * 1024 / 8}),
        ("8GB", {"data size": 8 * 1024 * 1024 * 1024}),
        ("1536Byte, 2048Byte", {"data size 1": 1536, "data size 2": 2048}),
        ("4096x18", {"data size": 4096 * 18 / 8}),
        ("4Kx9", {"data size": 4 * 1024 * 9 / 8}),
    ],
)
def test_memory_size(value, expected, capsys):
    values = normalized_values("Memory Size", value, capsys)

    for quantity, data_size in expected.items():
        assert_quantity(values[quantity], data_size, "data_size")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("8KB", 8 * 1024),
        ("384KB", 384 * 1024),
    ],
)
def test_memory_space(value, expected, capsys):
    values = normalized_values("Memory Space", value, capsys)

    assert_quantity(values["data size"], expected, "data_size")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Cache Size", "0.094KB", 0.094 * 1024),
        ("Cache Size", "1536Byte", 1536),
        ("Cache Size", "-", "NaN"),
        ("Fifo'S", "64Byte", 64),
    ],
)
def test_additional_data_size_aliases(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    assert_quantity(values["data size"], expected, "data_size")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("24V/us", {"slew rate": 24e6}),
        ("15kV/us", {"slew rate": 15e9}),
        ("520V/ms", {"slew rate": 520e3}),
        ("1.4V/ns", {"slew rate": 1.4e9}),
        ("0.0015mV/us", {"slew rate": 1.5}),
        ("1.8V/us, 1.4V/us, 1.6V/us", {
            "slew rate 1": 1.8e6,
            "slew rate 2": 1.4e6,
            "slew rate 3": 1.6e6,
        }),
        ("220/390V/us", {"slew rate 1": 220e6, "slew rate 2": 390e6}),
        ("-", {"slew rate": "NaN"}),
    ],
)
@pytest.mark.parametrize("key", ["Slew Rate", "Slew Rate(Sr)"])
def test_slew_rate(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, slew_rate in expected.items():
        assert_quantity(values[quantity], slew_rate, "slew_rate")

def test_droop_rate(capsys):
    values = normalized_values("Droop Rate", "2uV/us", capsys)

    assert_quantity(values["droop rate"], 2.0, "slew_rate")

@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("15kV/us", 15e9),
        ("0.5V/ns", 0.5e9),
    ],
)
def test_cmti(value, expected, capsys):
    values = normalized_values("Cmti(K V/Us)", value, capsys)

    assert_quantity(values["cmti"], expected, "slew_rate")


def test_static_dv_dt(capsys):
    values = normalized_values("Static Dv/Dt", "7kV/us", capsys)

    assert_quantity(values["dv/dt"], 7e9, "slew_rate")

def test_common_mode_transient_immunity_alias(capsys):
    values = normalized_values("Common Mode Transient Immunity (Cmti)", "20kV/us", capsys)

    assert_quantity(values["cmti"], 20e9, "slew_rate")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("3000K", {"temperature 1": 3000.0}),
        ("1800K~6500K", {"temperature 1 min": 1800.0, "temperature 1 max": 6500.0}),
        (
            "5300K~5750K, 5750K~6350K, 6350K~7050K",
            {
                "temperature 1 min": 5300.0,
                "temperature 1 max": 5750.0,
                "temperature 2 min": 5750.0,
                "temperature 2 max": 6350.0,
                "temperature 3 min": 6350.0,
                "temperature 3 max": 7050.0,
            },
        ),
        ("-", {"temperature 1": "NaN"}),
    ],
)
def test_color_temperature(value, expected, capsys):
    values = normalized_values("Color Temperature", value, capsys)

    for quantity, temperature in expected.items():
        assert_quantity(values[quantity], temperature, "kelvin")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2.5", {"area 1": 2.5}),
        ("0.5~4", {"area 1 min": 0.5, "area 1 max": 4.0}),
        ("0.5~4, 0.75~6", {
            "area 1 min": 0.5,
            "area 1 max": 4.0,
            "area 2 min": 0.75,
            "area 2 max": 6.0,
        }),
        ("5, 6", {"area 1": 5.0, "area 2": 6.0}),
        ("-", {"area 1": "NaN"}),
        ("0.3~0.4", {"area 1 min": 0.3, "area 1 max": 0.4}),
    ],
)
@pytest.mark.parametrize("key", ["Wire Gauge - MM2", "Wire Gauge - Mm", "Wire Gauge - Sqmm", "Wire Gauge - Sqmm (Per)", "Wire Gauge - MM2 (Not Stranded Wire)"])
def test_wire_gauge_mm2(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, area in expected.items():
        assert_quantity(values[quantity], area, "area_mm2")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("22", {"awg 1": 22.0}),
        ("17~20", {"awg 1 min": 17.0, "awg 1 max": 20.0}),
        ("10~18, 12~20", {
            "awg 1 min": 10.0,
            "awg 1 max": 18.0,
            "awg 2 min": 12.0,
            "awg 2 max": 20.0,
        }),
        ("10, 12", {"awg 1": 10.0, "awg 2": 12.0}),
        ("16/18/20AWG", {"awg 1": 16.0, "awg 2": 18.0, "awg 3": 20.0}),
        ("1/0", {"awg 1": 0}),
        ("2/0~10", {"awg 1 min": -1, "awg 1 max": 10.0}),
        ("3/0~500", {"awg 1 min": -2, "awg 1 max": 500.0}),
        ("22 AWG", {"awg 1": 22.0}),
        ("26~28", {"awg 1 min": 26.0, "awg 1 max": 28.0}),
        ("-", {"awg 1": "NaN"}),
    ],
)
@pytest.mark.parametrize("key", ["Wire Gauge - Awg", "Wire Gauge", "Recommended Wire Gauge", "Wire Gauge - Awg (Per)", "Wire Gauge - Awg (Not Stranded Wire)"])
def test_wire_gauge_awg(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, awg in expected.items():
        assert_quantity(values[quantity], awg, "awg")


def test_wire_rod_awg(capsys):
    values = normalized_values("Wire Rod", "UL1015 16AWG", capsys)

    assert_quantity(values["awg 1"], 16, "awg")


def test_core_wire_gauge(capsys):
    values = normalized_values("Core Wire Gauge", "Diameter 2mm", capsys)
    assert_quantity(values["diameter"], 0.002, "length")

    values = normalized_values("Core Wire Gauge", "30AWG", capsys)
    assert_quantity(values["awg 1"], 30, "awg")

    values = normalized_values("Core Wire Gauge", "RG0.81 white cable, OD: 0.81mm", capsys)
    assert_quantity(values["diameter"], 0.00081, "length")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2mT", {"field 1": 0.002}),
        ("9Gs", {"field 1": 0.0009}),
        ("±3.8mT", {"field 1 min": -0.0038, "field 1 max": 0.0038}),
        ("2mT~15mT", {"field 1 min": 0.002, "field 1 max": 0.015}),
        ("2.5mT, -2.5mT", {"field 1": 0.0025, "field 2": -0.0025}),
        ("6Gs~6mT, -6mT~-6Gs", {
            "field 1 min": 0.0006,
            "field 1 max": 0.006,
            "field 2 min": -0.006,
            "field 2 max": -0.0006,
        }),
        ("-", {"field 1": "NaN"}),
    ],
)
@pytest.mark.parametrize("key", ["Operation Points", "Release Points"])
def test_operation_points(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, field in expected.items():
        assert_quantity(values[quantity], field, "magnetic_flux_density")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("565nm, 627nm", {"wavelength 1": 565e-9, "wavelength 2": 627e-9}),
        ("R:625nm~645nm, G:524nm~533nm, B:462nm~478nm", {
            "wavelength R min": 625e-9,
            "wavelength R max": 645e-9,
            "wavelength G min": 524e-9,
            "wavelength G max": 533e-9,
            "wavelength B min": 462e-9,
            "wavelength B max": 478e-9,
        }),
        ("390nm~400nm@UVA, 270nm~285nm@UVC", {
            "wavelength 1 min": 390e-9,
            "wavelength 1 max": 400e-9,
            "wavelength 2 min": 270e-9,
            "wavelength 2 max": 285e-9,
        }),
        ("150mcd, 400mcd", {"intensity 1": 0.15, "intensity 2": 0.4}),
    ],
)
def test_peak_wavelength_lists(value, expected, capsys):
    values = normalized_values("Peak Wavelength", value, capsys)

    for quantity, expected_value in expected.items():
        unit = "luminous_intensity" if quantity.startswith("intensity") else "length"
        assert_quantity(values[quantity], expected_value, unit)


@pytest.mark.parametrize("key", ["Spectral Peak", "Wavelength - Peak"])
def test_peak_wavelength_aliases(key, capsys):
    values = normalized_values(key, "540nm", capsys)

    assert_quantity(values["wavelength"], 540e-9, "length")


def test_wavelength_alias_labels(capsys):
    values = normalized_values("Wavelength", "R:625nm, G:525nm, B:470nm", capsys)

    assert_quantity(values["wavelength R"], 625e-9, "length")
    assert_quantity(values["wavelength G"], 525e-9, "length")
    assert_quantity(values["wavelength B"], 470e-9, "length")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1080", 1080.0),
        ("0.0004", 0.0004),
        ("-", "NaN"),
    ],
)
def test_melting_i2t(value, expected, capsys):
    values = normalized_values("Melting I2t", value, capsys)

    assert_quantity(values["melting i2t"], expected, "melting_i2t")

def test_melt_i2t_alias(capsys):
    values = normalized_values("Melt I2t", "1100", capsys)

    assert_quantity(values["melting i2t"], 1100.0, "melting_i2t")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1.5kW", 1500.0),
        ("150mW", 0.15),
        ("60W@8/20us", 60.0),
        ("-", "NaN"),
    ],
)
def test_peak_pulse_power_dissipation_at_pulse(value, expected, capsys):
    values = normalized_values("Peak Pulse Power Dissipation (Ppp)@10/1000us", value, capsys)

    assert_quantity(values["power"], expected, "power")


def test_peak_pulse_power_dissipation_pulse_list(capsys):
    values = normalized_values(
        "Peak Pulse Power Dissipation (Ppp)",
        "60W@8/20us, 3kW@8/20us",
        capsys,
    )

    assert_quantity(values["power 1"], 60.0, "power")
    assert_quantity(values["pulse rise time 1"], 8e-6, "time")
    assert_quantity(values["pulse duration 1"], 20e-6, "time")
    assert_quantity(values["power 2"], 3000.0, "power")
    assert_quantity(values["pulse rise time 2"], 8e-6, "time")
    assert_quantity(values["pulse duration 2"], 20e-6, "time")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("500mW", 0.5),
        ("21.6w", 21.6),
    ],
)
def test_rated_power(value, expected, capsys):
    values = normalized_values("Rated Power", value, capsys)

    assert_quantity(values["power"], expected, "power")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("400mW", 0.4),
        ("30.4W", 30.4),
        ("-", "NaN"),
    ],
)
def test_rated_wattage(value, expected, capsys):
    values = normalized_values("Rated Wattage", value, capsys)

    assert_quantity(values["power"], expected, "power")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("700mW", {"power": 0.7}),
        ("1.6W, 1.8W", {"power 1": 1.6, "power 2": 1.8}),
    ],
)
def test_coil_rated_power(value, expected, capsys):
    values = normalized_values("Coil Rated Power", value, capsys)

    for quantity, power in expected.items():
        assert_quantity(values[quantity], power, "power")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("470mW, 294mW", {"power 1": 0.47, "power 2": 0.294}),
        ("500mW@UVA, 240mW@UVC", {"power 1": 0.5, "power 2": 0.24}),
        ("330mW, 400mW, 580mW", {"power 1": 0.33, "power 2": 0.4, "power 3": 0.58}),
    ],
)
def test_power_dissipation_pd_list(value, expected, capsys):
    values = normalized_values("Power Dissipation (Pd)", value, capsys)

    for quantity, power in expected.items():
        assert_quantity(values[quantity], power, "power")


def test_pd_power_dissipation_alias(capsys):
    values = normalized_values("Pd - Power Dissipation(Pd)", "200mW", capsys)

    assert_quantity(values["power"], 0.2, "power")


def test_total_power_dissipation_alias(capsys):
    values = normalized_values("Total Power Dissipation(Pd)", "150mW", capsys)

    assert_quantity(values["power"], 0.15, "power")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("150mW", 0.15),
        ("1.8W", 1.8),
        ("-", "NaN"),
    ],
)
def test_total_device_dissipation_alias(value, expected, capsys):
    values = normalized_values("Total Device Dissipation (Pd)", value, capsys)

    assert_quantity(values["power"], expected, "power")


def test_average_gate_power_dissipation_alias(capsys):
    values = normalized_values("Average Gate Power Dissipation (Pg(Av))", "200mW", capsys)

    assert_quantity(values["power"], 0.2, "power")

@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Power Consumption", "30mW", 0.03),
        ("Dissipation Power", "1.48W", 1.48),
        ("Power Capacity", "50W", 50.0),
        ("Corresponding Power", "100W-600W", {"power 1 min": 100.0, "power 1 max": 600.0}),
    ],
)
def test_additional_power_aliases(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    if isinstance(expected, dict):
        for quantity, power in expected.items():
            assert_quantity(values[quantity], power, "power")
    else:
        assert_quantity(values["power"], expected, "power")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("400W", {"power": 400.0}),
        ("1.8kW", {"power": 1800.0}),
        ("200W@(8/20us)", {"power": 200.0}),
        ("54W;63W", {"power 1": 54.0, "power 2": 63.0}),
    ],
)
def test_peak_pulse_power_8_20us(value, expected, capsys):
    values = normalized_values("Peak Pulse Power(Ppp)@8/20us", value, capsys)

    for quantity, power in expected.items():
        assert_quantity(values[quantity], power, "power")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("35mcd", {"intensity 1": 0.035}),
        ("2.25cd", {"intensity 1": 2.25}),
        ("68mcd~102mcd", {"intensity 1 min": 0.068, "intensity 1 max": 0.102}),
        ("800mcd, 1.3cd, 350mcd", {"intensity 1": 0.8, "intensity 2": 1.3, "intensity 3": 0.35}),
        ("330mcd;840mcd;160mcd", {"intensity 1": 0.33, "intensity 2": 0.84, "intensity 3": 0.16}),
        ("R:170mcd~360mcd, G:650mcd~1000mcd, B:220mcd~350mcd", {
            "intensity R min": 0.17,
            "intensity R max": 0.36,
            "intensity G min": 0.65,
            "intensity G max": 1.0,
            "intensity B min": 0.22,
            "intensity B max": 0.35,
        }),
        ("R:400mcd G:560mcd B:86mcd", {
            "intensity R": 0.4,
            "intensity G": 0.56,
            "intensity B": 0.086,
        }),
        ("-", {"intensity 1": "NaN"}),
    ],
)
@pytest.mark.parametrize("key", ["Luminous Intensity", "Light Intensity"])
def test_luminous_intensity(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, intensity in expected.items():
        assert_quantity(values[quantity], intensity, "luminous_intensity")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Lumens", "383lm", {"flux": 383}),
        ("Lumens", "1380lm, 2070lm", {"flux 1": 1380, "flux 2": 2070}),
        ("Luminous Flux (25°C)", "938lm", {"flux": 938}),
        ("Luminous Flux (@25°C)", "1lm~5lm", {"flux min": 1, "flux max": 5}),
        ("Luminous Flux (@25°C)", "34.5lm", {"flux": 34.5}),
        ("Luminous Flux (@25°C)", "-", {"flux": "NaN"}),
    ],
)
def test_luminous_flux(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, flux in expected.items():
        assert_quantity(values[quantity], flux, "luminous_flux")


def test_cri_color_rendering_index(capsys):
    values = normalized_values("Cri Color Rendering Index", "90", capsys)

    assert_quantity(values["cri"], 90, "ratio")


def test_luminance_values(capsys):
    values = normalized_values("Luminance", "180cd/m2", capsys)

    assert_quantity(values["luminance"], 180.0, "luminance")


def test_photoresistor_resistance_values(capsys):
    values = normalized_values("Illuminated Resistance @ 10lux", "5kΩ~10kΩ", capsys)
    assert_quantity(values["resistance min"], 5000, "resistance")
    assert_quantity(values["resistance max"], 10000, "resistance")

    values = normalized_values("Cell Resistance @ Illuminance", "5kΩ~10kΩ", capsys)
    assert_quantity(values["resistance min"], 5000, "resistance")
    assert_quantity(values["resistance max"], 10000, "resistance")

    values = normalized_values("Dark Resistance", "200kΩ", capsys)
    assert_quantity(values["resistance"], 200000, "resistance")


def test_photoresistor_gamma_value(capsys):
    values = normalized_values("Γ Value", "0.6", capsys)

    assert_quantity(values["gamma"], 0.6, "ratio")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("±7Kpa", {"pressure min": -7000.0, "pressure max": 7000.0}),
        ("30Kpa~1.25bar", {"pressure min": 30000.0, "pressure max": 125000.0}),
        ("-1Kpa~1Kpa, -10Kpa~10Kpa", {
            "pressure 1 min": -1000.0,
            "pressure 1 max": 1000.0,
            "pressure 2 min": -10000.0,
            "pressure 2 max": 10000.0,
        }),
    ],
)
def test_pressure_range(value, expected, capsys):
    values = normalized_values("Pressure Range", value, capsys)

    for quantity, pressure in expected.items():
        assert_quantity(values[quantity], pressure, "pressure")


@pytest.mark.parametrize("key", ["Absolute Accuracy", "Relative Accuracy"])
def test_pressure_accuracy(key, capsys):
    values = normalized_values(key, "0.4Kpa", capsys)

    assert_quantity(values["pressure"], 400.0, "pressure")

    values = normalized_values(key, "1.5mbar", capsys)

    assert_quantity(values["pressure"], 150.0, "pressure")


def test_pressure_temperature_drift(capsys):
    values = normalized_values("Temperature Coefficient of Offset(TCO)", "0.6pa/K", capsys)

    assert_quantity(values["pressure drift"], 0.6, "pressure_temperature_drift")


def test_ripple_noise_voltage(capsys):
    values = normalized_values("Ripple Noise", "150mVp-p, 70mVp-p", capsys)

    assert_quantity(values["noise 1"], 0.15, "voltage")
    assert_quantity(values["noise 2"], 0.07, "voltage")


@pytest.mark.parametrize(
    ("value", "quantity", "expected", "unit"),
    [
        ("100mV", "ripple", 0.1, "voltage"),
        ("0.5dB, 0.4dB", "ripple 1", 0.5, "decibel"),
    ],
)
def test_ripple_values(value, quantity, expected, unit, capsys):
    values = normalized_values("Ripple", value, capsys)

    assert_quantity(values[quantity], expected, unit)


def test_photoperceptivity(capsys):
    values = normalized_values("Photoperceptivity", "120klx", capsys)

    assert_quantity(values["illuminance"], 120000.0, "illuminance")


@pytest.mark.parametrize(
    ("value", "quantity", "expected", "unit"),
    [
        ("2.5m", "accuracy", 2.5, "length"),
        ("Grade 2.5", "accuracy grade", 2.5, "ratio"),
        ("±0.25dB", "accuracy min", -0.25, "decibel"),
    ],
)
def test_accuracy_values(value, quantity, expected, unit, capsys):
    values = normalized_values("Accuracy", value, capsys)

    assert_quantity(values[quantity], expected, unit)


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Humidity", "0%RH~100%RH", {"percentage min": 0.0, "percentage max": 100.0}),
        ("Humidity Tolerance", "±1.8%RH", {"percentage min": -1.8, "percentage max": 1.8}),
    ],
)
def test_humidity_values(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, percentage in expected.items():
        assert_quantity(values[quantity], percentage, "percentage")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Measurement Range", "0ppm~40000ppm", {"ppm min": 0.0, "ppm max": 40000.0}),
        ("Gas Range", "100ppm~10000ppm", {"ppm min": 100.0, "ppm max": 10000.0}),
    ],
)
def test_ppm_range_aliases(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, ppm in expected.items():
        assert_quantity(values[quantity], ppm, "ppm")


def test_temperature_tolerance(capsys):
    values = normalized_values("Temperature Tolerance", "±0.2℃", capsys)

    assert_quantity(values["temperature min"], -0.2, "temperature")
    assert_quantity(values["temperature max"], 0.2, "temperature")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("20mW/sr@IF=100mA", {"intensity 1": 0.02}),
        ("8mW/sr~16mW/sr", {"intensity 1 min": 0.008, "intensity 1 max": 0.016}),
        ("200mW~260mW", {"intensity 1 min": 0.2, "intensity 1 max": 0.26}),
        ("420mW/sr, 620mW/sr", {"intensity 1": 0.42, "intensity 2": 0.62}),
        (
            "170mW/sr@IF=350mA, 350mW/sr@IF=1000mA",
            {"intensity 1": 0.17, "intensity 2": 0.35},
        ),
        ("-", {"intensity 1": "NaN"}),
    ],
)
def test_radiant_intensity(value, expected, capsys):
    values = normalized_values("Radiant Intensity", value, capsys)

    for quantity, intensity in expected.items():
        assert_quantity(values[quantity], intensity, "radiant_intensity")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("15nV/√Hz@10kHz", {"density": 15e-9}),
        ("600pV/√Hz@1kHz", {"density": 600e-12}),
        ("1.4uV/√Hz@30kHz", {"density": 1.4e-6}),
        ("11nV/√Hz@0.1kHz,10kHz", {"density": 11e-9}),
        ("10nV/√Hz, 20nV/√Hz@10kHz", {"density 1": 10e-9, "density 2": 20e-9}),
        ("-", {"density": "NaN"}),
    ],
)
@pytest.mark.parametrize("key", ["Input Voltage Noise Density", "Noise Density(E N)"])
def test_input_voltage_noise_density(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, density in expected.items():
        assert_quantity(values[quantity], density, "voltage_noise_density")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("5uV/℃", {"drift 1": 5e-6}),
        ("2000nV/℃", {"drift 1": 2000e-9}),
        ("1.2mV/℃", {"drift 1": 0.0012}),
        ("2.4uV/℃, 8.8uV/℃", {"drift 1": 2.4e-6, "drift 2": 8.8e-6}),
        ("-", {"drift 1": "NaN"}),
        ("±15uV/°C", {"drift 1 min": -15e-6, "drift 1 max": 15e-6}),
    ],
)
def test_input_offset_voltage_drift(value, expected, capsys):
    values = normalized_values("Input Offset Voltage Drift(VOS TC)", value, capsys)

    for quantity, drift in expected.items():
        assert_quantity(values[quantity], drift, "voltage_temperature_drift")


def test_spaced_input_offset_voltage_drift(capsys):
    values = normalized_values("Input Offset Voltage Drift (VOS TC)", "1uV/°C", capsys)

    assert_quantity(values["drift 1"], 1e-6, "voltage_temperature_drift")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Input Offset Current Drift (IOS TC)", "10pA/℃", {"drift 1": 10e-12}),
        ("Input Offset Current Drift (IOS TC)", "0.01uA/℃", {"drift 1": 0.01e-6}),
        ("Input Offset Current Drift(IOS TC)", "47.4pA/℃", {"drift 1": 47.4e-12}),
        ("Input Offset Current Drift(IOS TC)", "10uA/℃", {"drift 1": 10e-6}),
    ],
)
def test_input_offset_current_drift(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, drift in expected.items():
        assert_quantity(values[quantity], drift, "current_temperature_drift")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("9.6uVp-p", {"noise 1 p-p": [9.6e-6, "voltage"]}),
        ("4.3uVrms", {"noise 1 rms": [4.3e-6, "voltage"]}),
        ("3.8ppmp-p", {"noise 1 p-p": [3.8, "ppm"]}),
        ("0.11ppmp-p, 0.275uVp-p", {
            "noise 1 p-p": [0.11, "ppm"],
            "noise 2 p-p": [0.275e-6, "voltage"],
        }),
        ("-", {"noise 1": ["NaN", "voltage"]}),
    ],
)
def test_low_frequency_noise(value, expected, capsys):
    values = normalized_values("Noise - 1/10hz to 10hz", value, capsys)

    for quantity, expected_value in expected.items():
        assert_quantity(values[quantity], expected_value[0], expected_value[1])


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("30uVrms", {"noise 1 rms": [30e-6, "voltage"]}),
        ("38uVpp", {"noise 1 p-p": [38e-6, "voltage"]}),
        ("0.002%Vout", {"noise 1": [0.002, "percentage"]}),
        ("17.8dB(A)", {"noise 1": [17.8, "decibel"]}),
        ("1.6uVrms, 1uVrms", {
            "noise 1 rms": [1.6e-6, "voltage"],
            "noise 2 rms": [1e-6, "voltage"],
        }),
        ("-", {"noise 1": ["NaN", "voltage"]}),
    ],
)
def test_noise_values(value, expected, capsys):
    values = normalized_values("Noise", value, capsys)

    for quantity, expected_value in expected.items():
        assert_quantity(values[quantity], expected_value[0], expected_value[1])


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("-38dB", {"sensitivity": [-38.0, "decibel"]}),
        ("-25dB@±3dB", {
            "sensitivity": [-25.0, "decibel"],
            "sensitivity tolerance": [3.0, "decibel"],
        }),
        ("-95.5dBm", {"sensitivity": [-95.5, "decibel_milliwatt"]}),
        ("100mV/A", {"sensitivity": [0.1, "voltage_per_current"]}),
        ("40V/A", {"sensitivity": [40.0, "voltage_per_current"]}),
        ("1500mV/mT", {"sensitivity": [1500.0, "voltage_per_magnetic_flux_density"]}),
        ("2.25mV/Gs, 3.8mV/Gs", {
            "sensitivity 1": [22.5, "voltage_per_magnetic_flux_density"],
            "sensitivity 2": [38.0, "voltage_per_magnetic_flux_density"],
        }),
        ("10mV/g", {"sensitivity": [0.01, "voltage_per_g"]}),
        ("0.5mA/A", {"sensitivity": [0.0005, "current_per_current"]}),
        ("-", {"sensitivity": ["NaN", "decibel"]}),
    ],
)
def test_sensitivity_values(value, expected, capsys):
    values = normalized_values("Sensitivity", value, capsys)

    for quantity, expected_value in expected.items():
        assert_quantity(values[quantity], expected_value[0], expected_value[1])


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("35ppm/℃", {"coefficient": [35.0, "temperature_coefficient"]}),
        ("190ppb/℃", {"coefficient": [0.19, "temperature_coefficient"]}),
        ("±50ppm/℃", {
            "coefficient min": [-50.0, "temperature_coefficient"],
            "coefficient max": [50.0, "temperature_coefficient"],
        }),
        ("0ppm/℃~+700ppm/℃", {
            "coefficient min": [0.0, "temperature_coefficient"],
            "coefficient max": [700.0, "temperature_coefficient"],
        }),
        ("C0G", {"coefficient": ["C0G", "temperature_coefficient_code"]}),
        ("C0G, NP0", {
            "coefficient 1": ["C0G", "temperature_coefficient_code"],
            "coefficient 2": ["NP0", "temperature_coefficient_code"],
        }),
        ("±75ppm/℃, ±50ppm/℃", {
            "coefficient 1 min": [-75.0, "temperature_coefficient"],
            "coefficient 1 max": [75.0, "temperature_coefficient"],
            "coefficient 2 min": [-50.0, "temperature_coefficient"],
            "coefficient 2 max": [50.0, "temperature_coefficient"],
        }),
    ],
)
def test_temperature_coefficient(value, expected, capsys):
    values = normalized_values("Temperature Coefficient", value, capsys)

    for quantity, expected_value in expected.items():
        if expected_value[1] == "temperature_coefficient_code":
            assert values[quantity] == expected_value
        else:
            assert_quantity(values[quantity], expected_value[0], expected_value[1])


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("±4ppm", {"stability min": -4.0, "stability max": 4.0}),
        ("±280ppb", {"stability min": -0.28, "stability max": 0.28}),
        ("±0.2%", {"stability min": [-0.2, "percentage"], "stability max": [0.2, "percentage"]}),
        ("-120ppm~+10ppm", {"stability min": -120.0, "stability max": 10.0}),
        ("50ppm", {"stability": 50.0}),
        ("±2ppm", {"stability min": -2.0, "stability max": 2.0}),
        ("-", {"stability": "NaN"}),
    ],
)
def test_frequency_stability(value, expected, capsys):
    values = normalized_values("Frequency Stability", value, capsys)

    for quantity, stability in expected.items():
        if isinstance(stability, list):
            assert_quantity(values[quantity], stability[0], stability[1])
        else:
            assert_quantity(values[quantity], stability, "ppm")


def test_aging_per_year_frequency_stability_alias(capsys):
    values = normalized_values("Aging Per Year", "±2ppm", capsys)

    assert_quantity(values["stability min"], -2.0, "ppm")
    assert_quantity(values["stability max"], 2.0, "ppm")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("±20ppm", {"tolerance min": -20.0, "tolerance max": 20.0}),
        ("-6ppm~+8ppm", {"tolerance min": -6.0, "tolerance max": 8.0}),
        ("3000ppm", {"tolerance": 3000.0}),
        ("-", {"tolerance": "NaN"}),
    ],
)
def test_normal_temperature_frequency_tolerance(value, expected, capsys):
    values = normalized_values("Normal Temperature Frequency Tolerance", value, capsys)

    for quantity, tolerance in expected.items():
        assert_quantity(values[quantity], tolerance, "ppm")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Frequency Tolerance", "±0.5%", {"tolerance min": [-0.5, "percentage"], "tolerance max": [0.5, "percentage"]}),
        ("Frequency Tolerance", "±20ppm", {"tolerance min": [-20.0, "ppm"], "tolerance max": [20.0, "ppm"]}),
        ("Frequency Stability(Full Temperature Range)", "-6ppm~+8ppm", {"stability min": [-6.0, "ppm"], "stability max": [8.0, "ppm"]}),
        ("Absolute Pull Range (Apr)", "±30ppm", {"stability min": [-30.0, "ppm"], "stability max": [30.0, "ppm"]}),
        ("Temperature Coefficient of Frequency", "±12ppm", {"stability min": [-12.0, "ppm"], "stability max": [12.0, "ppm"]}),
    ],
)
def test_additional_frequency_stability_values(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, expected_value in expected.items():
        assert_quantity(values[quantity], expected_value[0], expected_value[1])


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Voltage Reference Drift", "50ppm/℃, 40ppm/℃", {
            "coefficient 1": [50.0, "temperature_coefficient"],
            "coefficient 2": [40.0, "temperature_coefficient"],
        }),
        ("Voltage Reference Drift", "500ppb/℃", {
            "coefficient": [0.5, "temperature_coefficient"],
        }),
        ("Gain Drift", "3ppm/℃", {
            "coefficient": [3.0, "temperature_coefficient"],
        }),
        ("Temperature Stability", "50ppm/℃, 200ppm/℃", {
            "coefficient 1": [50.0, "temperature_coefficient"],
            "coefficient 2": [200.0, "temperature_coefficient"],
        }),
    ],
)
def test_temperature_coefficient_aliases(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, expected_value in expected.items():
        assert_quantity(values[quantity], expected_value[0], expected_value[1])


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Energy", "900mJ", 0.9),
        ("Energy", "3.5kJ", 3500.0),
        ("Energy (Max)", "0.05J", 0.05),
        ("Energy (Max)", "-", "NaN"),
        ("Turn-on Energy (Eon)", "310uJ", 310e-6),
        ("Switching Energy(Eoff)", "12.9mJ", 0.0129),
        ("Avalanche Energy", "10mJ", 0.01),
        ("Turn on Switching Loss (Eon)", "0.22mJ", 0.00022),
        ("Turn Off Switching Loss (Eoff)", "0.33mJ", 0.00033),
    ],
)
def test_energy_values(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)
    assert_quantity(values["energy"], expected, "energy")


def test_switching_energy_lists(capsys):
    values = normalized_values("Turn-on Energy (Eon)", "300uJ, 670uJ", capsys)

    assert_quantity(values["energy 1"], 300e-6, "energy")
    assert_quantity(values["energy 2"], 670e-6, "energy")

    values = normalized_values("Switching Energy(Eoff)", "960uJ, 1.36mJ", capsys)

    assert_quantity(values["energy 1"], 960e-6, "energy")
    assert_quantity(values["energy 2"], 0.00136, "energy")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Attenuation", "20dB", [20.0]),
        ("Attenuation", "-30dB, -28dB, -38dB", [-30.0, -28.0, -38.0]),
        ("Insertion Loss", "2.5dB, 4dB", [2.5, 4.0]),
        ("Signal-to-Noise Ratio", "90dB, 91dB, 86dB, 88dB", [90.0, 91.0, 86.0, 88.0]),
        ("S/N Ratio", "64dB, 69dB, 68dB, 66dB", [64.0, 69.0, 68.0, 66.0]),
        ("Snr(Signal to Noise Ratio)", "64.3dB;64dB", [64.3, 64.0]),
        ("Signal to Noise Ratio", "58dB", [58.0]),
        ("Power Supply Rejection Ratio (Psrr)", "125dB, 110dB", [125.0, 110.0]),
        ("Power Supply Rejection Ratio (Psrr)", "-", ["NaN"]),
        ("Noise Figure", "7.9dB, 8.1dB", [7.9, 8.1]),
        ("Common Mode Rejection Ratio(CMRR)", "94dB, 118dB", [94.0, 118.0]),
        ("Common Mode Rejection Ratio (CMRR)", "100dB, 90dB, 86dB", [100.0, 90.0, 86.0]),
        ("Common Mode Rejection Ratio", "20dB", [20.0]),
        ("Return Loss (Min)", "9.5dB", [9.5]),
        ("Return Loss (Low Band/High Band)", "9.54dB", [9.54]),
        ("High Band Return Loss (Min)", "14dB", [14.0]),
        ("Low Band Return Loss (Min)", "20dB", [20.0]),
        ("Harmonics", "-40dBc", [-40.0]),
        ("Phase Noise", "-95dBc/Hz", [-95.0]),
        ("Output Return Loss", "13.5dB", [13.5]),
        ("Input Return Loss", "12.5dB", [12.5]),
        ("Sound Pressure Level(Spl)", "95dB", [95.0]),
        ("Sound Pressure Level(Spl)", "83dB@0.1W,10cm", [83.0]),
        ("Sound Pressure Level (Spl)", "95dB@12V,10cm", [95.0]),
        ("Isolation", "19dB", [19.0]),
        ("Isolation", "25dB, 23dB", [25.0, 23.0]),
        ("Isolation(L-I)", "44dB", [44.0]),
        ("Isolation(L-R)", "40dB", [40.0]),
    ],
)
def test_decibel_lists(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for index, level in enumerate(expected, start=1):
        assert_quantity(values[f"level {index}"], level, "decibel")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2500V", {"voltage 1": 2500.0}),
        ("2.5kV", {"voltage 1": 2500.0}),
        ("Non-isolated", {"isolation": "Non-isolated"}),
    ],
)
def test_mixed_isolation_values(value, expected, capsys):
    values = normalized_values("Isolation", value, capsys)

    for quantity, expected_value in expected.items():
        if isinstance(expected_value, str):
            assert values[quantity] == [expected_value, "identifier"]
        else:
            assert_quantity(values[quantity], expected_value, "voltage")


def test_insertion_loss_db_max(capsys):
    values = normalized_values("Insertion Loss (dB Max)", "1.6dB, 1.1dB", capsys)

    assert_quantity(values["level 1"], 1.6, "decibel")
    assert_quantity(values["level 2"], 1.1, "decibel")


@pytest.mark.parametrize(
    "key",
    [
        "Gain/Loss",
        "Amplitude Balance (Max)",
        "Amplitude Unbalance",
        "Return Loss",
        "Coupling Factor",
        "Input Return Loss(Receive)",
        "Output Return Loss(Transmit)",
    ],
)
def test_rf_decibel_aliases(key, capsys):
    values = normalized_values(key, "7dB, 9dB", capsys)

    assert_quantity(values["level 1"], 7.0, "decibel")
    assert_quantity(values["level 2"], 9.0, "decibel")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("4.2dB", [4.2]),
        ("1.5dBi", [1.5]),
        ("4dBic", [4.0]),
        ("0.3dBi, 0.75dBi", [0.3, 0.75]),
        ("-", ["NaN"]),
    ],
)
def test_peak_gain(value, expected, capsys):
    values = normalized_values("Peak Gain", value, capsys)

    for index, gain in enumerate(expected, start=1):
        assert_quantity(values[f"gain {index}"], gain, "decibel")


def test_decibel_at_frequency(capsys):
    values = normalized_values(
        "Power Supply Rejection Ratio (Psrr)",
        "70dB@(1kHz), 66dB@(100Hz), 65dB@(10kHz)",
        capsys,
    )

    assert_quantity(values["level 1"], 70.0, "decibel")
    assert_quantity(values["frequency 1"], 1000.0, "frequency")
    assert_quantity(values["level 2"], 66.0, "decibel")
    assert_quantity(values["frequency 2"], 100.0, "frequency")
    assert_quantity(values["level 3"], 65.0, "decibel")
    assert_quantity(values["frequency 3"], 10000.0, "frequency")


def test_decibel_at_frequency_ranges_and_ignored_conditions(capsys):
    values = normalized_values(
        "Power Supply Rejection Ratio (Psrr)",
        "80dB@(1kHz~100kHz)",
        capsys,
    )

    assert_quantity(values["level 1"], 80.0, "decibel")
    assert_quantity(values["frequency 1 min"], 1000.0, "frequency")
    assert_quantity(values["frequency 1 max"], 100000.0, "frequency")

    values = normalized_values("Power Supply Rejection Ratio (Psrr)", "68dB@(1mA)", capsys)
    assert_quantity(values["level 1"], 68.0, "decibel")
    assert "frequency 1" not in values


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("15dB@2.4GHz, 21dB@5GHz, 17dB@6GHz", {
            "level 1": 15.0,
            "frequency 1": 2.4e9,
            "level 2": 21.0,
            "frequency 2": 5e9,
            "level 3": 17.0,
            "frequency 3": 6e9,
        }),
        ("9.6dB~10.6dB, 10.2dB~11.2dB", {
            "level 1 min": 9.6,
            "level 1 max": 10.6,
            "level 2 min": 10.2,
            "level 2 max": 11.2,
        }),
        ("25dB~33dB", {"level 1 min": 25.0, "level 1 max": 33.0}),
        ("55dB;62dB", {"level 1": 55.0, "level 2": 62.0}),
        ("-", {"level 1": "NaN"}),
    ],
)
def test_attenuation_value(value, expected, capsys):
    values = normalized_values("Attenuation Value", value, capsys)

    for quantity, level in expected.items():
        unit = "frequency" if quantity.startswith("frequency") else "decibel"
        assert_quantity(values[quantity], level, unit)


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("IP3", "28dBm", [28.0]),
        ("IP3", "+41.9dBm", [41.9]),
        ("P1d B", "-25dBm", [-25.0]),
        ("P1d B(Receive)", "16dBm", [16.0]),
        ("IP3(Receive)", "30dBm", [30.0]),
        ("IP3(Transmit)", "23dBm", [23.0]),
    ],
)
def test_decibel_milliwatt_values(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for index, level in enumerate(expected, start=1):
        assert_quantity(values[f"level {index}"], level, "decibel_milliwatt")


def test_transmit_receive_rf_aliases(capsys):
    values = normalized_values("Input Return Loss(Transmit)", "-10dB", capsys)
    assert_quantity(values["level 1"], -10.0, "decibel")

    values = normalized_values("P1d B(Transmit)", "21.5dBm", capsys)
    assert_quantity(values["level 1"], 21.5, "decibel_milliwatt")


def test_rf_range_aliases(capsys):
    values = normalized_values("Noise Floor", "-162dBm/Hz", capsys)
    assert_quantity(values["noise 1"], -162.0, "decibel_milliwatt_per_hertz")

    values = normalized_values("Input Range", "-29dBm~17dBm", capsys)
    assert_quantity(values["level min"], -29.0, "decibel_milliwatt")
    assert_quantity(values["level max"], 17.0, "decibel_milliwatt")


def test_frequency_band_aliases(capsys):
    values = normalized_values(
        "Frequency Bands (Low/High)",
        "1.572GHz~1.578GHz;2.4GHz~2.5GHz",
        capsys,
    )

    assert_quantity(values["frequency 1 min"], 1.572e9, "frequency")
    assert_quantity(values["frequency 1 max"], 1.578e9, "frequency")
    assert_quantity(values["frequency 2 min"], 2.4e9, "frequency")
    assert_quantity(values["frequency 2 max"], 2.5e9, "frequency")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Output Rate", "1250MHz", 1250e6),
        ("Frequency Response", "3kHz", 3000.0),
    ],
)
def test_additional_scalar_frequency_aliases(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    assert_quantity(values["frequency"], expected, "frequency")


def test_oscillator_frequency_range_alias(capsys):
    values = normalized_values("Oscillator Frequency Range", "0.1MHz~30MHz", capsys)

    assert_quantity(values["frequency 1 min"], 100000.0, "frequency")
    assert_quantity(values["frequency 1 max"], 30e6, "frequency")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("325mWx1@8Ω", {"power 1": (0.325, "power"), "channels 1": (1.0, "count"), "load 1": (8.0, "resistance")}),
        ("2W×2@3Ω", {"power 1": (2.0, "power"), "channels 1": (2.0, "count"), "load 1": (3.0, "resistance")}),
        ("2×7W@4Ω", {"power 1": (7.0, "power"), "channels 1": (2.0, "count"), "load 1": (4.0, "resistance")}),
        ("21.7dBm", {"power 1": (21.7, "decibel_milliwatt")}),
        ("30Wx1@8Ω, 15Wx2@4Ω", {
            "power 1": (30.0, "power"),
            "channels 1": (1.0, "count"),
            "load 1": (8.0, "resistance"),
            "power 2": (15.0, "power"),
            "channels 2": (2.0, "count"),
            "load 2": (4.0, "resistance"),
        }),
        ("8W×2+12W×1@8Ω", {
            "power 1": (8.0, "power"),
            "channels 1": (2.0, "count"),
            "load 1": (8.0, "resistance"),
            "power 2": (12.0, "power"),
            "channels 2": (1.0, "count"),
            "load 2": (8.0, "resistance"),
        }),
        ("2.3W(Max)", {"power 1": (2.3, "power")}),
    ],
)
def test_output_power(value, expected, capsys):
    values = normalized_values("Output Power", value, capsys)

    for quantity, expected_value in expected.items():
        value, unit = expected_value
        assert_quantity(values[quantity], value, unit)


def test_contact_rating(capsys):
    values = normalized_values("Contact Rating", "6A@250VAC, 6A@30VDC", capsys)

    assert_quantity(values["current 1"], 6.0, "current")
    assert_quantity(values["voltage 1"], 250.0, "voltage")
    assert_quantity(values["current 2"], 6.0, "current")
    assert_quantity(values["voltage 2"], 30.0, "voltage")

    values = normalized_values("Contact Rating", "5A@250AC", capsys)
    assert_quantity(values["current 1"], 5.0, "current")
    assert_quantity(values["voltage 1"], 250.0, "voltage")


def test_breaking_ability(capsys):
    values = normalized_values("Breaking Ability", "80A@250VAC", capsys)

    assert_quantity(values["current 1"], 80.0, "current")
    assert_quantity(values["voltage 1"], 250.0, "voltage")


@pytest.mark.parametrize(
    ("value", "quantity", "expected", "unit"),
    [
        ("3dBm", "power", 3.0, "decibel_milliwatt"),
        ("100mW", "power", 0.1, "power"),
    ],
)
def test_output_power_max(value, quantity, expected, unit, capsys):
    values = normalized_values("Output Power (Max)", value, capsys)

    assert_quantity(values[quantity], expected, unit)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("6mVp-p", 0.006),
        ("0.2mVRMS", 0.0002),
        ("150uVRMS", 150e-6),
        ("-", "NaN"),
    ],
)
def test_clock_feedthrough_voltage(value, expected, capsys):
    values = normalized_values("Clock Feedthrough", value, capsys)

    assert_quantity(values["voltage 1"], expected, "voltage")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("3.43mm", {"length": 0.00343}),
        ("1.27mm~1.8mm", {"length min": 0.00127, "length max": 0.0018}),
        ("-", {"length": "NaN"}),
    ],
)
def test_insulation_od_lengths(value, expected, capsys):
    values = normalized_values("Insulation Od", value, capsys)

    for quantity, length in expected.items():
        assert_quantity(values[quantity], length, "length")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Insulation Height", "8.51mm", 0.00851),
        ("Interface Length/Height", "11mm", 0.011),
        ("Height - Seated (Max)", "73.5mm", 0.0735),
        ("Height - Seated (Max)", "-", "NaN"),
        ("L", "110mm", 0.11),
        ("L", "null", "NaN"),
        ("Switch Length", "12.78mm", 0.01278),
        ("Switch Length", "-", "NaN"),
        ("Switch Width", "6.8mm", 0.0068),
        ("Diameter", "50mm", 0.05),
        ("Diameter", "M3", 0.003),
        ("Length", "0.984'(300.00mm,11.81\")", 0.3),
        ("Diameter (Φd)", "30mm", 0.03),
        ("Diameter (Φd)", "1.36cm", 0.0136),
        ("Interface Diameter", "7.5mm", 0.0075),
        ("Length of Mating Pin", "5.84mm", 0.00584),
        ("Operating Height", "8.3mm", 0.0083),
        ("Operational Height", "2.2mm", 0.0022),
        ("Row Spacing", "2.54mm", 0.00254),
        ("System Fit Height", "1.5mm", 0.0015),
        ("Overall Length/Height", "11mm", 0.011),
        ("Head Width", "19.05mm", 0.01905),
        ("Center Height", "1.68mm", 0.00168),
        ("Outside Contact Diameter", "6.4mm", 0.0064),
        ("Length of End Connection Pin", "2mm", 0.002),
        ("Diameter of Bolt Mouth", "5mm", 0.005),
        ("Pin Length", "3.15mm", 0.00315),
        ("Diameter(Φd)", "30mm", 0.03),
        ("Lead Pitch", "6.5mm", 0.0065),
        ("Inner Diameter Φ/Inner Width D", "9mm@φ", 0.009),
        ("Lead Spacing", "22.4mm", 0.0224),
        ("Φd", "50mm", 0.05),
        ("Pin Spacing", "22.4mm", 0.0224),
        ("Capacitor Length", "10mm", 0.01),
        ("Pin Spaceing", "3.5mm", 0.0035),
        ("Capacitor Diameter", "8mm", 0.008),
        ("Size/Dimension", "18mm", 0.018),
        ("Body Thickness", "5mm", 0.005),
        ("Body Height", "0.3mm", 0.0003),
        ("Body Height (Max)", "1.18mm", 0.00118),
        ("Maximum Body Height", "1.65mm", 0.00165),
        ("Body Length", "168mm", 0.168),
        ("Body Width", "76mm", 0.076),
        ("Thickness", "0.06mm", 0.00006),
        ("Fuse Length", "20mm", 0.02),
        ("Fuse Diameter (Φd)", "5.2mm", 0.0052),
        ("Fuse Width", "3.8mm", 0.0038),
        ("Fuse Height", "8.3mm", 0.0083),
        ("Inside Contact Diameter", "1.3mm", 0.0013),
        ("Hole/Pin Spacing", "2.54mm", 0.00254),
        ("(For Insertion) Insertion Piece Thickness", "0.81mm", 0.00081),
        ("Length of Copper Pipe", "8mm", 0.008),
        ("Tail Width", "3.7mm", 0.0037),
        ("Spacing", "5.08mm", 0.00508),
        ("Spacing", "-", "NaN"),
        ("Slice Width", "2.8mm", 0.0028),
        ("Needle Diameter", "1.78mm", 0.00178),
        ("Full Length of Copper Pipe", "9.525mm", 0.009525),
        ("Length of Fit", "11.94m", 0.01194),
        ("Tail Diameter", "6.6mm", 0.0066),
        ("Head Diameter", "5", 0.005),
        ("Blade Width", "6.4mm", 0.0064),
        ("Pin Spacing(Adjacent)", "8.75m", 0.00875),
        ("Insert Thickness", "0.303mm", 0.000303),
        ("Spacing - Connector", "0.118\"(3.00mm)", 0.003),
        ("Sheath (Insulation) Diameter", "0.200\"(5.08mm)", 0.00508),
        ("Wire Diameter", "2.5mm", 0.0025),
        ("Digit/Alpha Size(Inch)", "0.56", 0.014224),
        ("Thread Length", "30cm", 0.3),
        ("Slot Width", "1.2mm", 0.0012),
        ("Slit Width", "0.12mm", 0.00012),
        ("Link Range(Standard Mode)", "30cm", 0.3),
    ],
)
def test_scalar_length_attributes(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)
    assert_quantity(values["length"], expected, "length")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1.0mm±0.03mm", {"length": 0.001, "length tolerance": 0.00003, "length min": 0.00097, "length max": 0.00103}),
        ("0.8±0.1mm", {"length": 0.0008, "length tolerance": 0.0001, "length min": 0.0007, "length max": 0.0009}),
        ("1.5mm ± 0.02mm", {"length": 0.0015, "length tolerance": 0.00002, "length min": 0.00148, "length max": 0.00152}),
    ],
)
def test_toleranced_thickness(value, expected, capsys):
    values = normalized_values("Thickness", value, capsys)

    for quantity, length in expected.items():
        assert_quantity(values[quantity], length, "length")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Iinearity Range", "0cm~62cm", {"length min": 0.0, "length max": 0.62}),
        ("Iinearity Range", "8m", {"length": 8.0}),
        ("Operating Wavelength", "5um~14um", {"length 1 min": 5e-6, "length 1 max": 14e-6}),
        ("Window Size", "3x4mm", {"length 1": 0.003, "length 2": 0.004}),
    ],
)
def test_additional_length_values(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, length in expected.items():
        assert_quantity(values[quantity], length, "length")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Inner Diameter After Contraction", "≤6.5mm", {"length": 0.0065}),
        ("Inner Diameter After Contraction", "14.0±0.1(mm)", {
            "length": 0.014,
            "length tolerance": 0.0001,
            "length min": 0.0139,
            "length max": 0.0141,
        }),
        ("Undeclared Tolerance", "±0.1mm", {
            "length": 0.0,
            "length tolerance": 0.0001,
            "length min": -0.0001,
            "length max": 0.0001,
        }),
    ],
)
def test_additional_toleranced_lengths(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, length in expected.items():
        assert_quantity(values[quantity], length, "length")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("FFC, Fcb Thickness", "0.13mm~0.38mm", {
            "length min": 0.00013,
            "length max": 0.00038,
        }),
        ("FFC, Fcb Thickness", "0.3mm;0.33mm", {
            "length 1": 0.0003,
            "length 2": 0.00033,
        }),
        ("Tail Diameter", "3.2mm, 4mm", {
            "length 1": 0.0032,
            "length 2": 0.004,
        }),
        ("Total Length", "5cm", {"length 1": 0.05}),
        ("Line Length", "30cm, 23cm", {"length 1": 0.3, "length 2": 0.23}),
        ("Length", "7.7mm, 8.3mm", {"length 1": 0.0077, "length 2": 0.0083}),
        ("Wire Diameter", "1.6mm, Rib Line Diameter 1.8MM", {
            "length 1": 0.0016,
            "length 2": 0.0018,
        }),
        ("Half Wave Width", "60nm", {"length 1": 60e-9}),
        ("Spectral Range", "940nm, 850nm", {"length 1": 940e-9, "length 2": 850e-9}),
    ],
)
def test_additional_length_lists(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, length in expected.items():
        assert_quantity(values[quantity], length, "length")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("3.2mmx1.6mm", {"length 1": 0.0032, "length 2": 0.0016}),
        ("2.5mm", {"length": 0.0025}),
        ("-", {"length": "NaN"}),
    ],
)
def test_board_space_dimensions(value, expected, capsys):
    values = normalized_values("Board Space (Diameter Φ/Length X Width)", value, capsys)

    for quantity, length in expected.items():
        assert_quantity(values[quantity], length, "length")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Module Size", "19mmx12.6mmx8mm", {
            "length 1": 0.019,
            "length 2": 0.0126,
            "length 3": 0.008,
        }),
        ("Display Range", "43.2x57.6mm", {
            "length 1": 0.0432,
            "length 2": 0.0576,
        }),
    ],
)
def test_display_dimensions(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, length in expected.items():
        assert_quantity(values[quantity], length, "length")


def test_pixel_size(capsys):
    values = normalized_values("Pixel Size", "4.2umx4.2um", capsys)

    assert_quantity(values["length 1"], 4.2e-6, "length")
    assert_quantity(values["length 2"], 4.2e-6, "length")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("15mm~150mm", {"length min": 0.015, "length max": 0.15}),
        ("350cm", {"length": 3.5}),
    ],
)
def test_linear_range_lengths(value, expected, capsys):
    values = normalized_values("Linear Range", value, capsys)

    for quantity, length in expected.items():
        assert_quantity(values[quantity], length, "length")


def test_communication_distance(capsys):
    values = normalized_values("Communication Distance", "150m, 500m", capsys)

    assert_quantity(values["length 1"], 150.0, "length")
    assert_quantity(values["length 2"], 500.0, "length")

    values = normalized_values("Communication Distance", "3km~5km", capsys)

    assert_quantity(values["length 1 min"], 3000.0, "length")
    assert_quantity(values["length 1 max"], 5000.0, "length")


def test_distance_aliases(capsys):
    values = normalized_values("Distance", "50m, 200m, 120m", capsys)
    assert_quantity(values["length 1"], 50.0, "length")
    assert_quantity(values["length 2"], 200.0, "length")
    assert_quantity(values["length 3"], 120.0, "length")

    values = normalized_values("Sensing Range", "1cm~30cm", capsys)
    assert_quantity(values["length 1 min"], 0.01, "length")
    assert_quantity(values["length 1 max"], 0.3, "length")


def test_mechanical_dimension_aliases(capsys):
    values = normalized_values("Product Size", "16.5*16*25MM", capsys)

    assert_quantity(values["length 1"], 0.0165, "length")
    assert_quantity(values["length 2"], 0.016, "length")
    assert_quantity(values["length 3"], 0.025, "length")

    values = normalized_values("Metal Size", "φ4mm", capsys)
    assert_quantity(values["length"], 0.004, "length")

    values = normalized_values("Size/Size", '0.55" L x 0.30" W x 0.40" H (14.0mm x 7.5mm x 10.1mm)', capsys)
    assert_quantity(values["length 1"], 0.014, "length")
    assert_quantity(values["length 2"], 0.0075, "length")
    assert_quantity(values["length 3"], 0.0101, "length")


@pytest.mark.parametrize("key", ["Conduction Travel", "Total Travel"])
def test_travel_length_aliases(key, capsys):
    values = normalized_values(key, "1.5mm", capsys)

    assert_quantity(values["length"], 0.0015, "length")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2.54mm", 0.00254),
        ("0.5", 0.0005),
        ("-", "NaN"),
    ],
)
def test_pitch_attribute(value, expected, capsys):
    values = normalized_values("Pitch", value, capsys)
    assert_quantity(values["length"], expected, "length")


def test_insulation_od_length_range_lists(capsys):
    values = normalized_values(
        "Insulation Od",
        "0.7366mm~0.889mm, 0.8382mm~0.9652mm",
        capsys,
    )

    assert_quantity(values["length 1 min"], 0.0007366, "length")
    assert_quantity(values["length 1 max"], 0.000889, "length")
    assert_quantity(values["length 2 min"], 0.0008382, "length")
    assert_quantity(values["length 2 max"], 0.0009652, "length")


def test_interface_length_height_lists(capsys):
    values = normalized_values("Interface Length/Height", "8.5mm, 8.7mm", capsys)

    assert_quantity(values["length 1"], 0.0085, "length")
    assert_quantity(values["length 2"], 0.0087, "length")


def test_system_fit_height_lists(capsys):
    values = normalized_values("System Fit Height", "3mm;3.5mm", capsys)

    assert_quantity(values["length 1"], 0.003, "length")
    assert_quantity(values["length 2"], 0.0035, "length")


def test_interface_diameter_lists(capsys):
    values = normalized_values("Interface Diameter", "9.6mm, 6.35mm", capsys)

    assert_quantity(values["length 1"], 0.0096, "length")
    assert_quantity(values["length 2"], 0.00635, "length")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Fuse Length", "20mm, 30mm, 25mm", [0.02, 0.03, 0.025]),
        ("Fuse Diameter (Φd)", "6.3mm, 5mm", [0.0063, 0.005]),
    ],
)
def test_fuse_dimension_lists(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for index, length in enumerate(expected, start=1):
        assert_quantity(values[f"length {index}"], length, "length")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("13@500MHz", [(13.0, 500e6)]),
        ("30@796KHz", [(30.0, 796e3)]),
        ("24", [(24.0, None)]),
        ("-", [("NaN", None)]),
        ("67@900MHz, 108@1.7GHz, 146@2.4GHz", [(67.0, 900e6), (108.0, 1.7e9), (146.0, 2.4e9)]),
    ],
)
def test_q_at_frequency(value, expected, capsys):
    values = normalized_values("Q @ Frequency", value, capsys)

    for index, (q, frequency) in enumerate(expected, start=1):
        assert_quantity(values[f"q {index}"], q, "ratio")
        if frequency is not None:
            assert_quantity(values[f"frequency {index}"], frequency, "frequency")
        else:
            assert f"frequency {index}" not in values


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("180", {"gain": 180.0}),
        ("475, 415", {"gain 1": 475.0, "gain 2": 415.0}),
        ("100, 1000~12000", {"gain 1": 100.0, "gain 2 min": 1000.0, "gain 2 max": 12000.0}),
        ("300@5A,10V", {"gain": 300.0}),
    ],
)
def test_dc_current_gain_values(value, expected, capsys):
    values = normalized_values("DC Current Gain", value, capsys)

    for quantity, gain in expected.items():
        assert_quantity(values[quantity], gain, "ratio")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("40@200mA,1V", {
            "gain 1": (40.0, "ratio"),
            "current 1": (0.2, "current"),
            "voltage 1": (1.0, "voltage"),
        }),
        ("80@5V", {
            "gain 1": (80.0, "ratio"),
            "voltage 1": (5.0, "voltage"),
        }),
        ("30@5mA,5V;150@100mA.2V", {
            "gain 1": (30.0, "ratio"),
            "current 1": (0.005, "current"),
            "voltage 1": (5.0, "voltage"),
            "gain 2": (150.0, "ratio"),
            "current 2": (0.1, "current"),
            "voltage 2": (2.0, "voltage"),
        }),
        ("100~300", {
            "gain 1 min": (100.0, "ratio"),
            "gain 1 max": (300.0, "ratio"),
        }),
        ("900", {"gain 1": (900.0, "ratio")}),
    ],
)
def test_dc_current_gain_hfe_conditions(value, expected, capsys):
    values = normalized_values("DC Current Gain (H Fe@IC,VCE)", value, capsys)

    for quantity, expected_value in expected.items():
        value, unit = expected_value
        assert_quantity(values[quantity], value, unit)


def test_dc_current_gain_hfe_vce_ic_alias(capsys):
    values = normalized_values("DC Current Gain (H Fe@VCE,IC)", "750@3V,2A", capsys)

    assert_quantity(values["gain 1"], 750.0, "ratio")
    assert_quantity(values["voltage 1"], 3.0, "voltage")
    assert_quantity(values["current 1"], 2.0, "current")


@pytest.mark.parametrize("key", ["Magnetic Conductivity-U''", "Magnetic Conductivity-U'"])
def test_magnetic_conductivity_frequency(key, capsys):
    values = normalized_values(key, "1.3@13.56MHz", capsys)

    assert_quantity(values["magnetic conductivity 1"], 1.3, "ratio")
    assert_quantity(values["frequency 1"], 13.56e6, "frequency")


def test_turns_ratio(capsys):
    values = normalized_values("Turns Ratio", "1CT:1CT, 1CT:2.4CT", capsys)

    assert_quantity(values["ratio 1.1"], 1.0, "ratio")
    assert_quantity(values["ratio 1.2"], 1.0, "ratio")
    assert_quantity(values["ratio 2.1"], 1.0, "ratio")
    assert_quantity(values["ratio 2.2"], 2.4, "ratio")


def test_ethernet_rate(capsys):
    values = normalized_values("Rate", "1G/2.5G/5G Base-T", capsys)

    assert_quantity(values["data rate 1"], 1e9, "data_rate")
    assert_quantity(values["data rate 2"], 2.5e9, "data_rate")
    assert_quantity(values["data rate 3"], 5e9, "data_rate")


def test_shrinkage_ratio(capsys):
    values = normalized_values("Shrinkage Ratio", "2:1, -", capsys)
    assert_quantity(values["ratio 1"], 2.0, "ratio")
    assert_quantity(values["ratio 2"], "NaN", "ratio")

    values = normalized_values("Shrinkage Ratio", "Lateral Shrinkage ≥50%, Longitudinal Shrinkage ≤8%", capsys)
    assert_quantity(values["lateral shrinkage min"], 50.0, "percentage")
    assert_quantity(values["longitudinal shrinkage max"], 8.0, "percentage")


def test_fraction_list_attributes(capsys):
    values = normalized_values("Bias", "1/3,1/2", capsys)
    assert_quantity(values["ratio 1"], 1 / 3, "ratio")
    assert_quantity(values["ratio 2"], 0.5, "ratio")

    values = normalized_values("Capacitance Ratio", "2@C1V/C4V", capsys)
    assert_quantity(values["ratio 1"], 2.0, "ratio")


def test_voltage_and_frequency_range_aliases(capsys):
    values = normalized_values("Voltage Range", "1000/100V", capsys)
    assert_quantity(values["voltage 1.1"], 1000.0, "voltage")
    assert_quantity(values["voltage 1.2"], 100.0, "voltage")

    values = normalized_values("Range", "45-65Hz", capsys)
    assert_quantity(values["frequency 1 min"], 45.0, "frequency")
    assert_quantity(values["frequency 1 max"], 65.0, "frequency")


def test_resistor_ratio_values(capsys):
    values = normalized_values("Resistor Ratio", "4.7", capsys)

    assert_quantity(values["ratio"], 4.7, "ratio")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Dynamic Range", "1000:1", {"dynamic range": (1000.0, "ratio")}),
        ("Dynamic Range", "1000:1, 3000:1", {
            "dynamic range 1": (1000.0, "ratio"),
            "dynamic range 2": (3000.0, "ratio"),
        }),
        ("Dynamic Range", "120dB", {"dynamic range 1": (120.0, "decibel")}),
        ("Clock to Corner Frequency Ratio", "100:1", {"ratio": (100.0, "ratio")}),
        ("Clock to Corner Frequency Ratio", "-", {"ratio": ("NaN", "ratio")}),
        ("Switch Circuit", "2:1", {"ratio": (2.0, "ratio")}),
        ("Switch Circuit", "-", {"ratio": ("NaN", "ratio")}),
        ("Swr", "1.25", {"swr": (1.25, "ratio")}),
        ("Vswr", "1.5, 1.8", {"vswr 1": (1.5, "ratio"), "vswr 2": (1.8, "ratio")}),
    ],
)
def test_additional_ratio_values(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, expected_value in expected.items():
        value, unit = expected_value
        assert_quantity(values[quantity], value, unit)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("20V/V", {"gain": (20.0, "ratio")}),
        ("7.6~8.4", {"gain min": (7.6, "ratio"), "gain max": (8.4, "ratio")}),
        ("-22dB~20dB", {"gain min": (-22.0, "decibel"), "gain max": (20.0, "decibel")}),
        ("50V/V, 100V/V", {"gain 1": (50.0, "ratio"), "gain 2": (100.0, "ratio")}),
        ("-", {"gain": ("NaN", "ratio")}),
    ],
)
def test_gain_values(value, expected, capsys):
    values = normalized_values("Gain", value, capsys)

    for quantity, expected_value in expected.items():
        value, unit = expected_value
        assert_quantity(values[quantity], value, unit)


@pytest.mark.parametrize(
    ("value", "capacitance"),
    [
        ("190pF@1kHz", 190e-12),
        ("3.3nF", 3.3e-9),
        ("-", "NaN"),
    ],
)
def test_typical_capacitance(value, capacitance, capsys):
    values = normalized_values("Typical Capatitance", value, capsys)
    assert_quantity(values["capacitance"], capacitance, "capacitance")

    if "@" in value:
        assert_quantity(values["frequency"], 1000.0, "frequency")


def test_junction_capacitance_at_frequency(capsys):
    values = normalized_values("Junction Capacitance(Cj)@1mhz", "75pF@1MHz", capsys)

    assert_quantity(values["capacitance"], 75e-12, "capacitance")
    assert_quantity(values["frequency"], 1e6, "frequency")

    values = normalized_values("Junction Capacitance(Cj)@1mhz", "0.4pF@200MHz~3GHz", capsys)

    assert_quantity(values["capacitance"], 0.4e-12, "capacitance")
    assert_quantity(values["frequency min"], 200e6, "frequency")
    assert_quantity(values["frequency max"], 3e9, "frequency")


def test_junction_capacitance_at_frequency_list(capsys):
    values = normalized_values(
        "Junction Capacitance(Cj)@1mhz",
        "0.5pF@1MHz;0.25pF@1MHz",
        capsys,
    )

    assert_quantity(values["capacitance 1"], 0.5e-12, "capacitance")
    assert_quantity(values["frequency 1"], 1e6, "frequency")
    assert_quantity(values["capacitance 2"], 0.25e-12, "capacitance")
    assert_quantity(values["frequency 2"], 1e6, "frequency")


def test_total_gate_charge_with_current_voltage_conditions(capsys):
    values = normalized_values("Total Gate Charge (Qg@IC,VGE)", "95nC@40A,15V", capsys)

    assert_quantity(values["charge"], 95e-9, "charge")
    assert_quantity(values["voltage"], 15.0, "voltage")


@pytest.mark.parametrize(
    ("key", "value", "capacitance"),
    [
        ("CISS-Input Capacitance", "1.23nF", 1.23e-9),
        ("CISS-Input Capacitance", "24pF", 24e-12),
        ("Output Capacitance(Coes)", "262nF", 262e-9),
        ("Output Capacitance(Coes)", "160pF", 160e-12),
        ("Reverse Transfer Capacitance (Cres)", "25pF", 25e-12),
        ("Reverse Transfer Capacitance (Cres)", "1.1nF", 1.1e-9),
        ("Reverse Transfer Capacitance (Crss)", "7pF", 7e-12),
        ("Con", "380pF", 380e-12),
    ],
)
def test_scalar_capacitance_attributes(key, value, capacitance, capsys):
    values = normalized_values(key, value, capsys)
    assert_quantity(values["capacitance"], capacitance, "capacitance")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("12.1us", [12.1e-6]),
        ("199ns", [199e-9]),
        ("116ns, 115ns", [116e-9, 115e-9]),
    ],
)
def test_td_off_times(value, expected, capsys):
    values = normalized_values("Td(Off)", value, capsys)

    if len(expected) == 1:
        assert_quantity(values["time"], expected[0], "time")
    else:
        for index, time in enumerate(expected, start=1):
            assert_quantity(values[f"time {index}"], time, "time")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("3ms", {"time": 0.003}),
        ("1ms~4ms", {"time min": 0.001, "time max": 0.004}),
    ],
)
def test_action_time_ton_values(value, expected, capsys):
    values = normalized_values("Action Time (Ton)", value, capsys)

    for quantity, time in expected.items():
        assert_quantity(values[quantity], time, "time")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2ms", {"time": 0.002}),
        ("2s@(64KB)", {"time": 2.0}),
        ("150ms@(32KB), 250ms@(64KB)", {"time 1": 0.15, "time 2": 0.25}),
    ],
)
def test_block_erase_time(value, expected, capsys):
    values = normalized_values("Block Erase Time(T Be)", value, capsys)

    for quantity, time in expected.items():
        assert_quantity(values[quantity], time, "time")

@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2ms", {"time": 0.002}),
        ("500ms@(64KB)", {"time": 0.5}),
        ("2ms;3ms", {"time 1": 0.002, "time 2": 0.003}),
    ],
)
def test_block_erase_time_spaced(value, expected, capsys):
    values = normalized_values("Block Erase Time (T Be)", value, capsys)

    for quantity, time in expected.items():
        assert_quantity(values[quantity], time, "time")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("50ms", {"time": 0.05}),
        ("40us", {"time": 40e-6}),
        ("10.5ms, 5.5ms, 4ms", {"time 1": 0.0105, "time 2": 0.0055, "time 3": 0.004}),
    ],
)
def test_temperature_conversion_time(value, expected, capsys):
    values = normalized_values("Temperature Conversion Time", value, capsys)

    for quantity, time in expected.items():
        assert_quantity(values[quantity], time, "time")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("15ns", [15e-9]),
        ("200ps", [200e-12]),
        ("15ns, 30ns", [15e-9, 30e-9]),
    ],
)
def test_propagation_delay_tpd_times(value, expected, capsys):
    values = normalized_values("Propagation Delay (TPD)", value, capsys)

    if len(expected) == 1:
        assert_quantity(values["time"], expected[0], "time")
    else:
        for index, time in enumerate(expected, start=1):
            assert_quantity(values[f"time {index}"], time, "time")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Propagation Delay Tp Hl", "105ns", {"time": 105e-9}),
        ("Propagation Delay Tp Lh", "55ns, 63ns", {"time 1": 55e-9, "time 2": 63e-9}),
        ("Propagation Delay Time", "400ns, 420ns", {"time 1": 400e-9, "time 2": 420e-9}),
        ("Max Propagation Delay", "10.6ns@5V,50pF", {"time": 10.6e-9}),
        ("Maximum Propagation Delay", "32ns@6V,150pF", {"time": 32e-9}),
        ("High Level Delay Time", "200ns", {"time": 200e-9}),
        ("Low Level Delay Time", "200ns", {"time": 200e-9}),
        ("Reverse Recovery Time (Trr)", "28ns, 25ns", {"time 1": 28e-9, "time 2": 25e-9}),
        ("Diode Reverse Recovery Time (Trr)", "44ns", {"time": 44e-9}),
        ("Td(on)", "30ns, 31.6ns", {"time 1": 30e-9, "time 2": 31.6e-9}),
        ("Setup Time", "6ns", {"time": 6e-9}),
        ("Setup Time", "20ns, 10ns, 7.5ns", {"time 1": 20e-9, "time 2": 10e-9, "time 3": 7.5e-9}),
        ("Acquisition Time", "20us", {"time": 20e-6}),
        ("Hold Settling Time", "0.165us", {"time": 0.165e-6}),
        ("Page Programming Time (Tpp)", "90ns", {"time": 90e-9}),
        ("Page Programming Time (Tpp)", "4ms, 8ms", {"time 1": 0.004, "time 2": 0.008}),
        ("Page Program Time (Tprog)", "250us", {"time": 250e-6}),
        ("Page Program Time (Tprog)", "0.35ms", {"time": 0.00035}),
        ("Page Program Time (Tpp)", "700us", {"time": 700e-6}),
        ("Page Program Time (Tpp)", "20ns", {"time": 20e-9}),
        ("Turn Off Delay Time (Td(Off))", "13.5us", {"time": 13.5e-6}),
        ("Thermal Time Constant", "1.43min", {"time": 85.8}),
        ("Thermal Time Constant", "3s, 700ms", {"time 1": 3.0, "time 2": 0.7}),
        ("Hold Time", "-300ps", {"time": -300e-12}),
        ("Hold Time", "20ns, 10ns, 7.5ns", {"time 1": 20e-9, "time 2": 10e-9, "time 3": 7.5e-9}),
        ("Phase Jitter", "500fs", {"time": 500e-15}),
        ("Phase Jitter", "1ps, 200fs", {"time 1": 1e-12, "time 2": 200e-15}),
        ("Cycle-to-Cycle Jitter", "90ps, 170ps", {"time 1": 90e-12, "time 2": 170e-12}),
        ("Period Jitter", "500fs", {"time": 500e-15}),
        ("Period Jitter", "180ps, 100ps", {"time 1": 180e-12, "time 2": 100e-12}),
        ("Available Total Delays", "3.2ns~14.8ns", {"time min": 3.2e-9, "time max": 14.8e-9}),
        ("Available Total Delays", "1us~33.6s", {"time min": 1e-6, "time max": 33.6}),
        ("Output Skew", "30ps", {"time": 30e-12}),
        ("Continuous Adjustable Delay Range", "63.75ns", {"time": 63.75e-9}),
        ("Continuous Adjustable Delay Range", "2.2ns~12.2ns", {"time min": 2.2e-9, "time max": 12.2e-9}),
        ("Time Intervals", "100ms~7200s", {"time min": 0.1, "time max": 7200.0}),
        ("Access Time", "150ns", {"time": 150e-9}),
        ("Access Time", "-", {"time": "NaN"}),
        ("Delay Time", "250ns", {"time": 250e-9}),
        ("Rise Time(Tr)", "2us", {"time": 2e-6}),
        ("Rise Time (Tr)", "1.5us", {"time": 1.5e-6}),
        ("Write Cycle Time (Tw)", "5ms", {"time": 0.005}),
        ("Write Cycle Time(Tw)", "480us", {"time": 480e-6}),
        ("Write Cycle Time (T Wc)", "70ns", {"time": 70e-9}),
        ("Time to First Fix", "30s, 5.5s", {"time 1": 30.0, "time 2": 5.5}),
        ("Switch Time(Toff)", "40ns", {"time": 40e-9}),
        ("Operate Time", "2.5min", {"time": 150.0}),
        ("Release Time", "5ms, 15ms", {"time 1": 0.005, "time 2": 0.015}),
        ("Operation Time", "600us", {"time": 600e-6}),
        ("Switching Power", "3W, 150us", {"time": 150e-6}),
        ("Propagation Delay Tp Lh/Tp Hl", "100ns;130ns", {"time 1": 100e-9, "time 2": 130e-9}),
        ("Maximum Delay Time TPD", "5.1ns", {"time": 5.1e-9}),
        ("Turn-Off Delay", "1.1us", {"time": 1.1e-6}),
        ("Measuring Range", "3.5ns~2.5us", {"time min": 3.5e-9, "time max": 2.5e-6}),
        ("Turn on Delay Time (Td(on))", "40ns", {"time": 40e-9}),
        ("Lifetime", "18000hrs@85℃", {"time": 18000 * 3600}),
        ("Lifetime @ Temperature", "10000hrs@105℃", {"time": 10000 * 3600}),
        ("Load Life", "4000hrs@125℃", {"time": 4000 * 3600}),
        ("Data Retention - Tdr (Year)", "40.2 Years", {"time": 40.2 * 365 * 24 * 3600}),
    ],
)
def test_delay_time_attributes(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, time in expected.items():
        assert_quantity(values[quantity], time, "time")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("240ms", [0.24]),
        ("100us", [100e-6]),
        ("12.5s, 7.5s", [12.5, 7.5]),
    ],
)
def test_reset_timeout_times(value, expected, capsys):
    values = normalized_values("Reset Timeout", value, capsys)

    if len(expected) == 1:
        assert_quantity(values["time"], expected[0], "time")
    else:
        for index, time in enumerate(expected, start=1):
            assert_quantity(values[f"time {index}"], time, "time")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("50us", [50e-6]),
        ("500ps", [500e-12]),
        ("5.4us, 2.9us", [5.4e-6, 2.9e-6]),
    ],
)
def test_settling_time_values(value, expected, capsys):
    values = normalized_values("Settling Time", value, capsys)

    if len(expected) == 1:
        assert_quantity(values["time"], expected[0], "time")
    else:
        for index, time in enumerate(expected, start=1):
            assert_quantity(values[f"time {index}"], time, "time")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("300ns", [300e-9]),
        ("37ps", [37e-12]),
        ("1.3us, 0.3us", [1.3e-6, 0.3e-6]),
    ],
)
def test_response_time_tr_values(value, expected, capsys):
    values = normalized_values("Response Time (Tr)", value, capsys)

    if len(expected) == 1:
        assert_quantity(values["time"], expected[0], "time")
    else:
        for index, time in enumerate(expected, start=1):
            assert_quantity(values[f"time {index}"], time, "time")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1ms", 1e-3),
        ("800us", 800e-6),
        ("1s", 1),
    ],
)
def test_response_time_values(value, expected, capsys):
    values = normalized_values("Response Time", value, capsys)

    assert_quantity(values["time"], expected, "time")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Turn-on Time", "20ns, 28ns", [20e-9, 28e-9]),
        ("Turn-Off Time", "80us, 800us", [80e-6, 800e-6]),
    ],
)
def test_turn_on_off_time_lists(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for index, time in enumerate(expected, start=1):
        assert_quantity(values[f"time {index}"], time, "time")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("300ms", [0.3]),
        ("1.17min", [70.2]),
        ("100ms;8.2s;4.8s", [0.1, 8.2, 4.8]),
        ("2.5s, 6.3s, 11.4s", [2.5, 6.3, 11.4]),
    ],
)
def test_time_to_trip_max_values(value, expected, capsys):
    values = normalized_values("Time to Trip (Max)", value, capsys)

    if len(expected) == 1:
        assert_quantity(values["time"], expected[0], "time")
    else:
        for index, time in enumerate(expected, start=1):
            assert_quantity(values[f"time {index}"], time, "time")
