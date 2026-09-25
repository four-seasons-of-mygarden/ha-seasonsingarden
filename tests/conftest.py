"""Fixtures for SeasonsInGarden tests."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.seasonsingarden.const import (
    CONF_ACCESS_KEY,
    CONF_CATEGORY,
    CONF_DEVICE_NAME,
    CONF_ENTITY_ID,
    CONF_FIELD_NAME,
    CONF_HOST,
    CONF_INTERVAL,
    CONF_SECRET_KEY,
    CONF_SENSORS,
    DEFAULT_HOST,
    DOMAIN,
)

ACCESS_KEY = "test-access-key"
SECRET_KEY = "test-secret-key"
DEVICE_NAME = "베란다 화분"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading the integration from custom_components."""


@pytest.fixture
def mock_validate() -> Generator[AsyncMock]:
    """Patch credential validation."""
    with patch(
        "custom_components.seasonsingarden.config_flow.SeasonsInGardenClient.async_validate",
    ) as mock:
        yield mock


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Skip setting up the entry after a config flow."""
    with patch(
        "custom_components.seasonsingarden.async_setup_entry", return_value=True
    ) as mock:
        yield mock


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Return an entry sending one temperature and one humidity sensor."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=DEVICE_NAME,
        unique_id=ACCESS_KEY,
        data={
            CONF_DEVICE_NAME: DEVICE_NAME,
            CONF_ACCESS_KEY: ACCESS_KEY,
            CONF_SECRET_KEY: SECRET_KEY,
            CONF_HOST: DEFAULT_HOST,
        },
        options={
            CONF_INTERVAL: 5,
            CONF_SENSORS: [
                {
                    CONF_ENTITY_ID: "sensor.living_temperature",
                    CONF_CATEGORY: "01",
                    CONF_FIELD_NAME: "temp",
                },
                {
                    CONF_ENTITY_ID: "sensor.living_humidity",
                    CONF_CATEGORY: "02",
                    CONF_FIELD_NAME: "humidity",
                },
            ],
        },
    )


def set_sensor_states(hass: HomeAssistant) -> None:
    """Create sensor states covering several categories."""
    hass.states.async_set(
        "sensor.living_temperature",
        "75.2",
        {"device_class": "temperature", "unit_of_measurement": "°F"},
    )
    hass.states.async_set(
        "sensor.living_humidity",
        "58",
        {"device_class": "humidity", "unit_of_measurement": "%"},
    )
    hass.states.async_set(
        "sensor.pot_moisture",
        "41",
        {"device_class": "moisture", "unit_of_measurement": "%"},
    )
    hass.states.async_set(
        "sensor.grow_light_ppfd", "350", {"unit_of_measurement": "µmol/m²/s"}
    )
    hass.states.async_set(
        "sensor.living_illuminance",
        "12000",
        {"device_class": "illuminance", "unit_of_measurement": "lx"},
    )
    hass.states.async_set(
        "sensor.phone_battery",
        "80",
        {"device_class": "battery", "unit_of_measurement": "%"},
    )
