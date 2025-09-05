"""Calendar platform for Schulmanager integration."""
from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .util import normalize_student_slug


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Schulmanager calendar entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    coord = data["coordinator"]
    hub = data["hub"]
    entities: list[CalendarEntity] = []

    for st in hub._students:  # noqa: SLF001
        sid = st["id"]
        name = st["name"]
        slug = normalize_student_slug(name)
        entities.append(ExamsCalendar(hub, coord, sid, name, slug))

    async_add_entities(entities)


class ExamsCalendar(CalendarEntity):
    """Calendar entity for student exams."""

    _attr_has_entity_name = True

    def __init__(
        self, hub, coordinator, student_id: str, student_name: str, slug: str
    ) -> None:
        """Initialize the calendar entity."""
        self.hub = hub
        self.coordinator = coordinator
        self.student_id = student_id
        self.student_name = student_name
        self._attr_unique_id = f"schulmanager_{slug}_arbeiten"
        self._attr_name = f"{student_name} Arbeiten"
        self._attr_icon = "mdi:book-education"

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming exam event."""
        items = (self.coordinator.data or {}).get("exams", {}).get(self.student_id, [])
        now = dt_util.now()

        for exam in items or []:
            # Handle exam data structure from API
            exam_date = exam.get("date")
            if not exam_date:
                continue

            try:
                # Parse the date (should be YYYY-MM-DD format)
                if "T" in exam_date:
                    d = datetime.fromisoformat(exam_date).date()
                else:
                    d = datetime.fromisoformat(exam_date).date()
            except (ValueError, TypeError):
                try:
                    d = datetime.strptime(exam_date, "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    continue

            # Create start time based on class hour if available
            start_time = None
            end_time = None
            if "startClassHour" in exam:
                try:
                    hour_from = exam["startClassHour"].get("from", "08:00:00")
                    hour_until = exam["startClassHour"].get("until", "09:00:00")

                    start_time = datetime.strptime(
                        f"{exam_date} {hour_from}", "%Y-%m-%d %H:%M:%S"
                    )
                    end_time = datetime.strptime(
                        f"{exam_date} {hour_until}", "%Y-%m-%d %H:%M:%S"
                    )

                    # Make timezone aware
                    start_time = dt_util.as_local(start_time)
                    end_time = dt_util.as_local(end_time)
                except (ValueError, TypeError):
                    # Fall back to all-day event
                    start_time = dt_util.start_of_local_day(d)
                    end_time = start_time + timedelta(days=1)
            else:
                # All-day event
                start_time = dt_util.start_of_local_day(d)
                end_time = start_time + timedelta(days=1)

            # Return the next upcoming exam
            if end_time >= now:
                summary = self._generate_exam_summary(exam)
                description = self._generate_exam_description(exam)

                return CalendarEvent(
                    start=start_time,
                    end=end_time,
                    summary=summary,
                    description=description,
                )

        return None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Get events in a specific date range."""
        items = (self.coordinator.data or {}).get("exams", {}).get(self.student_id, [])
        out: list[CalendarEvent] = []

        for exam in items or []:
            # Handle exam data structure from API
            exam_date = exam.get("date")
            if not exam_date:
                continue

            try:
                # Parse the date (should be YYYY-MM-DD format)
                if "T" in exam_date:
                    d = datetime.fromisoformat(exam_date).date()
                else:
                    d = datetime.fromisoformat(exam_date).date()
            except (ValueError, TypeError):
                try:
                    d = datetime.strptime(exam_date, "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    continue

            # Create start time based on class hour if available
            start_time = None
            end_time = None
            if "startClassHour" in exam:
                try:
                    hour_from = exam["startClassHour"].get("from", "08:00:00")
                    hour_until = exam["startClassHour"].get("until", "09:00:00")

                    start_time = datetime.strptime(
                        f"{exam_date} {hour_from}", "%Y-%m-%d %H:%M:%S"
                    )
                    end_time = datetime.strptime(
                        f"{exam_date} {hour_until}", "%Y-%m-%d %H:%M:%S"
                    )

                    # Make timezone aware
                    start_time = dt_util.as_local(start_time)
                    end_time = dt_util.as_local(end_time)
                except (ValueError, TypeError):
                    # Fall back to all-day event
                    start_time = dt_util.start_of_local_day(d)
                    end_time = start_time + timedelta(days=1)
            else:
                # All-day event
                start_time = dt_util.start_of_local_day(d)
                end_time = start_time + timedelta(days=1)

            # Check if event is in requested range
            if end_time < start_date or start_time > end_date:
                continue

            # Generate summary with type and subject
            summary = self._generate_exam_summary(exam)
            description = self._generate_exam_description(exam)

            out.append(
                CalendarEvent(
                    start=start_time,
                    end=end_time,
                    summary=summary,
                    description=description,
                )
            )

        return out

    def _generate_exam_summary(self, exam: dict) -> str:
        """Generate summary text for exam event."""
        # Get exam type (Test, Klausur, etc.)
        exam_type = "Prüfung"
        if "type" in exam and "name" in exam["type"]:
            exam_type = exam["type"]["name"]

        # Get subject name
        subject_name = "Unbekanntes Fach"
        if "subject" in exam:
            if "abbreviation" in exam["subject"]:
                subject_name = exam["subject"]["abbreviation"]
            elif "name" in exam["subject"]:
                subject_name = exam["subject"]["name"]

        # Format: "Test EN" or "Klausur Mathematik"
        return f"{exam_type} {subject_name}"

    def _generate_exam_description(self, exam: dict) -> str:
        """Generate description text for exam event."""
        description_parts = []

        # Add subject details
        if "subject" in exam and "name" in exam["subject"]:
            description_parts.append(f"Fach: {exam['subject']['name']}")

        # Add exam type with color if available
        if "type" in exam:
            type_info = exam["type"]["name"]
            if "color" in exam["type"]:
                type_info += f" ({exam['type']['color']})"
            description_parts.append(f"Art: {type_info}")

        # Add comment/topic if available
        if exam.get("comment"):
            description_parts.append(f"Thema: {exam['comment']}")

        # Add class hour info if available
        if "startClassHour" in exam:
            hour_info = exam["startClassHour"]
            if "number" in hour_info:
                time_info = f"Stunde {hour_info['number']}"
                if "from" in hour_info and "until" in hour_info:
                    time_info += (
                        f" ({hour_info['from'][:5]} - {hour_info['until'][:5]})"
                    )
                description_parts.append(f"Zeit: {time_info}")

        return "\n".join(description_parts)

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
        return self.coordinator.last_update_success
