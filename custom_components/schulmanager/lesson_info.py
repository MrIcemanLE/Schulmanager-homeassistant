"""Extract subject, room and teacher from Schulmanager lesson records.

Shared by the schedule sensors and the schedule-change detection so both read
original and actual lessons the same way.
"""

from typing import Any


def teacher_names(source: dict[str, Any]) -> str:
    """Return the teacher abbreviations (or names) of a lesson, comma-separated."""
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


def extract_core_info(source: dict[str, Any] | None) -> dict[str, str]:
    """Return subject, room and teacher of a single lesson record."""
    if not isinstance(source, dict):
        return {"subject": "", "subject_full": "", "room": "", "teacher": ""}
    subject = ""
    subject_full = ""
    subject_data = source.get("subject")
    if isinstance(subject_data, dict):
        subject = (
            subject_data.get("abbreviation") or subject_data.get("shortName") or ""
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
        subject_full = source.get("subjectLong") or source.get("subjectFull") or subject
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
    teacher = teacher_names(source)
    return {
        "subject": subject,
        "subject_full": subject_full,
        "room": room,
        "teacher": teacher,
    }


def extract_primary_info(lesson: dict[str, Any]) -> dict[str, str]:
    """Return the lesson as it actually takes place."""
    candidates = [
        lesson.get("actualLesson"),
        lesson.get("lesson"),
        lesson,
    ]
    for candidate in candidates:
        info = extract_core_info(candidate)
        if any(info.values()):
            return info
    return {"subject": "", "subject_full": "", "room": "", "teacher": ""}


def extract_original_info(lesson: dict[str, Any]) -> dict[str, str]:
    """Return the originally scheduled lesson of a changed/cancelled lesson."""
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
        info = extract_core_info(candidate)
        if any(info.values()):
            return info
    return {"subject": "", "subject_full": "", "room": "", "teacher": ""}
