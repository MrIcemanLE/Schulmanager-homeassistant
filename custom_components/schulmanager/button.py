
from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo, DeviceEntryType
from homeassistant.exceptions import ServiceValidationError

from .const import DOMAIN, VERSION
from .utils import get_validated_refresh_cooldown

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
        self.config_entry = coordinator.config_entry
    
    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for the service device."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"service_{self.config_entry.entry_id}")},
            name="Schulmanager Online",
            manufacturer="Schulmanager Online",
            model="Portal-Zugang",
            sw_version=VERSION,
            entry_type=DeviceEntryType.SERVICE,
            suggested_area="Schule",
            configuration_url="https://login.schulmanager-online.de/",
        )

    @property
    def available(self) -> bool:
        """Return if entity is available (not in cooldown)."""
        return self.coordinator.is_manual_refresh_allowed()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return state attributes with cooldown information."""
        remaining_seconds = self.coordinator.get_cooldown_remaining_seconds()
        cooldown_total_minutes = get_validated_refresh_cooldown(self.config_entry)
        cooldown_total_seconds = cooldown_total_minutes * 60
        
        return {
            "cooldown_active": remaining_seconds > 0,
            "cooldown_remaining_seconds": remaining_seconds,
            "cooldown_total_seconds": cooldown_total_seconds,
            "cooldown_total_minutes": cooldown_total_minutes,
            "next_refresh_allowed": "jetzt verfügbar" if remaining_seconds == 0 else f"in {remaining_seconds} Sekunden",
            "last_manual_refresh": (
                self.coordinator.cooldown_manager._last_manual_refresh.isoformat()
                if self.coordinator.cooldown_manager._last_manual_refresh
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
