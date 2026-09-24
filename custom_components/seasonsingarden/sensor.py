"""Diagnostic sensors that report the upload status."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SeasonsInGardenConfigEntry
from .const import CONF_DEVICE_NAME, DOMAIN
from .uploader import SensorUploader, UploadResult

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class UploadSensorEntityDescription(SensorEntityDescription):
    """Describes an upload status sensor."""

    value_fn: Callable[[SensorUploader], str | int | datetime | None]


SENSORS: tuple[UploadSensorEntityDescription, ...] = (
    UploadSensorEntityDescription(
        key="last_success",
        translation_key="last_success",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda uploader: uploader.last_success,
    ),
    UploadSensorEntityDescription(
        key="last_result",
        translation_key="last_result",
        device_class=SensorDeviceClass.ENUM,
        options=[result.value for result in UploadResult],
        value_fn=lambda uploader: uploader.last_result,
    ),
    UploadSensorEntityDescription(
        key="last_sent_count",
        translation_key="last_sent_count",
        value_fn=lambda uploader: uploader.last_sent_count,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SeasonsInGardenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the upload status sensors."""
    async_add_entities(
        UploadStatusSensor(entry, description) for description in SENSORS
    )


class UploadStatusSensor(SensorEntity):
    """Reports one aspect of the last upload attempt."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    entity_description: UploadSensorEntityDescription

    def __init__(
        self,
        entry: SeasonsInGardenConfigEntry,
        description: UploadSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        self.entity_description = description
        self._uploader = entry.runtime_data
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data[CONF_DEVICE_NAME],
            manufacturer="Seasons In Garden",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self) -> str | int | datetime | None:
        """Return the current value."""
        return self.entity_description.value_fn(self._uploader)

    async def async_added_to_hass(self) -> None:
        """Update when an upload attempt finishes."""
        self.async_on_remove(
            self._uploader.async_add_listener(self.async_write_ha_state)
        )
