"""Repair flows for the Schulmanager integration."""

import re
from typing import Any

import voluptuous as vol

from homeassistant.components.repairs import RepairsFlow, RepairsFlowResult
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv, issue_registry as ir

from .api_client import (
    SchulmanagerAuthError,
    SchulmanagerHubClient,
    SchulmanagerTwoFactorRequiredError,
)
from .const import CONF_PASSWORD, CONF_USER_DEVICES, CONF_USERNAME, DOMAIN
from .privacy import get_logger

_LOGGER = get_logger(__name__)

TWO_FACTOR_ISSUE = "school_two_factor_required"
CONF_CODE = "code"
CODE_SCHEMA = vol.Schema({vol.Required(CONF_CODE): cv.string})


def two_factor_issue_id(entry_id: str) -> str:
    """Return the id of the issue asking for a new two-factor code."""
    return f"{TWO_FACTOR_ISSUE}_{entry_id}"


def school_label(label: str) -> str:
    """Return a school name to show for a stored school label."""
    # Entries migrated from single-school setups only stored "School <id>"
    if not label or re.fullmatch(r"School \d+", label):
        return "Schulmanager"
    return label


@callback
def async_create_two_factor_issue(
    hass: HomeAssistant, entry: ConfigEntry, schools: list[str]
) -> None:
    """Ask the user for a new code, e.g. after the remembered device expired."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        two_factor_issue_id(entry.entry_id),
        is_fixable=True,
        severity=ir.IssueSeverity.ERROR,
        translation_key=TWO_FACTOR_ISSUE,
        translation_placeholders={"schools": ", ".join(schools)},
        data={"entry_id": entry.entry_id},
    )


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None
) -> RepairsFlow:
    """Create the flow that fixes an issue."""
    assert data is not None
    return TwoFactorRepairFlow(data["entry_id"])


class TwoFactorRepairFlow(RepairsFlow):
    """Ask for a two-factor code so Schulmanager remembers this device again."""

    def __init__(self, entry_id: str) -> None:
        """Initialize the flow for a config entry."""
        self._entry_id = entry_id
        self._hub: SchulmanagerHubClient | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> RepairsFlowResult:
        """Find out which school accounts need a code."""
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        if entry is None:
            return self.async_abort(reason="entry_removed")
        hub = SchulmanagerHubClient(
            self.hass,
            entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD],
            user_devices=entry.data.get(CONF_USER_DEVICES),
        )
        try:
            await hub.async_login(
                schools=entry.data.get("schools"),
                institution_id=entry.data.get("institution_id"),
            )
        except SchulmanagerTwoFactorRequiredError:
            pass
        except SchulmanagerAuthError:
            return self.async_abort(reason="password_rejected")
        except Exception:
            _LOGGER.exception("Login for the two-factor repair failed")
            return self.async_abort(reason="cannot_connect")
        self._hub = hub
        if not hub.get_two_factor_pending():
            if any(f["reason"] == "password" for f in hub.get_failed_schools()):
                return self.async_abort(reason="password_rejected")
            return self._async_finish(entry)
        return await self.async_step_code()

    async def async_step_code(
        self, user_input: dict[str, Any] | None = None
    ) -> RepairsFlowResult:
        """Log in with the code of the next school account."""
        assert self._hub is not None
        account = self._hub.get_two_factor_pending()[0]
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await self._hub.async_register_device(
                    account, user_input[CONF_CODE].strip()
                )
            except SchulmanagerTwoFactorRequiredError:
                errors["base"] = "invalid_code"
            except Exception:
                _LOGGER.exception("Login with two-factor code failed")
                errors["base"] = "cannot_connect"
            else:
                if self._hub.get_two_factor_pending():
                    return await self.async_step_code()
                entry = self.hass.config_entries.async_get_entry(self._entry_id)
                if entry is None:
                    return self.async_abort(reason="entry_removed")
                return self._async_finish(entry)

        return self.async_show_form(
            step_id="code",
            data_schema=CODE_SCHEMA,
            errors=errors,
            description_placeholders={"school": school_label(account["label"])},
        )

    @callback
    def _async_finish(self, entry: ConfigEntry) -> RepairsFlowResult:
        """Store the devices and reload the entry with them."""
        assert self._hub is not None
        changed = self.hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_USER_DEVICES: self._hub.get_user_devices()}
        )
        # A loaded entry already reloads through its update listener on a change
        if not changed or entry.state is not ConfigEntryState.LOADED:
            self.hass.config_entries.async_schedule_reload(entry.entry_id)
        return self.async_create_entry(data={})
