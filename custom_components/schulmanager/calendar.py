"""Calendar platform for Schulmanager integration."""
from __future__ import annotations

from datetime import datetime, timedelta
from logging import getLogger
from typing import Any, cast

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    OPT_ENABLE_SCHEDULE,
    OPT_SCHEDULE_HIDE_CANCELLED_NO_HIGHLIGHT,
    OPT_SCHEDULE_HIGHLIGHT,
)
from .coordinator import SchulmanagerCoordinator
from .util import normalize_student_slug

_LOGGER = getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Schulmanager calendar entities."""
    runtime = entry.runtime_data or {}
    coord: SchulmanagerCoordinator | None = runtime.get("coordinator")
    client = runtime.get("client")
    if coord is None or client is None:
        missing = [n for n, v in {"coordinator": coord, "client": client}.items() if v is None]
        _LOGGER.warning(
            "Runtime data incomplete for entry %s: missing %s; skipping calendar setup",
            entry.entry_id,
            ", ".join(missing),
        )
        return
    entities: list[CalendarEntity] = []

    opts = dict(entry.options or {})
    enable_schedule = bool(opts.get(OPT_ENABLE_SCHEDULE, True))
    schedule_highlight = bool(opts.get(OPT_SCHEDULE_HIGHLIGHT, True))
    hide_cancelled_no_highlight = bool(
        opts.get(OPT_SCHEDULE_HIDE_CANCELLED_NO_HIGHLIGHT, False)
    )

    for st in client.get_students():
        sid = st["id"]
        name = st["name"]
        slug = normalize_student_slug(name)
        # Exams calendar
        entities.append(ExamsCalendar(client, coord, sid, name, slug))
        # Schedule calendar (optional)
        if enable_schedule:
            entities.append(
                ScheduleCalendar(
                    client, coord, sid, name, slug, schedule_highlight, hide_cancelled_no_highlight
                )
            )

    async_add_entities(entities)


class ExamsCalendar(CalendarEntity):
    """Calendar entity for student exams."""

    _attr_has_entity_name = False

    def __init__(
        self,
        client: Any,
        coordinator: SchulmanagerCoordinator,
        student_id: str,
        student_name: str,
        slug: str,
    ) -> None:
        """Initialize the calendar entity."""
        self.hub = client
        self.coordinator = coordinator
        self.student_id = student_id
        self.student_name = student_name
        # Stable unique ID based on immutable student ID
        self._attr_unique_id = f"schulmanager_{self.student_id}_exams"
        # Full name with student for clarity
        self._attr_name = f"{self.student_name} Arbeiten"
        self._attr_icon = "mdi:book-education"



    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming exam event."""
        data = cast(dict[str, Any], self.coordinator.data)
        items = data.get("exams", {}).get(self.student_id, [])
        now = dt_util.now()

        for exam in items:
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
        data = cast(dict[str, Any], self.coordinator.data)
        items = data.get("exams", {}).get(self.student_id, [])
        out: list[CalendarEvent] = []

        for exam in items:
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
            suggested_area="Schule",
            configuration_url="https://login.schulmanager-online.de/",

        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return bool(self.coordinator.last_update_success)


class ScheduleCalendar(CalendarEntity):
    """Calendar entity for student schedule lessons."""

    _attr_has_entity_name = False

    def __init__(
        self,
        client: Any,
        coordinator: SchulmanagerCoordinator,
        student_id: str,
        student_name: str,
        slug: str,
        highlight: bool,
        hide_cancelled_no_highlight: bool,
    ) -> None:
        """Initialize the schedule calendar entity."""
        self.hub = client
        self.coordinator = coordinator
        self.student_id = student_id
        self.student_name = student_name
        self._attr_unique_id = f"schulmanager_{self.student_id}_schedule"
        self._attr_name = f"{self.student_name} Stundenplan"
        self._attr_icon = "mdi:calendar-school"
        self.highlight = highlight
        self.hide_cancelled_no_highlight = hide_cancelled_no_highlight

    @property
    def available(self) -> bool:
        """Return availability based on coordinator state."""
        return bool(self.coordinator.last_update_success)

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming schedule event (lesson)."""
        data = cast(dict[str, Any], self.coordinator.data)
        week = (data.get("schedule", {}) or {}).get(self.student_id, {}).get("week", {})
        now = dt_util.now()
        next_evt: CalendarEvent | None = None

        for date_str, lessons in week.items():
            for evt in self._iter_events_for_day(date_str, lessons):
                if evt.end >= now and (next_evt is None or evt.start < next_evt.start):
                    next_evt = evt
        return next_evt

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return schedule events within a date range from the current week payload."""
        data = cast(dict[str, Any], self.coordinator.data)
        week = (data.get("schedule", {}) or {}).get(self.student_id, {}).get("week", {})
        events: list[CalendarEvent] = [
            evt
            for date_str, lessons in week.items()
            for evt in self._iter_events_for_day(date_str, lessons)
            if not (evt.end < start_date or evt.start > end_date)
        ]
        return events

    def _iter_events_for_day(self, date_str: str, lessons: list[dict]) -> list[CalendarEvent]:
        """Build CalendarEvent list for a given date and list of lessons with de-duplication.

        If a cancelled lesson and a replacement (substitution/special) occur for the
        same hour, only create the replacement event and mention the cancelled lesson
        in the description to avoid duplicates.
        """
        out: list[CalendarEvent] = []

        # Group lessons by class hour number if available, else keep separate
        groups: dict[str, list[dict]] = {}
        for i, lesson in enumerate(lessons):
            ch = (lesson.get("classHour") or {})
            num = ch.get("number")
            key = str(num) if num is not None else f"idx_{i}"
            groups.setdefault(key, []).append(lesson)

        # Helper to format original (cancelled) info
        def original_info(canc: dict) -> str:
            orig = ""
            originals = canc.get("originalLessons") or []
            if originals:
                o = originals[0]
                s = (o.get("subject") or {})
                subj = s.get("abbreviation") or s.get("name") or ""
                tlist = o.get("teachers") or []
                teacher = ""
                if tlist:
                    teacher = tlist[0].get("abbreviation", "") or ""
                rname = (o.get("room") or {}).get("name", "")
                parts = [p for p in [subj, f"({teacher})" if teacher else "", f"in {rname}" if rname else ""] if p]
                orig = " ".join(parts)
            return orig

        for items in groups.values():
            cancelled = [itm for itm in items if itm.get("type") == "cancelledLesson"]
            active = [itm for itm in items if itm.get("type") != "cancelledLesson"]

            if active:
                chosen = active[0]
                start_dt, end_dt = self._lesson_times(date_str, chosen)
                summary, description = self._lesson_texts(chosen)
                # Append info about cancelled original if present
                if cancelled:
                    oi = original_info(cancelled[0])
                    if oi:
                        description = (description + "\n" if description else "") + f"Ursprünglich: {oi}"
                out.append(
                    CalendarEvent(start=start_dt, end=end_dt, summary=summary, description=description)
                )
            else:
                # Only cancellations present
                if (not self.highlight) and self.hide_cancelled_no_highlight:
                    continue
                canc = cancelled[0]
                start_dt, end_dt = self._lesson_times(date_str, canc)
                summary, description = self._lesson_texts(canc)
                out.append(
                    CalendarEvent(start=start_dt, end=end_dt, summary=summary, description=description)
                )

        return out

    def _lesson_times(self, date_str: str, lesson: dict) -> tuple[datetime, datetime]:
        """Derive start/end datetimes for a lesson."""
        # Prefer explicit classHour times if available
        ch = lesson.get("classHour", {}) or {}
        start_time = ch.get("from") or ch.get("start") or "08:00:00"
        end_time = ch.get("until") or ch.get("end") or "09:00:00"
        try:
            # If there are no concrete times, try to map by hour number
            number = ch.get("number")
            if (not ch.get("from")) and isinstance(number, (int, str)):
                # Default 45-min blocks with common breaks
                # You can adjust these to your school's timetable if needed
                hour_times = {
                    1: ("08:00:00", "08:45:00"),
                    2: ("08:45:00", "09:30:00"),
                    3: ("09:50:00", "10:35:00"),
                    4: ("10:35:00", "11:20:00"),
                    5: ("11:40:00", "12:25:00"),
                    6: ("12:25:00", "13:10:00"),
                    7: ("13:30:00", "14:15:00"),
                    8: ("14:15:00", "15:00:00"),
                    9: ("15:00:00", "15:45:00"),
                    10: ("15:45:00", "16:30:00"),
                }
                try:
                    num = int(number)
                    mapped = hour_times.get(num)
                    if mapped:
                        start_time, end_time = mapped
                except (TypeError, ValueError):
                    pass

            start_dt = datetime.fromisoformat(f"{date_str} {start_time}")
            end_dt = datetime.fromisoformat(f"{date_str} {end_time}")
            start_dt = dt_util.as_local(start_dt)
            end_dt = dt_util.as_local(end_dt)
        except (TypeError, ValueError):
            # Fallback: 1 Stunde ab Tagesbeginn
            start_dt = dt_util.start_of_local_day(datetime.fromisoformat(date_str))
            end_dt = start_dt + timedelta(hours=1)
        return start_dt, end_dt

    def _lesson_texts(self, lesson: dict) -> tuple[str, str]:
        """Generate summary and description with emoji highlighting (optional)."""
        lesson_type = lesson.get("type", "regularLesson")
        actual = lesson.get("actualLesson", {}) or {}
        # We no longer need original subject for title
        # 'originalLessons' can exist but is not required for summary
        if lesson_type == "cancelledLesson" and lesson.get("originalLessons"):
            _ = lesson.get("originalLessons") or []

        # Subjects
        new_sub = (actual.get("subject", {}) or {}).get("abbreviation") or (actual.get("subject", {}) or {}).get("name") or ""
        if not new_sub and lesson.get("subject"):
            s = lesson.get("subject") or {}
            new_sub = s.get("abbreviation") or s.get("name") or ""
        # Determine room name once for title/description
        room = (actual.get("room", {}) or lesson.get("room", {}) or {}).get("name", "")

        # Emoji highlighting only (no ASCII markers, no color hints)
        emoji = ""
        if self.highlight:
            if lesson_type == "cancelledLesson":
                emoji = "❌ "
            elif lesson_type in {"substitution", "specialLesson", "teacherChange", "irregularLesson"}:
                emoji = "🔁 "
            elif lesson_type == "roomChange":
                emoji = "🚪 "
            elif lesson_type == "exam":
                emoji = "📝 "

        # Build base title from subject + room
        base_title = new_sub or "Unterricht"
        if room:
            base_title = f"{base_title} – {room}"

        # Summary
        if (not self.highlight) and lesson_type == "cancelledLesson":
            # Simple cancellation marker without emojis
            summary = f"X {base_title}"
        else:
            # With highlight (or non-cancelled without highlight): optional emoji prefix
            summary = f"{emoji}{base_title}"

        # Description with teacher and room
        teachers = (actual.get("teachers") or lesson.get("teachers") or [])
        teacher_abbr = ", ".join(
            t.get("abbreviation") or (t.get("firstname", "") + " " + t.get("lastname", "")).strip()
            for t in teachers if isinstance(t, dict)
        )
        change_reason = lesson.get("substitutionText") or lesson.get("comment") or ""
        desc_parts = []
        if teacher_abbr:
            desc_parts.append(f"Lehrer: {teacher_abbr}")
        if room:
            desc_parts.append(f"Raum: {room}")
        if lesson_type != "regularLesson":
            desc_parts.append(f"Typ: {lesson_type}")
        if change_reason:
            desc_parts.append(f"Hinweis: {change_reason}")
        description = "\n".join(desc_parts)
        return summary, description
