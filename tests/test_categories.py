"""Tests for category matching and unit conversion."""

from __future__ import annotations

import pytest

from custom_components.seasonsingarden.categories import (
    candidate_categories,
    convert_state,
    format_value,
)


@pytest.mark.parametrize(
    ("device_class", "unit", "expected"),
    [
        ("temperature", "°C", ["01", "10", "13"]),
        ("temperature", "°F", ["01", "10", "13"]),
        (None, "°C", ["01", "10", "13"]),
        ("humidity", "%", ["02", "07"]),
        ("moisture", "%", ["07", "02"]),
        (None, "%", []),
        ("battery", "%", []),
        ("carbon_dioxide", "ppm", ["12"]),
        (None, "µmol/m²/s", ["09"]),
        (None, "μmol/m²/s", ["09"]),
        (None, "umol/m2/s", ["09"]),
        (None, "µmol/s⋅m²", ["09"]),
        ("illuminance", "lx", []),
        ("pressure", "kPa", ["14"]),
        (None, "hPa", ["14"]),
        ("conductivity", "µS/cm", ["15"]),
        (None, "dS/m", ["15"]),
        ("temperature", None, []),
        (None, "W", []),
    ],
)
def test_candidate_categories(
    device_class: str | None, unit: str | None, expected: list[str]
) -> None:
    """Sensors are matched by device class and unit."""
    assert candidate_categories(device_class, unit) == expected


@pytest.mark.parametrize(
    ("category", "state", "unit", "expected"),
    [
        ("01", "24.5", "°C", 24.5),
        ("01", "75.2", "°F", 24.0),
        ("13", "297.15", "K", 24.0),
        ("02", "58", "%", 58.0),
        ("09", "350", "µmol/m²/s", 350.0),
        ("12", "800", "ppm", 800.0),
        ("14", "12.5", "hPa", 1.25),
        ("15", "350", "µS/cm", 0.35),
        ("15", "1.2", "mS/cm", 1.2),
        ("15", "1.2", "dS/m", 1.2),
    ],
)
def test_convert_state(category: str, state: str, unit: str, expected: float) -> None:
    """States are converted to the category's unit."""
    assert convert_state(category, state, unit) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("category", "state", "unit"),
    [
        ("01", "abc", "°C"),
        ("01", "nan", "°C"),
        ("01", "inf", "°C"),
        ("01", "24", "%"),
        ("99", "24", "°C"),
    ],
)
def test_convert_state_rejects(category: str, state: str, unit: str) -> None:
    """Non-numeric states and mismatched units are not sent."""
    assert convert_state(category, state, unit) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [(24.0, "24"), (24.5, "24.5"), (0.35, "0.35"), (1.23456, "1.235"), (-0.0001, "0")],
)
def test_format_value(value: float, expected: str) -> None:
    """Values are sent without insignificant zeros."""
    assert format_value(value) == expected
