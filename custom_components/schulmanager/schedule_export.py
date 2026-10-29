"""Build the structured timetable returned by the schulmanager.get_schedule service.

The format was agreed with the stundenplan-suite maintainer
(github.com/fabel-smith/stundenplan-card/issues/16). Lesson fields follow the
suite's Lesson model, so kind/status/changes use its vocabulary.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from homeassistant.util import dt as dt_util

from .lesson_info import normalize_hour

SCHEMA_VERSION = 1

STATUS_OK = "ok"
STATUS_STALE = "stale"
STATUS_UNAVAILABLE = "unavailable"

# Schulmanager entry type -> (kind, status)
_TYPE_MAP: dict[str, tuple[str, str]] = {
    "regularLesson": ("lesson", "scheduled"),
    "changedLesson": ("lesson", "changed"),
    "cancelledLesson": ("lesson", "cancelled"),
    "specialLesson": ("lesson", "changed"),
    "event": ("event", "scheduled"),
}


def _period_sort_key(period: str) -> tuple[int, str]:
    return (int(period), "") if period.isdigit() else (10**6, period)


def _hhmm(value: Any) -> str | None:
    """Return "HH:MM" from Schulmanager's "HH:MM:SS"."""
    if not isinstance(value, str) or len(value) < 5:
        return None
    return value[:5]


def _local_iso(day: str, clock: Any) -> str | None:
    if not isinstance(clock, str):
        return None
    try:
        moment = datetime.combine(date.fromisoformat(day), time.fromisoformat(clock))
    except ValueError:
        return None
    return moment.replace(tzinfo=dt_util.get_default_time_zone()).isoformat()


def _teachers(record: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for teacher in record.get("teachers") or []:
        if not isinstance(teacher, dict):
            continue
        name = teacher.get("abbreviation") or " ".join(
            part for part in (teacher.get("firstname"), teacher.get("lastname")) if part
        )
        if name:
            names.append(str(name))
    return names


def _rooms(record: dict[str, Any]) -> list[str]:
    rooms = [record.get("room"), *(record.get("rooms") or [])]
    names: list[str] = []
    for room in rooms:
        name = room.get("name") if isinstance(room, dict) else room
        if isinstance(name, str) and name and name not in names:
            names.append(name)
    return names


def _group(record: dict[str, Any]) -> str | None:
    names = [
        str(group["name"])
        for group in record.get("studentGroups") or []
        if isinstance(group, dict) and group.get("name")
    ]
    return ", ".join(names) or None


def _summary(record: dict[str, Any] | None) -> dict[str, Any]:
    """Return subject, teachers, rooms and group of a lesson record."""
    if not record:
        return {
            "subject": "",
            "subject_full": "",
            "teachers": [],
            "rooms": [],
            "group": None,
        }
    subject = record.get("subject")
    if isinstance(subject, dict):
        short = subject.get("abbreviation") or subject.get("name") or ""
        full = subject.get("name") or short
    else:
        short = full = subject if isinstance(subject, str) else ""
    return {
        "subject": short,
        "subject_full": full,
        "teachers": _teachers(record),
        "rooms": _rooms(record),
        "group": _group(record),
    }


def _first_original(entry: dict[str, Any]) -> dict[str, Any] | None:
    originals = [o for o in entry.get("originalLessons") or [] if isinstance(o, dict)]
    return originals[0] if originals else None


def _lesson_id(
    entry: dict[str, Any], actual: dict[str, Any], original: dict[str, Any] | None
) -> str:
    """Return an id that is stable across fetches and unique within the day.

    lessonId identifies a weekly timetable slot (same weekday and period), so it
    only becomes unique together with the date. Changed lessons carry it on the
    original only; special lessons have a substitutionId instead.
    """
    day = entry.get("date", "")
    lesson_id = actual.get("lessonId") or (original or {}).get("lessonId")
    if lesson_id is not None:
        return f"{day}-{lesson_id}"
    if (substitution_id := actual.get("substitutionId")) is not None:
        return f"{day}-s{substitution_id}"
    period = normalize_hour((entry.get("classHour") or {}).get("number"))
    subject = _summary(actual)["subject"] or _summary(original)["subject"]
    return f"{day}-{period}-{subject}"


def export_lesson(entry: dict[str, Any]) -> dict[str, Any]:
    """Convert one get-actual-lessons entry to the agreed lesson format."""
    source_type = str(entry.get("type") or "")
    actual = entry.get("actualLesson") or entry.get("event") or {}
    original = _first_original(entry)
    kind, status = _TYPE_MAP.get(source_type, ("unknown", "unknown"))
    if entry.get("isCancelled") and kind == "lesson":
        status = "cancelled"

    current = _summary(actual)
    before = _summary(original) if original else None

    changes: list[str] = []
    if status == "cancelled":
        changes.append("cancellation")
        # A cancelled entry has no actual lesson; show what was scheduled
        if before:
            current = {**before, "teachers": [], "rooms": []}
    elif before:
        if current["subject"] != before["subject"]:
            changes.append("subject")
        if current["teachers"] != before["teachers"]:
            changes.append("teacher")
        if current["rooms"] != before["rooms"]:
            changes.append("room")
    if source_type == "specialLesson":
        changes.append("special")
    if current["group"] is None and before:
        current["group"] = before["group"]

    notes: list[str] = []
    for note in (
        entry.get("comment"),
        actual.get("comment"),
        entry.get("substitutionText"),
    ):
        if isinstance(note, str) and note.strip() and note.strip() not in notes:
            notes.append(note.strip())

    course_id = actual.get("courseId") or (original or {}).get("courseId")
    class_hour = entry.get("classHour") or {}
    day = str(entry.get("date") or "")[:10]

    return {
        "id": _lesson_id(entry, actual, original),
        "date": day,
        "period": normalize_hour(class_hour.get("number")),
        "start": _local_iso(day, class_hour.get("from")),
        "end": _local_iso(day, class_hour.get("until")),
        "subject": current["subject"],
        "subject_full": current["subject_full"],
        "group": current["group"],
        "course_id": str(course_id) if course_id is not None else None,
        "teachers": current["teachers"],
        "rooms": current["rooms"],
        "kind": kind,
        "status": status,
        "changes": changes,
        "notes": notes,
        "original": (
            {
                key: before[key]
                for key in ("subject", "subject_full", "teachers", "rooms", "group")
            }
            if before
            else None
        ),
        "source_type": source_type,
    }


def export_periods(class_hours: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the school's default period times, ordered by period."""
    periods = [
        {
            "period": normalize_hour(hour.get("number")),
            "start": _hhmm(hour.get("from")),
            "end": _hhmm(hour.get("until")),
        }
        for hour in class_hours
        if isinstance(hour, dict)
    ]
    return sorted(periods, key=lambda p: _period_sort_key(p["period"]))


def export_days(
    week: dict[str, list[dict[str, Any]]], range_start: str, range_end: str
) -> list[dict[str, Any]]:
    """Return one entry per day in the range; days without lessons stay empty."""
    days: list[dict[str, Any]] = []
    current = date.fromisoformat(range_start)
    last = date.fromisoformat(range_end)
    while current <= last:
        day = current.isoformat()
        lessons = [
            export_lesson(entry)
            for entry in week.get(day) or []
            if isinstance(entry, dict)
        ]
        seen: dict[str, int] = {}
        for lesson in lessons:
            # Guard against duplicate ids should the API ever repeat a slot
            count = seen.get(lesson["id"], 0)
            seen[lesson["id"]] = count + 1
            if count:
                lesson["id"] = f"{lesson['id']}-{count + 1}"
        lessons.sort(
            key=lambda lesson: (
                lesson["start"] or "",
                _period_sort_key(lesson["period"]),
            )
        )
        days.append({"date": day, "loaded": True, "lessons": lessons})
        current += timedelta(days=1)
    return days


def export_student_schedule(
    config_entry_id: str,
    student: dict[str, Any],
    payload: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return the structured schedule of one student from a fresh schedule payload.

    A payload without "fetched_at" comes from a failed or disabled fetch and is
    reported as unavailable; the coordinator turns it into "stale" when it still
    has an older successful export.
    """
    base = {
        "config_entry_id": config_entry_id,
        "student_id": str(student.get("id")),
        "name": student.get("name") or "",
        "school": student.get("school_name") or "",
    }
    if not payload or not payload.get("fetched_at"):
        return {
            **base,
            "status": STATUS_UNAVAILABLE,
            "fetched_at": None,
            "range": None,
            "periods": [],
            "days": [],
        }
    range_start = payload["range_start"]
    range_end = payload["range_end"]
    return {
        **base,
        "status": STATUS_OK,
        "fetched_at": payload["fetched_at"],
        "range": {"start": range_start, "end": range_end},
        "periods": export_periods(payload.get("class_hours") or []),
        "days": export_days(payload.get("week") or {}, range_start, range_end),
    }


def without_fetch_time(export: dict[str, Any]) -> dict[str, Any]:
    """Return the export without fields that change on every fetch."""
    return {key: value for key, value in export.items() if key != "fetched_at"}
