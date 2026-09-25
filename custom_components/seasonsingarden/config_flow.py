"""Config and options flows for Seasons In Garden."""

from __future__ import annotations

from collections.abc import Mapping
import logging
import re
from typing import Any

from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import ATTR_DEVICE_CLASS, ATTR_UNIT_OF_MEASUREMENT
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
import voluptuous as vol

from .api import CannotConnect, InvalidAuth, SeasonsInGardenClient
from .categories import CATEGORIES, candidate_categories
from .const import (
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
    DEFAULT_INTERVAL_MINUTES,
    DOMAIN,
    FIELD_NAME_MAX_LENGTH,
    MAX_INTERVAL_MINUTES,
    MAX_SENSORS,
    MIN_INTERVAL_MINUTES,
)

_LOGGER = logging.getLogger(__name__)

CONF_ENTITIES = "entities"
CONF_ADVANCED = "advanced"

FIELD_NAME_PATTERN = re.compile(rf"^[A-Za-z0-9_-]{{1,{FIELD_NAME_MAX_LENGTH}}}$")

_PASSWORD = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


async def _async_validate(
    hass: HomeAssistant, host: str, access_key: str, secret_key: str, device_name: str
) -> dict[str, str]:
    """Return form errors for the credentials, empty when they work."""
    client = SeasonsInGardenClient(
        async_get_clientsession(hass), host, access_key, secret_key
    )
    try:
        await client.async_validate(device_name)
    except InvalidAuth:
        return {"base": "invalid_auth"}
    except CannotConnect:
        return {"base": "cannot_connect"}
    except Exception:
        _LOGGER.exception("Unexpected error while validating the API key")
        return {"base": "unknown"}
    return {}


@callback
def _eligible_entities(hass: HomeAssistant) -> list[str]:
    """Return sensor entities whose unit fits at least one category."""
    registry = er.async_get(hass)
    eligible = []
    for state in hass.states.async_all(SENSOR_DOMAIN):
        entry = registry.async_get(state.entity_id)
        if entry is not None and entry.platform == DOMAIN:
            continue
        if candidate_categories(
            state.attributes.get(ATTR_DEVICE_CLASS),
            state.attributes.get(ATTR_UNIT_OF_MEASUREMENT),
        ):
            eligible.append(state.entity_id)
    return sorted(eligible)


def _default_field_name(entity_id: str) -> str:
    object_id = entity_id.split(".", 1)[-1]
    return re.sub(r"[^A-Za-z0-9_-]", "_", object_id)[:FIELD_NAME_MAX_LENGTH]


class _SensorSelectionFlow:
    """Steps shared by the config and options flows to pick sensors.

    The `sensors` step selects up to MAX_SENSORS entities and the upload
    interval; `map_sensors` then sets the category and field name of all of
    them on one form.
    """

    hass: HomeAssistant
    async_show_form: Any
    async_abort: Any

    _interval: int = DEFAULT_INTERVAL_MINUTES
    _existing: dict[str, dict[str, str]]
    _selected: list[str]

    def _init_selection(self, options: Mapping[str, Any]) -> None:
        self._interval = options.get(CONF_INTERVAL, DEFAULT_INTERVAL_MINUTES)
        self._existing = {
            sensor[CONF_ENTITY_ID]: sensor for sensor in options.get(CONF_SENSORS, [])
        }
        self._selected = []

    async def _async_finish_selection(
        self, interval: int, sensors: list[dict[str, str]]
    ) -> ConfigFlowResult:
        raise NotImplementedError

    async def async_step_sensors(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select the sensors to send and the upload interval."""
        errors: dict[str, str] = {}
        if user_input is not None:
            selected: list[str] = user_input[CONF_ENTITIES]
            if not selected:
                errors[CONF_ENTITIES] = "no_sensors"
            elif len(selected) > MAX_SENSORS:
                errors[CONF_ENTITIES] = "too_many_sensors"
            else:
                self._interval = int(user_input[CONF_INTERVAL])
                self._selected = selected
                return await self.async_step_map_sensors()

        eligible = _eligible_entities(self.hass)
        # Keep previously chosen sensors selectable even if they are
        # currently unavailable and missing their unit.
        include = sorted({*eligible, *self._existing})
        if not include:
            return self.async_abort(reason="no_eligible_sensors")

        default = user_input[CONF_ENTITIES] if user_input else list(self._existing)
        schema = vol.Schema(
            {
                vol.Required(CONF_ENTITIES, default=default): EntitySelector(
                    EntitySelectorConfig(include_entities=include, multiple=True)
                ),
                vol.Required(CONF_INTERVAL, default=self._interval): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_INTERVAL_MINUTES,
                        max=MAX_INTERVAL_MINUTES,
                        step=1,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="min",
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="sensors",
            data_schema=schema,
            errors=errors,
            description_placeholders={"max_sensors": str(MAX_SENSORS)},
        )

    async def async_step_map_sensors(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the category and field name of every selected sensor."""
        errors: dict[str, str] = {}
        error_sensor = ""

        if user_input is not None:
            mapped: list[dict[str, str]] = []
            for key, entity_id in self._section_keys():
                field_name = user_input[key][CONF_FIELD_NAME].strip()
                error = None
                if not FIELD_NAME_PATTERN.match(field_name):
                    error = "invalid_field_name"
                elif any(m[CONF_FIELD_NAME] == field_name for m in mapped):
                    error = "duplicate_field_name"
                if error:
                    # Fields inside sections cannot show their own errors, so
                    # the form-level error names the sensor instead.
                    errors["base"] = error
                    error_sensor = self._sensor_name(entity_id)
                    break
                mapped.append(
                    {
                        CONF_ENTITY_ID: entity_id,
                        CONF_CATEGORY: user_input[key][CONF_CATEGORY],
                        CONF_FIELD_NAME: field_name,
                    }
                )
            else:
                return await self._async_finish_selection(self._interval, mapped)

        fields: dict[vol.Marker, Any] = {}
        placeholders = {"error_sensor": error_sensor}
        for key, entity_id in self._section_keys():
            candidates, category, field_name = self._sensor_defaults(entity_id)
            if user_input is not None:
                category = user_input[key][CONF_CATEGORY]
                field_name = user_input[key][CONF_FIELD_NAME]
            fields[vol.Required(key)] = section(
                vol.Schema(
                    {
                        vol.Required(CONF_CATEGORY, default=category): SelectSelector(
                            SelectSelectorConfig(
                                options=candidates,
                                mode=SelectSelectorMode.DROPDOWN,
                                translation_key="category",
                            )
                        ),
                        vol.Required(
                            CONF_FIELD_NAME, default=field_name
                        ): TextSelector(),
                    }
                ),
                {"collapsed": False},
            )
            placeholders[key] = self._sensor_title(entity_id)

        return self.async_show_form(
            step_id="map_sensors",
            data_schema=vol.Schema(fields),
            errors=errors,
            description_placeholders=placeholders,
        )

    def _section_keys(self) -> list[tuple[str, str]]:
        # Section keys are fixed (sensor_1..sensor_N) so their titles can be
        # translated; the sensor name is filled in through a placeholder.
        return [(f"sensor_{i}", e) for i, e in enumerate(self._selected, start=1)]

    def _sensor_name(self, entity_id: str) -> str:
        state = self.hass.states.get(entity_id)
        return state.name if state else entity_id

    def _sensor_title(self, entity_id: str) -> str:
        state = self.hass.states.get(entity_id)
        if state is None:
            return entity_id
        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) or ""
        return f"{state.name} ({f'{state.state} {unit}'.strip()})"

    def _sensor_defaults(self, entity_id: str) -> tuple[list[str], str, str]:
        """Return category choices, default category and default field name."""
        state = self.hass.states.get(entity_id)
        candidates = (
            candidate_categories(
                state.attributes.get(ATTR_DEVICE_CLASS),
                state.attributes.get(ATTR_UNIT_OF_MEASUREMENT),
            )
            if state
            else []
        )
        existing = self._existing.get(entity_id, {})
        if not candidates:
            candidates = [existing[CONF_CATEGORY]] if existing else list(CATEGORIES)
        category = existing.get(CONF_CATEGORY)
        if category not in candidates:
            category = candidates[0]
        field_name = existing.get(CONF_FIELD_NAME, _default_field_name(entity_id))
        return candidates, category, field_name


class SeasonsInGardenConfigFlow(_SensorSelectionFlow, ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Seasons In Garden."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._data: dict[str, str] = {}
        self._init_selection({})

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlowHandler:
        """Return the options flow."""
        return OptionsFlowHandler()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Enter the device name and API key pair."""
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {
                CONF_DEVICE_NAME: user_input[CONF_DEVICE_NAME].strip(),
                CONF_ACCESS_KEY: user_input[CONF_ACCESS_KEY].strip(),
                CONF_SECRET_KEY: user_input[CONF_SECRET_KEY].strip(),
                CONF_HOST: user_input.get(CONF_ADVANCED, {})
                .get(CONF_HOST, DEFAULT_HOST)
                .strip(),
            }
            await self.async_set_unique_id(data[CONF_ACCESS_KEY])
            self._abort_if_unique_id_configured()
            errors = await _async_validate(
                self.hass,
                data[CONF_HOST],
                data[CONF_ACCESS_KEY],
                data[CONF_SECRET_KEY],
                data[CONF_DEVICE_NAME],
            )
            if not errors:
                self._data = data
                return await self.async_step_sensors()

        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE_NAME): str,
                vol.Required(CONF_ACCESS_KEY): str,
                vol.Required(CONF_SECRET_KEY): _PASSWORD,
                vol.Required(CONF_ADVANCED): section(
                    vol.Schema({vol.Required(CONF_HOST, default=DEFAULT_HOST): str}),
                    {"collapsed": True},
                ),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                {k: v for k, v in (user_input or {}).items() if k != CONF_SECRET_KEY},
            ),
            errors=errors,
        )

    async def _async_finish_selection(
        self, interval: int, sensors: list[dict[str, str]]
    ) -> ConfigFlowResult:
        return self.async_create_entry(
            title=self._data[CONF_DEVICE_NAME],
            data=self._data,
            options={CONF_INTERVAL: interval, CONF_SENSORS: sensors},
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle a rejected API key."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Enter a new API key pair."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            access_key = user_input[CONF_ACCESS_KEY].strip()
            secret_key = user_input[CONF_SECRET_KEY].strip()
            if access_key != entry.unique_id and any(
                other.unique_id == access_key
                for other in self._async_current_entries(include_ignore=False)
            ):
                return self.async_abort(reason="already_configured")
            errors = await _async_validate(
                self.hass,
                entry.data.get(CONF_HOST, DEFAULT_HOST),
                access_key,
                secret_key,
                entry.data[CONF_DEVICE_NAME],
            )
            if not errors:
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=access_key,
                    data_updates={
                        CONF_ACCESS_KEY: access_key,
                        CONF_SECRET_KEY: secret_key,
                    },
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ACCESS_KEY, default=entry.data[CONF_ACCESS_KEY]
                    ): str,
                    vol.Required(CONF_SECRET_KEY): _PASSWORD,
                }
            ),
            errors=errors,
            description_placeholders={"name": entry.title},
        )


class OptionsFlowHandler(_SensorSelectionFlow, OptionsFlowWithReload):
    """Change the sensors to send and the upload interval."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Start from the current options."""
        self._init_selection(self.config_entry.options)
        return await self.async_step_sensors()

    async def _async_finish_selection(
        self, interval: int, sensors: list[dict[str, str]]
    ) -> ConfigFlowResult:
        return self.async_create_entry(
            data={CONF_INTERVAL: interval, CONF_SENSORS: sensors}
        )
