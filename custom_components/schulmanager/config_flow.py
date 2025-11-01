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

from .api_client import MultiSchoolClient, SchulmanagerClient
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
    MINOR_VERSION = 2  # ↑ erhöht wegen Speicherung von user_id

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial user step by validating credentials."""
        errors: dict[str, str] = {}

        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=USER_SCHEMA)

        username = user_input[CONF_USERNAME]
        password = user_input[CONF_PASSWORD]

        # Ensure we don't add duplicates: use username as unique ID
        await self.async_set_unique_id(username.lower())
        self._abort_if_unique_id_configured()

        try:
            # Debug-Dumps während der Einrichtung aktiv, um Login-Probleme sichtbar zu machen
            hub = SchulmanagerClient(
                self.hass,
                username,
                password,
                debug_dumps=True,
            )

            await hub.async_login()

            multiple_accounts = hub.get_multiple_accounts()
            if multiple_accounts:
                # Multi-school account: in alle Schulen parallel einloggen (per userId)
                _LOGGER.info(
                    "Multi-school account detected with %d schools - logging into all",
                    len(multiple_accounts),
                )

                multi_client = MultiSchoolClient(
                    self.hass,
                    username,
                    password,
                    debug_dumps=True,
                )
                await multi_client.async_login_all_schools(multiple_accounts)

                all_students = multi_client.get_all_students()
                if not all_students:
                    errors["base"] = "no_students"
                else:
                    _LOGGER.info(
                        "Found %d total students across %d schools",
                        len(all_students),
                        len(multiple_accounts),
                    )
                    # WICHTIG: Wir speichern die bereitgestellte Liste unverändert ab.
                    # Deren Einträge haben 'id' (= userId) und 'label' (Schulname).
                    return self.async_create_entry(
                        title="Schulmanager Online",
                        data={
                            CONF_USERNAME: username,
                            CONF_PASSWORD: password,
                            "schools": multiple_accounts,
                        },
                        options=DEFAULT_OPTIONS.copy(),
                    )

            # Single-school account (normal flow)
            students = hub.get_students()
            if not students:
                errors["base"] = "no_students"
            else:
                # Zusätzlich zu institutionId jetzt auch user_id sichern
                user_id = None
                institution_id = hub.get_institution_id()
                # user_id steckt nach erfolgreichem Login in hub._user_id; wir bekommen ihn
                # nicht direkt über Getter, also nehmen wir einen kleinen Trick:
                try:
                    # pylint: disable=protected-access
                    user_id = getattr(hub, "_user_id", None)
                except Exception:  # noqa: BLE001
                    user_id = None

                entry_data: dict[str, Any] = {
                    CONF_USERNAME: username,
                    CONF_PASSWORD: password,
                }
                if user_id is not None:
                    entry_data["user_id"] = int(user_id)
                    _LOGGER.info("Stored user_id %s", user_id)
                if institution_id is not None:
                    entry_data["institution_id"] = int(institution_id)
                    _LOGGER.info("Stored institutionId %s", institution_id)

                _LOGGER.info(
                    "Single-school account: Found %s students: %s",
                    len(students),
                    [s["name"] for s in students],
                )

                return self.async_create_entry(
                    title="Schulmanager Online",
                    data=entry_data,
                    options=DEFAULT_OPTIONS.copy(),
                )

        except Exception:  # noqa: BLE001
            _LOGGER.exception("Failed to connect to Schulmanager")
            errors["base"] = "cannot_connect"
            _LOGGER.error(
                "Login failed. Debug dumps (requests/responses) are in: "
                "config/custom_components/schulmanager/debug/"
            )

        if errors:
            return self.async_show_form(step_id="user", data_schema=USER_SCHEMA, errors=errors)

        return self.async_show_form(
            step_id="user",
            data_schema=USER_SCHEMA,
            errors={"base": "unknown"},
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
            return self.async_show_form(
                step_id="reauth_confirm",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_USERNAME): cv.string,
                        vol.Required(CONF_PASSWORD): cv.string,
                    }
                ),
            )

        # Bestehende Kontexte ziehen (user_id bevorzugt, sonst institution_id)
        institution_id: int | None = None
        user_id: int | None = None
        if hasattr(self, "_reauth_entry") and self._reauth_entry:
            institution_id = self._reauth_entry.data.get("institution_id")
            user_id = self._reauth_entry.data.get("user_id")

        try:
            hub = SchulmanagerClient(
                self.hass,
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                debug_dumps=False,
                institution_id=institution_id,
                user_id=user_id,
            )
            await hub.async_login()
        except Exception:  # noqa: BLE001
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

        # Credentials übernehmen; Kontext beibehalten
        assert hasattr(self, "_reauth_entry") and self._reauth_entry is not None

        update_data: dict[str, Any] = {
            CONF_USERNAME: user_input[CONF_USERNAME],
            CONF_PASSWORD: user_input[CONF_PASSWORD],
        }

        # Nach erfolgreichem Login ggf. aktualisierte IDs speichern
        try:
            # pylint: disable=protected-access
            new_user_id = getattr(hub, "_user_id", None)
        except Exception:  # noqa: BLE001
            new_user_id = None

        new_institution_id = hub.get_institution_id()

        # user_id bevorzugen; nur setzen, wenn vorhanden
        if new_user_id is not None:
            update_data["user_id"] = int(new_user_id)
        elif user_id is not None:
            update_data["user_id"] = int(user_id)

        if new_institution_id is not None:
            update_data["institution_id"] = int(new_institution_id)
        elif institution_id is not None:
            update_data["institution_id"] = int(institution_id)

        self.hass.config_entries.async_update_entry(
            self._reauth_entry,
            data=update_data,
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
        self._entry_data = config_entry.data
        self._entry_options = config_entry.options

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Render and handle options for this integration."""
        if user_input is not None:
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