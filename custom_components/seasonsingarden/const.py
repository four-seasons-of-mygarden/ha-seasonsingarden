"""Constants for the SeasonsInGarden integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "seasonsingarden"

DEFAULT_HOST: Final = "collector.seasonsingarden.life"
API_PATH: Final = "/api/sensor/v1/data"
API_METHOD: Final = "POST"

CONF_ACCESS_KEY: Final = "access_key"
CONF_SECRET_KEY: Final = "secret_key"
CONF_DEVICE_NAME: Final = "device_name"
CONF_HOST: Final = "host"

CONF_SENSORS: Final = "sensors"
CONF_INTERVAL: Final = "interval"
CONF_ENTITY_ID: Final = "entity_id"
CONF_FIELD_NAME: Final = "field_nm"
CONF_CATEGORY: Final = "category"

# The service stores one value per sensor every 3 minutes, so shorter
# intervals only add requests that are accepted but not recorded.
DEFAULT_INTERVAL_MINUTES: Final = 5
MIN_INTERVAL_MINUTES: Final = 3
MAX_INTERVAL_MINUTES: Final = 60

MAX_SENSORS: Final = 10
FIELD_NAME_MAX_LENGTH: Final = 50
