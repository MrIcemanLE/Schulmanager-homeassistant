from __future__ import annotations

from typing import Any
from datetime import datetime, timedelta

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.typing import StateType

from .const import DOMAIN
from .util import normalize_student_slug


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Schulmanager sensor entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    coord = data["coordinator"]
    hub = data["hub"]
    entities: list[SensorEntity] = []

    for st in hub._students:
        sid = st["id"]
        name = st["name"]
        slug = normalize_student_slug(name)
        entities.append(ScheduleSensor(hub, coord, sid, name, slug, "today"))
        entities.append(ScheduleSensor(hub, coord, sid, name, slug, "tomorrow"))
        entities.append(ScheduleChangesSensor(hub, coord, sid, name, slug))
        
        # Add grade sensors for each subject
        # We'll check for available subjects from the first update
        grades_data = coord.data.get("grades", {}).get(sid, {}) if coord.data else {}
        subjects = grades_data.get("subjects", {})
        
        for subject_id, subject_data in subjects.items():
            subject_name = subject_data.get("name", f"Fach {subject_id}")
            subject_abbrev = subject_data.get("abbreviation", subject_name)
            entities.append(GradeSensor(hub, coord, sid, name, subject_id, subject_name, subject_abbrev))

        # Add overall average sensor
        entities.append(OverallGradeSensor(hub, coord, sid, name))

    async_add_entities(entities)


class ScheduleSensor(SensorEntity):
    """Sensor entity for student schedule."""

    _attr_has_entity_name = True

    def __init__(
        self, hub: Any, coordinator: Any, student_id: str, student_name: str, slug: str, day: str
    ) -> None:
        self.hub = hub
        self.coordinator = coordinator
        self.student_id = student_id
        self.student_name = student_name
        self.day = day
        self._attr_unique_id = f"schulmanager_{slug}_stundenplan_{day}"
        pretty = "heute" if day == "today" else "morgen"
        self._attr_name = f"{student_name} Stundenplan {pretty}"
        self._attr_icon = "mdi:school-outline"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"student_{self.student_id}")},
            name=self.student_name,
            manufacturer="Schulmanager Online",
            model="Schüler",
            sw_version="2025.1",
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

        attrs = {
            "raw": raw_data,
            "html": html,
            "lesson_count": len(raw_data["lessons"])
        }
        return attrs

    def _is_weekend_day(self) -> bool:
        """Check if the target day is a weekend."""
        target_date = self._get_target_date()
        return target_date.weekday() >= 5  # Saturday (5) or Sunday (6)

    def _get_target_date(self) -> datetime:
        """Get the date for the current day (today/tomorrow)."""
        now = datetime.now()
        if self.day == "today":
            return now
        elif self.day == "tomorrow":
            return now + timedelta(days=1)
        return now


class ScheduleChangesSensor(SensorEntity):
    """Sensor entity for schedule changes structured for LLM processing."""

    _attr_has_entity_name = True

    def __init__(
        self, hub: Any, coordinator: Any, student_id: str, student_name: str, slug: str
    ) -> None:
        """Initialize the schedule changes sensor."""
        self.hub = hub
        self.coordinator = coordinator
        self.student_id = student_id
        self.student_name = student_name
        self._attr_unique_id = f"schulmanager_{slug}_stundenplan_changes"
        self._attr_name = f"{student_name} Stundenplan Änderungen"
        self._attr_icon = "mdi:calendar-alert"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"student_{self.student_id}")},
            name=self.student_name,
            manufacturer="Schulmanager Online",
            model="Schüler",
            sw_version="2025.1",
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
        total_changes = today_changes + tomorrow_changes
        
        return total_changes

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


class GradeSensor(SensorEntity):
    """Sensor entity for student grades in a specific subject."""

    _attr_has_entity_name = True
    _attr_state_class = None
    _attr_suggested_display_precision = 2

    def __init__(
        self, hub: Any, coordinator: Any, student_id: str, student_name: str, subject_id: str, subject_name: str, subject_abbrev: str
    ) -> None:
        """Initialize the grade sensor."""
        self.hub = hub
        self.coordinator = coordinator
        self.student_id = student_id
        self.student_name = student_name
        self.subject_id = subject_id
        self.subject_name = subject_name
        self.subject_abbrev = subject_abbrev
        
        # Create reliable entity ID using student name slug and subject abbreviation for reconnection
        import re
        student_slug = re.sub(r'[^a-zA-Z0-9]', '_', student_name.lower())
        subject_slug = re.sub(r'[^a-zA-Z0-9]', '_', subject_abbrev.lower())
        self._attr_unique_id = f"schulmanager_{student_slug}_noten_{subject_slug}"
        
        # Simple name: just "Noten" + subject abbreviation (device connection shows student)
        self._attr_name = f"Noten {subject_abbrev}"
        self._attr_icon = "mdi:school"

    def _parse_german_grade(self, grade_value: str | int | float) -> float | None:
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
                base_grade = float(grade_str[:-1])
                # Treat both 4+ and 4- as 4.0 (ignore plus/minus for simplicity)
                return base_grade
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
            sw_version="2025.1",
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
        subjects = grades_data.get("subjects", {})
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
        subjects = grades_data.get("subjects", {})
        subject_data = subjects.get(self.subject_id, {})
        
        if not subject_data:
            return {
                "subject_name": self.subject_name,
                "subject_id": self.subject_id,
                "total_grades": 0,
                "grade_categories": {}
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
        
        return {
            "subject_name": self.subject_name,
            "subject_id": self.subject_id,
            "total_grades": total_grades,
            "grade_categories": category_summary,  # Only non-empty categories
            "statistics": statistics,
            "last_updated": datetime.now().isoformat()
        }


class OverallGradeSensor(SensorEntity):
    """Sensor entity for student's overall grade average."""

    _attr_has_entity_name = True
    _attr_state_class = None
    _attr_suggested_display_precision = 2

    def __init__(
        self, hub: Any, coordinator: Any, student_id: str, student_name: str
    ) -> None:
        """Initialize the overall grade sensor."""
        self.hub = hub
        self.coordinator = coordinator
        self.student_id = student_id
        self.student_name = student_name
        
        # Create reliable entity ID using student name slug
        import re
        student_slug = re.sub(r'[^a-zA-Z0-9]', '_', student_name.lower())
        self._attr_unique_id = f"schulmanager_{student_slug}_noten_gesamt"
        
        # Simple name: "Noten Gesamt" 
        self._attr_name = "Noten Gesamt"
        self._attr_icon = "mdi:school"

    def _parse_german_grade(self, grade_value: str | int | float) -> float | None:
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
                base_grade = float(grade_str[:-1])
                # Treat both 4+ and 4- as 4.0 (ignore plus/minus for simplicity)
                return base_grade
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
            sw_version="2025.1",
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
                "subject_averages": {}
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
        
        return {
            "total_subjects": grades_data.get("total_subjects", 0),
            "subjects_with_grades": grades_data.get("subjects_with_grades", 0),
            "subject_averages": subject_averages,
            "last_updated": datetime.now().isoformat()
        }
