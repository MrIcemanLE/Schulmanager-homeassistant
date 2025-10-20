"""Config flow for the Schulmanager integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.helpers import config_validation as cv

from .api_client import SchulmanagerClient
from .const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    DEFAULT_OPTIONS,
    DOMAIN,
    MAX_REFRESH_COOLDOWN,
    MIN_REFRESH_COOLDOWN,
    OPT_DEBUG_DUMPS,
    OPT_ENABLE_EXAMS,
    OPT_ENABLE_GRADES,
    OPT_ENABLE_HOMEWORK,
    OPT_ENABLE_SCHEDULE,
    OPT_RANGE_FUTURE_DAYS,
    OPT_RANGE_PAST_DAYS,
    OPT_REFRESH_COOLDOWN,
    OPT_SCHEDULE_HIDE_CANCELLED_NO_HIGHLIGHT,
    OPT_SCHEDULE_HIGHLIGHT,
    OPT_SCHEDULE_WEEKS,
)

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
    MINOR_VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial user step by validating credentials."""
        errors = {}

        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=USER_SCHEMA)

        # Test the connection and get student data
        try:
            # Enable debug dumps during config flow to help diagnose login issues
            hub = SchulmanagerClient(
                self.hass,
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                debug_dumps=True,
            )

            # Test login and get student data
            await hub.async_login()

            students = hub.get_students()
            if not students:
                errors["base"] = "no_students"
            else:
                _LOGGER.info(
                    "Found %s students: %s",
                    len(students),
                    [s["name"] for s in students],
                )

                # Store student data for device creation
                self._students_data = students

        except Exception as err:
            _LOGGER.exception("Failed to connect to Schulmanager")
            errors["base"] = "cannot_connect"

            # Log path to debug dumps for troubleshooting
            _LOGGER.error(
                "Login failed. Debug dumps are available in: "
                "config/custom_components/schulmanager/debug/"
            )

        if errors:
            return self.async_show_form(step_id="user", data_schema=USER_SCHEMA, errors=errors)

        # Ensure we don't add duplicates: use username as unique ID
        await self.async_set_unique_id(user_input[CONF_USERNAME].lower())
        self._abort_if_unique_id_configured()

        # Store institutionId if available (for multi-school support)
        institution_id = hub.get_institution_id()
        entry_data = {
            CONF_USERNAME: user_input[CONF_USERNAME],
            CONF_PASSWORD: user_input[CONF_PASSWORD],
        }
        if institution_id is not None:
            entry_data["institution_id"] = institution_id
            _LOGGER.info("Stored institutionId %s for multi-school support", institution_id)

        return self.async_create_entry(
            title="Schulmanager Online",
            data=entry_data,
            options=DEFAULT_OPTIONS.copy(),
        )

    # Reauthentication support
    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Start reauthentication step for updating credentials."""
        entry_id = self.context.get("entry_id")
        if not isinstance(entry_id, str):
            return self.async_abort(reason="reauth_successful")
        self._reauth_entry = self.hass.config_entries.async_get_entry(entry_id)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm reauthentication with new credentials and update entry."""
        errors: dict[str, str] = {}

        if user_input is None:
            # Ask for updated credentials
            return self.async_show_form(
                step_id="reauth_confirm",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_USERNAME): cv.string,
                        vol.Required(CONF_PASSWORD): cv.string,
                    }
                ),
            )

        # Validate new credentials
        try:
            hub = SchulmanagerClient(
                self.hass,
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                debug_dumps=False,
            )
            await hub.async_login()
        except Exception:  # noqa: BLE001 - config flows intentionally swallow unknown errors to prompt retry
            errors["base"] = "invalid_auth"
            return self.async_show_form(
                step_id="reauth_confirm",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_USERNAME, default=user_input.get(CONF_USERNAME, "")): cv.string,
                        vol.Required(CONF_PASSWORD): cv.string,
                    }
                ),
                errors=errors,
            )

        # Update the existing entry with new credentials
        assert hasattr(self, "_reauth_entry") and self._reauth_entry is not None
        self.hass.config_entries.async_update_entry(
            self._reauth_entry,
            data={
                CONF_USERNAME: user_input[CONF_USERNAME],
                CONF_PASSWORD: user_input[CONF_PASSWORD],
            },
        )
        await self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
        return self.async_abort(reason="reauth_successful")

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow handler."""
        return SchulmanagerOptionsFlowHandler(config_entry)


class SchulmanagerOptionsFlowHandler(OptionsFlow):
    """Handle Schulmanager options."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow state from the given entry."""
        super().__init__()
        # Store config entry data, not the entry itself
        self._entry_data = config_entry.data
        self._entry_options = config_entry.options

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Render and handle options for this integration."""
        if user_input is not None:
            # Optionen speichern
            return self.async_create_entry(title="", data=user_input)

        opts = self._entry_options
        schema = vol.Schema(
            {
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
                    OPT_SCHEDULE_WEEKS,
                    default=opts.get(
                        OPT_SCHEDULE_WEEKS, DEFAULT_OPTIONS[OPT_SCHEDULE_WEEKS]
                    ),
                ): vol.All(cv.positive_int, vol.Range(min=1, max=3)),
                vol.Required(
                    OPT_SCHEDULE_HIGHLIGHT,
                    default=opts.get(
                        OPT_SCHEDULE_HIGHLIGHT, DEFAULT_OPTIONS[OPT_SCHEDULE_HIGHLIGHT]
                    ),
                ): cv.boolean,
                vol.Required(
                    OPT_SCHEDULE_HIDE_CANCELLED_NO_HIGHLIGHT,
                    default=opts.get(
                        OPT_SCHEDULE_HIDE_CANCELLED_NO_HIGHLIGHT,
                        DEFAULT_OPTIONS[OPT_SCHEDULE_HIDE_CANCELLED_NO_HIGHLIGHT],
                    ),
                ): cv.boolean,
                vol.Required(
                    OPT_DEBUG_DUMPS,
                    default=opts.get(OPT_DEBUG_DUMPS, DEFAULT_OPTIONS[OPT_DEBUG_DUMPS]),
                ): cv.boolean,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
