"""Scale-aware grade parsing, validation and averaging.

Schulmanager supports two grading scales: the classic German 1-6 scale
(used in Sekundarstufe I, values like "0~3+", "0~2-") and a 0-15 points
scale ("Notenpunkte", used in Sekundarstufe II course-system classes,
where 15 = "1+" down to 0 = "6"). Both scales are transmitted in the same
tilde-separated wire format (e.g. "0~3" vs "1~5"); the leading number is
a scale indicator, not part of the value, so a single parser handles both.
Which scale applies is carried per course via `gradingPreset.gradingSystem`.
"""

from typing import Final

GRADING_SYSTEM_CLASSIC: Final = 0
GRADING_SYSTEM_POINTS: Final = 1

# Schulmanager's own names for its grading systems (from its web app)
GRADING_SYSTEM_LABELS: Final = {
    GRADING_SYSTEM_CLASSIC: "Noten 1 bis 6",
    GRADING_SYSTEM_POINTS: "Notenpunkte 0 bis 15",
}
POINTS_UNIT: Final = "Punkte"


def unit_of_measurement(grading_system: int | None) -> str | None:
    """Return the sensor unit for a grading system; classic grades have none."""
    return POINTS_UNIT if grading_system == GRADING_SYSTEM_POINTS else None

FINAL_GRADE_CATEGORY: Final = "Tendenz"


def parse_grade_value(
    grade_value: str | float, grading_system: int
) -> float | int | None:
    """Parse a raw grade value into a numeric value for the given grading scale.

    Points-scale values are always whole numbers and are returned as int;
    classic-scale values keep their existing float representation (e.g. a
    tendency marker like "3+"/"3-" is stripped, both becoming 3.0).
    """
    if not grade_value and grade_value != 0:
        return None

    if isinstance(grade_value, (int, float)):
        return (
            int(grade_value)
            if grading_system == GRADING_SYSTEM_POINTS
            else float(grade_value)
        )

    grade_str = str(grade_value).strip()
    if not grade_str:
        return None

    if "~" in grade_str:
        try:
            grade_part = grade_str.split("~")[1]
        except IndexError:
            return None
        if grade_part.endswith(("+", "-")):
            grade_part = grade_part[:-1]
        try:
            return (
                int(grade_part)
                if grading_system == GRADING_SYSTEM_POINTS
                else float(grade_part)
            )
        except ValueError:
            return None

    if grade_str.endswith(("+", "-")):
        try:
            grade_part = grade_str[:-1]
            return (
                int(grade_part)
                if grading_system == GRADING_SYSTEM_POINTS
                else float(grade_part)
            )
        except ValueError:
            return None

    try:
        return (
            int(grade_str)
            if grading_system == GRADING_SYSTEM_POINTS
            else float(grade_str)
        )
    except ValueError:
        return None


def grade_value_in_range(value: float, grading_system: int) -> bool:
    """Return whether a parsed value is within the valid range for its scale."""
    if grading_system == GRADING_SYSTEM_POINTS:
        return 0 <= value <= 15
    return 1.0 <= value <= 6.0


def is_higher_better(grading_system: int) -> bool:
    """Return whether a higher numeric value means a better grade on this scale."""
    return grading_system == GRADING_SYSTEM_POINTS


def calculate_average(
    grade_categories: dict[str, list[dict[str, object]]], grading_system: int
) -> float | None:
    """Weighted average across all counted grades, rounded to one decimal place.

    Entries explicitly marked `counts_toward_average=False` (Tendenz entries
    derived from finalGrades, or grades superseded by a repeat exam of the
    same type) are excluded.

    The remaining entries are weighted in two steps, matching how schools
    themselves compute the grade: each entry's own `weighting` (e.g. an exam
    counting double within its block) first determines its share *within*
    its grading block (e.g. "Klassenarbeit"), and each block's `block_weighting`
    (e.g. Klassenarbeiten 50% / Sonstige 50%, from the API's per-course
    `blockPresets`) then determines that block's share of the subject grade.
    This two-level average is computed as a single weighted sum by scaling
    each entry's own weighting by `block_weighting / (sum of that block's
    entry weightings)` - see the module's implementation notes for the
    derivation. Entries with no known block (`grading_block_id` absent, e.g.
    Tendenz entries that already got excluded above) fall back to an
    unweighted 1.0 block share.
    """
    parsed: list[tuple[float | int, float, object, float]] = []
    for grades_list in grade_categories.values():
        for grade in grades_list:
            if grade.get("counts_toward_average") is False:
                continue
            numeric_value = parse_grade_value(grade.get("value", ""), grading_system)
            if numeric_value is None or not grade_value_in_range(
                numeric_value, grading_system
            ):
                continue
            weighting = grade.get("weighting") or 1
            block_id = grade.get("grading_block_id")
            block_weighting = grade.get("block_weighting") or 1.0
            parsed.append(
                (numeric_value, float(weighting), block_id, float(block_weighting))
            )

    if not parsed:
        return None

    block_weighting_sum: dict[object, float] = {}
    for _value, weighting, block_id, _block_weighting in parsed:
        block_weighting_sum[block_id] = (
            block_weighting_sum.get(block_id, 0.0) + weighting
        )

    numerator = 0.0
    denominator = 0.0
    for value, weighting, block_id, block_weighting in parsed:
        effective_weight = weighting * (block_weighting / block_weighting_sum[block_id])
        numerator += value * effective_weight
        denominator += effective_weight

    if denominator == 0:
        return None
    return round(numerator / denominator, 1)
