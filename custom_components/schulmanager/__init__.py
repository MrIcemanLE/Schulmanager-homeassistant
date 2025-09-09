from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.device_registry import async_get as async_get_device_registry

from .const import (
    DOMAIN,
    VERSION,
    OPT_POLL_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    OPT_DEBUG_DUMPS,
    OPT_ENABLE_HOMEWORK,
    OPT_ENABLE_SCHEDULE,
    OPT_ENABLE_EXAMS,
    OPT_ENABLE_GRADES,
    CONF_USERNAME,
    CONF_PASSWORD,
)
from .api_client import SchulmanagerHub
from .coordinator import SchulmanagerCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.TODO, Platform.CALENDAR, Platform.BUTTON]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Schulmanager from a config entry."""
    options = dict(entry.options)
    debug_dumps = bool(options.get(OPT_DEBUG_DUMPS, True))

    # Get enabled features from options
    enable_homework = bool(options.get(OPT_ENABLE_HOMEWORK, True))
    enable_schedule = bool(options.get(OPT_ENABLE_SCHEDULE, True))
    enable_exams = bool(options.get(OPT_ENABLE_EXAMS, True))
    enable_grades = bool(options.get(OPT_ENABLE_GRADES, True))

    hub = SchulmanagerHub(
        hass,
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        debug_dumps=debug_dumps,
    )
    coordinator = SchulmanagerCoordinator(hass, hub, entry)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as e:
        _LOGGER.exception("Failed to initialize Schulmanager")
        raise ConfigEntryNotReady from e

    # Create or update device entries for students early in the setup process
    device_registry = async_get_device_registry(hass)
    for student in hub._students:
        device_entry = device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, f"student_{student['id']}")},
            name=student["name"],
            manufacturer="Schulmanager Online",
            model="Schüler",
            sw_version=VERSION,
            suggested_area="Schule",
            configuration_url="https://login.schulmanager-online.de/",
        )

        # If device was orphaned, make sure it's properly linked to this config entry
        if entry.entry_id not in device_entry.config_entries:
            device_registry.async_update_device(
                device_entry.id,
                add_config_entry_id=entry.entry_id
            )

    _LOGGER.info("Created device entries for %d students", len(hub._students))

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "hub": hub,
        "coordinator": coordinator,
    }

    # Set up platforms based on enabled features
    platforms_to_load = []

    if enable_schedule:
        platforms_to_load.append(Platform.SENSOR)  # Schedule sensors

    if enable_homework:
        platforms_to_load.append(Platform.TODO)  # Homework todo lists

    if enable_exams:
        platforms_to_load.append(Platform.CALENDAR)  # Exam calendar

    # Always load button for manual refresh
    platforms_to_load.append(Platform.BUTTON)

    if platforms_to_load:
        await hass.config_entries.async_forward_entry_setups(entry, platforms_to_load)

    # Register services
    await _async_register_services(hass)

    # Add options update listener to trigger reload when settings change
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options change."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    options = dict(entry.options)
    enable_homework = bool(options.get(OPT_ENABLE_HOMEWORK, True))
    enable_schedule = bool(options.get(OPT_ENABLE_SCHEDULE, True))
    enable_exams = bool(options.get(OPT_ENABLE_EXAMS, True))

    platforms_to_unload = []

    if enable_schedule:
        platforms_to_unload.append(Platform.SENSOR)

    if enable_homework:
        platforms_to_unload.append(Platform.TODO)

    if enable_exams:
        platforms_to_unload.append(Platform.CALENDAR)

    platforms_to_unload.append(Platform.BUTTON)

    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, platforms_to_unload
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    # Unregister services if this was the last entry
    if not hass.data[DOMAIN]:
        hass.services.async_remove(DOMAIN, "clear_cache")
        hass.services.async_remove(DOMAIN, "refresh")
        hass.services.async_remove(DOMAIN, "clear_debug")

    return unload_ok


async def _async_register_services(hass: HomeAssistant) -> None:
    """Register Schulmanager services."""

    async def clear_cache_service(_call: ServiceCall) -> None:
        """Clear cache for all Schulmanager instances."""
        for entry_data in hass.data[DOMAIN].values():
            hub = entry_data["hub"]
            hub._token = None
            hub._bundle_version = None
            _LOGGER.info("Cleared cache for Schulmanager")

    async def refresh_service(_call: ServiceCall) -> None:
        """Refresh data for all Schulmanager instances with cooldown enforcement."""
        for entry_data in hass.data[DOMAIN].values():
            coordinator = entry_data["coordinator"]
            await coordinator.async_request_manual_refresh()

    async def clear_debug_service(_call: ServiceCall) -> None:
        """Clear debug files."""
        import os
        import shutil

        for entry_data in hass.data[DOMAIN].values():
            hub = entry_data["hub"]
            if hub.debug_dumps:
                debug_path = hass.config.path(
                    "custom_components", "schulmanager", "debug"
                )
                if os.path.exists(debug_path):
                    shutil.rmtree(debug_path)
                    _LOGGER.info("Cleared debug files")

    # Register services only once
    if not hass.services.has_service(DOMAIN, "clear_cache"):
        hass.services.async_register(DOMAIN, "clear_cache", clear_cache_service)
        hass.services.async_register(DOMAIN, "refresh", refresh_service)
        hass.services.async_register(DOMAIN, "clear_debug", clear_debug_service)
