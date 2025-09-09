from __future__ import annotations

import hashlib
import logging
from typing import Any

from homeassistant.components.todo import TodoItem, TodoItemStatus, TodoListEntity
from homeassistant.components.todo.const import TodoListEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, VERSION
from .util import normalize_student_slug

_LOGGER = logging.getLogger(__name__)


def _make_uid(student_id: str, item: dict) -> str:
    """Generate unique ID for homework item."""
    # Vereinfachte UID-Generierung
    date = item.get('date', '')
    subject = item.get('subject', '')
    homework = item.get('homework', '')
    key = f"{student_id}_{date}{subject}{homework}"
    return hashlib.md5(key.encode("utf-8")).hexdigest()


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Schulmanager todo list entities."""
    _LOGGER.debug("Setting up Schulmanager todo entities")

    data = hass.data[DOMAIN][entry.entry_id]
    coord = data["coordinator"]
    hub = data["hub"]
    entities: list[TodoListEntity] = []

    # Debug: Prüfe ob Schüler vorhanden
    _LOGGER.debug("Students available: %s", hub._students)

    for st in hub._students:
        sid = st["id"]
        name = st["name"]
        slug = normalize_student_slug(name)

        _LOGGER.debug("Creating todo entity for student %s (ID: %s)", name, sid)
        entities.append(HomeworkTodoList(hub, coord, sid, name, slug))

    _LOGGER.debug("Adding %d todo entities", len(entities))
    async_add_entities(entities, update_before_add=True)


class HomeworkTodoList(CoordinatorEntity, TodoListEntity):
    """Todo list entity for student homework."""

    _attr_has_entity_name = False
    _attr_supported_features = TodoListEntityFeature.UPDATE_TODO_ITEM

    def __init__(
        self, hub: Any, coordinator: Any, student_id: str, student_name: str, slug: str
    ) -> None:
        super().__init__(coordinator)
        self.hub = hub
        self.student_id = student_id
        self.student_name = student_name
        self._attr_unique_id = f"schulmanager_{slug}_hausaufgaben"
        self._attr_name = f"Hausaufgaben {student_name}"
        self._attr_icon = "mdi:clipboard-check-multiple-outline"
        self._attr_todo_items: list[TodoItem] | None = None

        _LOGGER.info(
            "Created HomeworkTodoList for %s (unique_id: %s, entity_id: todo.%s)",
            student_name,
            self._attr_unique_id,
            self._attr_unique_id,
        )

    async def async_added_to_hass(self) -> None:
        """Handle entity added to hass."""
        _LOGGER.info(
            "HomeworkTodoList %s (student %s) added to hass, subscribing to coordinator",
            self._attr_unique_id,
            self.student_id
        )
        await super().async_added_to_hass()
        # Force an immediate update to make sure entity receives current data
        self._handle_coordinator_update()

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"student_{self.student_id}")},
            name=self.student_name,
            manufacturer="Schulmanager Online",
            model="Schüler",
            sw_version=VERSION,
            suggested_area="Schule",
            configuration_url="https://login.schulmanager-online.de/",
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        coord_data = self.coordinator.data or {}
        homework_data = coord_data.get("homework", {})
        student_homework = homework_data.get(self.student_id, [])

        _LOGGER.debug(
            "Updating homework items for student %s: found %d items. Available students in homework data: %s",
            self.student_id,
            len(student_homework),
            list(homework_data.keys())
        )

        # Create a map of existing items by UID for status preservation
        existing_items = {}
        if self._attr_todo_items:
            existing_items = {
                item.uid: item
                for item in self._attr_todo_items
                if item.uid
            }

        if not student_homework:
            self._attr_todo_items = []
        else:
            todo_items = []
            current_uids = set()

            for item in student_homework:
                if not isinstance(item, dict):
                    continue

                # Debug: Zeige Item-Details
                _LOGGER.debug("Processing homework item: %s", item)

                uid = _make_uid(self.student_id, item)
                current_uids.add(uid)

                # Erstelle Titel aus Fach und Hausaufgabe
                subject = item.get("subject", "").strip()
                homework = item.get("homework", "").strip()
                date = item.get("date", "").strip()

                # Verschiedene Titel-Formate probieren
                if subject and homework:
                    if date:
                        title = f"[{date}] {subject}: {homework}"
                    else:
                        title = f"{subject}: {homework}"
                elif homework:
                    title = homework
                elif subject:
                    title = f"{subject}: (Hausaufgabe)"
                else:
                    title = "Hausaufgabe"

                # Titel-Länge begrenzen
                title = title[:255]

                # Preserve existing status if item already exists
                existing_item = existing_items.get(uid)
                status = (
                    existing_item.status
                    if existing_item
                    else TodoItemStatus.NEEDS_ACTION
                )

                todo_items.append(TodoItem(
                    summary=title,
                    uid=uid,
                    status=status
                ))

                if existing_item:
                    _LOGGER.debug(
                        "Preserved status for TodoItem: %s (uid: %s, status: %s)",
                        title[:50], uid[:8], status
                    )
                else:
                    _LOGGER.debug(
                        "Created new TodoItem: %s (uid: %s)",
                        title[:50], uid[:8]
                    )

            # Log removed items for debugging
            if existing_items:
                removed_uids = set(existing_items.keys()) - current_uids
                if removed_uids:
                    _LOGGER.debug(
                        "Removed %d outdated todo items for student %s: %s",
                        len(removed_uids),
                        self.student_id,
                        [uid[:8] for uid in removed_uids]
                    )

            self._attr_todo_items = todo_items

        _LOGGER.debug(
            "Updated %d todo items for student %s",
            len(self._attr_todo_items or []),
            self.student_id
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

        # Find and update the item in our local list
        for i, existing_item in enumerate(self._attr_todo_items):
            if existing_item.uid == item.uid:
                # Only allow status updates, preserve other fields from original
                updated_item = TodoItem(
                    summary=existing_item.summary,
                    uid=existing_item.uid,
                    status=item.status or existing_item.status,
                    due=existing_item.due,
                    description=existing_item.description,
                )
                self._attr_todo_items[i] = updated_item

                _LOGGER.debug(
                    "Updated TodoItem status: %s (uid: %s, status: %s)",
                    (existing_item.summary or "")[:50],
                    (item.uid or "unknown")[:8],
                    updated_item.status
                )

                # Notify Home Assistant of the state change
                self.async_write_ha_state()
                return

        _LOGGER.warning(
            "TodoItem with uid %s not found for update",
            (item.uid or "unknown")[:8]
        )

    async def async_delete_todo_items(self, _uids: list[str]) -> None:
        """Delete todo items."""
        raise NotImplementedError("Cannot delete homework items from Schulmanager")

    @property
    def should_poll(self) -> bool:
        """No polling needed, coordinator handles updates."""
        return False
