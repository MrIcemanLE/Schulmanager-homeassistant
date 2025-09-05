
from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.exceptions import ServiceValidationError

from .const import DOMAIN

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coord = data["coordinator"]
    async_add_entities([RefreshButton(coord)])

class RefreshButton(ButtonEntity):
    """Button entity for manual refresh with cooldown support."""

    _attr_unique_id = "schulmanager_refresh_now"
    _attr_name = "Schulmanager jetzt aktualisieren"
    _attr_icon = "mdi:book-sync"

    def __init__(self, coordinator) -> None:
        """Initialize the refresh button."""
        self.coordinator = coordinator

    @property
    def available(self) -> bool:
        """Return if entity is available (not in cooldown)."""
        return self.coordinator.is_manual_refresh_allowed()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return state attributes with cooldown information."""
        remaining_seconds = self.coordinator.get_cooldown_remaining_seconds()
        cooldown_total = self.coordinator._get_cooldown_seconds()
        
        return {
            "cooldown_active": remaining_seconds > 0,
            "cooldown_remaining_seconds": remaining_seconds,
            "cooldown_total_seconds": cooldown_total,
            "next_refresh_allowed": "jetzt verfügbar" if remaining_seconds == 0 else f"in {remaining_seconds} Sekunden",
            "last_manual_refresh": (
                self.coordinator._last_manual_refresh.isoformat()
                if self.coordinator._last_manual_refresh
                else "nie"
            ),
        }

    async def async_press(self) -> None:
        """Press the button with cooldown enforcement."""
        try:
            await self.coordinator.async_request_manual_refresh()
        except Exception as err:
            # Convert HomeAssistantError to ServiceValidationError for better UI display
            raise ServiceValidationError(str(err)) from err
