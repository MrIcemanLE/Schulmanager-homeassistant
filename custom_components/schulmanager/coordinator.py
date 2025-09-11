
"""Coordinator for Schulmanager client updates and cooldown management."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any, Iterator, Union

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import OPT_RANGE_FUTURE_DAYS, OPT_RANGE_PAST_DAYS
from .types import IntegrationData
from .utils import (
    CooldownManager,
    get_feature_config,
    get_validated_auto_update_interval,
)

_LOGGER = logging.getLogger(__name__)

class SchulmanagerCoordinator(DataUpdateCoordinator[IntegrationData]):
    """Coordinator for Schulmanager integration with cooldown support."""

    def __init__(self, hass: HomeAssistant, client: Any, config_entry: ConfigEntry) -> None:
        """Initialize the coordinator with cooldown tracking."""
        # Get the update interval from config, with validation
        interval_hours = get_validated_auto_update_interval(config_entry)
        interval_seconds = interval_hours * 3600  # Convert hours to seconds

        super().__init__(
            hass,
            _LOGGER,
            name="SchulmanagerCoordinator",
            update_interval=timedelta(seconds=interval_seconds),
            config_entry=config_entry,
        )
        self.client = client
        self.cooldown_manager = CooldownManager(config_entry)
        self._initial_refresh_done = False
        self._seen_homework: set[str] = set()
        self._seen_grades: set[str] = set()

        _LOGGER.info(
            "Schulmanager coordinator initialized with %d hour automatic update interval",
            interval_hours
        )

    async def _async_update_data(self) -> IntegrationData:
        """Update data from API with only enabled features to minimize server load."""
        # Get enabled features from config entry options
        if self.config_entry is None:
            raise HomeAssistantError("Config entry is not available")

        enabled_features = get_feature_config(self.config_entry)

        # Get date range configuration for exams
        options = dict(self.config_entry.options or {})
        date_range_config = {
            "past_days": int(options.get(OPT_RANGE_PAST_DAYS, 30)),
            "future_days": int(options.get(OPT_RANGE_FUTURE_DAYS, 180)),
        }

        _LOGGER.debug("Fetching data with features: %s and date range: %s", enabled_features, date_range_config)
        data = await self.client.async_update(enabled_features, date_range_config)

        # Detect new homework/grades after the first successful refresh only
        try:
            if self._initial_refresh_done:
                self._detect_and_fire_events(data)
            else:
                # Seed seen sets but do not fire on initial load
                self._seed_seen_sets(data)
                self._initial_refresh_done = True
        except Exception as err:  # noqa: BLE001 - defensive guard, do not break updates
            _LOGGER.debug("Event detection error: %s", err)

        return data

    def _seed_seen_sets(self, data: dict[str, Any]) -> None:
        for st in data.get("students", []):
            sid = st.get("id")
            if not sid:
                continue
            for item in data.get("homework", {}).get(sid, []) or []:
                key = self._homework_key(sid, item)
                if key:
                    self._seen_homework.add(key)
            grades = data.get("grades", {}).get(sid, {}) or {}
            for gkey in self._iter_grade_keys(sid, grades):
                self._seen_grades.add(gkey)

    def _detect_and_fire_events(self, data: dict[str, Any]) -> None:
        by_id = {str(s.get("id")): s.get("name") for s in data.get("students", [])}

        # Homework
        for sid, items in (data.get("homework", {}) or {}).items():
            for item in items or []:
                key = self._homework_key(sid, item)
                if not key or key in self._seen_homework:
                    continue
                self._seen_homework.add(key)
                self.hass.bus.async_fire(
                    "schulmanager_homework_new",
                    {
                        "student_id": sid,
                        "student_name": by_id.get(str(sid), ""),
                        "item": item,
                    },
                )

        # Grades
        for sid, grades in (data.get("grades", {}) or {}).items():
            for gkey, payload in self._iter_grade_keys(sid, grades, return_payload=True):
                if gkey in self._seen_grades:
                    continue
                self._seen_grades.add(gkey)
                self.hass.bus.async_fire(
                    "schulmanager_grade_new",
                    {
                        "student_id": sid,
                        "student_name": by_id.get(str(sid), ""),
                        "subject_id": payload.get("subject_id"),
                        "subject_name": payload.get("subject_name"),
                        "grade": payload.get("grade"),
                    },
                )

    def _homework_key(self, sid: str, item: dict[str, Any]) -> str | None:
        date = str(item.get("date") or "").strip()
        subject = str(item.get("subject") or "").strip()
        hw = str(item.get("homework") or "").strip()
        if not (date and (subject or hw)):
            return None
        return f"{sid}:{date}:{subject}:{hw}"

    def _iter_grade_keys(
        self, sid: str, grades: dict[str, Any], return_payload: bool = False
    ) -> Iterator[Union[str, tuple[str, dict[str, Any]]]]:
        subjects = grades.get("subjects", {}) or {}
        for subject_id, subject in subjects.items():
            subject_name = subject.get("name", f"Fach {subject_id}")
            for category, grades_list in (subject.get("grades") or {}).items():
                for g in grades_list or []:
                    orig = str(g.get("original_value", g.get("value", "")))
                    date = str(g.get("date", ""))
                    topic = str(g.get("topic", ""))
                    gkey = f"{sid}:{subject_id}:{category}:{date}:{orig}:{topic}"
                    if return_payload:
                        yield gkey, {
                            "subject_id": subject_id,
                            "subject_name": subject_name,
                            "grade": g,
                        }
                    else:
                        yield gkey

    def is_manual_refresh_allowed(self) -> bool:
        """Check if a manual refresh is allowed (not in cooldown)."""
        return self.cooldown_manager.can_refresh()

    def get_cooldown_remaining_seconds(self) -> int:
        """Get remaining cooldown time in seconds. Returns 0 if no cooldown active."""
        return self.cooldown_manager.get_remaining_cooldown()

    async def async_request_manual_refresh(self) -> None:
        """Request a manual refresh with cooldown enforcement."""
        if not self.is_manual_refresh_allowed():
            remaining = self.get_cooldown_remaining_seconds()
            raise HomeAssistantError(
                f"Manuelle Aktualisierung ist noch {remaining} Sekunden lang gesperrt. "
                f"Bitte warten Sie, bevor Sie erneut aktualisieren."
            )

        # Record the manual refresh time
        self.cooldown_manager.record_refresh()
        _LOGGER.info(
            "Manual refresh requested. Next manual refresh allowed in %d seconds.",
            self.cooldown_manager.get_remaining_cooldown()
        )

        # Perform the refresh
        await self.async_request_refresh()
