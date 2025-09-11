"""Typed models for Schulmanager integration payloads."""

from __future__ import annotations

from typing import Any, TypedDict


class ScheduleChange(TypedDict, total=False):
    """A single schedule change entry."""

    day: str
    hour: int | str
    type: str
    new_subject: str
    original_subject: str
    new_teacher: str
    original_teacher: str
    new_room: str
    original_room: str
    reason: str
    note: str
    date: str


class ScheduleChanges(TypedDict):
    """Collection of changes for today and tomorrow."""

    today: list[ScheduleChange]
    tomorrow: list[ScheduleChange]
    summary: str


class SchedulePayload(TypedDict):
    """Typed schedule payload returned by the client."""

    today: list[dict[str, Any]]
    tomorrow: list[dict[str, Any]]
    changes: ScheduleChanges


class GradeEntry(TypedDict, total=False):
    """Typed single grade entry with optional enrichment."""

    value: str | float | int
    date: str | None
    topic: str
    weighting: int | float
    duration: int | None
    type_abbreviation: str | None
    is_repeat_exam: bool | None
    numeric_value: float | None


class SubjectGrades(TypedDict):
    """Typed grades for a single subject grouped by category."""

    name: str
    abbreviation: str
    average: float | None
    grades: dict[str, list[GradeEntry]]


class GradesPayload(TypedDict):
    """Typed payload for all subjects and overall stats."""

    subjects: dict[int, SubjectGrades]
    overall_average: float | None
    total_subjects: int
    subjects_with_grades: int


class IntegrationData(TypedDict):
    """Top-level data structure stored on the coordinator."""

    students: list[dict[str, Any]]
    homework: dict[str, list[dict[str, Any]]]
    schedule: dict[str, SchedulePayload]
    exams: dict[str, list[dict[str, Any]]]
    grades: dict[str, GradesPayload]
