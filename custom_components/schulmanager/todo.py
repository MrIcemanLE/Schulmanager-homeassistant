"""Todo platform for Schulmanager homework lists."""

from __future__ import annotations

import hashlib
from typing import Any, cast

from homeassistant.components.todo import TodoItem, TodoItemStatus, TodoListEntity
from homeassistant.components.todo.const import TodoListEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SchulmanagerCoordinator
from .privacy import get_logger
from .util import normalize_student_slug

_LOGGER = get_logger(__name__)

# Coordinator-based, no requests per entity
PARALLEL_UPDATES = 0

STORAGE_VERSION = 1
# Before 0.14.1 statuses were stored per student, shared by all config entries
LEGACY_STORAGE_KEY_PREFIX = f"{DOMAIN}_todo"


def todo_status_store(
    hass: HomeAssistant, entry_id: str
) -> Store[dict[str, dict[str, str]]]:
    """Return the store of the checked-off homework of a config entry."""
    return Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}.todo_statuses")


class TodoStatusStore:
    """Statuses of checked-off homework per student: student_id -> uid -> status."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize the store of a config entry."""
        self._hass = hass
        self._store = todo_status_store(hass, entry_id)
        self.statuses: dict[str, dict[str, str]] = {}

    async def async_load(self, student_ids: list[str]) -> None:
        """Load the statuses, taking over the per-student stores of older versions."""
        if (stored := await self._store.async_load()) is not None:
            self.statuses = stored
            return
        for sid in student_ids:
            legacy = Store[dict[str, Any]](
                self._hass, STORAGE_VERSION, f"{LEGACY_STORAGE_KEY_PREFIX}_{sid}"
            )
            if (data := await legacy.async_load()) and data.get("statuses"):
                self.statuses[sid] = dict(data["statuses"])
            await legacy.async_remove()
        if self.statuses:
            await self._store.async_save(self.statuses)

    def student(self, student_id: str) -> dict[str, str]:
        """Return the statuses of a student, to read and change."""
        return self.statuses.setdefault(student_id, {})

    async def async_save(self) -> None:
        """Persist the statuses."""
        await self._store.async_save(self.statuses)


def _make_uid(student_id: str, item: dict, occurrence: int = 0) -> str:
    """Generate a stable ID for homework items, including duplicates.

    For identical homework payloads we keep the first item's legacy UID and
    disambiguate additional occurrences with an occurrence suffix.
    """
    date = str(item.get("date", "")).strip()
    subject = str(item.get("subject", "")).strip()
    homework = str(item.get("homework", "")).strip()
    key = f"{student_id}_{date}{subject}{homework}"
    if occurrence > 0:
        key = f"{key}#{occurrence}"
    return hashlib.md5(key.encode("utf-8")).hexdigest()


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Schulmanager todo list entities."""
    _LOGGER.debug("Setting up Schulmanager todo entities")

    runtime = entry.runtime_data or {}
    coord = runtime.get("coordinator")
    client = runtime.get("client")
    if coord is None or client is None:
        missing = [
            n for n, v in {"coordinator": coord, "client": client}.items() if v is None
        ]
        _LOGGER.warning(
            "Runtime data incomplete for entry %s: missing %s; skipping todo setup",
            entry.entry_id,
            ", ".join(missing),
        )
        return
    try:
        students = client.get_all_students()
    except Exception as err:
        _LOGGER.exception("Failed to load students for todo: %s", err)
        return

    valid: list[tuple[str, str]] = []
    for st in students:
        if not isinstance(st, dict):
            _LOGGER.debug("Skip non-dict student entry: %r", st)
            continue
        sid = st.get("id")
        name = st.get("name")
        if not sid or not name:
            _LOGGER.debug("Skip student with missing id/name: %r", st)
            continue
        valid.append((sid, name))

    status_store = TodoStatusStore(hass, entry.entry_id)
    await status_store.async_load([sid for sid, _ in valid])

    entities: list[TodoListEntity] = []
    for sid, name in valid:
        _LOGGER.debug("Creating todo entity for student %s (ID: %s)", name, sid)
        entities.append(
            HomeworkTodoList(
                client, coord, sid, name, normalize_student_slug(name), status_store
            )
        )

    _LOGGER.debug("Adding %d todo entities", len(entities))
    # No update_before_add: it would make the coordinator fetch everything again
    async_add_entities(entities)


class HomeworkTodoList(CoordinatorEntity[SchulmanagerCoordinator], TodoListEntity):
    """Todo list entity for student homework."""

    _attr_has_entity_name = True
    _attr_supported_features = TodoListEntityFeature.UPDATE_TODO_ITEM

    def __init__(
        self,
        client: Any,
        coordinator: SchulmanagerCoordinator,
        student_id: str,
        student_name: str,
        slug: str,
        status_store: TodoStatusStore,
    ) -> None:
        """Initialize a homework todo list entity for a student."""
        super().__init__(coordinator)
        self.client = client
        self.student_id = student_id
        self.student_name = student_name
        # Stable unique ID, scoped to this config entry so the same student
        # appearing in another entry does not collide with it.
        entry_id = self.coordinator.config_entry.entry_id
        self._attr_unique_id = f"schulmanager_{entry_id}_{self.student_id}_homework"
        # Entity name via translations
        self._attr_translation_key = "homework"
        self._attr_icon = "mdi:clipboard-check-multiple-outline"
        self._attr_todo_items: list[TodoItem] | None = None
        self._status_store = status_store
        # uid -> TodoItemStatus string value; persisted across restarts
        self._persisted_statuses = status_store.student(student_id)

        _LOGGER.info(
            "Created HomeworkTodoList for %s (unique_id: %s)",
            student_name,
            self._attr_unique_id,
        )

    async def async_added_to_hass(self) -> None:
        """Handle entity added to hass, apply the persisted todo statuses."""
        await super().async_added_to_hass()
        self._handle_coordinator_update()

    @property
    def available(self) -> bool:
        """Return if entity is available; a failed fetch leaves the student out."""
        return super().available and self.coordinator.has_student_data(
            "homework", self.student_id
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"student_{self.student_id}")},
            name=self.student_name,
            manufacturer="Schulmanager Online",
            model="Schüler",
            suggested_area="Schule",
            configuration_url="https://login.schulmanager-online.de/",
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        coord_data = cast(dict[str, Any] | None, self.coordinator.data)
        homework_data: dict[str, list[dict[str, Any]]] = (
            {}
            if coord_data is None
            else cast(dict[str, list[dict[str, Any]]], coord_data.get("homework", {}))
        )
        if self.student_id not in homework_data:
            # Failed fetch: keep the items, the entity is unavailable meanwhile
            super()._handle_coordinator_update()
            return
        student_homework = homework_data[self.student_id]

        _LOGGER.debug(
            "Updating homework items for student %s: found %d items",
            self.student_id,
            len(student_homework),
        )

        # Build map of current in-memory items for status lookup
        existing_items: dict[str, TodoItem] = {}
        if self._attr_todo_items:
            existing_items = {
                item.uid: item for item in self._attr_todo_items if item.uid
            }

        if not student_homework:
            self._attr_todo_items = []
        else:
            todo_items: list[TodoItem] = []
            duplicate_counters: dict[str, int] = {}

            for item in student_homework:
                base_uid = _make_uid(self.student_id, item)
                occurrence = duplicate_counters.get(base_uid, 0)
                uid = (
                    base_uid
                    if occurrence == 0
                    else _make_uid(self.student_id, item, occurrence)
                )
                duplicate_counters[base_uid] = occurrence + 1

                subject = item.get("subject", "").strip()
                homework = item.get("homework", "").strip()
                date = item.get("date", "").strip()

                if subject and homework:
                    title = (
                        f"[{date}] {subject}: {homework}"
                        if date
                        else f"{subject}: {homework}"
                    )
                elif homework:
                    title = homework
                elif subject:
                    title = f"{subject}: (Hausaufgabe)"
                else:
                    title = "Hausaufgabe"

                title = title[:255]

                # Status priority:
                # 1. Current in-memory item (reflects any unsaved changes in this session)
                # 2. Persisted status from storage (survives restarts and updates)
                # 3. Default: NEEDS_ACTION
                if existing_item := existing_items.get(uid):
                    status = existing_item.status
                elif persisted := self._persisted_statuses.get(uid):
                    status = TodoItemStatus(persisted)
                    _LOGGER.debug(
                        "Restored persisted status for TodoItem: %s (uid: %s, status: %s)",
                        title[:50],
                        uid[:8],
                        status,
                    )
                else:
                    status = TodoItemStatus.NEEDS_ACTION

                todo_items.append(TodoItem(summary=title, uid=uid, status=status))

            duplicate_uid_groups = sum(
                1 for count in duplicate_counters.values() if count > 1
            )
            if duplicate_uid_groups:
                _LOGGER.debug(
                    "Disambiguated duplicate homework UIDs for student %s: %d groups",
                    self.student_id,
                    duplicate_uid_groups,
                )

            self._attr_todo_items = todo_items

        # Forget statuses of homework Schulmanager no longer lists
        current = {item.uid for item in self._attr_todo_items}
        if stale := [uid for uid in self._persisted_statuses if uid not in current]:
            for uid in stale:
                del self._persisted_statuses[uid]
            self.hass.async_create_task(self._async_save_statuses())

        _LOGGER.debug(
            "Updated %d todo items for student %s",
            len(self._attr_todo_items or []),
            self.student_id,
        )
        super()._handle_coordinator_update()

    async def async_create_todo_item(self, _item: TodoItem) -> None:
        """Create a new todo item."""
        raise NotImplementedError(
            "Cannot create items in a homework list from Schulmanager"
        )

    async def async_update_todo_item(self, item: TodoItem) -> None:
        """Update an existing todo item (status changes only)."""
        if not item.uid or not self._attr_todo_items:
            return

        for i, existing_item in enumerate(self._attr_todo_items):
            if existing_item.uid == item.uid:
                new_status = item.status or existing_item.status
                updated_item = TodoItem(
                    summary=existing_item.summary,
                    uid=existing_item.uid,
                    status=new_status,
                    due=existing_item.due,
                    description=existing_item.description,
                )
                self._attr_todo_items[i] = updated_item

                # Persist the status change
                # Use str() to handle both StrEnum and plain str from HA
                status_str = str(new_status)
                if status_str == TodoItemStatus.NEEDS_ACTION:
                    # Remove from storage when reset to default (keeps storage clean)
                    self._persisted_statuses.pop(item.uid, None)
                else:
                    self._persisted_statuses[item.uid] = status_str

                await self._async_save_statuses()

                _LOGGER.debug(
                    "Updated TodoItem status: %s (uid: %s, status: %s)",
                    (existing_item.summary or "")[:50],
                    (item.uid or "unknown")[:8],
                    new_status,
                )
                self.async_write_ha_state()
                return

        _LOGGER.warning(
            "TodoItem with uid %s not found for update",
            (item.uid or "unknown")[:8],
        )

    async def async_delete_todo_items(self, _uids: list[str]) -> None:
        """Delete todo items."""
        raise NotImplementedError("Cannot delete homework items from Schulmanager")

    async def _async_save_statuses(self) -> None:
        """Persist current todo statuses to HA storage."""
        await self._status_store.async_save()
        _LOGGER.debug(
            "Saved %d todo statuses for student %s",
            len(self._persisted_statuses),
            self.student_id,
        )

    @property
    def should_poll(self) -> bool:
        """No polling needed, coordinator handles updates."""
        return False
