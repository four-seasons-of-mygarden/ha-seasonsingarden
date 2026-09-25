"""Mapping between Home Assistant sensors and SeasonsInGarden categories.

The service accepts a fixed set of measurement categories, each with one
unit. A Home Assistant sensor can be sent when its unit can be converted to
that unit and its device class (if any) matches the measurement.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
import math
from types import MappingProxyType

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import UnitOfPressure, UnitOfTemperature
from homeassistant.util.unit_conversion import (
    ConductivityConverter,
    PressureConverter,
    TemperatureConverter,
)

# Home Assistant uses the Greek small letter mu (U+03BC) in its unit constants,
# while many integrations and templates type the micro sign (U+00B5).
_MICRO_SIGN = "µ"
_GREEK_MU = "μ"

PPFD_UNIT = f"{_GREEK_MU}mol/m²/s"
EC_UNIT = "dS/m"

# Common spellings of µmol/m²/s. Compared after normalize_unit().
_PPFD_SPELLINGS = (
    "μmol/m²/s",
    "μmol/m²s",
    "μmol/m²·s",
    "μmol/(m²·s)",
    "μmol/(m²s)",
    "μmol/s/m²",
    "μmol/s·m²",
    "μmol/(s·m²)",
    "μmolm⁻²s⁻¹",
    "μmols⁻¹m⁻²",
    "μmol·m⁻²·s⁻¹",
)

Converter = Callable[[float, str], float]


def normalize_unit(unit: str | None) -> str | None:
    """Return a canonical spelling of a unit string for comparison."""
    if unit is None:
        return None
    normalized = unit.strip().replace(_MICRO_SIGN, _GREEK_MU)
    if normalized.startswith("umol"):
        normalized = _GREEK_MU + normalized[1:]
    for dot in ("⋅", "∙", "*"):
        normalized = normalized.replace(dot, "·")
    normalized = normalized.replace("m^2", "m²").replace("m2", "m²")
    return normalized.replace(" ", "")


def _identity(value: float, _unit: str) -> float:
    return value


def _to_celsius(value: float, unit: str) -> float:
    return TemperatureConverter.convert(value, unit, UnitOfTemperature.CELSIUS)


def _to_kpa(value: float, unit: str) -> float:
    return PressureConverter.convert(value, unit, UnitOfPressure.KPA)


def _to_ds_per_m(value: float, unit: str) -> float:
    if unit == EC_UNIT:
        return value
    # 1 dS/m equals 1 mS/cm.
    return ConductivityConverter.convert(value, unit, "mS/cm")


@dataclass(frozen=True, slots=True)
class Category:
    """A measurement category accepted by the Open API."""

    code: str
    unit: str
    # The class that makes this category the default choice.
    preferred_device_class: str | None
    # Classes accepted in addition to sensors without a device class.
    device_classes: frozenset[str]
    # Normalized unit -> spelling passed to the converter.
    units: MappingProxyType[str, str]
    converter: Converter

    def accepts(self, device_class: str | None, unit: str | None) -> bool:
        """Return whether a sensor with this class and unit can be sent."""
        if normalize_unit(unit) not in self.units:
            return False
        return device_class is None or device_class in self.device_classes


def _category(
    code: str,
    unit: str,
    device_classes: Iterable[SensorDeviceClass],
    units: Iterable[str],
    converter: Converter = _identity,
) -> Category:
    device_classes = [str(dc) for dc in device_classes]
    return Category(
        code=code,
        unit=unit,
        preferred_device_class=device_classes[0] if device_classes else None,
        device_classes=frozenset(device_classes),
        units=MappingProxyType({normalize_unit(u): str(u) for u in units}),
        converter=converter,
    )


_TEMPERATURE = (SensorDeviceClass.TEMPERATURE,)
# Many soil sensors (for example Tuya Zigbee probes) report soil moisture with
# the humidity device class, so percent sensors of either class fit both.
_HUMIDITY = (SensorDeviceClass.HUMIDITY, SensorDeviceClass.MOISTURE)
_MOISTURE = (SensorDeviceClass.MOISTURE, SensorDeviceClass.HUMIDITY)

CATEGORIES: dict[str, Category] = {
    c.code: c
    for c in (
        _category("01", "°C", _TEMPERATURE, UnitOfTemperature, _to_celsius),
        _category("02", "%", _HUMIDITY, ("%",)),
        _category("07", "%", _MOISTURE, ("%",)),
        _category("09", PPFD_UNIT, (), _PPFD_SPELLINGS),
        _category("10", "°C", _TEMPERATURE, UnitOfTemperature, _to_celsius),
        _category("12", "ppm", (SensorDeviceClass.CO2,), ("ppm",)),
        _category("13", "°C", _TEMPERATURE, UnitOfTemperature, _to_celsius),
        _category("14", "kPa", (SensorDeviceClass.PRESSURE,), UnitOfPressure, _to_kpa),
        _category(
            "15",
            EC_UNIT,
            (SensorDeviceClass.CONDUCTIVITY,),
            (*ConductivityConverter.VALID_UNITS, EC_UNIT),
            _to_ds_per_m,
        ),
    )
}


def candidate_categories(device_class: str | None, unit: str | None) -> list[str]:
    """Return category codes a sensor can be sent as, best match first.

    Categories preferring the sensor's device class come first, so a humidity
    sensor defaults to "02" and a moisture sensor to "07" even though both
    report percent.
    """
    matches = [c for c in CATEGORIES.values() if c.accepts(device_class, unit)]
    matches.sort(key=lambda c: c.preferred_device_class != device_class)
    return [c.code for c in matches]


def convert_state(category: str, state: str, unit: str | None) -> float | None:
    """Convert a sensor state to the category's unit.

    Returns None when the state is not a finite number or the unit no longer
    fits the category.
    """
    cat = CATEGORIES.get(category)
    if cat is None or (source_unit := cat.units.get(normalize_unit(unit))) is None:
        return None
    try:
        value = float(state)
    except ValueError:
        return None
    if not math.isfinite(value):
        return None
    return cat.converter(value, source_unit)


def format_value(value: float) -> str:
    """Format a value for the API, dropping insignificant trailing zeros."""
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return "0" if text == "-0" else text
