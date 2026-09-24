"""Send Home Assistant sensor data to Seasons In Garden."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SeasonsInGardenClient
from .const import CONF_ACCESS_KEY, CONF_HOST, CONF_SECRET_KEY, DEFAULT_HOST
from .uploader import SensorUploader

PLATFORMS: list[Platform] = [Platform.SENSOR]

type SeasonsInGardenConfigEntry = ConfigEntry[SensorUploader]


async def async_setup_entry(
    hass: HomeAssistant, entry: SeasonsInGardenConfigEntry
) -> bool:
    """Set up Seasons In Garden from a config entry."""
    client = SeasonsInGardenClient(
        async_get_clientsession(hass),
        entry.data.get(CONF_HOST, DEFAULT_HOST),
        entry.data[CONF_ACCESS_KEY],
        entry.data[CONF_SECRET_KEY],
    )
    uploader = SensorUploader(hass, entry, client)
    entry.runtime_data = uploader

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(uploader.async_start())
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: SeasonsInGardenConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
