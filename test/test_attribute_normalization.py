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
        ("Single Supply", "2V~36V", (2.0, 36.0)),
        ("Operating Voltage", "±15V", (-15.0, 15.0)),
        ("Operating Voltage", "-15V~15V", (-15.0, 15.0)),
        ("Voltage - Input(DC)", "900mV~5.5V", (0.9, 5.5)),
        ("Voltage - Input(DC)", "45V", 45.0),
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
    ("key", "value", "quantity", "expected", "unit"),
    [
        ("Sampling Rate", "352800Hz", "frequency", 352800.0, "frequency"),
        ("Non-Repetitive Peak Forward Surge Current", "1.95kA", "current", 1950.0, "current"),
        ("Quiescent Supply Current", "50nA", "current", 50e-9, "current"),
    ],
)
def test_scalar_frequency_and_current_attributes(key, value, quantity, expected, unit, capsys):
    values = normalized_values(key, value, capsys)
    assert_quantity(values[quantity], expected, unit)


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


def test_sampling_rate_time_range(capsys):
    values = normalized_values("Sampling Rate", "0.1ms~23.5ms", capsys)

    assert_quantity(values["time min"], 0.0001, "time")
    assert_quantity(values["time max"], 0.0235, "time")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Non-Repetitive Peak Forward Surge Current", "120A, 240A", [120.0, 240.0]),
        ("Quiescent Supply Current", "2mA, 1mA, 600uA", [0.002, 0.001, 0.0006]),
    ],
)
def test_current_lists(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for index, current in enumerate(expected, start=1):
        assert_quantity(values[f"current {index}"], current, "current")


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
def test_luminous_intensity(value, expected, capsys):
    values = normalized_values("Luminous Intensity", value, capsys)

    for quantity, intensity in expected.items():
        assert_quantity(values[quantity], intensity, "luminous_intensity")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Energy", "900mJ", 0.9),
        ("Energy", "3.5kJ", 3500.0),
        ("Energy (Max)", "0.05J", 0.05),
        ("Energy (Max)", "-", "NaN"),
    ],
)
def test_energy_values(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)
    assert_quantity(values["energy"], expected, "energy")


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("Attenuation", "20dB", [20.0]),
        ("Attenuation", "-30dB, -28dB, -38dB", [-30.0, -28.0, -38.0]),
        ("Power Supply Rejection Ratio (Psrr)", "125dB, 110dB", [125.0, 110.0]),
        ("Power Supply Rejection Ratio (Psrr)", "-", ["NaN"]),
    ],
)
def test_decibel_lists(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

    for index, level in enumerate(expected, start=1):
        assert_quantity(values[f"level {index}"], level, "decibel")


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
        ("3.43mm", {"length": 0.00343}),
        ("1.27mm~1.8mm", {"length min": 0.00127, "length max": 0.0018}),
        ("-", {"length": "NaN"}),
    ],
)
def test_insulation_od_lengths(value, expected, capsys):
    values = normalized_values("Insulation Od", value, capsys)

    for quantity, length in expected.items():
        assert_quantity(values[quantity], length, "length")


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
