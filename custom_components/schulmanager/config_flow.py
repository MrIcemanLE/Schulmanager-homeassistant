from __future__ import annotations

from typing import Any
import logging

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigEntry,
    OptionsFlow,
    ConfigFlowResult,
)
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    CONF_USERNAME,
    CONF_PASSWORD,
    OPT_AUTO_UPDATE_INTERVAL,
    OPT_POLL_INTERVAL,
    OPT_ENABLE_SCHEDULE,
    OPT_ENABLE_HOMEWORK,
    OPT_ENABLE_EXAMS,
    OPT_ENABLE_GRADES,
    OPT_RANGE_PAST_DAYS,
    OPT_RANGE_FUTURE_DAYS,
    OPT_REFRESH_COOLDOWN,
    OPT_DEBUG_DUMPS,
    DEFAULT_OPTIONS,
    MIN_AUTO_UPDATE_INTERVAL,
    MAX_AUTO_UPDATE_INTERVAL,
    MIN_REFRESH_COOLDOWN,
    MAX_REFRESH_COOLDOWN,
)
from .api_client import SchulmanagerHub

_LOGGER = logging.getLogger(__name__)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
    }
)


class SchulmanagerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for the Schulmanager integration."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors = {}

        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=USER_SCHEMA)

        # Test the connection and get student data
        try:
            hub = SchulmanagerHub(
                self.hass,
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                debug_dumps=False,
            )

            # Test login and get student data
            await hub.async_login()

            if not hub._students:
                errors["base"] = "no_students"
            else:
                _LOGGER.info(f"Found {len(hub._students)} students: {[s['name'] for s in hub._students]}")

                # Store student data for device creation
                self._students_data = hub._students

        except Exception as ex:
            _LOGGER.exception("Failed to connect to Schulmanager: %s", ex)
            errors["base"] = "cannot_connect"

        if errors:
            return self.async_show_form(step_id="user", data_schema=USER_SCHEMA, errors=errors)

        return self.async_create_entry(
            title="Schulmanager Online",
            data={
                CONF_USERNAME: user_input[CONF_USERNAME],
                CONF_PASSWORD: user_input[CONF_PASSWORD],
            },
            options=DEFAULT_OPTIONS.copy(),
        )

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow handler."""
        return SchulmanagerOptionsFlowHandler(config_entry)


class SchulmanagerOptionsFlowHandler(OptionsFlow):
    """Handle Schulmanager options."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        super().__init__()
        # Store config entry data, not the entry itself
        self._entry_data = config_entry.data
        self._entry_options = config_entry.options

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            # Optionen speichern
            return self.async_create_entry(title="", data=user_input)

        opts = self._entry_options
        schema = vol.Schema(
            {
                vol.Required(
                    OPT_AUTO_UPDATE_INTERVAL,
                    default=opts.get(
                        OPT_AUTO_UPDATE_INTERVAL, DEFAULT_OPTIONS[OPT_AUTO_UPDATE_INTERVAL]
                    ),
                ): vol.All(cv.positive_int, vol.Range(min=MIN_AUTO_UPDATE_INTERVAL, max=MAX_AUTO_UPDATE_INTERVAL)),
                vol.Required(
                    OPT_POLL_INTERVAL,
                    default=opts.get(
                        OPT_POLL_INTERVAL, DEFAULT_OPTIONS[OPT_POLL_INTERVAL]
                    ),
                ): cv.positive_int,
                vol.Required(
                    OPT_ENABLE_SCHEDULE,
                    default=opts.get(
                        OPT_ENABLE_SCHEDULE, DEFAULT_OPTIONS[OPT_ENABLE_SCHEDULE]
                    ),
                ): cv.boolean,
                vol.Required(
                    OPT_ENABLE_HOMEWORK,
                    default=opts.get(
                        OPT_ENABLE_HOMEWORK, DEFAULT_OPTIONS[OPT_ENABLE_HOMEWORK]
                    ),
                ): cv.boolean,
                vol.Required(
                    OPT_ENABLE_EXAMS,
                    default=opts.get(
                        OPT_ENABLE_EXAMS, DEFAULT_OPTIONS[OPT_ENABLE_EXAMS]
                    ),
                ): cv.boolean,
                vol.Required(
                    OPT_ENABLE_GRADES,
                    default=opts.get(
                        OPT_ENABLE_GRADES, DEFAULT_OPTIONS[OPT_ENABLE_GRADES]
                    ),
                ): cv.boolean,
                vol.Required(
                    OPT_RANGE_PAST_DAYS,
                    default=opts.get(
                        OPT_RANGE_PAST_DAYS, DEFAULT_OPTIONS[OPT_RANGE_PAST_DAYS]
                    ),
                ): cv.positive_int,
                vol.Required(
                    OPT_RANGE_FUTURE_DAYS,
                    default=opts.get(
                        OPT_RANGE_FUTURE_DAYS, DEFAULT_OPTIONS[OPT_RANGE_FUTURE_DAYS]
                    ),
                ): cv.positive_int,
                vol.Required(
                    OPT_REFRESH_COOLDOWN,
                    default=opts.get(
                        OPT_REFRESH_COOLDOWN, DEFAULT_OPTIONS[OPT_REFRESH_COOLDOWN]
                    ),
                ): vol.All(cv.positive_int, vol.Range(min=MIN_REFRESH_COOLDOWN, max=MAX_REFRESH_COOLDOWN)),
                vol.Required(
                    OPT_DEBUG_DUMPS,
                    default=opts.get(OPT_DEBUG_DUMPS, DEFAULT_OPTIONS[OPT_DEBUG_DUMPS]),
                ): cv.boolean,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
