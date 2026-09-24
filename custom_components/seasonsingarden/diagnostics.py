"""Diagnostics support for Seasons In Garden."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import SeasonsInGardenConfigEntry
from .const import CONF_ACCESS_KEY, CONF_SECRET_KEY

TO_REDACT = {CONF_ACCESS_KEY, CONF_SECRET_KEY}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SeasonsInGardenConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    return {
        "data": async_redact_data(entry.data, TO_REDACT),
        "options": dict(entry.options),
        "upload": entry.runtime_data.as_diagnostics(),
    }
