"""Tests for periodic uploads and status sensors."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.seasonsingarden.const import DEFAULT_HOST, DOMAIN

from .conftest import ACCESS_KEY, SECRET_KEY, set_sensor_states

URL = f"https://{DEFAULT_HOST}/api/sensor/v1/data"


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _tick(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.tick(timedelta(minutes=5))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_upload_after_interval(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Converted states are sent once per interval, not at startup."""
    set_sensor_states(hass)
    aioclient_mock.post(URL, text="데이터 수신 성공")
    await _setup(hass, config_entry)
    assert aioclient_mock.call_count == 0

    await _tick(hass, freezer)
    assert aioclient_mock.call_count == 1
    body = aioclient_mock.mock_calls[0][2]
    assert body["sensors"] == [
        {"field_nm": "temp", "category": "01", "data": "24"},
        {"field_nm": "humidity", "category": "02", "data": "58"},
    ]

    result = next(
        s
        for s in hass.states.async_all("sensor")
        if s.entity_id.endswith("last_upload_result")
    )
    assert result.state == "success"
    count = next(
        s
        for s in hass.states.async_all("sensor")
        if s.entity_id.endswith("sensors_sent")
    )
    assert count.state == "2"


async def test_skips_unavailable_states(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Unavailable sensors and wrong units are left out."""
    set_sensor_states(hass)
    hass.states.async_set("sensor.living_humidity", "unavailable")
    hass.states.async_set(
        "sensor.living_temperature", "20", {"unit_of_measurement": "W"}
    )
    aioclient_mock.post(URL, text="ok")
    await _setup(hass, config_entry)

    await _tick(hass, freezer)
    assert aioclient_mock.call_count == 0
    result = next(
        s
        for s in hass.states.async_all("sensor")
        if s.entity_id.endswith("last_upload_result")
    )
    assert result.state == "no_data"


async def test_auth_failure_starts_reauth(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A rejected key stops uploads and asks for a new key."""
    set_sensor_states(hass)
    aioclient_mock.post(URL, status=401, text="Invalid Signature")
    await _setup(hass, config_entry)

    await _tick(hass, freezer)
    await _tick(hass, freezer)
    assert aioclient_mock.call_count == 1
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["context"]["source"] for flow in flows] == ["reauth"]


async def test_server_error_retries(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Server errors are retried on the next interval."""
    set_sensor_states(hass)
    aioclient_mock.post(URL, status=500)
    await _setup(hass, config_entry)

    await _tick(hass, freezer)
    await _tick(hass, freezer)
    assert aioclient_mock.call_count == 2


async def test_unload(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """The entry unloads cleanly."""
    await _setup(hass, config_entry)
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_diagnostics_redacts_keys(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    config_entry: MockConfigEntry,
) -> None:
    """Diagnostics never contain the key pair."""
    set_sensor_states(hass)
    await _setup(hass, config_entry)
    diagnostics = await get_diagnostics_for_config_entry(
        hass, hass_client, config_entry
    )
    text = str(diagnostics)
    assert ACCESS_KEY not in text
    assert SECRET_KEY not in text
    assert diagnostics["upload"]["pending_readings"][0]["field_nm"] == "temp"
