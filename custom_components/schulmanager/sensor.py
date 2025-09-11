"""Sensors for the Schulmanager integration.

Provides schedule, schedule-changes, grade sensors and an exam countdown per
student. All sensors subscribe to the integration coordinator for updates and
use stable, ID-based unique IDs.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, VERSION
from .coordinator import SchulmanagerCoordinator
from .util import normalize_student_slug

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Schulmanager sensor entities."""
    # Prefer runtime_data over hass.data for runtime storage
    runtime = entry.runtime_data or {}
    coord = runtime.get("coordinator")
    client = runtime.get("client")
    if coord is None or client is None:
        missing = [n for n, v in {"coordinator": coord, "client": client}.items() if v is None]
        _LOGGER.warning(
            "Runtime data incomplete for entry %s: missing %s; skipping sensor setup",
            entry.entry_id,
            ", ".join(missing),
        )
        return
    entities: list[SensorEntity] = []

    for st in (coord.data or {}).get("students", []):
        sid = st["id"]
        name = st["name"]
        slug = normalize_student_slug(name)
        entities.append(ScheduleSensor(client, coord, sid, name, slug, "today"))
        entities.append(ScheduleSensor(client, coord, sid, name, slug, "tomorrow"))
        entities.append(ScheduleChangesSensor(client, coord, sid, name, slug))

        # Add grade sensors for each subject
        # We'll check for available subjects from the first update
        grades_data = coord.data.get("grades", {}).get(sid, {}) if coord.data else {}
        subjects = grades_data.get("subjects", {})

        for subject_id, subject_data in subjects.items():
            subject_name = subject_data.get("name", f"Fach {subject_id}")
            subject_abbrev = subject_data.get("abbreviation", subject_name)
            entities.append(GradeSensor(client, coord, sid, name, slug, subject_id, subject_name, subject_abbrev))

        # Add overall average sensor
        entities.append(OverallGradeSensor(client, coord, sid, name, slug))

        # Add days until next exam sensor
        entities.append(NextExamCountdownSensor(client, coord, sid, name, slug))

    async_add_entities(entities)


class ScheduleSensor(CoordinatorEntity[SchulmanagerCoordinator], SensorEntity):
    """Sensor entity for student schedule."""

    _attr_has_entity_name = True

    def __init__(
        self, client: Any, coordinator: SchulmanagerCoordinator, student_id: str, student_name: str, slug: str, day: str
    ) -> None:
        """Initialize a schedule sensor for the given day."""
        super().__init__(coordinator)
        self.client = client
        self.student_id = student_id
        self.student_name = student_name
        self.day = day
        # Stable unique ID based on immutable student ID
        self._attr_unique_id = f"schulmanager_{self.student_id}_schedule_{day}"
        pretty = "heute" if day == "today" else "morgen"
        self._attr_name = f"Stundenplan {pretty}"
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
        data = (
            (self.coordinator.data or {}).get("schedule", {}).get(self.student_id, {})
        )
        items = data.get(self.day, [])

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
        data = (
            (self.coordinator.data or {}).get("schedule", {}).get(self.student_id, {})
        )
        items = data.get(self.day, [])

        # Structure the raw data properly as JSON
        raw_data: dict[str, Any] = {
            "lessons": [],
            "day": self.day,
            "student_id": self.student_id,
            "date": self._get_target_date().isoformat() if items else None
        }

        def td(x: str) -> str:
            return f"<td>{x}</td>"

        rows = []
        for lesson in items:
            if not isinstance(lesson, dict):
                continue

            # Extract data from new structure
            class_hour = lesson.get("classHour", {})
            actual_lesson = lesson.get("actualLesson", {})
            lesson_type = lesson.get("type", "")

            # Get lesson hour number
            hour = class_hour.get("number", "")

            # Get subject info
            subject_info = actual_lesson.get("subject", {})
            subject_name = subject_info.get("name", "")
            subject_abbr = subject_info.get("abbreviation", "")
            subject = subject_abbr if subject_abbr else subject_name

            # Get room info
            room_info = actual_lesson.get("room", {})
            room = room_info.get("name", "")

            # Get teacher info
            teachers = actual_lesson.get("teachers", [])
            teacher_names = []
            for teacher in teachers:
                abbr = teacher.get("abbreviation", "")
                if abbr:
                    teacher_names.append(abbr)
                else:
                    firstname = teacher.get("firstname", "")
                    lastname = teacher.get("lastname", "")
                    if firstname and lastname:
                        teacher_names.append(f"{firstname} {lastname}")
            teacher = ", ".join(teacher_names) if teacher_names else ""

            # Build info field
            info_parts = []
            if lesson_type != "regularLesson":
                info_parts.append(f"Typ: {lesson_type}")
            if teacher:
                info_parts.append(teacher)
            info = " - ".join(info_parts)

            # Add to raw data structure
            lesson_data = {
                "hour": hour,
                "subject": subject,
                "subject_full": subject_name,
                "room": room,
                "teacher": teacher,
                "type": lesson_type,
                "date": lesson.get("date")
            }
            raw_data["lessons"].append(lesson_data)

            # Format time as hour number (Stunde)
            time_display = f"{hour}. Std" if hour else ""

            rows.append(f"<tr>{td(time_display)}{td(subject)}{td(room)}{td(info)}</tr>")

        # Check if weekend day
        if self._is_weekend_day():
            html = (
                "<table><thead><tr><th>Wochenende</th></tr></thead><tbody>"
                "<tr><td>Heute ist Wochenende - keine Schule</td></tr>"
                "</tbody></table>"
            )
        elif not rows:
            html = (
                "<table><thead><tr><th>Schulfrei</th></tr></thead><tbody>"
                "<tr><td>Heute ist schulfrei</td></tr>"
                "</tbody></table>"
            )
        else:
            html = (
                "<table><thead><tr><th>Stunde</th><th>Fach</th><th>Raum</th><th>Info</th></tr></thead><tbody>"
                + "".join(rows)
                + "</tbody></table>"
            )

        return {
            "raw": raw_data,
            "html": html,
            "lesson_count": len(raw_data["lessons"]),
        }

    def _is_weekend_day(self) -> bool:
        """Check if the target day is a weekend."""
        target_date = self._get_target_date()
        return target_date.weekday() >= 5  # Saturday (5) or Sunday (6)

    def _get_target_date(self) -> datetime:
        """Get the date for the current day (today/tomorrow)."""
        now = datetime.now()
        if self.day == "today":
            return now
        if self.day == "tomorrow":
            return now + timedelta(days=1)
        return now


class ScheduleChangesSensor(CoordinatorEntity[SchulmanagerCoordinator], SensorEntity):
    """Sensor entity for schedule changes structured for LLM processing."""

    _attr_has_entity_name = True

    def __init__(
        self, client: Any, coordinator: SchulmanagerCoordinator, student_id: str, student_name: str, slug: str
    ) -> None:
        """Initialize the schedule changes sensor."""
        super().__init__(coordinator)
        self.client = client
        self.student_id = student_id
        self.student_name = student_name
        # Stable unique ID based on immutable student ID
        self._attr_unique_id = f"schulmanager_{self.student_id}_schedule_changes"
        self._attr_name = "Stundenplan Änderungen"
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
        data = (
            (self.coordinator.data or {}).get("schedule", {}).get(self.student_id, {})
        )
        changes = data.get("changes", {})

        today_changes = len(changes.get("today", []))
        tomorrow_changes = len(changes.get("tomorrow", []))
        return today_changes + tomorrow_changes

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the structured schedule changes for LLM processing."""
        data = (
            (self.coordinator.data or {}).get("schedule", {}).get(self.student_id, {})
        )
        changes = data.get("changes", {})

        if not changes:
            return {
                "changes": {
                    "today": [],
                    "tomorrow": [],
                    "summary": "Keine Stundenplanänderungen erkannt"
                },
                "llm_structured_data": {
                    "has_changes": False,
                    "total_changes": 0,
                    "today_count": 0,
                    "tomorrow_count": 0,
                    "natural_language_summary": "Keine Stundenplanänderungen für heute und morgen erkannt."
                }
            }

        today_changes = changes.get("today", [])
        tomorrow_changes = changes.get("tomorrow", [])
        total_changes = len(today_changes) + len(tomorrow_changes)

        # Create LLM-optimized structured data
        llm_data = {
            "has_changes": total_changes > 0,
            "total_changes": total_changes,
            "today_count": len(today_changes),
            "tomorrow_count": len(tomorrow_changes),
            "natural_language_summary": changes.get("summary", "No changes detected"),
            "detailed_changes": []
        }

        # Add detailed changes for LLM processing
        for day_name, day_changes in [("today", today_changes), ("tomorrow", tomorrow_changes)]:
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
                    "date": change.get("date", "")
                }
                llm_data["detailed_changes"].append(detail)

        return {
            "changes": changes,
            "llm_structured_data": llm_data,
            "last_updated": datetime.now().isoformat()
        }


class GradeSensor(CoordinatorEntity[SchulmanagerCoordinator], SensorEntity):
    """Sensor entity for student grades in a specific subject."""

    _attr_has_entity_name = True
    _attr_state_class = None
    _attr_suggested_display_precision = 2

    def __init__(
        self, client: Any, coordinator: SchulmanagerCoordinator, student_id: str, student_name: str, slug: str, subject_id: int, subject_name: str, subject_abbrev: str
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
        self._attr_unique_id = f"schulmanager_{self.student_id}_grades_{self.subject_id!s}"

        # Simple name: just "Noten" + subject abbreviation (device connection shows student)
        self._attr_name = f"Noten {subject_abbrev}"
        self._attr_icon = "mdi:school"

    def _parse_german_grade(self, grade_value: str | float) -> float | None:
        """Parse German grade formats and return numeric value."""
        if not grade_value and grade_value != 0:
            return None

        # Handle direct numeric values
        if isinstance(grade_value, (int, float)):
            return float(grade_value)

        grade_str = str(grade_value).strip()
        if not grade_str:
            return None

        # Handle format "0~3" -> 3.0
        if "~" in grade_str:
            try:
                return float(grade_str.split("~")[1])
            except (ValueError, IndexError):
                return None

        # Handle formats like "4+", "4-", "2+"
        if grade_str.endswith(("+", "-")):
            try:
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
        grades_data = (
            (self.coordinator.data or {}).get("grades", {}).get(self.student_id, {})
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
        grades_data = (
            (self.coordinator.data or {}).get("grades", {}).get(self.student_id, {})
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

        grade_categories = subject_data.get("grades", {})
        total_grades = 0

        # Count total grades and prepare category data with numeric values
        category_summary = {}
        for category, grades_list in grade_categories.items():
            # Process grades to include numeric values
            processed_grades = []
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
                    "grades": processed_grades
                }
                total_grades += len(processed_grades)

        # Extract numeric grade values (German grades are always numeric 1-6)
        all_grade_values = []
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
                "total_numeric_grades": len(all_grade_values)
            }

        # Build human-readable summaries (plain text and Markdown)
        def _format_grade_line(g: dict) -> str:
            val = str(g.get("value", "")).strip()
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
            grades_list = data["grades"]
            if not grades_list:
                continue
            lines_text.append(f"{category} ({len(grades_list)}):")
            lines_md.append(f"- **{category}** ({len(grades_list)}):")
            for g in grades_list:
                line = _format_grade_line(g)
                lines_text.append(f"  - {line}")
                lines_md.append(f"  - {line}")

        grades_summary = "\n".join(lines_text) if lines_text else "Keine Noten verfügbar"
        grades_summary_md = "\n".join(lines_md) if lines_md else "_Keine Noten verfügbar_"

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
        self, client: Any, coordinator: Any, student_id: str, student_name: str, slug: str
    ) -> None:
        """Initialize the overall grade sensor."""
        super().__init__(coordinator)
        self.client = client
        self.student_id = student_id
        self.student_name = student_name
        # Stable unique ID based on immutable student ID
        self._attr_unique_id = f"schulmanager_{self.student_id}_grades_overall"

        # Simple name: "Noten Gesamt"
        self._attr_name = "Noten Gesamt"
        self._attr_icon = "mdi:school"

    def _parse_german_grade(self, grade_value: str | float) -> float | None:
        """Parse German grade formats and return numeric value."""
        if not grade_value and grade_value != 0:
            return None

        # Handle direct numeric values
        if isinstance(grade_value, (int, float)):
            return float(grade_value)

        grade_str = str(grade_value).strip()
        if not grade_str:
            return None

        # Handle format "0~3" -> 3.0
        if "~" in grade_str:
            try:
                return float(grade_str.split("~")[1])
            except (ValueError, IndexError):
                return None

        # Handle formats like "4+", "4-", "2+"
        if grade_str.endswith(("+", "-")):
            try:
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
        grades_data = (
            (self.coordinator.data or {}).get("grades", {}).get(self.student_id, {})
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
        grades_data = (
            (self.coordinator.data or {}).get("grades", {}).get(self.student_id, {})
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
        subjects = grades_data.get("subjects", {})
        subject_averages = {}

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
            lines_md.append(f"- **{name}** ({abbr}): {avg if avg is not None else '-'} – {count} Noten")

        grades_summary = "\n".join(lines_text) if lines_text else "Keine Noten verfügbar"
        grades_summary_md = "\n".join(lines_md) if lines_md else "_Keine Noten verfügbar_"

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
        self, client: Any, coordinator: SchulmanagerCoordinator, student_id: str, student_name: str, slug: str
    ) -> None:
        """Initialize the next exam countdown sensor."""
        super().__init__(coordinator)
        self.client = client
        self.student_id = student_id
        self.student_name = student_name
        # Stable unique ID based on immutable student ID
        self._attr_unique_id = f"schulmanager_{self.student_id}_next_exam_days"

        # Simple name: "Tage bis nächste Arbeit"
        self._attr_name = "Tage bis nächste Arbeit"
        self._attr_icon = "mdi:calendar-clock"

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

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return bool(self.coordinator.last_update_success)

    @property
    def native_value(self) -> StateType:
        """Return days until next exam."""
        items = (self.coordinator.data or {}).get("exams", {}).get(self.student_id, [])
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
        items = (self.coordinator.data or {}).get("exams", {}).get(self.student_id, [])
        if not items:
            return {
                "next_exam": None,
                "total_upcoming_exams": 0,
                "last_updated": datetime.now().isoformat()
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
                        "subject": exam.get("subject", {}).get("name", "Unbekanntes Fach"),
                        "subject_abbr": exam.get("subject", {}).get("abbreviation", ""),
                        "type": exam.get("type", {}).get("name", "Prüfung"),
                        "comment": exam.get("comment", "")
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
                            "subject": exam.get("subject", {}).get("name", "Unbekanntes Fach"),
                            "subject_abbr": exam.get("subject", {}).get("abbreviation", ""),
                            "type": exam.get("type", {}).get("name", "Prüfung"),
                            "comment": exam.get("comment", "")
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
            "last_updated": datetime.now().isoformat()
        }
