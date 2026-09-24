"""Tests for the config and options flows."""

from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.seasonsingarden.api import CannotConnect, InvalidAuth
from custom_components.seasonsingarden.const import (
    CONF_ACCESS_KEY,
    CONF_DEVICE_NAME,
    CONF_HOST,
    CONF_SECRET_KEY,
    DEFAULT_HOST,
    DOMAIN,
)

from .conftest import ACCESS_KEY, DEVICE_NAME, SECRET_KEY, set_sensor_states

USER_INPUT = {
    CONF_DEVICE_NAME: DEVICE_NAME,
    CONF_ACCESS_KEY: ACCESS_KEY,
    CONF_SECRET_KEY: SECRET_KEY,
    "advanced": {CONF_HOST: DEFAULT_HOST},
}


async def test_user_flow(
    hass: HomeAssistant, mock_validate: AsyncMock, mock_setup_entry: AsyncMock
) -> None:
    """Credentials, sensor selection and mapping create an entry."""
    set_sensor_states(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["step_id"] == "sensors"
    include = result["data_schema"].schema["entities"].config["include_entities"]
    assert include == [
        "sensor.grow_light_ppfd",
        "sensor.living_humidity",
        "sensor.living_temperature",
        "sensor.pot_moisture",
    ]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"entities": ["sensor.pot_moisture", "sensor.grow_light_ppfd"], "interval": 10},
    )
    assert result["step_id"] == "map_sensor"
    assert result["description_placeholders"]["position"] == "1/2"
    schema = result["data_schema"].schema
    category_key = next(k for k in schema if k == "category")
    assert category_key.default() == "07"
    assert schema["category"].config["options"] == ["07", "02"]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"category": "07", "field_nm": "soil_moisture"}
    )
    assert result["step_id"] == "map_sensor"
    assert result["description_placeholders"]["position"] == "2/2"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"category": "09", "field_nm": "ppfd"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == DEVICE_NAME
    assert result["data"] == {
        CONF_DEVICE_NAME: DEVICE_NAME,
        CONF_ACCESS_KEY: ACCESS_KEY,
        CONF_SECRET_KEY: SECRET_KEY,
        CONF_HOST: DEFAULT_HOST,
    }
    assert result["options"] == {
        "interval": 10,
        "sensors": [
            {
                "entity_id": "sensor.pot_moisture",
                "category": "07",
                "field_nm": "soil_moisture",
            },
            {
                "entity_id": "sensor.grow_light_ppfd",
                "category": "09",
                "field_nm": "ppfd",
            },
        ],
    }
    assert result["result"].unique_id == ACCESS_KEY
    mock_validate.assert_awaited_once_with(DEVICE_NAME)


@pytest.mark.parametrize(
    ("side_effect", "error"),
    [
        (InvalidAuth, "invalid_auth"),
        (CannotConnect, "cannot_connect"),
        (ValueError, "unknown"),
    ],
)
async def test_user_flow_errors(
    hass: HomeAssistant,
    mock_validate: AsyncMock,
    mock_setup_entry: AsyncMock,
    side_effect: type[Exception],
    error: str,
) -> None:
    """Validation errors are shown and the user can retry."""
    set_sensor_states(hass)
    mock_validate.side_effect = side_effect
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["errors"] == {"base": error}

    mock_validate.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["step_id"] == "sensors"


async def test_user_flow_already_configured(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_validate: AsyncMock
) -> None:
    """The same Access Key cannot be added twice."""
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    mock_validate.assert_not_awaited()


async def test_user_flow_no_eligible_sensors(
    hass: HomeAssistant, mock_validate: AsyncMock
) -> None:
    """The flow aborts when no sensor can be sent."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_eligible_sensors"


async def test_sensor_count_limits(
    hass: HomeAssistant, mock_validate: AsyncMock
) -> None:
    """At least one and at most ten sensors can be selected."""
    for i in range(11):
        hass.states.async_set(
            f"sensor.temp_{i}",
            "20",
            {"device_class": "temperature", "unit_of_measurement": "°C"},
        )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"entities": [], "interval": 5}
    )
    assert result["errors"] == {"entities": "no_sensors"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"entities": [f"sensor.temp_{i}" for i in range(11)], "interval": 5},
    )
    assert result["errors"] == {"entities": "too_many_sensors"}


async def test_field_name_validation(
    hass: HomeAssistant, mock_validate: AsyncMock
) -> None:
    """Field names must be valid and unique within the entry."""
    set_sensor_states(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "entities": ["sensor.living_temperature", "sensor.pot_moisture"],
            "interval": 5,
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"category": "01", "field_nm": "거실 온도"}
    )
    assert result["errors"] == {"field_nm": "invalid_field_name"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"category": "01", "field_nm": "temp"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"category": "07", "field_nm": "temp"}
    )
    assert result["errors"] == {"field_nm": "duplicate_field_name"}


async def test_options_flow(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """The options flow starts from the current mapping."""
    set_sensor_states(hass)
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["step_id"] == "sensors"
    entities_key = next(k for k in result["data_schema"].schema if k == "entities")
    assert entities_key.default() == [
        "sensor.living_temperature",
        "sensor.living_humidity",
    ]

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"entities": ["sensor.living_temperature"], "interval": 15},
    )
    field_key = next(k for k in result["data_schema"].schema if k == "field_nm")
    assert field_key.default() == "temp"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"category": "13", "field_nm": "soil_temp"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert config_entry.options == {
        "interval": 15,
        "sensors": [
            {
                "entity_id": "sensor.living_temperature",
                "category": "13",
                "field_nm": "soil_temp",
            }
        ],
    }


async def test_reauth(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_validate: AsyncMock,
    mock_setup_entry: AsyncMock,
) -> None:
    """A new key pair replaces the rejected one."""
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    mock_validate.side_effect = InvalidAuth
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ACCESS_KEY: "new-key", CONF_SECRET_KEY: "wrong"}
    )
    assert result["errors"] == {"base": "invalid_auth"}

    mock_validate.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ACCESS_KEY: "new-key", CONF_SECRET_KEY: "new-secret"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.unique_id == "new-key"
    assert config_entry.data[CONF_ACCESS_KEY] == "new-key"
    assert config_entry.data[CONF_SECRET_KEY] == "new-secret"
