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
        ("Resistor on-State", "34mΩ", {"resistance": 0.034}),
        ("Resistor on-State", "10mΩ;30mΩ", {"resistance 1": 0.01, "resistance 2": 0.03}),
    ],
)
def test_resistance_list_attributes(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)

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
    ("key", "value", "quantity", "expected", "unit"),
    [
        ("Sampling Rate", "352800Hz", "frequency", 352800.0, "frequency"),
        ("-3d B Bandwidth", "14kHz", "frequency", 14000.0, "frequency"),
        ("-3d B Bandwidth", "1.7GHz", "frequency", 1.7e9, "frequency"),
        ("Non-Repetitive Peak Forward Surge Current", "1.95kA", "current", 1950.0, "current"),
        ("Quiescent Supply Current", "50nA", "current", 50e-9, "current"),
        ("Input Offset Current(IOS)", "8nA", "current", 8e-9, "current"),
        ("Receive Current", "46mA", "current", 0.046, "current"),
        ("Current - Collector(Ic)", "4A", "current", 4.0, "current"),
        ("Supply Current (Iq)", "1uA", "current", 1e-6, "current"),
        ("Current - Input Bias(Ib)", "1.2pA", "current", 1.2e-12, "current"),
        ("Current - Output Low(Iol)", "2.5mA", "current", 0.0025, "current"),
        ("Current - Output High(Ioh)", "-6mA", "current", -0.006, "current"),
        ("Current - Surge(Itsm@F)", "284A@60Hz", "current", 284.0, "current"),
        ("Send Current", "266mA", "current", 0.266, "current"),
        ("Current of Transmitting", "21mA", "current", 0.021, "current"),
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


def test_switching_frequency_lists(capsys):
    values = normalized_values("Frequency - Switching", "2.5MHz, 1.25MHz", capsys)

    assert_quantity(values["frequency 1"], 2.5e6, "frequency")
    assert_quantity(values["frequency 2"], 1.25e6, "frequency")

    values = normalized_values("Frequency - Switching", "100kHz~1MHz, 340kHz~520kHz", capsys)

    assert_quantity(values["frequency 1 min"], 100e3, "frequency")
    assert_quantity(values["frequency 1 max"], 1e6, "frequency")
    assert_quantity(values["frequency 2 min"], 340e3, "frequency")
    assert_quantity(values["frequency 2 max"], 520e3, "frequency")


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
    ("key", "value", "expected"),
    [
        ("Non-Repetitive Peak Forward Surge Current", "120A, 240A", [120.0, 240.0]),
        ("Quiescent Supply Current", "2mA, 1mA, 600uA", [0.002, 0.001, 0.0006]),
        ("Input Offset Current(IOS)", "2nA, 5nA", [2e-9, 5e-9]),
        ("Receive Current", "3.5mA, 5mA", [0.0035, 0.005]),
        ("Current - Collector(Ic)", "5A, 4.45A", [5.0, 4.45]),
        ("Current - Output Low(Iol)", "2.6mA, 6.8mA, 1mA", [0.0026, 0.0068, 0.001]),
        ("Current - Output High(Ioh)", "1mA, 2.6mA, 6.8mA", [0.001, 0.0026, 0.0068]),
        ("Current - Surge(Itsm@F)", "170A@60Hz, 155A@50Hz", [170.0, 155.0]),
        ("Send Current", "9.5mA, 16mA", [0.0095, 0.016]),
        ("Current of Transmitting", "7.1mA, 3.5mA", [0.0071, 0.0035]),
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


def test_number_of_io_count(capsys):
    values = normalized_values("Number of I/O", "8", capsys)

    assert_quantity(values["count"], 8, "count")


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
        ("Switch Length", "12.78mm", 0.01278),
        ("Switch Length", "-", "NaN"),
    ],
)
def test_scalar_length_attributes(key, value, expected, capsys):
    values = normalized_values(key, value, capsys)
    assert_quantity(values["length"], expected, "length")


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
