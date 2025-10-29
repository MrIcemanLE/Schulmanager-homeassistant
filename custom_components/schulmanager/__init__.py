"""Integration setup for Schulmanager Online."""

from __future__ import annotations

import logging
from pathlib import Path
import shutil

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.device_registry import (
    DeviceEntryType,
    async_get as async_get_device_registry,
)

from .api_client import MultiSchoolClient, SchulmanagerClient
from .const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    DOMAIN,
    OPT_DEBUG_DUMPS,
    OPT_ENABLE_EXAMS,
    OPT_ENABLE_GRADES,
    OPT_ENABLE_HOMEWORK,
    OPT_ENABLE_SCHEDULE,
    VERSION,
)
from .coordinator import SchulmanagerCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.TODO, Platform.CALENDAR, Platform.BUTTON]


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entry versions.

    - v1 -> v2: remove deprecated polling options (auto_update_interval, poll_interval)
    - v2 -> v3: convert institution_id to schools array (multi-school support)
    """
    version = entry.version

    if version < 2:
        options = dict(entry.options)
        removed: list[str] = []
        for key in ("auto_update_interval", "poll_interval"):
            if key in options:
                options.pop(key)
                removed.append(key)

        if removed:
            _LOGGER.debug(
                "Migrating config entry %s: removing deprecated options %s",
                entry.entry_id,
                removed,
            )
            hass.config_entries.async_update_entry(entry, options=options)

        entry.version = 2

    if version < 3:
        # Migration v2 -> v3: Convert institution_id to schools array
        data = dict(entry.data)
        institution_id = data.get("institution_id")

        if institution_id and "schools" not in data:
            _LOGGER.info(
                "Migrating config entry %s from v2 to v3: Converting institution_id to schools array",
                entry.entry_id,
            )

            # Try to fetch school name from API
            try:
                client = SchulmanagerClient(
                    hass,
                    data[CONF_USERNAME],
                    data[CONF_PASSWORD],
                    debug_dumps=False,
                    institution_id=institution_id,
                )
                await client.async_login()

                # Use the institution_id to create a schools entry
                # School name might not be available, use placeholder
                schools = [
                    {
                        "id": institution_id,
                        "label": f"School {institution_id}",  # Placeholder
                    }
                ]

                data["schools"] = schools
                data.pop("institution_id", None)  # Remove old key

                hass.config_entries.async_update_entry(entry, data=data)
                _LOGGER.info("Migration successful: Created schools array with %d school(s)", len(schools))

            except Exception as err:
                _LOGGER.warning(
                    "Migration failed for entry %s, keeping institution_id for now: %s",
                    entry.entry_id,
                    err,
                )
                # Keep the old institution_id if migration fails - backwards compatibility

        entry.version = 3
        return True

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Schulmanager from a config entry."""
    options = dict(entry.options)
    debug_dumps = bool(options.get(OPT_DEBUG_DUMPS, True))

    # Get enabled features from options
    enable_homework = bool(options.get(OPT_ENABLE_HOMEWORK, True))
    enable_schedule = bool(options.get(OPT_ENABLE_SCHEDULE, True))
    enable_exams = bool(options.get(OPT_ENABLE_EXAMS, True))
    enable_grades = bool(options.get(OPT_ENABLE_GRADES, True))

    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]

    # Check if multi-school or single-school configuration
    schools = entry.data.get("schools")

    if schools:
        # Multi-school configuration
        _LOGGER.info("Setting up multi-school configuration with %d schools", len(schools))

        client = MultiSchoolClient(
            hass,
            username,
            password,
            debug_dumps=debug_dumps,
        )

        await client.async_login_all_schools(schools)

    else:
        # Single-school configuration (backwards compatibility)
        institution_id = entry.data.get("institution_id")
        if institution_id is not None:
            _LOGGER.debug("Using single-school configuration with institutionId %s", institution_id)

        client = SchulmanagerClient(
            hass,
            username,
            password,
            debug_dumps=debug_dumps,
            institution_id=institution_id,
        )

    coordinator = SchulmanagerCoordinator(hass, client, entry)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as e:
        _LOGGER.exception("Failed to initialize Schulmanager")
        raise ConfigEntryNotReady from e

    # Create the main Schulmanager service device
    device_registry = async_get_device_registry(hass)

    # Main service device
    service_device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"service_{entry.entry_id}")},
        name="Schulmanager Online",
        manufacturer="Schulmanager Online",
        model="Portal-Zugang",
        sw_version=VERSION,
        entry_type=DeviceEntryType.SERVICE,
        suggested_area="Schule",
        configuration_url="https://login.schulmanager-online.de/",
    )
    _LOGGER.info("Service device created with ID: %s, identifiers: %s", service_device.id, service_device.identifiers)

    # Student devices linked to the service
    # For multi-school clients, get_all_students() returns students with school_id and school_name
    # For single-school clients, get_students() returns students without school info
    students = client.get_all_students() if isinstance(client, MultiSchoolClient) else client.get_students()

    for student in students:
        student_device = device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, f"student_{student['id']}")},
            name=student["name"],
            manufacturer="Schulmanager Online",
            model="Schüler",
            suggested_area="Schule",
            configuration_url="https://login.schulmanager-online.de/",
            # Link student to service device
            via_device=(DOMAIN, f"service_{entry.entry_id}"),
        )

        # Ensure the device is properly linked to the service device and config entry
        device_registry.async_update_device(
            student_device.id,
            via_device_id=service_device.id,
        )
        _LOGGER.info("Student device %s updated with via_device_id: %s", student_device.name, service_device.id)

        # If device was orphaned, make sure it's properly linked to this config entry
        if entry.entry_id not in student_device.config_entries:
            device_registry.async_update_device(
                student_device.id,
                add_config_entry_id=entry.entry_id
            )

    _LOGGER.info("Created service device and %d student devices", len(students))

    # Store runtime data on the entry per guidelines
    entry.runtime_data = {"client": client, "coordinator": coordinator}

    # Keep minimal mapping for domain-level services bookkeeping
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"entry": entry}

    # Set up platforms based on enabled features
    platforms_to_load = []

    # Load sensors when any sensor-producing feature is enabled
    if enable_schedule or enable_exams or enable_grades:
        platforms_to_load.append(Platform.SENSOR)

    if enable_homework:
        platforms_to_load.append(Platform.TODO)  # Homework todo lists

    if enable_exams or enable_schedule:
        platforms_to_load.append(Platform.CALENDAR)  # Exam and/or schedule calendar

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
    enable_grades = bool(options.get(OPT_ENABLE_GRADES, True))

    platforms_to_unload = []

    # Unload sensors if any of their contributing features were enabled
    if enable_schedule or enable_exams or enable_grades:
        platforms_to_unload.append(Platform.SENSOR)

    if enable_homework:
        platforms_to_unload.append(Platform.TODO)

    if enable_exams or enable_schedule:
        platforms_to_unload.append(Platform.CALENDAR)

    platforms_to_unload.append(Platform.BUTTON)

    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, platforms_to_unload
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        entry.runtime_data = None

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
            entry: ConfigEntry = entry_data["entry"]
            client = entry.runtime_data["client"]
            client.clear_auth_cache()
            _LOGGER.info("Cleared service client cache")

    async def refresh_service(_call: ServiceCall) -> None:
        """Refresh data for all Schulmanager instances with cooldown enforcement."""
        for entry_data in hass.data[DOMAIN].values():
            entry: ConfigEntry = entry_data["entry"]
            coordinator = entry.runtime_data["coordinator"]
            await coordinator.async_request_manual_refresh()

    async def clear_debug_service(_call: ServiceCall) -> None:
        """Clear debug files."""

        for entry_data in hass.data[DOMAIN].values():
            entry: ConfigEntry = entry_data["entry"]
            client = entry.runtime_data["client"]
            if client.debug_dumps:
                debug_path = hass.config.path("custom_components", "schulmanager", "debug")
                if Path(debug_path).exists():
                    shutil.rmtree(debug_path)
                    _LOGGER.info("Cleared service debug files")

    # Register services only once
    if not hass.services.has_service(DOMAIN, "clear_cache"):
        hass.services.async_register(DOMAIN, "clear_cache", clear_cache_service)
        hass.services.async_register(DOMAIN, "refresh", refresh_service)
        hass.services.async_register(DOMAIN, "clear_debug", clear_debug_service)
