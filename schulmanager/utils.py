"""Shared utilities for Schulmanager integration."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.exceptions import HomeAssistantError

if TYPE_CHECKING:
    from .api_client import SchulmanagerHub

from .const import (
    OPT_AUTO_UPDATE_INTERVAL,
    OPT_POLL_INTERVAL,
    OPT_REFRESH_COOLDOWN,
    DEFAULT_AUTO_UPDATE_INTERVAL,
    DEFAULT_REFRESH_COOLDOWN,
    MIN_AUTO_UPDATE_INTERVAL,
    MAX_AUTO_UPDATE_INTERVAL,
    MIN_REFRESH_COOLDOWN,
    MAX_REFRESH_COOLDOWN,
    CALLS_URL,
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


async def ensure_authenticated(hub: SchulmanagerHub) -> None:
    """Ensure the hub is authenticated and has bundle version."""
    if not hub._token:
        await hub.async_login()
    if not hub._bundle_version:
        hub._bundle_version = await hub._discover_bundle_version()


async def make_api_call(
    hass: HomeAssistant,
    hub: SchulmanagerHub,
    module: str,
    endpoint: str,
    parameters: dict[str, Any],
    tag: str = "",
) -> Any:
    """Make authenticated API call to Schulmanager."""
    await ensure_authenticated(hub)
    
    headers = common_headers()
    headers.update({
        "Content-Type": "application/json;charset=UTF-8",
        "Authorization": f"Bearer {hub._token}",
    })

    payload: dict[str, Any] = {
        "requests": [{
            "moduleName": module,
            "endpointName": endpoint,
            "parameters": parameters,
        }]
    }
    
    if hub._bundle_version:
        payload["bundleVersion"] = hub._bundle_version

    session = async_get_clientsession(hass)
    
    try:
        async with session.post(CALLS_URL, json=payload, headers=headers) as response:
            if response.status != 200:
                raise HomeAssistantError(f"API call failed: {response.status}")
            
            response_data = await response.json()
            
            # Debug dump if enabled
            if hub.debug_dumps and tag:
                await hub._dump(f"{tag}_response", response_data)
            
            return response_data
            
    except Exception as err:
        _LOGGER.error("API call to %s/%s failed: %s", module, endpoint, err)
        raise HomeAssistantError(f"API call failed: {err}") from err


def get_validated_auto_update_interval(config_entry: ConfigEntry) -> int:
    """Get and validate the auto update interval from config."""
    options = config_entry.options
    
    # Check new option first, then legacy
    interval_hours = options.get(OPT_AUTO_UPDATE_INTERVAL)
    if interval_hours is None:
        # Convert legacy seconds to hours
        legacy_seconds = options.get(OPT_POLL_INTERVAL, DEFAULT_AUTO_UPDATE_INTERVAL * 3600)
        interval_hours = max(1, legacy_seconds // 3600)
    
    # Validate range
    return max(MIN_AUTO_UPDATE_INTERVAL, min(MAX_AUTO_UPDATE_INTERVAL, interval_hours))


def get_validated_refresh_cooldown(config_entry: ConfigEntry) -> int:
    """Get and validate the refresh cooldown from config."""
    options = config_entry.options
    cooldown_minutes = options.get(OPT_REFRESH_COOLDOWN, DEFAULT_REFRESH_COOLDOWN)
    
    # Validate range
    return max(MIN_REFRESH_COOLDOWN, min(MAX_REFRESH_COOLDOWN, cooldown_minutes))


class CooldownManager:
    """Manages cooldown timing for manual refreshes."""
    
    def __init__(self, config_entry: ConfigEntry):
        self._config_entry = config_entry
        self._last_manual_refresh: datetime | None = None
    
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
    from .const import (
        OPT_ENABLE_HOMEWORK,
        OPT_ENABLE_SCHEDULE, 
        OPT_ENABLE_EXAMS,
        OPT_ENABLE_GRADES,
        DEFAULT_ENABLE_HOMEWORK,
        DEFAULT_ENABLE_SCHEDULE,
        DEFAULT_ENABLE_EXAMS,
        DEFAULT_ENABLE_GRADES,
    )
    
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
            redacted = {}
            for k, v in obj.items():
                lk = k.lower()
                if lk in ("password", "jwt", "authorization", "token", "hash"):
                    if isinstance(v, str) and len(v) > 12:
                        redacted[k] = v[:10] + "...(redacted)"
                    else:
                        redacted[k] = "(redacted)"
                else:
                    redacted[k] = sanitize_for_log(v)
            return redacted
        if isinstance(obj, list):
            return [sanitize_for_log(x) for x in obj]
        return obj
    except Exception:
        return "(unloggable)"