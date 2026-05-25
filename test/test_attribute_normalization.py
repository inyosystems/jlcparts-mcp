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
