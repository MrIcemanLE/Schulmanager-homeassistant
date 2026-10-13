"""Sensors for the Schulmanager integration.

Provides schedule, schedule-changes, grade sensors and an exam countdown per
student. All sensors subscribe to the integration coordinator for updates and
use stable, ID-based unique IDs.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from html import escape, unescape
import logging
import re
from typing import Any, cast

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import grading
from .const import (
    DEFAULT_ENABLE_LETTERS,
    DEFAULT_ENABLE_MESSAGES,
    DOMAIN,
    OPT_ENABLE_LETTERS,
    OPT_ENABLE_MESSAGES,
    OPT_SCHEDULE_HIGHLIGHT,
    VERSION,
)
from .coordinator import SchulmanagerCoordinator
from .types import IntegrationData
from .util import normalize_student_slug

_LOGGER = logging.getLogger(__name__)

LESSON_TYPE_LABELS: dict[str, str] = {
    "regularLesson": "Regulär",
    "cancelledLesson": "Ausfall",
    "specialLesson": "Sonderstunde",
    "substitution": "Vertretung",
    "teacherChange": "Lehrkraftwechsel",
    "roomChange": "Raumwechsel",
    "irregularLesson": "Unregelmäßig",
    "event": "Veranstaltung",
    "exam": "Prüfung",
}

HIGHLIGHT_ROW_ATTR = " bgcolor="  # cfe8ff""


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Schulmanager sensor entities."""
    # Prefer runtime_data over hass.data for runtime storage
    runtime = entry.runtime_data or {}
    coord = runtime.get("coordinator")
    client = runtime.get("client")
    if coord is None or client is None:
        missing = [
            n for n, v in {"coordinator": coord, "client": client}.items() if v is None
        ]
        _LOGGER.warning(
            "Runtime data incomplete for entry %s: missing %s; skipping sensor setup",
            entry.entry_id,
            ", ".join(missing),
        )
        return
    entities: list[SensorEntity] = []

    data = cast(IntegrationData | None, coord.data)
    students: list[dict[str, Any]] = [] if data is None else data.get("students", [])

    for st in students:
        sid = st["id"]
        name = st["name"]
        slug = normalize_student_slug(name)
        entities.append(ScheduleSensor(client, coord, sid, name, slug, "today"))
        entities.append(ScheduleSensor(client, coord, sid, name, slug, "tomorrow"))
        entities.append(ScheduleChangesSensor(client, coord, sid, name, slug))
        entities.append(CurrentLessonSensor(client, coord, sid, name, slug))

        # Add grade sensors for each subject
        # We'll check for available subjects from the first update
        grades_data: dict[str, Any] = (
            {}
            if data is None
            else cast(dict[str, Any], data.get("grades", {}).get(sid, {}))
        )
        subjects: dict[int, dict[str, Any]] = cast(
            dict[int, dict[str, Any]], grades_data.get("subjects", {})
        )

        for subject_id, subject_data in subjects.items():
            subject_name = subject_data.get("name", f"Fach {subject_id}")
            subject_abbrev = subject_data.get("abbreviation", subject_name)
            entities.append(
                GradeSensor(
                    client,
                    coord,
                    sid,
                    name,
                    slug,
                    subject_id,
                    subject_name,
                    subject_abbrev,
                )
            )

        # Add overall average sensor
        entities.append(OverallGradeSensor(client, coord, sid, name, slug))

        # Add days until next exam sensor
        entities.append(NextExamCountdownSensor(client, coord, sid, name, slug))

        # Add school diagnostic sensor (shows which school the student belongs to)
        # Only relevant for multi-school accounts, but added for all students
        school_name = st.get("school_name")  # May be None for single-school accounts
        school_id = st.get("school_id")  # May be None for single-school accounts
        entities.append(SchoolDiagnosticSensor(coord, sid, name, slug, school_name, school_id))

        # Add Wochenplan JSON sensor (for Stundenplan Card integration)
        entities.append(WochenplanJsonSensor(client, coord, sid, name, slug))

    # Account-level sensors (parents' inbox): unread letters and messenger conversations
    if entry.options.get(OPT_ENABLE_LETTERS, DEFAULT_ENABLE_LETTERS):
        entities.append(UnreadLettersSensor(coord))
    if entry.options.get(OPT_ENABLE_MESSAGES, DEFAULT_ENABLE_MESSAGES):
        entities.append(UnreadMessagesSensor(coord))

    async_add_entities(entities)


class ScheduleSensor(CoordinatorEntity[SchulmanagerCoordinator], SensorEntity):
    """Sensor entity for student schedule."""

    _attr_has_entity_name = True

    def __init__(
        self,
        client: Any,
        coordinator: SchulmanagerCoordinator,
        student_id: str,
        student_name: str,
        slug: str,
        day: str,
    ) -> None:
        """Initialize a schedule sensor for the given day."""
        super().__init__(coordinator)
        self.client = client
        self.student_id = student_id
        self.student_name = student_name
        self.day = day
        # Stable unique ID, scoped to this config entry so the same student
        # appearing in another entry (e.g. their own login alongside a
        # parent's account) does not collide with it.
        entry_id = self.coordinator.config_entry.entry_id
        self._attr_unique_id = f"schulmanager_{entry_id}_{self.student_id}_schedule_{day}"
        # Use translations for entity name
        self._attr_translation_key = (
            "schedule_today" if day == "today" else "schedule_tomorrow"
        )
        self._attr_icon = "mdi:school-outline"

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

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return bool(self.coordinator.last_update_success)

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        integ = cast(IntegrationData | None, self.coordinator.data)
        items: list[dict[str, Any]] = []
        if integ is not None:
            sched = cast(
                dict[str, Any], integ.get("schedule", {}).get(self.student_id, {})
            )
            items = cast(list[dict[str, Any]], sched.get(self.day, []) or [])

        # Check if today/tomorrow is a weekend
        if self._is_weekend_day():
            return "Wochenende"

        # If no lessons, assume it's a day off
        if not items:
            return "Schulfrei"

        # Check if there are any deviations from normal schedule
        # In new structure, check for type != "regularLesson" or missing actualLesson
        deviations = any(
            lesson.get("type") != "regularLesson" or not lesson.get("actualLesson")
            for lesson in items
            if isinstance(lesson, dict)
        )

        return "Planmäßig" if not deviations else "Abweichung"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the state attributes."""
        integ = cast(IntegrationData | None, self.coordinator.data)
        items: list[dict[str, Any]] = []
        if integ is not None:
            sched = cast(
                dict[str, Any], integ.get("schedule", {}).get(self.student_id, {})
            )
            items = cast(list[dict[str, Any]], sched.get(self.day, []) or [])

        def _resolve_hour_str(lesson: dict[str, Any]) -> str:
            class_hour = lesson.get("classHour", {})
            hour = class_hour.get("number")
            if isinstance(hour, int):
                return str(hour)
            if isinstance(hour, str) and hour.strip():
                return hour.strip()
            for alt_key in ("hour", "lessonHour", "lessonNumber", "hourNumber"):
                alt_val = lesson.get(alt_key)
                if isinstance(alt_val, int):
                    return str(alt_val)
                if isinstance(alt_val, str) and alt_val.strip():
                    return alt_val.strip()
            return ""

        def get_hour_number(lesson: dict[str, Any]) -> int:
            """Extract hour number from lesson, defaulting to 999 for sorting."""
            hour_str = _resolve_hour_str(lesson)
            if hour_str.isdigit():
                return int(hour_str)
            try:
                return int(float(hour_str.replace(",", ".")))
            except (ValueError, TypeError):
                return 999

        items_sorted = sorted(items, key=get_hour_number)

        raw_data: dict[str, Any] = {
            "lessons": [],
            "day": self.day,
            "student_id": self.student_id,
            "date": self._get_target_date().isoformat() if items else None,
        }

        if self._is_weekend_day():
            html = (
                '<table width="100%"><thead><tr><th>Wochenende</th></tr></thead><tbody>'
                "<tr><td>Heute ist Wochenende - keine Schule</td></tr>"
                "</tbody></table>"
            )
            return {
                "raw": raw_data,
                "html": html,
                "lesson_count": len(raw_data["lessons"]),
            }

        def _teacher_names(source: dict[str, Any]) -> str:
            names: list[str] = []
            teachers = source.get("teachers")
            if isinstance(teachers, list):
                for teacher in teachers:
                    if not isinstance(teacher, dict):
                        continue
                    abbr = teacher.get("abbreviation")
                    if abbr:
                        names.append(str(abbr))
                        continue
                    firstname = teacher.get("firstname")
                    lastname = teacher.get("lastname")
                    if firstname and lastname:
                        names.append(f"{firstname} {lastname}")
                    elif lastname:
                        names.append(str(lastname))
            return ", ".join(names)

        def _extract_core_info(source: dict[str, Any] | None) -> dict[str, str]:
            if not isinstance(source, dict):
                return {"subject": "", "subject_full": "", "room": "", "teacher": ""}
            subject = ""
            subject_full = ""
            subject_data = source.get("subject")
            if isinstance(subject_data, dict):
                subject = (
                    subject_data.get("abbreviation")
                    or subject_data.get("shortName")
                    or ""
                )
                subject_full = (
                    subject_data.get("name") or subject_data.get("longName") or subject
                )
            elif isinstance(subject_data, str):
                subject = subject_full = subject_data
            else:
                subject = (
                    source.get("subjectShort")
                    or source.get("subject_name")
                    or source.get("subject")
                    or ""
                )
                subject_full = (
                    source.get("subjectLong") or source.get("subjectFull") or subject
                )
            room_data = source.get("room")
            if isinstance(room_data, dict):
                room = (
                    room_data.get("name")
                    or room_data.get("shortName")
                    or room_data.get("abbreviation")
                    or ""
                )
            elif isinstance(room_data, str):
                room = room_data
            else:
                room = ""
            teacher = _teacher_names(source)
            return {
                "subject": subject,
                "subject_full": subject_full,
                "room": room,
                "teacher": teacher,
            }

        def _extract_primary_info(lesson: dict[str, Any]) -> dict[str, str]:
            candidates = [
                lesson.get("actualLesson"),
                lesson.get("lesson"),
                lesson,
            ]
            for candidate in candidates:
                info = _extract_core_info(candidate)
                if any(info.values()):
                    return info
            return {"subject": "", "subject_full": "", "room": "", "teacher": ""}

        def _extract_original_info(lesson: dict[str, Any]) -> dict[str, str]:
            candidates: list[dict[str, Any] | None] = []
            original = lesson.get("originalLesson")
            if isinstance(original, dict):
                candidates.append(original)
            original_list = lesson.get("originalLessons")
            if isinstance(original_list, list):
                for entry in original_list:
                    if isinstance(entry, dict):
                        candidates.append(entry)
            candidates.append(lesson.get("lesson"))
            for candidate in candidates:
                info = _extract_core_info(candidate)
                if any(info.values()):
                    return info
            return {"subject": "", "subject_full": "", "room": "", "teacher": ""}

        def _build_info_text(lesson: dict[str, Any], teacher_text: str) -> str:
            info_parts: list[str] = []
            if teacher_text:
                info_parts.append(teacher_text)
            extra_parts: list[str] = []
            for key in ("substitutionText", "comment", "note", "informationText"):
                value = lesson.get(key)
                if isinstance(value, str) and value.strip():
                    extra_parts.append(value.strip())
            if extra_parts:
                info_parts.append(" / ".join(extra_parts))
            return " - ".join(info_parts)

        def _hour_display(lesson: dict[str, Any]) -> tuple[str, str]:
            hour_str = _resolve_hour_str(lesson)
            label = f"{hour_str}. Std" if hour_str else ""
            return hour_str, label

        blocks: list[dict[str, Any]] = []
        block_lists: dict[str, list[dict[str, Any]]] = {}

        def _acquire_block(lesson: dict[str, Any], lesson_type: str) -> dict[str, Any]:
            hour_value, hour_label = _hour_display(lesson)
            if not hour_value:
                originals = []
                original_single = lesson.get("originalLesson")
                if isinstance(original_single, dict):
                    originals.append(original_single)
                original_list = lesson.get("originalLessons")
                if isinstance(original_list, list):
                    originals.extend(o for o in original_list if isinstance(o, dict))
                for original in originals:
                    hour_value = _resolve_hour_str(original)
                    if hour_value:
                        hour_label = f"{hour_value}. Std"
                        break
            class_hour = lesson.get("classHour", {})
            date_key = (
                lesson.get("date") or lesson.get("day") or lesson.get("start") or ""
            )[:10]
            class_hour_id = class_hour.get("id")
            hour_key = hour_value or (
                str(class_hour_id) if class_hour_id is not None else ""
            )
            if not hour_key:
                linked_lesson = lesson.get("lesson")
                if isinstance(linked_lesson, dict):
                    candidate = linked_lesson.get("id") or linked_lesson.get("lessonId")
                    if candidate:
                        hour_key = str(candidate)
                if not hour_key:
                    for candidate_key in ("id", "lessonId", "lessonID", "lesson_id"):
                        candidate_val = lesson.get(candidate_key)
                        if candidate_val:
                            hour_key = str(candidate_val)
                            break
            if not hour_key:
                hour_key = f"fallback-{len(blocks)}"
            key = f"{date_key}|{hour_key}"
            block_list = block_lists.setdefault(key, [])
            if lesson_type == "cancelledLesson":
                for block in block_list:
                    if block.get("secondary") is None:
                        block.setdefault("hour_display", hour_label)
                        block.setdefault("hour_value", hour_value)
                        return block
            else:
                for block in block_list:
                    if block.get("primary") is None:
                        block.setdefault("hour_display", hour_label)
                        block.setdefault("hour_value", hour_value)
                        return block
            block = {
                "hour_display": hour_label,
                "hour_value": hour_value,
                "primary": None,
                "secondary": None,
                "has_change": False,
            }
            blocks.append(block)
            block_list.append(block)
            return block

        for lesson in items_sorted:
            lesson_type = lesson.get("type", "regularLesson")
            primary_info = _extract_primary_info(lesson)
            original_info = _extract_original_info(lesson)
            hour_value, _ = _hour_display(lesson)
            lesson_entry = {
                "hour": hour_value,
                "subject": primary_info["subject"],
                "subject_full": primary_info["subject_full"],
                "room": primary_info["room"],
                "teacher": primary_info["teacher"],
                "type": lesson_type,
                "date": lesson.get("date"),
            }
            if any(original_info.values()):
                lesson_entry["original"] = original_info
            raw_data["lessons"].append(lesson_entry)

            block = _acquire_block(lesson, lesson_type)
            if lesson_type == "cancelledLesson":
                block["has_change"] = True
                block.setdefault("cancel_lesson", lesson)
                info_for_cancel = (
                    original_info if any(original_info.values()) else primary_info
                )
                block["secondary"] = {
                    "subject": info_for_cancel["subject"],
                    "room": info_for_cancel["room"],
                    "info": info_for_cancel["teacher"],
                    "strike": True,
                }
                block.setdefault(
                    "cancel_type_label",
                    LESSON_TYPE_LABELS.get(lesson_type, lesson_type),
                )
            else:
                info_text = _build_info_text(lesson, primary_info["teacher"])
                block["primary"] = {
                    "subject": primary_info["subject"],
                    "room": primary_info["room"],
                    "info": info_text,
                    "lesson_type": lesson_type,
                    "highlight": lesson_type != "regularLesson",
                }
                if lesson_type != "regularLesson":
                    block["has_change"] = True

        rows: list[str] = []

        def _format_cell(value: str, *, strike: bool = False) -> str:
            if value:
                content = escape(value)
                if strike:
                    content = f"<i><s>{content}</s></i>"
            else:
                content = "&nbsp;"
            return f"<td>{content}</td>"

        for block in blocks:
            primary = block.get("primary")
            secondary = block.get("secondary")
            if primary is None:
                cancel_lesson = block.get("cancel_lesson", {})
                cancel_label = block.get("cancel_type_label", "Ausfall")
                teacher_text = ""
                if isinstance(cancel_lesson, dict):
                    teacher_text = _extract_original_info(cancel_lesson).get(
                        "teacher", ""
                    )
                info_text = (
                    _build_info_text(cancel_lesson, teacher_text)
                    if isinstance(cancel_lesson, dict)
                    else ""
                )
                primary = {
                    "subject": cancel_label,
                    "room": "",
                    "info": info_text,
                    "highlight": True,
                    "lesson_type": "cancelledLesson",
                }
                block["has_change"] = True
                block["primary"] = primary
            else:
                highlight = (
                    block.get("has_change")
                    or primary.get("lesson_type") != "regularLesson"
                )
                primary["highlight"] = bool(highlight)
                # lesson_type is kept (not popped) - _generate_plain_text needs it
                # for emoji selection and it's otherwise unused by the html rows.
            if secondary is None:
                secondary = {"subject": "", "room": "", "info": "", "strike": False}
                block["secondary"] = secondary

            hour_label = block.get("hour_display") or ""
            hour_markup = (
                f"<strong>{escape(hour_label)}</strong>" if hour_label else "&nbsp;"
            )
            row_attr = HIGHLIGHT_ROW_ATTR if primary.get("highlight") else ""
            hour_cell = f'<td rowspan="2" valign="top">{hour_markup}</td>'
            rows.append(

                    f"<tr{row_attr}>{hour_cell}"
                    f"{_format_cell(primary.get('subject', ''))}"
                    f"{_format_cell(primary.get('room', ''))}"
                    f"{_format_cell(primary.get('info', ''))}"
                    "</tr>"

            )
            rows.append(

                    f"<tr{row_attr}>"
                    f"{_format_cell(secondary.get('subject', ''), strike=secondary.get('strike', False))}"
                    f"{_format_cell(secondary.get('room', ''), strike=secondary.get('strike', False))}"
                    f"{_format_cell(secondary.get('info', ''), strike=secondary.get('strike', False))}"
                    "</tr>"

            )

        if not rows:
            html = (
                '<table width="100%"><thead><tr><th>Schulfrei</th></tr></thead><tbody>'
                "<tr><td>Heute ist schulfrei</td></tr>"
                "</tbody></table>"
            )
        else:
            html = (
                '<table width="100%"><thead><tr>'
                "<th align=\"left\">Stunde</th><th align=\"left\">Fach</th><th align=\"left\">Raum</th><th align=\"left\">Info</th>"
                "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
            )

        # Generate plain text format for notifications (with emoji highlighting).
        # Reuses the already per-hour-merged `blocks` (not the raw lesson list)
        # so a cancelled lesson with a same-hour substitution produces exactly
        # one line, matching the html attribute instead of showing both.
        plain_text = self._generate_plain_text(blocks)

        return {
            "raw": raw_data,
            "html": html,
            "plain": plain_text,
            "lesson_count": len(raw_data["lessons"]),
        }

    def _is_weekend_day(self) -> bool:
        """Check if the target day is a weekend."""
        target_date = self._get_target_date()
        return target_date.weekday() >= 5

    def _get_target_date(self) -> datetime:
        """Get the date for the current day (today/tomorrow)."""
        now = datetime.now()
        if self.day == "today":
            return now
        if self.day == "tomorrow":
            return now + timedelta(days=1)
        return now

    def _generate_plain_text(self, blocks: list[dict[str, Any]]) -> str:
        """Generate plain text schedule with emoji highlighting for notifications.

        Format: "1. Std: 🔁 Mathematik – Raum 204 (Vertretung)"
        Uses same emoji logic as calendar.

        Consumes the same per-hour-merged `blocks` structure the html
        attribute is built from (one entry per hour, cancellation already
        suppressed when a same-hour substitution exists), so a cancelled
        lesson with a substitution produces exactly one line here too,
        instead of one line per raw lesson.
        """
        if not blocks:
            if self._is_weekend_day():
                return "Wochenende - keine Schule"
            return "Schulfrei"

        # Get highlight option from config entry
        highlight = False
        if self.coordinator.config_entry:
            opts = dict(self.coordinator.config_entry.options or {})
            highlight = bool(opts.get(OPT_SCHEDULE_HIGHLIGHT, True))

        lines: list[str] = []

        for block in blocks:
            primary = block.get("primary") or {}
            lesson_type = primary.get("lesson_type", "regularLesson")
            hour_str = block.get("hour_display") or ""
            subject = primary.get("subject") or "Unterricht"
            room = primary.get("room") or ""

            # Emoji highlighting (same logic as calendar.py)
            emoji = ""
            if highlight:
                if lesson_type == "cancelledLesson":
                    emoji = "❌ "
                elif lesson_type in {"substitution", "specialLesson", "teacherChange", "irregularLesson"}:
                    emoji = "🔁 "
                elif lesson_type == "roomChange":
                    emoji = "🚪 "
                elif lesson_type == "exam":
                    emoji = "📝 "
            elif lesson_type == "cancelledLesson":
                # Without highlight: simple X marker for cancellations
                emoji = "X "

            # Build line
            line_parts = [hour_str] if hour_str else []

            # Subject with emoji
            subject_part = f"{emoji}{subject}"
            if room:
                subject_part += f" – {room}"
            line_parts.append(subject_part)

            # Additional info (teacher/reason, already combined by the html
            # path's _build_info_text), falling back to a type label
            info_parts: list[str] = []
            info_text = primary.get("info") or ""
            if info_text:
                info_parts.append(info_text)
            elif lesson_type not in ("regularLesson", "cancelledLesson"):
                info_parts.append(LESSON_TYPE_LABELS.get(lesson_type, lesson_type))

            # Assemble line
            if line_parts:
                line = ": ".join(line_parts)
                if info_parts:
                    line += f" ({', '.join(info_parts)})"
                lines.append(line)

        return "\n".join(lines) if lines else "Keine Stunden"


class ScheduleChangesSensor(CoordinatorEntity[SchulmanagerCoordinator], SensorEntity):
    """Sensor entity for schedule changes structured for LLM processing."""

    _attr_has_entity_name = True

    def __init__(
        self,
        client: Any,
        coordinator: SchulmanagerCoordinator,
        student_id: str,
        student_name: str,
        slug: str,
    ) -> None:
        """Initialize the schedule changes sensor."""
        super().__init__(coordinator)
        self.client = client
        self.student_id = student_id
        self.student_name = student_name
        # Stable unique ID, scoped to this config entry so the same student
        # appearing in another entry does not collide with it.
        entry_id = self.coordinator.config_entry.entry_id
        self._attr_unique_id = f"schulmanager_{entry_id}_{self.student_id}_schedule_changes"
        self._attr_translation_key = "schedule_changes"
        self._attr_icon = "mdi:calendar-alert"

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

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return bool(self.coordinator.last_update_success)

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor - total number of changes."""
        integ = cast(IntegrationData | None, self.coordinator.data)
        changes: dict[str, Any] = {}
        if integ is not None:
            sched = cast(
                dict[str, Any], integ.get("schedule", {}).get(self.student_id, {})
            )
            changes = cast(dict[str, Any], sched.get("changes", {}) or {})

        today_changes = len(changes.get("today", []))
        tomorrow_changes = len(changes.get("tomorrow", []))
        return today_changes + tomorrow_changes

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the structured schedule changes for LLM processing."""
        integ = cast(IntegrationData | None, self.coordinator.data)
        changes: dict[str, Any] = {}
        if integ is not None:
            sched = cast(
                dict[str, Any], integ.get("schedule", {}).get(self.student_id, {})
            )
            changes = cast(dict[str, Any], sched.get("changes", {}) or {})

        if not changes:
            return {
                "changes": {
                    "today": [],
                    "tomorrow": [],
                    "summary": "Keine Stundenplanänderungen erkannt",
                },
                "llm_structured_data": {
                    "has_changes": False,
                    "total_changes": 0,
                    "today_count": 0,
                    "tomorrow_count": 0,
                    "natural_language_summary": "Keine Stundenplanänderungen für heute und morgen erkannt.",
                },
            }

        today_changes = changes.get("today", [])
        tomorrow_changes = changes.get("tomorrow", [])
        total_changes = len(today_changes) + len(tomorrow_changes)

        # Create LLM-optimized structured data
        detailed_changes: list[dict[str, Any]] = []
        llm_data: dict[str, Any] = {
            "has_changes": total_changes > 0,
            "total_changes": total_changes,
            "today_count": len(today_changes),
            "tomorrow_count": len(tomorrow_changes),
            "natural_language_summary": changes.get("summary", "No changes detected"),
            "detailed_changes": detailed_changes,
        }

        # Add detailed changes for LLM processing
        for day_name, day_changes in [
            ("today", today_changes),
            ("tomorrow", tomorrow_changes),
        ]:
            for change in day_changes:
                detail = {
                    "day": day_name,
                    "hour": change.get("hour", "?"),
                    "change_type": change.get("type", "Unknown"),
                    "subject": change.get("new_subject", ""),
                    "teacher": change.get("new_teacher", ""),
                    "room": change.get("new_room", ""),
                    "reason": change.get("reason", ""),
                    "note": change.get("note", ""),
                    "date": change.get("date", ""),
                }
                detailed_changes.append(detail)

        return {
            "changes": changes,
            "llm_structured_data": llm_data,
            "last_updated": datetime.now().isoformat(),
        }


class GradeSensor(CoordinatorEntity[SchulmanagerCoordinator], SensorEntity):
    """Sensor entity for student grades in a specific subject."""

    _attr_has_entity_name = True
    _attr_state_class = None
    _attr_suggested_display_precision = 1

    def __init__(
        self,
        client: Any,
        coordinator: SchulmanagerCoordinator,
        student_id: str,
        student_name: str,
        slug: str,
        subject_id: int,
        subject_name: str,
        subject_abbrev: str,
    ) -> None:
        """Initialize the grade sensor."""
        super().__init__(coordinator)
        self.client = client
        self.student_id = student_id
        self.student_name = student_name
        self.subject_id = subject_id
        self.subject_name = subject_name
        self.subject_abbrev = subject_abbrev
        # Stable unique ID, scoped to this config entry so the same student
        # appearing in another entry does not collide with it.
        entry_id = self.coordinator.config_entry.entry_id
        self._attr_unique_id = (
            f"schulmanager_{entry_id}_{self.student_id}_grades_{self.subject_id!s}"
        )

        # Keep dynamic name since it includes subject abbreviation
        self._attr_name = f"Noten {subject_abbrev}"
        self._attr_icon = "mdi:school"

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

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return bool(self.coordinator.last_update_success)

    @property
    def native_value(self) -> StateType:
        """Return the average grade for this subject (if available)."""
        integ = cast(IntegrationData | None, self.coordinator.data)
        grades_data: dict[str, Any] = (
            {}
            if integ is None
            else cast(dict[str, Any], integ.get("grades", {}).get(self.student_id, {}))
        )
        subjects: dict[int, Any] = grades_data.get("subjects", {})
        subject_data = subjects.get(self.subject_id, {})

        # API doesn't provide calculated average, so we'll return None for now
        # The user requested not to calculate it ourselves, but read from API response
        average = subject_data.get("average")
        if average is not None:
            try:
                return float(average)
            except (ValueError, TypeError):
                pass

        # If no average is provided, return None (German grades are always numeric)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the detailed grade information by category."""
        integ = cast(IntegrationData | None, self.coordinator.data)
        grades_data: dict[str, Any] = (
            {}
            if integ is None
            else cast(dict[str, Any], integ.get("grades", {}).get(self.student_id, {}))
        )
        subjects: dict[int, Any] = grades_data.get("subjects", {})
        subject_data = subjects.get(self.subject_id, {})

        if not subject_data:
            return {
                "subject_name": self.subject_name,
                "subject_id": self.subject_id,
                "total_grades": 0,
                "grade_categories": {},
                "grades_summary": "No grades available",
                "grades_summary_markdown": "_Keine Noten verfügbar_",
            }

        grade_categories: dict[str, list[dict[str, Any]]] = cast(
            dict[str, list[dict[str, Any]]], subject_data.get("grades", {})
        )
        grading_system = subject_data.get("grading_system", grading.GRADING_SYSTEM_CLASSIC)
        total_grades = 0

        # Count total grades and prepare category data with numeric values
        category_summary: dict[str, dict[str, Any]] = {}
        for category, grades_list in grade_categories.items():
            # Process grades to include numeric values
            processed_grades: list[dict[str, Any]] = []
            for grade in grades_list:
                grade_info = dict(grade)  # Copy original grade data
                grade_value = grade.get("value", "")

                # Extract numeric value using the same parsing logic as API client
                numeric_value = grading.parse_grade_value(grade_value, grading_system)
                if numeric_value is not None and grading.grade_value_in_range(
                    numeric_value, grading_system
                ):
                    grade_info["numeric_value"] = numeric_value

                processed_grades.append(grade_info)

            # Only include categories that have grades
            if processed_grades:
                category_summary[category] = {
                    "count": len(processed_grades),
                    "grades": processed_grades,
                }
                total_grades += len(processed_grades)

        # Extract numeric grade values for best/worst (average comes from the
        # already-computed subject_data["average"] instead of recomputing it)
        all_grade_values: list[float | int] = []
        for grades_list in grade_categories.values():
            for grade in grades_list:
                grade_value = grade.get("value", "")
                numeric_grade = grading.parse_grade_value(grade_value, grading_system)
                if numeric_grade is not None and grading.grade_value_in_range(
                    numeric_grade, grading_system
                ):
                    all_grade_values.append(numeric_grade)

        # Calculate basic statistics
        statistics = {}
        if all_grade_values:
            higher_is_better = grading.is_higher_better(grading_system)
            statistics = {
                "average": subject_data.get("average"),
                "best_grade": max(all_grade_values) if higher_is_better else min(all_grade_values),
                "worst_grade": min(all_grade_values) if higher_is_better else max(all_grade_values),
                "total_numeric_grades": len(all_grade_values),
            }

        # Build human-readable summaries (plain text and Markdown)
        def _format_grade_line(g: dict) -> str:
            # Use display_value if available (clean notation like "3+", "2-"), otherwise fallback to value
            val = str(g.get("display_value") or g.get("value", "")).strip()
            topic = (g.get("topic") or "").strip()
            date = (g.get("date") or "").strip()
            type_abbr = (g.get("type_abbreviation") or "").strip()
            weighting = g.get("weighting")
            s = val
            info: list[str] = []
            if topic:
                info.append(topic)
            if date:
                info.append(date)
            if type_abbr:
                info.append(type_abbr)
            if weighting not in (None, 1):
                info.append(f"w={weighting}")
            if info:
                s += " (" + ", ".join(info) + ")"
            return s

        lines_text: list[str] = []
        lines_md: list[str] = [f"### {self.subject_name} ({self.subject_abbrev})"]
        if statistics.get("average") is not None:
            lines_text.append(f"Durchschnitt: {statistics['average']}")
            lines_md.append(f"**Durchschnitt:** {statistics['average']}")
        for category, data in category_summary.items():
            grades_list = cast(list[dict[str, Any]], data["grades"])
            if not grades_list:
                continue
            lines_text.append(f"{category} ({len(grades_list)}):")
            lines_md.append(f"- **{category}** ({len(grades_list)}):")
            for g in grades_list:
                line = _format_grade_line(g)
                lines_text.append(f"  - {line}")
                lines_md.append(f"  - {line}")

        grades_summary = (
            "\n".join(lines_text) if lines_text else "Keine Noten verfügbar"
        )
        grades_summary_md = (
            "\n".join(lines_md) if lines_md else "_Keine Noten verfügbar_"
        )

        return {
            "subject_name": self.subject_name,
            "subject_id": self.subject_id,
            "total_grades": total_grades,
            "grade_categories": category_summary,  # Only non-empty categories
            "statistics": statistics,
            "grades_summary": grades_summary,
            "grades_summary_markdown": grades_summary_md,
            "last_updated": datetime.now().isoformat(),
        }


class OverallGradeSensor(CoordinatorEntity[SchulmanagerCoordinator], SensorEntity):
    """Sensor entity for student's overall grade average."""

    _attr_has_entity_name = True
    _attr_state_class = None
    _attr_suggested_display_precision = 1

    def __init__(
        self,
        client: Any,
        coordinator: Any,
        student_id: str,
        student_name: str,
        slug: str,
    ) -> None:
        """Initialize the overall grade sensor."""
        super().__init__(coordinator)
        self.client = client
        self.student_id = student_id
        self.student_name = student_name
        # Stable unique ID, scoped to this config entry so the same student
        # appearing in another entry does not collide with it.
        entry_id = self.coordinator.config_entry.entry_id
        self._attr_unique_id = f"schulmanager_{entry_id}_{self.student_id}_grades_overall"

        # Use translation for entity name
        self._attr_translation_key = "grades_overall"
        self._attr_icon = "mdi:school"

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

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return bool(self.coordinator.last_update_success)

    @property
    def native_value(self) -> StateType:
        """Return the overall average grade for this student."""
        integ = cast(IntegrationData | None, self.coordinator.data)
        grades_data: dict[str, Any] = (
            {}
            if integ is None
            else cast(dict[str, Any], integ.get("grades", {}).get(self.student_id, {}))
        )

        overall_average = grades_data.get("overall_average")
        if overall_average is not None:
            try:
                return float(overall_average)
            except (ValueError, TypeError):
                pass

        # If no overall average, return None
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the overall grade statistics."""
        integ = cast(IntegrationData | None, self.coordinator.data)
        grades_data: dict[str, Any] = (
            {}
            if integ is None
            else cast(dict[str, Any], integ.get("grades", {}).get(self.student_id, {}))
        )

        if not grades_data:
            return {
                "total_subjects": 0,
                "subjects_with_grades": 0,
                "subject_averages": {},
                "grades_summary": "No grades available",
                "grades_summary_markdown": "_Keine Noten verfügbar_",
                "last_updated": datetime.now().isoformat(),
            }

        # Collect subject averages
        subjects: dict[int, dict[str, Any]] = cast(
            dict[int, dict[str, Any]], grades_data.get("subjects", {})
        )
        subject_averages: dict[str, Any] = {}

        for subject_id, subject_data in subjects.items():
            subject_name = subject_data.get("name", f"Fach {subject_id}")
            subject_abbrev = subject_data.get("abbreviation", subject_name)
            avg = subject_data.get("average")

            if avg is not None:
                subject_averages[subject_abbrev] = avg

        # Build overall summaries (plain text and Markdown)
        lines_text: list[str] = []
        lines_md: list[str] = ["### Noten Übersicht"]
        overall = grades_data.get("overall_average")
        if overall is not None:
            lines_text.append(f"Gesamtdurchschnitt: {overall}")
            lines_md.append(f"**Gesamtdurchschnitt:** {overall}")
        for sid, subj in subjects.items():
            name = subj.get("name", f"Fach {sid}")
            abbr = subj.get("abbreviation", "")
            avg = subj.get("average")
            count = sum(len(v) for v in (subj.get("grades") or {}).values())
            txt = f"{name} ({abbr})"
            if avg is not None:
                txt += f": {avg}"
            txt += f" – {count} Noten"
            lines_text.append(txt)
            lines_md.append(
                f"- **{name}** ({abbr}): {avg if avg is not None else '-'} – {count} Noten"
            )

        grades_summary = (
            "\n".join(lines_text) if lines_text else "Keine Noten verfügbar"
        )
        grades_summary_md = (
            "\n".join(lines_md) if lines_md else "_Keine Noten verfügbar_"
        )

        return {
            "total_subjects": grades_data.get("total_subjects", 0),
            "subjects_with_grades": grades_data.get("subjects_with_grades", 0),
            "subject_averages": subject_averages,
            "grades_summary": grades_summary,
            "grades_summary_markdown": grades_summary_md,
            "last_updated": datetime.now().isoformat(),
        }


class NextExamCountdownSensor(CoordinatorEntity[SchulmanagerCoordinator], SensorEntity):
    """Sensor entity showing days until next exam."""

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = "Tage"
    _attr_state_class = None

    def __init__(
        self,
        client: Any,
        coordinator: SchulmanagerCoordinator,
        student_id: str,
        student_name: str,
        slug: str,
    ) -> None:
        """Initialize the next exam countdown sensor."""
        super().__init__(coordinator)
        self.client = client
        self.student_id = student_id
        self.student_name = student_name
        # Stable unique ID, scoped to this config entry so the same student
        # appearing in another entry does not collide with it.
        entry_id = self.coordinator.config_entry.entry_id
        self._attr_unique_id = f"schulmanager_{entry_id}_{self.student_id}_next_exam_days"

        # Use translation for entity name
        self._attr_translation_key = "next_exam_days"
        self._attr_icon = "mdi:calendar-clock"

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

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return bool(self.coordinator.last_update_success)

    @property
    def native_value(self) -> StateType:
        """Return days until next exam."""
        integ = cast(IntegrationData | None, self.coordinator.data)
        items: list[dict[str, Any]] = (
            []
            if integ is None
            else cast(
                list[dict[str, Any]],
                integ.get("exams", {}).get(self.student_id, []) or [],
            )
        )
        # Only consider regular exams; exclude school-wide events
        items = [exam for exam in items if not exam.get("_isCalendarEvent")]
        if not items:
            return None

        # Get current date
        now = datetime.now().date()

        # Find the next upcoming exam
        next_exam_date = None
        for exam in items:
            exam_date = exam.get("date")
            if not exam_date:
                continue

            try:
                # Parse the date (should be YYYY-MM-DD format)
                if "T" in exam_date:
                    exam_date_obj = datetime.fromisoformat(exam_date).date()
                else:
                    exam_date_obj = datetime.fromisoformat(exam_date).date()

                # Only consider future exams
                if exam_date_obj >= now:
                    if next_exam_date is None or exam_date_obj < next_exam_date:
                        next_exam_date = exam_date_obj

            except (ValueError, TypeError):
                try:
                    exam_date_obj = datetime.strptime(exam_date, "%Y-%m-%d").date()
                    if exam_date_obj >= now:
                        if next_exam_date is None or exam_date_obj < next_exam_date:
                            next_exam_date = exam_date_obj
                except (ValueError, TypeError):
                    continue

        # Calculate days until next exam
        if next_exam_date:
            return (next_exam_date - now).days

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional exam information."""
        integ = cast(IntegrationData | None, self.coordinator.data)
        items: list[dict[str, Any]] = (
            []
            if integ is None
            else cast(
                list[dict[str, Any]],
                integ.get("exams", {}).get(self.student_id, []) or [],
            )
        )
        # Only consider regular exams; exclude school-wide events
        items = [exam for exam in items if not exam.get("_isCalendarEvent")]
        if not items:
            return {
                "next_exam": None,
                "total_upcoming_exams": 0,
                "last_updated": datetime.now().isoformat(),
            }

        # Get current date
        now = datetime.now().date()

        # Find next exam and collect upcoming exams
        next_exam = None
        next_exam_date = None
        upcoming_exams = []

        for exam in items:
            exam_date = exam.get("date")
            if not exam_date:
                continue

            try:
                # Parse the date
                if "T" in exam_date:
                    exam_date_obj = datetime.fromisoformat(exam_date).date()
                else:
                    exam_date_obj = datetime.fromisoformat(exam_date).date()

                # Only consider future exams
                if exam_date_obj >= now:
                    # Add to upcoming list
                    exam_info = {
                        "date": exam_date_obj.isoformat(),
                        "days_from_now": (exam_date_obj - now).days,
                        "subject": exam.get("subject", {}).get(
                            "name", "Unbekanntes Fach"
                        ),
                        "subject_abbr": exam.get("subject", {}).get("abbreviation", ""),
                        "type": exam.get("type", {}).get("name", "Prüfung"),
                        "comment": exam.get("comment", ""),
                    }
                    upcoming_exams.append(exam_info)

                    # Check if this is the next exam
                    if next_exam_date is None or exam_date_obj < next_exam_date:
                        next_exam_date = exam_date_obj
                        next_exam = exam_info

            except (ValueError, TypeError):
                try:
                    exam_date_obj = datetime.strptime(exam_date, "%Y-%m-%d").date()
                    if exam_date_obj >= now:
                        exam_info = {
                            "date": exam_date_obj.isoformat(),
                            "days_from_now": (exam_date_obj - now).days,
                            "subject": exam.get("subject", {}).get(
                                "name", "Unbekanntes Fach"
                            ),
                            "subject_abbr": exam.get("subject", {}).get(
                                "abbreviation", ""
                            ),
                            "type": exam.get("type", {}).get("name", "Prüfung"),
                            "comment": exam.get("comment", ""),
                        }
                        upcoming_exams.append(exam_info)

                        if next_exam_date is None or exam_date_obj < next_exam_date:
                            next_exam_date = exam_date_obj
                            next_exam = exam_info
                except (ValueError, TypeError):
                    continue

        # Sort upcoming exams by date
        upcoming_exams.sort(key=lambda x: x["date"])

        return {
            "next_exam": next_exam,
            "total_upcoming_exams": len(upcoming_exams),
            "upcoming_exams": upcoming_exams[:5],  # Show next 5 exams
            "last_updated": datetime.now().isoformat(),
        }


class SchoolDiagnosticSensor(CoordinatorEntity[SchulmanagerCoordinator], SensorEntity):
    """Diagnostic sensor showing which school a student belongs to.

    Only relevant for multi-school accounts. For single-school accounts,
    this sensor will show "Unknown" or a default value.
    """

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:school"
    _attr_translation_key = "school"

    def __init__(
        self,
        coordinator: SchulmanagerCoordinator,
        student_id: str,
        student_name: str,
        student_slug: str,
        school_name: str | None,
        school_id: int | None,
    ) -> None:
        """Initialize the school diagnostic sensor."""
        super().__init__(coordinator)
        self.student_id = student_id
        self.student_name = student_name
        self._school_name = school_name
        self._school_id = school_id

        # Stable unique ID, scoped to this config entry so the same student
        # appearing in another entry does not collide with it.
        entry_id = self.coordinator.config_entry.entry_id
        self._attr_unique_id = f"schulmanager_{entry_id}_{self.student_id}_school"

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

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return bool(self.coordinator.last_update_success)

    @property
    def native_value(self) -> str:
        """Return the name of the school."""
        if self._school_name:
            return self._school_name
        return "Unbekannt"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs: dict[str, Any] = {}

        if self._school_id is not None:
            attrs["school_id"] = self._school_id

        if self._school_name:
            attrs["school_name"] = self._school_name

        return attrs


class CurrentLessonSensor(CoordinatorEntity[SchulmanagerCoordinator], SensorEntity):
    """Sensor showing what is happening right now for a student.

    Updates every minute via a time-interval listener so state transitions
    (lesson start/end, break start) are reflected without waiting for the
    next coordinator refresh.
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:school-clock"
    _attr_translation_key = "current_lesson"

    def __init__(
        self,
        client: Any,
        coordinator: SchulmanagerCoordinator,
        student_id: str,
        student_name: str,
        slug: str,
    ) -> None:
        """Initialize the current-lesson sensor."""
        super().__init__(coordinator)
        self.client = client
        self.student_id = student_id
        self.student_name = student_name
        # Stable unique ID, scoped to this config entry so the same student
        # appearing in another entry does not collide with it.
        entry_id = self.coordinator.config_entry.entry_id
        self._attr_unique_id = f"schulmanager_{entry_id}_{student_id}_current_lesson"

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

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return bool(self.coordinator.last_update_success)

    async def async_added_to_hass(self) -> None:
        """Register a 1-minute interval to keep state current between coordinator updates."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_time_interval(
                self.hass,
                callback(lambda _: self.async_write_ha_state()),
                timedelta(minutes=1),
            )
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_today_lessons(self) -> list[dict[str, Any]]:
        """Return today's lesson list from coordinator data."""
        integ = cast(IntegrationData | None, self.coordinator.data)
        if integ is None:
            return []
        sched = cast(dict[str, Any], integ.get("schedule", {}).get(self.student_id, {}))
        return cast(list[dict[str, Any]], sched.get("today", []) or [])

    @staticmethod
    def _parse_time(time_str: str | None) -> time | None:
        """Parse a classHour time string like '08:30:00' or '08:30' to a time object."""
        if not time_str:
            return None
        try:
            return time.fromisoformat(time_str[:5])
        except (ValueError, TypeError):
            return None

    def _timed_lessons(
        self, lessons: list[dict[str, Any]]
    ) -> list[tuple[time, time, dict[str, Any]]]:
        """Return lessons that have valid from/until times, sorted by start time."""
        result: list[tuple[time, time, dict[str, Any]]] = []
        for lesson in lessons:
            ch = lesson.get("classHour") or {}
            from_t = self._parse_time(ch.get("from"))
            until_t = self._parse_time(ch.get("until"))
            if from_t is not None and until_t is not None:
                result.append((from_t, until_t, lesson))
        result.sort(key=lambda x: x[0])
        return result

    @staticmethod
    def _lesson_subject_room(lesson: dict[str, Any]) -> tuple[str, str]:
        """Extract subject abbreviation and room name from a lesson dict."""
        actual = lesson.get("actualLesson") or {}
        subject = (actual.get("subject") or {}).get("abbreviation") or ""
        room = (actual.get("room") or {}).get("name") or ""
        return subject, room

    @staticmethod
    def _lesson_teacher(lesson: dict[str, Any]) -> str:
        """Extract the first teacher's abbreviation from a lesson dict."""
        actual = lesson.get("actualLesson") or {}
        teachers = actual.get("teachers") or []
        if teachers:
            return (teachers[0] or {}).get("abbreviation") or ""
        return ""

    # ------------------------------------------------------------------
    # State & attributes
    # ------------------------------------------------------------------

    @property
    def native_value(self) -> StateType:
        """Return the current lesson state."""
        integ = cast(IntegrationData | None, self.coordinator.data)
        if integ is None:
            return None

        now = dt_util.now()

        # Weekend
        if now.weekday() >= 5:
            return "Wochenende"

        lessons = self._get_today_lessons()
        if not lessons:
            return "Schulfrei"

        timed = self._timed_lessons(lessons)

        # Fallback: no time info available
        if not timed:
            deviations = any(
                lesson.get("type") != "regularLesson" or not lesson.get("actualLesson")
                for lesson in lessons
                if isinstance(lesson, dict)
            )
            return "Abweichung" if deviations else "Planmäßig"

        now_t = now.time()

        # Before school starts
        if now_t < timed[0][0]:
            return f"Unterricht ab {timed[0][0].strftime('%H:%M')} Uhr"

        # After school ends
        if now_t >= timed[-1][1]:
            return "Unterricht beendet"

        # Currently in a lesson?
        for from_t, until_t, lesson in timed:
            if from_t <= now_t < until_t:
                subject, room = self._lesson_subject_room(lesson)
                if subject and room:
                    return f"{subject} – {room}"
                return subject or "Unterricht"

        # Between lessons → find next lesson start
        for from_t, _until_t, _lesson in timed:
            if from_t > now_t:
                return f"Pause (bis {from_t.strftime('%H:%M')} Uhr)"

        return "Pause"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return detailed current and next lesson information."""
        integ = cast(IntegrationData | None, self.coordinator.data)
        if integ is None:
            return None

        lessons = self._get_today_lessons()
        timed = self._timed_lessons(lessons)
        if not timed:
            return None

        now_t = dt_util.now().time()
        attrs: dict[str, Any] = {
            "current_subject": None,
            "current_subject_full": None,
            "current_teacher": None,
            "current_room": None,
            "lesson_end": None,
            "next_subject": None,
            "next_lesson_start": None,
        }

        # Find active lesson
        current_idx: int | None = None
        for idx, (from_t, until_t, lesson) in enumerate(timed):
            if from_t <= now_t < until_t:
                actual = lesson.get("actualLesson") or {}
                subj = actual.get("subject") or {}
                attrs["current_subject"] = subj.get("abbreviation")
                attrs["current_subject_full"] = subj.get("name")
                attrs["current_teacher"] = self._lesson_teacher(lesson)
                attrs["current_room"] = (actual.get("room") or {}).get("name")
                attrs["lesson_end"] = until_t.strftime("%H:%M")
                current_idx = idx
                break

        # Find next lesson
        start_search = (current_idx + 1) if current_idx is not None else 0
        for from_t, _until_t, lesson in timed[start_search:]:
            if from_t > now_t or current_idx is not None:
                subject, _ = self._lesson_subject_room(lesson)
                attrs["next_subject"] = subject or None
                attrs["next_lesson_start"] = from_t.strftime("%H:%M")
                break


# ---------------------------------------------------------------------------
# Wochenplan JSON Sensor (for Stundenplan Card integration)
# ---------------------------------------------------------------------------

_WEEKDAY_KEYS = ["Mo", "Di", "Mi", "Do", "Fr"]


class WochenplanJsonSensor(CoordinatorEntity[SchulmanagerCoordinator], SensorEntity):
    """Sensor providing the current week's schedule as JSON for the Stundenplan Card."""

    _attr_has_entity_name = True
    _attr_translation_key = "wochenplan_json"
    _attr_icon = "mdi:table-large"

    def __init__(
        self,
        client: Any,
        coordinator: SchulmanagerCoordinator,
        student_id: str,
        student_name: str,
        slug: str,
    ) -> None:
        """Initialize the Wochenplan JSON sensor."""
        super().__init__(coordinator)
        self.client = client
        self.student_id = student_id
        self.student_name = student_name
        # Stable unique ID, scoped to this config entry so the same student
        # appearing in another entry does not collide with it.
        entry_id = self.coordinator.config_entry.entry_id
        self._attr_unique_id = f"schulmanager_{entry_id}_{student_id}_wochenplan_json"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"student_{self.student_id}")},
            name=self.student_name,
            manufacturer="Schulmanager Online",
            model="Schüler",
        )

    @property
    def native_value(self) -> StateType:
        """Return the calendar week as state."""
        today = date.today()
        weekday = today.weekday()
        monday = today - timedelta(days=weekday) if weekday < 5 else today + timedelta(days=7 - weekday)
        iso = monday.isocalendar()
        return f"KW {iso[1]} ({monday.isoformat()})"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the plan as a list compatible with the Stundenplan Card."""
        coord_data = cast(IntegrationData | None, self.coordinator.data)
        if coord_data is None:
            return {"plan": []}

        schedule = cast(dict[str, Any], coord_data.get("schedule", {})).get(self.student_id, {})
        week_map: dict[str, list[dict[str, Any]]] = schedule.get("week", {})

        plan = self._build_plan(week_map)
        lesson_rows = [r for r in plan if not r.get("break")]
        return {
            "plan": plan,
            "lesson_count": len(lesson_rows),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_plan(self, week_map: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
        """Build the Stundenplan Card JSON plan from the current week's lessons."""
        if not week_map:
            return []

        today = date.today()
        weekday = today.weekday()
        # If weekend, show next week
        monday = today - timedelta(days=weekday) if weekday < 5 else today + timedelta(days=7 - weekday)

        # Try to build plan for this week
        plan = self._build_plan_for_week(week_map, monday)
        if plan:
            return plan

        # Fallback: If this week has no lessons, find first week with data
        _LOGGER.debug(
            "No lessons found for week starting %s, trying to find first available week",
            monday.isoformat(),
        )
        available_dates = sorted(week_map.keys())
        if not available_dates:
            return []

        # Find first date, then compute its Monday
        first_date = date.fromisoformat(available_dates[0])
        fallback_monday = first_date - timedelta(days=first_date.weekday())
        plan = self._build_plan_for_week(week_map, fallback_monday)
        if plan:
            _LOGGER.info("Using fallback week starting %s (first available)", fallback_monday.isoformat())
        return plan

    def _build_plan_for_week(
        self, week_map: dict[str, list[dict[str, Any]]], monday: date
    ) -> list[dict[str, Any]]:
        """Build plan for a specific Monday-start week."""

        # periods[period_num][day_index 0-4] = subject_label
        periods: dict[str, dict[int, str]] = {}
        period_times: dict[str, tuple[str, str]] = {}  # period_num -> (from, until)
        # Collect all lessons per (period, day) first so same-hour lessons
        # (e.g. a cancellation plus its substitution/event) can be combined
        # into one cell label instead of the last one silently overwriting
        # the others.
        cell_lessons: dict[tuple[str, int], list[dict[str, Any]]] = {}

        for day_offset in range(5):
            day_str = (monday + timedelta(days=day_offset)).isoformat()
            for lesson in week_map.get(day_str, []):
                ch = lesson.get("classHour") or {}
                # Schulmanager sometimes sends the period number with a
                # trailing "." (e.g. "4."); normalize it once here so sorting
                # and the "Stunde" label below don't inherit a stray dot.
                period_num = str(ch.get("number", "?")).rstrip(".")
                if period_num not in periods:
                    periods[period_num] = {}
                    period_times[period_num] = (
                        str(ch.get("from") or ""),
                        str(ch.get("until") or ""),
                    )
                cell_lessons.setdefault((period_num, day_offset), []).append(lesson)

        for (period_num, day_offset), lessons in cell_lessons.items():
            periods[period_num][day_offset] = self._combine_subject_labels(lessons)

        def _sort_key(p: str) -> float:
            if p.isdigit():
                return int(p)
            try:
                return float(p.replace(",", "."))
            except (ValueError, TypeError):
                return 999

        sorted_periods = sorted(periods.keys(), key=_sort_key)

        plan: list[dict[str, Any]] = []
        prev_num: str | None = None
        row_id = 1

        for period_num in sorted_periods:
            # Insert break if there is a gap between periods
            if prev_num is not None:
                try:
                    if int(period_num) > int(prev_num) + 1:
                        prev_until = period_times[prev_num][1]
                        curr_from = period_times[period_num][0]
                        break_time = f"{prev_until} - {curr_from}" if prev_until and curr_from else ""
                        plan.append({"break": True, "Stunde": break_time, "label": "Pause"})
                except (ValueError, TypeError):
                    pass

            from_t, until_t = period_times[period_num]
            stunde = f"{period_num}. {from_t} - {until_t}" if from_t else str(period_num)
            row: dict[str, Any] = {"ID": row_id, "Stunde": stunde}
            for idx, day_key in enumerate(_WEEKDAY_KEYS):
                row[day_key] = periods[period_num].get(idx, "")
            plan.append(row)

            prev_num = period_num
            row_id += 1

        return plan

    @staticmethod
    def _subject_label(lesson: dict[str, Any]) -> str:
        """Return a human-readable label for a lesson cell."""
        lesson_type = lesson.get("type", "regularLesson")
        actual = lesson.get("actualLesson") or {}
        subject_abbr = (actual.get("subject") or {}).get("abbreviation", "")

        if lesson_type == "cancelledLesson":
            orig_lessons = lesson.get("originalLessons") or []
            orig_abbr = (orig_lessons[0].get("subject") or {}).get("abbreviation", "?") if orig_lessons else "?"
            return f"{orig_abbr} ✗"

        if lesson_type in ("substitution", "teacherChange"):
            return f"{subject_abbr} ↔" if subject_abbr else "↔"

        if not subject_abbr and lesson_type not in ("regularLesson", ""):
            # e.g. type "event" typically has no actualLesson.subject - fall
            # back to the known German type label instead of an empty cell.
            return LESSON_TYPE_LABELS.get(lesson_type, lesson_type)

        return subject_abbr

    @staticmethod
    def _combine_subject_labels(lessons: list[dict[str, Any]]) -> str:
        """Combine same-hour lessons into one cell label.

        A cancelled lesson and its same-hour substitution/event previously
        overwrote each other (only the last-processed one survived); both
        are now shown, e.g. "Bio ✗ → Veranstaltung".
        """
        if len(lessons) == 1:
            return WochenplanJsonSensor._subject_label(lessons[0])

        cancelled = [lsn for lsn in lessons if lsn.get("type") == "cancelledLesson"]
        others = [lsn for lsn in lessons if lsn.get("type") != "cancelledLesson"]

        labels = [
            WochenplanJsonSensor._subject_label(lesson)
            for lesson in (*cancelled, *others)
        ]
        # Keep order, drop empties and exact duplicates.
        unique_labels = list(dict.fromkeys(label for label in labels if label))
        return " → ".join(unique_labels)


def _service_device_info(coordinator: SchulmanagerCoordinator) -> DeviceInfo:
    """Device of the Schulmanager account (shared with the refresh button)."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"service_{coordinator.config_entry.entry_id}")},
        name="Schulmanager Online",
        manufacturer="Schulmanager Online",
        model="Portal-Zugang",
        sw_version=VERSION,
        entry_type=DeviceEntryType.SERVICE,
        suggested_area="Schule",
        configuration_url="https://login.schulmanager-online.de/",
    )


def _plain_text(value: Any, limit: int = 800) -> str:
    """Convert letter HTML to compact plain text."""
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    text = re.sub(r"\s+", " ", unescape(text)).strip()
    return text[:limit]


class UnreadLettersSensor(CoordinatorEntity[SchulmanagerCoordinator], SensorEntity):
    """Number of unread parent letters (Elternbriefe) with details as attributes.

    Data comes from the dashboard widget endpoint of the web app; letters are never
    opened, so reading them in the app is still required to mark them as read.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "letters_unread"
    _attr_icon = "mdi:email-alert-outline"

    def __init__(self, coordinator: SchulmanagerCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"schulmanager_{coordinator.config_entry.entry_id}_letters_unread"
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return _service_device_info(self.coordinator)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return bool(self.coordinator.last_update_success)

    def _letters(self) -> list[dict[str, Any]]:
        data = cast(IntegrationData | None, self.coordinator.data) or {}
        return [x for x in data.get("letters_unread") or [] if isinstance(x, dict)]

    @property
    def native_value(self) -> StateType:
        """Return the number of unread letters."""
        return len(self._letters())

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the unread letters."""
        letters = []
        for letter in self._letters():
            students = []
            for status in letter.get("studentStatuses") or []:
                student = status.get("student") if isinstance(status, dict) else None
                if isinstance(student, dict):
                    name = " ".join(
                        x for x in (student.get("firstname"), student.get("lastname")) if x
                    )
                    if name:
                        students.append(name)
            letters.append(
                {
                    "id": letter.get("id"),
                    "title": letter.get("title"),
                    "sent": letter.get("sentDate"),
                    "deadline": letter.get("answerDeadline"),
                    "students": students,
                    "text": _plain_text(letter.get("text")),
                    "attachments": len(letter.get("attachments") or []),
                }
            )
        return {"letters": letters}


class UnreadMessagesSensor(CoordinatorEntity[SchulmanagerCoordinator], SensorEntity):
    """Number of unread messenger messages with the affected conversations.

    Only conversation metadata is fetched (subject, sender, unread count). Message
    bodies are not requested to avoid triggering read receipts.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "messages_unread"
    _attr_icon = "mdi:message-badge-outline"

    def __init__(self, coordinator: SchulmanagerCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"schulmanager_{coordinator.config_entry.entry_id}_messages_unread"
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return _service_device_info(self.coordinator)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return bool(self.coordinator.last_update_success)

    def _data(self) -> IntegrationData | dict[str, Any]:
        return cast(IntegrationData | None, self.coordinator.data) or {}

    @property
    def native_value(self) -> StateType:
        """Return the number of unread messages."""
        data = self._data()
        count = data.get("messages_unread_count")
        if isinstance(count, int):
            return count
        return sum(int(x.get("unreadCount") or 0) for x in data.get("messages_unread") or [])

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return conversations with unread messages, newest first."""
        threads = []
        for sub in self._data().get("messages_unread") or []:
            thread = sub.get("thread") if isinstance(sub.get("thread"), dict) else {}
            threads.append(
                {
                    "id": sub.get("id"),
                    "subject": thread.get("subject"),
                    "sender": thread.get("senderString"),
                    "recipients": thread.get("recipientString"),
                    "unread": sub.get("unreadCount"),
                    "last": thread.get("lastMessageTimestamp"),
                    "private": thread.get("isPrivateChat"),
                }
            )
        threads.sort(key=lambda t: str(t.get("last") or ""), reverse=True)
        return {"threads": threads}
