"""Periodically sends the selected sensor states to the Open API."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
from enum import StrEnum
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .api import (
    InvalidAuth,
    RequestRejected,
    SeasonsInGardenClient,
    SeasonsInGardenError,
    SensorReading,
)
from .categories import convert_state, format_value
from .const import (
    CONF_CATEGORY,
    CONF_DEVICE_NAME,
    CONF_ENTITY_ID,
    CONF_FIELD_NAME,
    CONF_INTERVAL,
    CONF_SENSORS,
    DEFAULT_INTERVAL_MINUTES,
)

_LOGGER = logging.getLogger(__name__)


class UploadResult(StrEnum):
    """Outcome of the last upload attempt."""

    SUCCESS = "success"
    NO_DATA = "no_data"
    AUTH_FAILED = "auth_failed"
    REJECTED = "rejected"
    ERROR = "error"


class SensorUploader:
    """Collects the configured sensor states and sends them on an interval."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: SeasonsInGardenClient,
    ) -> None:
        """Initialize the uploader from the entry's options."""
        self._hass = hass
        self._entry = entry
        self._client = client
        self._device_name: str = entry.data[CONF_DEVICE_NAME]
        self._sensors: list[dict[str, str]] = entry.options.get(CONF_SENSORS, [])
        self._interval = timedelta(
            minutes=entry.options.get(CONF_INTERVAL, DEFAULT_INTERVAL_MINUTES)
        )
        self._lock = asyncio.Lock()
        self._listeners: list[CALLBACK_TYPE] = []
        self._auth_failed = False
        self._warned_entities: set[str] = set()

        self.last_attempt: datetime | None = None
        self.last_success: datetime | None = None
        self.last_result: UploadResult | None = None
        self.last_error: str | None = None
        self.last_sent_count: int = 0

    @property
    def sensor_count(self) -> int:
        """Return the number of configured sensors."""
        return len(self._sensors)

    @callback
    def async_start(self) -> CALLBACK_TYPE:
        """Start the interval timer and return a function that stops it."""
        # The first upload waits one interval so restarts do not send extra
        # values inside the service's 3-minute storage window.
        return async_track_time_interval(
            self._hass,
            self._async_interval_elapsed,
            self._interval,
            name=f"{self._entry.title} upload",
            cancel_on_shutdown=True,
        )

    @callback
    def async_add_listener(self, update_callback: CALLBACK_TYPE) -> Callable[[], None]:
        """Register a callback that runs after every upload attempt."""
        self._listeners.append(update_callback)
        return lambda: self._listeners.remove(update_callback)

    async def _async_interval_elapsed(self, _now: datetime) -> None:
        await self.async_upload()

    async def async_upload(self) -> None:
        """Send the current states once, skipping if an upload is running."""
        if self._auth_failed or self._lock.locked():
            return
        async with self._lock:
            await self._async_upload()
        for update_callback in list(self._listeners):
            update_callback()

    async def _async_upload(self) -> None:
        self.last_attempt = dt_util.utcnow()
        readings = self.collect_readings()
        if not readings:
            self._set_result(UploadResult.NO_DATA, None, 0)
            return

        try:
            await self._client.async_send(self._device_name, readings)
        except InvalidAuth as err:
            # Retrying with the same keys cannot succeed; wait for reauth,
            # which reloads the entry and creates a new uploader.
            self._auth_failed = True
            self._set_result(UploadResult.AUTH_FAILED, str(err), 0)
            _LOGGER.error("Seasons In Garden rejected the API key: %s", err)
            self._entry.async_start_reauth(self._hass)
            return
        except SeasonsInGardenError as err:
            result = (
                UploadResult.REJECTED
                if isinstance(err, RequestRejected)
                else UploadResult.ERROR
            )
            self._set_result(result, str(err), 0)
            _LOGGER.warning("Could not send sensor data: %s", err)
            return

        self.last_success = self.last_attempt
        self._set_result(UploadResult.SUCCESS, None, len(readings))

    def _set_result(
        self, result: UploadResult, error: str | None, sent_count: int
    ) -> None:
        self.last_result = result
        self.last_error = error
        self.last_sent_count = sent_count

    @callback
    def collect_readings(self) -> list[SensorReading]:
        """Return readings for configured sensors with a usable state."""
        readings: list[SensorReading] = []
        for sensor in self._sensors:
            entity_id = sensor[CONF_ENTITY_ID]
            state = self._hass.states.get(entity_id)
            if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
                continue
            unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
            value = convert_state(sensor[CONF_CATEGORY], state.state, unit)
            if value is None:
                self._warn_once(entity_id, state.state, unit)
                continue
            self._warned_entities.discard(entity_id)
            readings.append(
                SensorReading(
                    field_nm=sensor[CONF_FIELD_NAME],
                    category=sensor[CONF_CATEGORY],
                    data=format_value(value),
                )
            )
        return readings

    def _warn_once(self, entity_id: str, state: str, unit: str | None) -> None:
        if entity_id in self._warned_entities:
            return
        self._warned_entities.add(entity_id)
        _LOGGER.warning(
            "Skipping %s: state %r with unit %r cannot be sent as the "
            "configured category",
            entity_id,
            state,
            unit,
        )

    def as_diagnostics(self) -> dict[str, Any]:
        """Return the upload status for diagnostics."""
        return {
            "interval_seconds": self._interval.total_seconds(),
            "last_attempt": self.last_attempt,
            "last_success": self.last_success,
            "last_result": self.last_result,
            "last_error": self.last_error,
            "last_sent_count": self.last_sent_count,
            "pending_readings": [
                {"field_nm": r.field_nm, "category": r.category, "data": r.data}
                for r in self.collect_readings()
            ],
        }
