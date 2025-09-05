
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.exceptions import HomeAssistantError

from .const import (
    OPT_RANGE_PAST_DAYS,
    OPT_RANGE_FUTURE_DAYS,
)
from .utils import (
    get_validated_auto_update_interval,
    get_feature_config,
    CooldownManager,
)

_LOGGER = logging.getLogger(__name__)

class SchulmanagerCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for Schulmanager integration with cooldown support."""

    def __init__(self, hass: HomeAssistant, hub: Any, config_entry: ConfigEntry) -> None:
        """Initialize the coordinator with cooldown tracking."""
        # Get the update interval from config, with validation
        interval_hours = get_validated_auto_update_interval(config_entry)
        interval_seconds = interval_hours * 3600  # Convert hours to seconds
        
        super().__init__(
            hass,
            _LOGGER,
            name="SchulmanagerCoordinator",
            update_interval=timedelta(seconds=interval_seconds),
            config_entry=config_entry,
        )
        self.hub = hub
        self.cooldown_manager = CooldownManager(config_entry)
        
        _LOGGER.info(
            "Schulmanager coordinator initialized with %d hour automatic update interval",
            interval_hours
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data from API with only enabled features to minimize server load."""
        # Get enabled features from config entry options  
        if self.config_entry is None:
            raise HomeAssistantError("Config entry is not available")
        
        enabled_features = get_feature_config(self.config_entry)
        
        # Get date range configuration for exams
        options = dict(self.config_entry.options or {})
        date_range_config = {
            "past_days": int(options.get(OPT_RANGE_PAST_DAYS, 30)),
            "future_days": int(options.get(OPT_RANGE_FUTURE_DAYS, 180)),
        }
        
        _LOGGER.debug("Fetching data with features: %s and date range: %s", enabled_features, date_range_config)
        return await self.hub.async_update(enabled_features, date_range_config)

    def is_manual_refresh_allowed(self) -> bool:
        """Check if a manual refresh is allowed (not in cooldown)."""
        return self.cooldown_manager.can_refresh()

    def get_cooldown_remaining_seconds(self) -> int:
        """Get remaining cooldown time in seconds. Returns 0 if no cooldown active."""
        return self.cooldown_manager.get_remaining_cooldown()

    async def async_request_manual_refresh(self) -> None:
        """Request a manual refresh with cooldown enforcement."""
        if not self.is_manual_refresh_allowed():
            remaining = self.get_cooldown_remaining_seconds()
            raise HomeAssistantError(
                f"Manuelle Aktualisierung ist noch {remaining} Sekunden lang gesperrt. "
                f"Bitte warten Sie, bevor Sie erneut aktualisieren."
            )
        
        # Record the manual refresh time
        self.cooldown_manager.record_refresh()
        _LOGGER.info(
            "Manual refresh requested. Next manual refresh allowed in %d seconds.",
            self.cooldown_manager.get_remaining_cooldown()
        )
        
        # Perform the refresh
        await self.async_request_refresh()
