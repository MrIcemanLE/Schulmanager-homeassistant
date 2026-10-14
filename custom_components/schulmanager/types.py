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
    # Map of ISO date (YYYY-MM-DD) to list of lessons for the current week
    week: dict[str, list[dict[str, Any]]]
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
    numeric_value: float | int | None
    # Absent is treated as True by all consumers (backward-compatible with
    # entries created before these fields existed).
    fires_event: bool
    counts_toward_average: bool
    # Used by grading.calculate_average's two-level weighting; absent means
    # "no known block" (falls back to an unweighted 1.0 block share).
    grading_block_id: int | None
    block_weighting: float


class SubjectGrades(TypedDict):
    """Typed grades for a single subject grouped by category."""

    name: str
    abbreviation: str
    average: float | None
    grades: dict[str, list[GradeEntry]]
    grading_system: int


class GradesPayload(TypedDict):
    """Typed payload for all subjects and overall stats."""

    subjects: dict[int, SubjectGrades]
    overall_average: float | None
    total_subjects: int
    subjects_with_grades: int


class _IntegrationDataBase(TypedDict):
    """Required keys of the coordinator data."""

    students: list[dict[str, Any]]
    homework: dict[str, list[dict[str, Any]]]
    schedule: dict[str, SchedulePayload]
    exams: dict[str, list[dict[str, Any]]]
    grades: dict[str, GradesPayload]


class IntegrationData(_IntegrationDataBase, total=False):
    """Top-level data structure stored on the coordinator.

    Account-level data (not per student) is only present when the feature is
    enabled, the school offers the module and the last fetch succeeded.
    """

    # Unread parent letters (Elternbriefe) as returned by the letters widget endpoint
    letters_unread: list[dict[str, Any]]
    # Messenger subscriptions (conversations) that contain unread messages
    messages_unread: list[dict[str, Any]]
    # Total number of unread messenger messages
    messages_unread_count: int
