"""Diagnostics support for the Schulmanager integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_PASSWORD, CONF_USERNAME

REDACT_KEYS = {CONF_USERNAME, CONF_PASSWORD, "jwt", "token", "authorization", "hash"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry with secrets redacted."""
    runtime = entry.runtime_data or {}
    coordinator = runtime.get("coordinator")
    client = runtime.get("client")

    coordinator_data: dict[str, Any] | None = None
    if coordinator is not None:
        coordinator_data = coordinator.data

    raw = {
        "entry": {
            "data": dict(entry.data),
            "options": dict(entry.options),
            "entry_id": entry.entry_id,
            "title": entry.title,
            "unique_id": entry.unique_id,
        },
        "coordinator": {
            "last_update_success": getattr(coordinator, "last_update_success", None),
            "data": coordinator_data,
        },
        "service": {
            "has_token": bool(getattr(client, "_token", None)),
            "has_bundle_version": bool(getattr(client, "_bundle_version", None)),
            "student_count": len(getattr(client, "_students", []) or []),
        },
    }

    return async_redact_data(raw, REDACT_KEYS)
