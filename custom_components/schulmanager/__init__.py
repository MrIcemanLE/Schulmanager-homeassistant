"""Integration setup for Schulmanager Online."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import shutil
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryError,
    ConfigEntryNotReady,
    ServiceValidationError,
)
from homeassistant.helpers import config_validation as cv, issue_registry as ir
from homeassistant.helpers.device_registry import (
    DeviceEntryType,
    async_get as async_get_device_registry,
)
from homeassistant.helpers.entity_registry import (
    async_entries_for_config_entry,
    async_get as async_get_entity_registry,
)
from homeassistant.helpers.service import async_register_admin_service

from .api_client import (
    SchulmanagerAuthError,
    SchulmanagerClient,
    SchulmanagerHubClient,
    SchulmanagerTwoFactorRequiredError,
)
from .const import (
    CONF_PASSWORD,
    CONF_USER_DEVICES,
    CONF_USERNAME,
    DOMAIN,
    OPT_ENABLE_EXAMS,
    OPT_ENABLE_GRADES,
    OPT_ENABLE_HOMEWORK,
    OPT_ENABLE_LETTERS,
    OPT_ENABLE_MESSAGES,
    OPT_ENABLE_SCHEDULE,
    VERSION,
)
from .coordinator import SchulmanagerCoordinator
from .privacy import get_logger
from .repairs import TWO_FACTOR_ISSUE, async_create_two_factor_issue, school_label
from .schedule_export import SCHEMA_VERSION, STATUS_OK, STATUS_STALE

_LOGGER = get_logger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.TODO, Platform.CALENDAR, Platform.BUTTON]

ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_STUDENT_ID = "student_id"
SERVICE_GET_SCHEDULE = "get_schedule"
GET_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(ATTR_STUDENT_ID): cv.string,
    }
)


# unique_id suffix -> deterministic object_id suffix to rename broken
# entities to. Deliberately the raw translation_key (not a translated
# string): renaming must not depend on Home Assistant's translation loading
# having completed yet, which is exactly what made the previous
# remove-and-let-HA-recreate-it approach unreliable (see docstring below).
_BROKEN_NAME_UNIQUE_ID_SUFFIX_TO_OBJECT_ID = {
    "_school": "school",
    "_current_lesson": "current_lesson",
    "_wochenplan_json": "wochenplan_json",
}


def _rename_entities_with_missing_translation(
    hass: HomeAssistant, entry: ConfigEntry
) -> list[tuple[str, str]]:
    """Rename registry entries left nameless by a past missing-translation bug.

    Three sensors (SchoolDiagnosticSensor, CurrentLessonSensor,
    WochenplanJsonSensor) used to have no resolvable name whenever their
    `_attr_translation_key` was missing from translations/*.json (fixed
    2026-09-20, github.com/MrIcemanLE/Schulmanager-homeassistant#7). Entities
    created while that bug was present got a degenerate entity_id (e.g.
    "sensor.<student>_none") that Home Assistant does not retroactively fix
    just because the translation now resolves.

    An earlier version of this migration removed the entity and relied on
    Home Assistant recreating it - with a proper, name-derived entity_id -
    on the next platform setup. In practice this was unreliable: the
    entity_id's suggested slug is computed from
    `EntityPlatform.object_id_platform_translations`
    (homeassistant/helpers/entity_platform.py), which is only populated once
    `async_load_translations()` has completed; on the very setup where the
    entity is (re)created for the first time this can still be empty,
    reproducing the exact same "_none" entity_id even though the
    integration's translation files are now correct. Renaming the entity_id
    directly, using the stable `translation_key` value itself as the new
    object_id, sidesteps that timing dependency entirely.

    Detection is based on the entity_id itself containing a "none" token
    (e.g. "..._none", "..._none_2") rather than the registry's
    `original_name` field: that field gets silently recomputed - and thus
    "heals" itself - on every setup once the translation is fixed, while the
    entity_id (deliberately) never changes on its own. By the time this
    migration runs, `original_name` may already look fine even though the
    entity_id is still the broken one, so it is not a reliable signal here.
    """
    entity_registry = async_get_entity_registry(hass)
    renamed: list[tuple[str, str]] = []
    for reg_entry in list(async_entries_for_config_entry(entity_registry, entry.entry_id)):
        object_id_suffix = next(
            (
                suffix
                for unique_id_suffix, suffix in _BROKEN_NAME_UNIQUE_ID_SUFFIX_TO_OBJECT_ID.items()
                if reg_entry.unique_id.endswith(unique_id_suffix)
            ),
            None,
        )
        if object_id_suffix is None:
            continue

        domain, object_id = reg_entry.entity_id.split(".", 1)
        tokens = object_id.split("_")
        if "none" not in tokens:
            continue
        prefix = "_".join(tokens[: tokens.index("none")])
        new_object_id = f"{prefix}_{object_id_suffix}" if prefix else object_id_suffix
        new_entity_id = f"{domain}.{new_object_id}"

        if new_entity_id == reg_entry.entity_id:
            continue
        if entity_registry.async_get(new_entity_id) is not None:
            # Target slug already taken (unexpected) - remove instead of
            # crashing, so Home Assistant can pick a disambiguated one.
            entity_registry.async_remove(reg_entry.entity_id)
            renamed.append((reg_entry.entity_id, new_entity_id))
            continue

        entity_registry.async_update_entity(
            reg_entry.entity_id, new_entity_id=new_entity_id
        )
        renamed.append((reg_entry.entity_id, new_entity_id))

    return renamed


def _scope_unique_ids_to_entry(
    hass: HomeAssistant, entry: ConfigEntry
) -> list[tuple[str, str, str]]:
    """Rewrite this entry's entity unique_ids to include the entry_id.

    Every entity's unique_id used to be built purely from the studentId
    (e.g. "schulmanager_1234567_grades_overall"). That collides whenever the
    same student is reachable from two config entries at once - e.g. a
    parent account and that student's own login, or two parents each with
    their own account - because Home Assistant requires unique_ids to be
    unique per platform, not per config entry. The second entry's entities
    were silently dropped ("does not generate unique IDs ... ignoring").

    Only the unique_id is rewritten via `new_unique_id`, never the
    entity_id, so existing dashboards/automations/history are unaffected.
    """
    entity_registry = async_get_entity_registry(hass)
    old_prefix = "schulmanager_"
    new_prefix = f"schulmanager_{entry.entry_id}_"
    rescoped: list[tuple[str, str, str]] = []

    for reg_entry in list(async_entries_for_config_entry(entity_registry, entry.entry_id)):
        old_unique_id = reg_entry.unique_id
        if not old_unique_id.startswith(old_prefix) or old_unique_id.startswith(
            new_prefix
        ):
            # Not one of ours, or already entry-scoped (e.g. RefreshButton,
            # or an entity a previous run of this migration already fixed).
            continue

        new_unique_id = new_prefix + old_unique_id[len(old_prefix) :]
        entity_registry.async_update_entity(
            reg_entry.entity_id, new_unique_id=new_unique_id
        )
        rescoped.append((reg_entry.entity_id, old_unique_id, new_unique_id))

    return rescoped


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entry versions.

    - v1 -> v2: remove deprecated polling options (auto_update_interval, poll_interval)
    - v2 -> v3: convert institution_id to schools array (multi-school support)
    - v3 -> v4: remove sensor entities left nameless by a missing-translation bug
      (superseded by v4 -> v5: this pass used `original_name is None` as its
      detection signal, which - unlike the actually-broken entity_id - turned
      out to silently heal itself on a later setup, so this step could
      complete without finding anything to remove on an already-affected entry)
    - v4 -> v5: re-run the v3 -> v4 cleanup with entity_id-based detection
      (superseded by v5 -> v6: removing and relying on Home Assistant to
      recreate the entity was unreliable - see _rename_entities_with_missing_translation)
    - v5 -> v6: rename (instead of remove) the still-affected entities
    - v6 -> v7: scope entity unique_ids to their config entry, so the same
      student appearing in multiple entries no longer collides
      (see _scope_unique_ids_to_entry)
    - v7 -> v8: remove the "debug_dumps" option; dumps now follow Home
      Assistant's debug logging toggle
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
            hass.config_entries.async_update_entry(entry, options=options, version=2)
        else:
            hass.config_entries.async_update_entry(entry, version=2)

    if version < 3:
        # Migration v2 -> v3: Convert institution_id to schools array
        data = dict(entry.data)
        institution_id = data.get("institution_id")

        if institution_id and "schools" not in data:
            _LOGGER.info(
                "Migrating config entry %s from v2 to v3: Converting institution_id to schools array",
                entry.entry_id,
            )

            # Convert institution_id to schools array (no API call needed)
            schools = [
                {
                    "id": institution_id,
                    "label": f"School {institution_id}",  # Placeholder name
                }
            ]
            data["schools"] = schools
            data.pop("institution_id", None)
            hass.config_entries.async_update_entry(entry, data=data, version=3)
            _LOGGER.info(
                "Migration successful: Converted institution_id %s to schools array",
                institution_id,
            )
        else:
            hass.config_entries.async_update_entry(entry, version=3)

    if version < 4:
        hass.config_entries.async_update_entry(entry, version=4)

    if version < 5:
        hass.config_entries.async_update_entry(entry, version=5)

    if version < 6:
        renamed = _rename_entities_with_missing_translation(hass, entry)
        if renamed:
            _LOGGER.info(
                "Migrating config entry %s to v6: renamed %d entities left nameless "
                "by a missing-translation bug: %s",
                entry.entry_id,
                len(renamed),
                renamed,
            )

        hass.config_entries.async_update_entry(entry, version=6)

    if version < 7:
        rescoped = _scope_unique_ids_to_entry(hass, entry)
        if rescoped:
            _LOGGER.info(
                "Migrating config entry %s to v7: scoped %d entity unique_ids "
                "to this config entry to avoid collisions when the same "
                "student appears in multiple entries: %s",
                entry.entry_id,
                len(rescoped),
                rescoped,
            )

        hass.config_entries.async_update_entry(entry, version=7)

    if version < 8:
        options = {k: v for k, v in entry.options.items() if k != "debug_dumps"}
        hass.config_entries.async_update_entry(entry, options=options, version=8)

    return True


def platforms_for_options(options: Mapping[str, Any]) -> list[Platform]:
    """Return the platforms needed for the enabled features."""
    enabled = {
        key: bool(options.get(key, True))
        for key in (
            OPT_ENABLE_HOMEWORK,
            OPT_ENABLE_SCHEDULE,
            OPT_ENABLE_EXAMS,
            OPT_ENABLE_GRADES,
            OPT_ENABLE_LETTERS,
            OPT_ENABLE_MESSAGES,
        )
    }
    platforms = []
    if (
        enabled[OPT_ENABLE_SCHEDULE]
        or enabled[OPT_ENABLE_EXAMS]
        or enabled[OPT_ENABLE_GRADES]
        or enabled[OPT_ENABLE_LETTERS]
        or enabled[OPT_ENABLE_MESSAGES]
    ):
        platforms.append(Platform.SENSOR)
    if enabled[OPT_ENABLE_HOMEWORK]:
        platforms.append(Platform.TODO)
    if enabled[OPT_ENABLE_EXAMS] or enabled[OPT_ENABLE_SCHEDULE]:
        platforms.append(Platform.CALENDAR)
    # Always loaded for the manual refresh button
    platforms.append(Platform.BUTTON)
    return platforms


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Schulmanager from a config entry."""
    options = dict(entry.options)

    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]

    # Build unified hub client – handles both single- and multi-school automatically
    schools = entry.data.get("schools")
    institution_id = entry.data.get("institution_id")

    client = SchulmanagerHubClient(
        hass, username, password, user_devices=entry.data.get(CONF_USER_DEVICES)
    )
    try:
        await client.async_login(schools=schools, institution_id=institution_id)
    except SchulmanagerTwoFactorRequiredError as err:
        async_create_two_factor_issue(
            hass,
            entry,
            [
                school_label(account["label"])
                for account in client.get_two_factor_pending()
            ],
        )
        # Retrying cannot help; the repair flow asks for the code and reloads
        raise ConfigEntryError("A two-factor code is needed") from err
    except SchulmanagerAuthError as err:
        raise ConfigEntryAuthFailed("Schulmanager rejected the password") from err
    finally:
        _async_store_login_results(hass, entry, client)
    _async_update_rejected_schools_issue(hass, entry, client)
    if client.get_two_factor_pending() and not client.has_token():
        raise ConfigEntryError("A two-factor code is needed")

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

    # Student devices linked to the service device
    students = client.get_all_students()

    for student in students:
        student_device = device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, f"student_{student['id']}")},
            name=student["name"],
            manufacturer="Schulmanager Online",
            model="Schüler",
            suggested_area="Schule",
            configuration_url="https://login.schulmanager-online.de/",
            via_device_id=service_device.id,
        )

        # If device was orphaned, make sure it's properly linked to this config entry
        if entry.entry_id not in student_device.config_entries:
            device_registry.async_update_device(
                student_device.id,
                add_config_entry_id=entry.entry_id
            )

    _LOGGER.info("Created service device and %d student devices", len(students))

    # Unload must use the platforms loaded here: on an options reload,
    # entry.options already holds the new values.
    platforms = platforms_for_options(options)
    entry.runtime_data = {
        "client": client,
        "coordinator": coordinator,
        "platforms": platforms,
    }

    # Keep minimal mapping for domain-level services bookkeeping
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"entry": entry}

    await hass.config_entries.async_forward_entry_setups(entry, platforms)

    # Register services
    await _async_register_services(hass)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


def _async_store_login_results(
    hass: HomeAssistant, entry: ConfigEntry, client: SchulmanagerHubClient
) -> None:
    """Persist 2FA devices and school names; runs before the update listener exists."""
    data = {**entry.data, CONF_USER_DEVICES: client.get_user_devices()}
    if not data[CONF_USER_DEVICES]:
        del data[CONF_USER_DEVICES]
    if entry.data.get("schools") and (schools := client.get_schools()):
        data["schools"] = schools
    hass.config_entries.async_update_entry(entry, data=data)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry so changed options take effect."""
    await hass.config_entries.async_reload(entry.entry_id)


# Failed-school reasons that the user can fix in their Schulmanager account
_SCHOOL_LOGIN_ISSUES = {
    "password": "school_login_rejected",
    "two_factor": TWO_FACTOR_ISSUE,
}


def _school_login_issue_id(entry: ConfigEntry, translation_key: str) -> str:
    return f"{translation_key}_{entry.entry_id}"


def _async_update_rejected_schools_issue(
    hass: HomeAssistant, entry: ConfigEntry, client: SchulmanagerHubClient
) -> None:
    """Raise a repair issue per reason while some schools cannot be logged into."""
    failed = client.get_failed_schools()
    for reason, translation_key in _SCHOOL_LOGIN_ISSUES.items():
        issue_id = _school_login_issue_id(entry, translation_key)
        schools = [school["label"] for school in failed if school["reason"] == reason]
        if not schools:
            ir.async_delete_issue(hass, DOMAIN, issue_id)
            continue
        if reason == "two_factor":
            async_create_two_factor_issue(
                hass, entry, [school_label(label) for label in schools]
            )
            continue
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=translation_key,
            translation_placeholders={"schools": ", ".join(schools)},
        )


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove the remembered 2FA devices from the Schulmanager accounts."""
    for device in entry.data.get(CONF_USER_DEVICES, []):
        client = SchulmanagerClient(
            hass,
            entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD],
            user_device=device,
        )
        try:
            # Deleting needs a session of the device's account
            await client.async_login()
            await client.async_delete_device()
        except Exception as err:  # noqa: BLE001 - removal must not fail on this
            _LOGGER.warning(
                "Could not remove the remembered device from Schulmanager: %s", err
            )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, entry.runtime_data["platforms"]
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        entry.runtime_data = None
        for translation_key in _SCHOOL_LOGIN_ISSUES.values():
            ir.async_delete_issue(
                hass, DOMAIN, _school_login_issue_id(entry, translation_key)
            )

    # Unregister services if this was the last entry
    if not hass.data[DOMAIN]:
        hass.services.async_remove(DOMAIN, "clear_cache")
        hass.services.async_remove(DOMAIN, "refresh")
        hass.services.async_remove(DOMAIN, "clear_debug")
        hass.services.async_remove(DOMAIN, SERVICE_GET_SCHEDULE)

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
        """Delete all debug dump files, also those written by older versions."""
        debug_path = Path(
            hass.config.path("custom_components", "schulmanager", "debug")
        )
        if await hass.async_add_executor_job(debug_path.exists):
            await hass.async_add_executor_job(shutil.rmtree, debug_path)
            _LOGGER.info("Cleared debug files")

    async def get_schedule_service(call: ServiceCall) -> ServiceResponse:
        """Return the structured schedules already fetched; never calls Schulmanager."""
        if entry_id := call.data.get(ATTR_CONFIG_ENTRY_ID):
            entry = hass.config_entries.async_get_entry(entry_id)
            if (
                entry is None
                or entry.domain != DOMAIN
                or entry.state is not ConfigEntryState.LOADED
            ):
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="config_entry_not_loaded",
                    translation_placeholders={"entry_id": entry_id},
                )
            entries = [entry]
        else:
            entries = [
                entry
                for entry in hass.config_entries.async_entries(DOMAIN)
                if entry.state is ConfigEntryState.LOADED
            ]

        student_id = call.data.get(ATTR_STUDENT_ID)
        students: list[dict[str, Any]] = []
        for entry in entries:
            coordinator: SchulmanagerCoordinator = entry.runtime_data["coordinator"]
            for export in coordinator.schedule_exports.values():
                if student_id is not None and export["student_id"] != student_id:
                    continue
                # A failed refresh keeps the previous data without rebuilding exports
                if (
                    export["status"] == STATUS_OK
                    and not coordinator.last_update_success
                ):
                    export = {**export, "status": STATUS_STALE}
                students.append(export)

        return {
            "schema_version": SCHEMA_VERSION,
            "source": DOMAIN,
            "students": students,
        }

    # Register services only once
    if not hass.services.has_service(DOMAIN, "clear_cache"):
        hass.services.async_register(DOMAIN, "clear_cache", clear_cache_service)
        hass.services.async_register(DOMAIN, "refresh", refresh_service)
        # Deletes files, so restricted to administrators
        async_register_admin_service(
            hass, DOMAIN, "clear_debug", clear_debug_service
        )
        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_SCHEDULE,
            get_schedule_service,
            schema=GET_SCHEDULE_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )
