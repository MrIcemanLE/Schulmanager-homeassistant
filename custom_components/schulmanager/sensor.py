"""Sensors for the Schulmanager integration.

Provides schedule, schedule-changes, grade sensors and an exam countdown per
student. All sensors subscribe to the integration coordinator for updates and
use stable, ID-based unique IDs.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from html import escape
from typing import Any, cast

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, OPT_SCHEDULE_HIGHLIGHT
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
        # Stable unique ID based on immutable student ID
        self._attr_unique_id = f"schulmanager_{self.student_id}_schedule_{day}"
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
                }
                block["has_change"] = True
                block["primary"] = primary
            else:
                highlight = (
                    block.get("has_change")
                    or primary.get("lesson_type") != "regularLesson"
                )
                primary["highlight"] = bool(highlight)
                primary.pop("lesson_type", None)
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
                (
                    f"<tr{row_attr}>{hour_cell}"
                    f"{_format_cell(primary.get('subject', ''))}"
                    f"{_format_cell(primary.get('room', ''))}"
                    f"{_format_cell(primary.get('info', ''))}"
                    "</tr>"
                )
            )
            rows.append(
                (
                    f"<tr{row_attr}>"
                    f"{_format_cell(secondary.get('subject', ''), strike=secondary.get('strike', False))}"
                    f"{_format_cell(secondary.get('room', ''), strike=secondary.get('strike', False))}"
                    f"{_format_cell(secondary.get('info', ''), strike=secondary.get('strike', False))}"
                    "</tr>"
                )
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

        # Generate plain text format for notifications (with emoji highlighting)
        plain_text = self._generate_plain_text(items_sorted)

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

    def _generate_plain_text(self, lessons: list[dict[str, Any]]) -> str:
        """Generate plain text schedule with emoji highlighting for notifications.

        Format: "1. Std: 🔁 Mathematik – Raum 204 (Vertretung)"
        Uses same emoji logic as calendar.
        """
        if not lessons:
            if self._is_weekend_day():
                return "Wochenende - keine Schule"
            return "Schulfrei"

        # Get highlight option from config entry
        highlight = False
        if self.coordinator.config_entry:
            opts = dict(self.coordinator.config_entry.options or {})
            highlight = bool(opts.get(OPT_SCHEDULE_HIGHLIGHT, True))

        lines: list[str] = []

        for lesson in lessons:
            lesson_type = lesson.get("type", "regularLesson")
            actual = lesson.get("actualLesson", {}) or {}

            # Get hour number
            hour_str = ""
            class_hour = lesson.get("classHour", {})
            hour_num = class_hour.get("number")
            if isinstance(hour_num, int):
                hour_str = f"{hour_num}. Std"
            elif isinstance(hour_num, str) and hour_num.strip():
                hour_str = f"{hour_num}. Std"

            # Get subject
            subject = ""
            if actual.get("subject"):
                subj_data = actual["subject"]
                subject = subj_data.get("abbreviation") or subj_data.get("name") or ""
            if not subject and lesson.get("subject"):
                subj_data = lesson["subject"]
                subject = subj_data.get("abbreviation") or subj_data.get("name") or ""
            if not subject:
                subject = "Unterricht"

            # Get room
            room = ""
            if actual.get("room"):
                room = actual["room"].get("name", "")
            elif lesson.get("room"):
                room = lesson["room"].get("name", "")

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

            # Additional info (teacher, reason)
            info_parts: list[str] = []

            # Teacher
            teachers = actual.get("teachers") or lesson.get("teachers") or []
            if teachers:
                teacher_abbr = ", ".join(
                    t.get("abbreviation") or f"{t.get('firstname', '')} {t.get('lastname', '')}".strip()
                    for t in teachers if isinstance(t, dict)
                )
                if teacher_abbr:
                    info_parts.append(teacher_abbr)

            # Change reason
            reason = lesson.get("substitutionText") or lesson.get("comment") or ""
            if reason:
                info_parts.append(reason)

            # Type label for non-regular lessons (if no other info)
            if not info_parts and lesson_type != "regularLesson":
                type_label = LESSON_TYPE_LABELS.get(lesson_type, lesson_type)
                info_parts.append(type_label)

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
        # Stable unique ID based on immutable student ID
        self._attr_unique_id = f"schulmanager_{self.student_id}_schedule_changes"
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
    _attr_suggested_display_precision = 2

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
        # Stable unique ID based on immutable student and subject IDs
        self._attr_unique_id = (
            f"schulmanager_{self.student_id}_grades_{self.subject_id!s}"
        )

        # Keep dynamic name since it includes subject abbreviation
        self._attr_name = f"Noten {subject_abbrev}"
        self._attr_icon = "mdi:school"

    def _parse_german_grade(self, grade_value: str | float) -> float | None:
        """Parse German grade formats and return numeric value.

        Handles formats like:
        - "0~3" -> 3.0
        - "0~3+" -> 3.0
        - "0~2-" -> 2.0
        - "3+" -> 3.0
        - "2-" -> 2.0
        - "2.5" -> 2.5
        """
        if not grade_value and grade_value != 0:
            return None

        # Handle direct numeric values
        if isinstance(grade_value, (int, float)):
            return float(grade_value)

        grade_str = str(grade_value).strip()
        if not grade_str:
            return None

        # Handle format "0~3" or "0~3+" or "0~2-" -> extract after tilde
        if "~" in grade_str:
            try:
                # Split by tilde and get the part after it
                grade_part = grade_str.split("~")[1]
                # Remove tendency markers (+/-)
                if grade_part.endswith(("+", "-")):
                    grade_part = grade_part[:-1]
                return float(grade_part)
            except (ValueError, IndexError):
                return None

        # Handle formats like "4+", "4-", "2+" (without tilde prefix)
        if grade_str.endswith(("+", "-")):
            try:
                # Treat both 4+ and 4- as 4.0 (ignore plus/minus for calculation)
                return float(grade_str[:-1])
            except ValueError:
                return None

        # Handle decimal grades like "2.5", "3.7"
        try:
            return float(grade_str)
        except ValueError:
            return None

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
                numeric_value = self._parse_german_grade(grade_value)
                if numeric_value is not None and 1.0 <= numeric_value <= 6.0:
                    grade_info["numeric_value"] = numeric_value

                processed_grades.append(grade_info)

            # Only include categories that have grades
            if processed_grades:
                category_summary[category] = {
                    "count": len(processed_grades),
                    "grades": processed_grades,
                }
                total_grades += len(processed_grades)

        # Extract numeric grade values (German grades are always numeric 1-6)
        all_grade_values: list[float] = []
        for grades_list in grade_categories.values():
            for grade in grades_list:
                grade_value = grade.get("value", "")
                # Use consistent grade parsing
                numeric_grade = self._parse_german_grade(grade_value)
                if numeric_grade is not None and 1.0 <= numeric_grade <= 6.0:
                    all_grade_values.append(numeric_grade)

        # Calculate basic statistics
        statistics = {}
        if all_grade_values:
            statistics = {
                "average": round(sum(all_grade_values) / len(all_grade_values), 2),
                "best_grade": min(all_grade_values),  # In German system, 1 is best
                "worst_grade": max(all_grade_values),
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
    _attr_suggested_display_precision = 2

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
        # Stable unique ID based on immutable student ID
        self._attr_unique_id = f"schulmanager_{self.student_id}_grades_overall"

        # Use translation for entity name
        self._attr_translation_key = "grades_overall"
        self._attr_icon = "mdi:school"

    def _parse_german_grade(self, grade_value: str | float) -> float | None:
        """Parse German grade formats and return numeric value.

        Handles formats like:
        - "0~3" -> 3.0
        - "0~3+" -> 3.0
        - "0~2-" -> 2.0
        - "3+" -> 3.0
        - "2-" -> 2.0
        - "2.5" -> 2.5
        """
        if not grade_value and grade_value != 0:
            return None

        # Handle direct numeric values
        if isinstance(grade_value, (int, float)):
            return float(grade_value)

        grade_str = str(grade_value).strip()
        if not grade_str:
            return None

        # Handle format "0~3" or "0~3+" or "0~2-" -> extract after tilde
        if "~" in grade_str:
            try:
                # Split by tilde and get the part after it
                grade_part = grade_str.split("~")[1]
                # Remove tendency markers (+/-)
                if grade_part.endswith(("+", "-")):
                    grade_part = grade_part[:-1]
                return float(grade_part)
            except (ValueError, IndexError):
                return None

        # Handle formats like "4+", "4-", "2+" (without tilde prefix)
        if grade_str.endswith(("+", "-")):
            try:
                # Treat both 4+ and 4- as 4.0 (ignore plus/minus for calculation)
                return float(grade_str[:-1])
            except ValueError:
                return None

        # Handle decimal grades like "2.5", "3.7"
        try:
            return float(grade_str)
        except ValueError:
            return None

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
        # Stable unique ID based on immutable student ID
        self._attr_unique_id = f"schulmanager_{self.student_id}_next_exam_days"

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

        # Unique ID based on student ID
        self._attr_unique_id = f"schulmanager_{self.student_id}_school"

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
