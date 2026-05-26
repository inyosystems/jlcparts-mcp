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
        ("Resistance Value", "100kΩ", {"resistance": 100000.0}),
        ("Resistance Value", "1.45kΩ, 2.54kΩ", {"resistance 1": 1450.0, "resistance 2": 2540.0}),
        ("Output Impedance", "2.2kΩ", {"resistance": 2200.0}),
        ("Rated Impeance", "8Ω", {"resistance": 8.0}),
        ("Resistor on-State", "34mΩ", {"resistance": 0.034}),
        ("Resistor on-State", "10mΩ;30mΩ", {"resistance 1": 0.01, "resistance 2": 0.03}),
        ("On-State Resistance (Max)", "3.5kΩ", {"resistance": 3500.0}),
        ("On-State Resistance (Max)", "4.6Ω;5.7Ω", {"resistance 1": 4.6, "resistance 2": 5.7}),
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
        ("Input Voltage Range", "-3V~3V, 0.06V~10V", {
            "voltage 1 min": -3.0,
            "voltage 1 max": 3.0,
            "voltage 2 min": 0.06,
            "voltage 2 max": 10.0,
        }),
        ("Common Mode Voltage", "0V~76V", {"voltage min": 0.0, "voltage max": 76.0}),
    ],
)
def test_extra_voltage_ranges(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, voltage in expected.items():
        assert_quantity(values[quantity], voltage, "voltage")


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
        ("Electrostatic Capacity", "30pF~60pF", {"capacitance min": 30e-12, "capacitance max": 60e-12}),
    ],
)
def test_extra_capacitance_attributes(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, capacitance in expected.items():
        assert_quantity(values[quantity], capacitance, "capacitance")


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
        ("Trigger Current", "5A~15A", {"current min": 5.0, "current max": 15.0}),
        ("Trigger Current", "650mA", {"current": 0.65}),
    ],
)
def test_additional_current_values(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, current in expected.items():
        assert_quantity(values[quantity], current, "current")


def test_sampling_rate_lists(capsys):
    values = normalized_values("Sampling Rate", "48000Hz, 32000Hz, 44100Hz", capsys)

    assert_quantity(values["frequency 1"], 48000.0, "frequency")
    assert_quantity(values["frequency 2"], 32000.0, "frequency")
    assert_quantity(values["frequency 3"], 44100.0, "frequency")


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
        ("-3db Bandwidth(G=1)", "60kHz", {"frequency": 60e3}),
        ("Frequency - Cutoff or Center", "1MHz", {"frequency": 1e6}),
        ("Frequency - Cutoff or Center", "900MHz~2GHz", {
            "frequency min": 900e6,
            "frequency max": 2e9,
        }),
    ],
)
def test_additional_frequency_aliases(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, frequency in expected.items():
        assert_quantity(values[quantity], frequency, "frequency")


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
        ("Current - Output Low(Iol)", "2.6mA, 6.8mA, 1mA", [0.0026, 0.0068, 0.001]),
        ("Current - Output High(Ioh)", "1mA, 2.6mA, 6.8mA", [0.001, 0.0026, 0.0068]),
        ("Current - Surge(Itsm@F)", "170A@60Hz, 155A@50Hz", [170.0, 155.0]),
        ("Send Current", "9.5mA, 16mA", [0.0095, 0.016]),
        ("Current of Transmitting", "7.1mA, 3.5mA", [0.0071, 0.0035]),
        ("Current - Collector Cutoff", "100uA, 500uA", [100e-6, 500e-6]),
        ("Load Current", "900mA, 1.2A", [0.9, 1.2]),
        ("Steady State Current (Max)", "440uA, 400uA", [440e-6, 400e-6]),
        ("Minimum Cathode Current for Regulation", "80uA, 55uA", [80e-6, 55e-6]),
        ("Holding Current (Ih)", "60mA, 30mA, 45mA", [0.06, 0.03, 0.045]),
        ("Current - Max", "60A, 125A, 40A", [60.0, 125.0, 40.0]),
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
        ("Number of Cells", "3~16", {"count min": 3, "count max": 16}),
        ("Number of Cells", "12", {"count": 12}),
    ],
)
def test_extra_count_attributes(key, value, expected, capsys):
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
    ("key", "value", "expected"),
    [
        ("Life", "100,000 cycles", 100000),
        ("Life", "4 million cycles", 4000000),
        ("Mechanical Life", "1万次", 10000),
        ("Mechanical Life", "5千次", 5000),
        ("Mechanical Life", "5 Million Times", 5000000),
    ],
)
def test_cycle_life_counts(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    assert_quantity(values["count"], expected, "count")


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

@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("10Mbit/s", {"data rate": 10e6}),
        ("8kHz, 32kHz", {"data rate 1": 8e3, "data rate 2": 32e3}),
        ("2Mbps;50Mbps", {"data rate 1": 2e6, "data rate 2": 50e6}),
        ("3.75Gbps, 1Gbps", {"data rate 1": 3.75e9, "data rate 2": 1e9}),
        ("NaN", {"data rate": "NaN"}),
    ],
)
def test_data_rate(value, expected, capsys):
    values = normalized_values("Data Rate", value, capsys)

    for quantity, rate in expected.items():
        assert_quantity(values[quantity], rate, "data_rate")


def test_b_constant_kelvin(capsys):
    values = normalized_values("B Constant (25°C/85°C)", "3434K", capsys)

    assert_quantity(values["temperature"], 3434.0, "kelvin")

    values = normalized_values("B Constant (25°C/85°C)", "-", capsys)

    assert_quantity(values["temperature"], "NaN", "kelvin")

    values = normalized_values("B Constant (25°C/50°C)", "3450K, 3950K", capsys)

    assert_quantity(values["temperature 1"], 3450.0, "kelvin")
    assert_quantity(values["temperature 2"], 3950.0, "kelvin")


def test_holding_temperature(capsys):
    values = normalized_values("Holding Temperature", "76℃", capsys)

    assert_quantity(values["temperature"], 76, "temperature")


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
@pytest.mark.parametrize("key", ["Viewing Angle", "Differential Phase"])
def test_angle_values(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, angle in expected.items():
        assert_quantity(values[quantity], angle, "angle")


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
    ],
)
def test_flexible_percentage_values(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for quantity, percentage in expected.items():
        assert_quantity(values[quantity], percentage, "percentage")


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
    ],
)
@pytest.mark.parametrize("key", ["Wire Gauge - MM2", "Wire Gauge - Sqmm"])
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
        ("1/0", {"awg 1": 0}),
        ("2/0~10", {"awg 1 min": -1, "awg 1 max": 10.0}),
        ("3/0~500", {"awg 1 min": -2, "awg 1 max": 500.0}),
        ("-", {"awg 1": "NaN"}),
    ],
)
def test_wire_gauge_awg(value, expected, capsys):
    values = normalized_values("Wire Gauge - Awg", value, capsys)

    for quantity, awg in expected.items():
        assert_quantity(values[quantity], awg, "awg")


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
    ],
)
def test_input_offset_voltage_drift(value, expected, capsys):
    values = normalized_values("Input Offset Voltage Drift(VOS TC)", value, capsys)

    for quantity, drift in expected.items():
        assert_quantity(values[quantity], drift, "voltage_temperature_drift")


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
        ("Return Loss (Min)", "9.5dB", [9.5]),
        ("Output Return Loss", "13.5dB", [13.5]),
        ("Input Return Loss", "12.5dB", [12.5]),
        ("Sound Pressure Level(Spl)", "95dB", [95.0]),
        ("Sound Pressure Level(Spl)", "83dB@0.1W,10cm", [83.0]),
    ],
)
def test_decibel_lists(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for index, level in enumerate(expected, start=1):
        assert_quantity(values[f"level {index}"], level, "decibel")


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
    ("key", "value", "expected"),
    [
        ("IP3", "28dBm", [28.0]),
        ("IP3", "+41.9dBm", [41.9]),
        ("P1d B", "-25dBm", [-25.0]),
    ],
)
def test_decibel_milliwatt_values(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for index, level in enumerate(expected, start=1):
        assert_quantity(values[f"level {index}"], level, "decibel_milliwatt")


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
        ("Body Length", "168mm", 0.168),
        ("Body Width", "76mm", 0.076),
        ("Thickness", "0.06mm", 0.00006),
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
        ("Diode Reverse Recovery Time (Trr)", "44ns", {"time": 44e-9}),
        ("Td(on)", "30ns, 31.6ns", {"time 1": 30e-9, "time 2": 31.6e-9}),
        ("Setup Time", "6ns", {"time": 6e-9}),
        ("Setup Time", "20ns, 10ns, 7.5ns", {"time 1": 20e-9, "time 2": 10e-9, "time 3": 7.5e-9}),
        ("Acquisition Time", "20us", {"time": 20e-6}),
        ("Hold Settling Time", "0.165us", {"time": 0.165e-6}),
        ("Page Programming Time (Tpp)", "90ns", {"time": 90e-9}),
        ("Page Programming Time (Tpp)", "4ms, 8ms", {"time 1": 0.004, "time 2": 0.008}),
        ("Turn Off Delay Time (Td(Off))", "13.5us", {"time": 13.5e-6}),
        ("Thermal Time Constant", "1.43min", {"time": 85.8}),
        ("Thermal Time Constant", "3s, 700ms", {"time 1": 3.0, "time 2": 0.7}),
        ("Hold Time", "-300ps", {"time": -300e-12}),
        ("Hold Time", "20ns, 10ns, 7.5ns", {"time 1": 20e-9, "time 2": 10e-9, "time 3": 7.5e-9}),
        ("Phase Jitter", "500fs", {"time": 500e-15}),
        ("Phase Jitter", "1ps, 200fs", {"time 1": 1e-12, "time 2": 200e-15}),
        ("Lifetime", "18000hrs@85℃", {"time": 18000 * 3600}),
        ("Lifetime @ Temperature", "10000hrs@105℃", {"time": 10000 * 3600}),
        ("Load Life", "4000hrs@125℃", {"time": 4000 * 3600}),
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
