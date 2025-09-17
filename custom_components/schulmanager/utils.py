"""Shared utilities for Schulmanager integration."""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

if TYPE_CHECKING:
    from .api_client import SchulmanagerClient

from .const import (
    CALLS_URL,
    DEFAULT_AUTO_UPDATE_INTERVAL,
    DEFAULT_ENABLE_EXAMS,
    DEFAULT_ENABLE_GRADES,
    DEFAULT_ENABLE_HOMEWORK,
    DEFAULT_ENABLE_SCHEDULE,
    DEFAULT_REFRESH_COOLDOWN,
    MAX_REFRESH_COOLDOWN,
    MIN_REFRESH_COOLDOWN,
    OPT_ENABLE_EXAMS,
    OPT_ENABLE_GRADES,
    OPT_ENABLE_HOMEWORK,
    OPT_ENABLE_SCHEDULE,
    OPT_REFRESH_COOLDOWN,
)

_LOGGER = logging.getLogger(__name__)

CHROME_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def common_headers() -> dict[str, str]:
    """Return common HTTP headers for requests."""
    return {
        "User-Agent": CHROME_UA,
        "Accept-Language": "de-DE,de;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Accept": "application/json, text/plain, */*",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }


def _raise_api_error(status: int) -> None:
    """Raise a HomeAssistantError for a non-200 API status."""
    raise HomeAssistantError(f"API call failed: {status}")


async def ensure_authenticated(client: SchulmanagerClient) -> None:
    """Ensure the service client is authenticated and has bundle version."""
    if not client.auth_token():
        await client.async_login()
    if not client.bundle_version():
        await client.async_discover_bundle_version()


async def make_api_call(
    hass: HomeAssistant,
    client: SchulmanagerClient,
    module: str,
    endpoint: str,
    parameters: dict[str, Any],
    tag: str = "",
) -> Any:
    """Make authenticated API call to Schulmanager."""
    await ensure_authenticated(client)

    headers = common_headers()
    headers.update({
        "Content-Type": "application/json;charset=UTF-8",
        "Authorization": f"Bearer {client.auth_token()}",
    })

    payload: dict[str, Any] = {
        "requests": [{
            "moduleName": module,
            "endpointName": endpoint,
            "parameters": parameters,
        }]
    }

    if client.bundle_version():
        payload["bundleVersion"] = client.bundle_version()

    session = async_get_clientsession(hass)

    try:
        async with session.post(CALLS_URL, json=payload, headers=headers) as response:
            if response.status != 200:
                _raise_api_error(response.status)

            response_data = await response.json()

            # Debug dump if enabled
            if client.debug_dumps and tag:
                await client.async_dump(f"{tag}_response", response_data)

            return response_data

    except Exception as err:
        _LOGGER.error("API call to %s/%s failed: %s", module, endpoint, err)
        raise HomeAssistantError(f"API call failed: {err}") from err


def get_validated_auto_update_interval(config_entry: ConfigEntry) -> int:
    """Return a fixed automatic update interval in hours.

    Polling intervals are not user-configurable per guidelines.
    """
    return DEFAULT_AUTO_UPDATE_INTERVAL


def get_validated_refresh_cooldown(config_entry: ConfigEntry) -> int:
    """Get and validate the refresh cooldown from config."""
    options = config_entry.options
    cooldown_raw = options.get(OPT_REFRESH_COOLDOWN, DEFAULT_REFRESH_COOLDOWN)
    try:
        cooldown_minutes = int(cooldown_raw)
    except (TypeError, ValueError):
        cooldown_minutes = DEFAULT_REFRESH_COOLDOWN
    # Validate range
    return max(MIN_REFRESH_COOLDOWN, min(MAX_REFRESH_COOLDOWN, cooldown_minutes))


class CooldownManager:
    """Manages cooldown timing for manual refreshes."""

    def __init__(self, config_entry: ConfigEntry):
        """Initialize cooldown manager for a given config entry."""
        self._config_entry = config_entry
        self._last_manual_refresh: datetime | None = None

    @property
    def last_manual_refresh(self) -> datetime | None:
        """Return timestamp of last manual refresh if available."""
        return self._last_manual_refresh

    def can_refresh(self) -> bool:
        """Check if manual refresh is allowed (outside cooldown period)."""
        if self._last_manual_refresh is None:
            return True

        cooldown_minutes = get_validated_refresh_cooldown(self._config_entry)
        cooldown_period = timedelta(minutes=cooldown_minutes)

        return datetime.now() - self._last_manual_refresh >= cooldown_period

    def get_remaining_cooldown(self) -> int:
        """Get remaining cooldown time in seconds."""
        if self._last_manual_refresh is None:
            return 0

        cooldown_minutes = get_validated_refresh_cooldown(self._config_entry)
        cooldown_period = timedelta(minutes=cooldown_minutes)
        elapsed = datetime.now() - self._last_manual_refresh

        if elapsed >= cooldown_period:
            return 0

        remaining = cooldown_period - elapsed
        return int(remaining.total_seconds())

    def record_refresh(self) -> None:
        """Record that a manual refresh was performed."""
        self._last_manual_refresh = datetime.now()


def get_feature_config(config_entry: ConfigEntry) -> dict[str, bool]:
    """Get feature enable/disable configuration."""

    options = config_entry.options
    return {
        "homework": options.get(OPT_ENABLE_HOMEWORK, DEFAULT_ENABLE_HOMEWORK),
        "schedule": options.get(OPT_ENABLE_SCHEDULE, DEFAULT_ENABLE_SCHEDULE),
        "exams": options.get(OPT_ENABLE_EXAMS, DEFAULT_ENABLE_EXAMS),
        "grades": options.get(OPT_ENABLE_GRADES, DEFAULT_ENABLE_GRADES),
    }


def sanitize_for_log(obj: Any) -> Any:
    """Remove sensitive information from objects for logging."""
    try:
        if isinstance(obj, dict):
            redacted: dict[str, Any] = {}
            for k, v in obj.items():
                lk = k.lower()
                if lk in ("password", "jwt", "authorization", "token", "hash"):
                    redacted[k] = (v[:10] + "...(redacted)") if isinstance(v, str) and len(v) > 12 else "(redacted)"
                else:
                    redacted[k] = sanitize_for_log(v)
            return redacted
        if isinstance(obj, list):
            return [sanitize_for_log(x) for x in obj]
        return obj  # noqa: TRY300
    except Exception:  # noqa: BLE001
        return "(unloggable)"
