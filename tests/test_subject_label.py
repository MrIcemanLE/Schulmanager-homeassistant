"""Regression tests for school-specific lesson labels (subjectLabel).

The Schulmanager API sends a ``subjectLabel`` alongside the generic subject
abbreviation/name. It must survive into the sensor attributes, the structured
schedule changes and the ``schulmanager.get_schedule`` response.
"""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from datetime import UTC
from pathlib import Path

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "schulmanager"


def _install_homeassistant_stub() -> None:
    """Provide the single HA helper schedule_export needs, without installing HA."""
    if "homeassistant.util.dt" in sys.modules:
        return
    ha = types.ModuleType("homeassistant")
    util = types.ModuleType("homeassistant.util")
    dt = types.ModuleType("homeassistant.util.dt")
    dt.get_default_time_zone = lambda: UTC
    util.dt = dt
    ha.util = util
    sys.modules.update(
        {
            "homeassistant": ha,
            "homeassistant.util": util,
            "homeassistant.util.dt": dt,
        }
    )


def _load_component_module(name: str) -> types.ModuleType:
    """Load a module as part of a synthetic package, skipping HA's __init__.py."""
    pkg_name = "schulmanager_tests_pkg"
    if pkg_name not in sys.modules:
        pkg = types.ModuleType(pkg_name)
        pkg.__path__ = [str(COMPONENT)]
        sys.modules[pkg_name] = pkg
    full_name = f"{pkg_name}.{name}"
    if full_name not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            full_name, COMPONENT / f"{name}.py"
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[full_name] = module
        spec.loader.exec_module(module)
    return sys.modules[full_name]


_install_homeassistant_stub()
lesson_info = _load_component_module("lesson_info")
schedule_export = _load_component_module("schedule_export")


def regular_entry(label: str = "NAWI 1") -> dict:
    return {
        "type": "regularLesson",
        "date": "2026-11-23",
        "classHour": {"number": "3", "from": "09:00:00", "until": "09:45:00"},
        "actualLesson": {
            "lessonId": 42,
            "subject": {"abbreviation": "NuT", "name": "Natur und Technik"},
            "subjectLabel": label,
            "room": {"name": "B204"},
        },
    }


def cancelled_entry(label: str = "WU Klettern") -> dict:
    return {
        "type": "cancelledLesson",
        "date": "2026-11-23",
        "classHour": {"number": "5", "from": "11:00:00", "until": "11:45:00"},
        "originalLessons": [
            {
                "lessonId": 99,
                "subject": {"abbreviation": "Smw", "name": "Sport (mw)"},
                "subjectLabel": label,
            }
        ],
    }


class SubjectLabelExtractionTest(unittest.TestCase):
    def test_core_info_reads_subject_label(self) -> None:
        info = lesson_info.extract_core_info(regular_entry()["actualLesson"])
        self.assertEqual(info["subject_label"], "NAWI 1")
        self.assertEqual(info["subject"], "NuT")
        self.assertEqual(info["subject_full"], "Natur und Technik")

    def test_primary_info_reads_subject_label(self) -> None:
        info = lesson_info.extract_primary_info(regular_entry())
        self.assertEqual(info["subject_label"], "NAWI 1")

    def test_original_info_reads_subject_label(self) -> None:
        info = lesson_info.extract_original_info(cancelled_entry())
        self.assertEqual(info["subject_label"], "WU Klettern")

    def test_missing_label_stays_empty(self) -> None:
        entry = regular_entry()
        del entry["actualLesson"]["subjectLabel"]
        self.assertEqual(lesson_info.extract_primary_info(entry)["subject_label"], "")


class SubjectLabelExportTest(unittest.TestCase):
    def test_exported_lesson_has_subject_label(self) -> None:
        lesson = schedule_export.export_lesson(regular_entry())
        self.assertEqual(lesson["subject_label"], "NAWI 1")

    def test_exported_cancelled_lesson_keeps_original_label(self) -> None:
        lesson = schedule_export.export_lesson(cancelled_entry())
        self.assertEqual(lesson["subject"], "Smw")
        self.assertEqual(lesson["original"]["subject_label"], "WU Klettern")

    def test_exported_lesson_without_label_is_empty(self) -> None:
        entry = regular_entry()
        del entry["actualLesson"]["subjectLabel"]
        lesson = schedule_export.export_lesson(entry)
        self.assertEqual(lesson["subject_label"], "")


class SubjectLabelConsumerTest(unittest.TestCase):
    """Sensor attributes and structured changes consume the extracted label."""

    @staticmethod
    def _source(filename: str) -> str:
        return (COMPONENT / filename).read_text(encoding="utf-8")

    def test_schedule_sensor_attributes_include_label(self) -> None:
        source = self._source("sensor.py")
        self.assertIn('"subject_label": primary_info["subject_label"]', source)
        self.assertIn('"current_subject_label": None', source)

    def test_change_detection_includes_label(self) -> None:
        source = self._source("api_client.py")
        self.assertIn('change_info["subject_label"] = (', source)


if __name__ == "__main__":
    unittest.main()
