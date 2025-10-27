"""HTTP client and API helpers for Schulmanager Online service.

Note: Some broad exception handling is left intentionally due to the
variability of upstream responses. Where appropriate, we dump sanitized
payloads for diagnostics. Ruff warnings for BLE001/B904 can be tuned
later if we further constrain error types upstream.
"""

# ruff: noqa: BLE001, B904

from __future__ import annotations

from datetime import date, timedelta
import hashlib
import json
import logging
from pathlib import Path
import re
from typing import Any, cast

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .types import GradesPayload, ScheduleChange, SchedulePayload
from .utils import common_headers, ensure_authenticated, sanitize_for_log

LOGIN_URL = "https://login.schulmanager-online.de/api/login"
GET_SALT_URL = "https://login.schulmanager-online.de/api/get-salt"
CALLS_URL = "https://login.schulmanager-online.de/api/calls"
INDEX_URL = "https://login.schulmanager-online.de/"

_LOGGER = logging.getLogger(__name__)


class SchulmanagerClient:
    """Service client for communicating with Schulmanager Online."""

    def __init__(
        self,
        hass: HomeAssistant,
        username: str,
        password: str,
        debug_dumps: bool = False,
        institution_id: int | None = None,
    ) -> None:
        """Initialize the service client with credentials and HA context."""
        self.hass = hass
        self.username = username
        self.password = password
        self._token: str | None = None
        self._bundle_version: str | None = None
        self._students: list[dict[str, Any]] = []
        self._subjects_cache: dict[int, dict[str, Any]] = {}
        self.debug_dumps = debug_dumps
        self.data: dict[str, Any] | None = None
        self._institution_id: int | None = institution_id
        self._multiple_accounts: list[dict[str, Any]] | None = None

    async def _dump(self, name: str, data: Any) -> None:
        """Save debug data to file if debug dumps are enabled."""
        if not self.debug_dumps:
            return
        lname = name.lower()
        if "response" not in lname:
            return
        base = Path(self.hass.config.path("custom_components", "schulmanager", "debug"))
        file_path = base / name

        def _write() -> None:
            base.mkdir(parents=True, exist_ok=True)
            with file_path.open("w", encoding="utf-8") as f:
                json.dump(
                    {"fetched_at": dt_util.utcnow().isoformat(), "data": data},
                    f,
                    ensure_ascii=False,
                    indent=2,
                )

        await self.hass.async_add_executor_job(_write)

    # Public helpers to avoid private attribute access outside
    def get_students(self) -> list[dict[str, Any]]:
        """Return the discovered students for this account."""
        return list(self._students)

    def clear_auth_cache(self) -> None:
        """Clear cached authentication and bundle version."""
        self._token = None
        self._bundle_version = None

    def auth_token(self) -> str | None:
        """Return the current auth token if available."""
        return self._token

    def bundle_version(self) -> str | None:
        """Return the current bundle version if available."""
        return self._bundle_version

    async def async_discover_bundle_version(self) -> str | None:
        """Discover and cache bundle version if missing; return it."""
        if not self._bundle_version:
            self._bundle_version = await self._discover_bundle_version()
        return self._bundle_version

    async def async_dump(self, name: str, data: Any) -> None:
        """Public alias for debug dump to avoid private access in callers."""
        await self._dump(name, data)

    # Convenience helpers
    def has_token(self) -> bool:
        """Return True if an auth token is available."""
        return self._token is not None

    def has_bundle_version(self) -> bool:
        """Return True if bundle version is available."""
        return self._bundle_version is not None

    def get_institution_id(self) -> int | None:
        """Return the institution ID if available."""
        return self._institution_id

    def get_multiple_accounts(self) -> list[dict[str, Any]] | None:
        """Return multiple accounts if available from login response."""
        return getattr(self, "_multiple_accounts", None)

    async def _fetch_salt(self, email: str) -> str:
        """Fetch salt for password hashing."""
        sess = async_get_clientsession(self.hass)
        headers = common_headers() | {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json;charset=UTF-8",
        }
        payload = {"emailOrUsername": email, "userId": None, "institutionId": None}

        await self._dump(
            "get_salt_request.json",
            {
                "url": GET_SALT_URL,
                "headers": sanitize_for_log(headers),
                "payload": payload,
            },
        )

        async with sess.post(GET_SALT_URL, json=payload, headers=headers) as resp:
            text = await resp.text()
            try:
                salt = str(json.loads(text))
            except Exception:
                await self._dump(
                    "get_salt_response.json", {"status": resp.status, "raw": text[:500]}
                )
                raise RuntimeError(f"get_salt_failed:{resp.status}")

        await self._dump(
            "get_salt_response.json", {"status": 200, "salt_len": len(salt)}
        )
        return salt

    @staticmethod
    def _pbkdf2_hash_hex(password: str, salt_str: str) -> str:
        """Hash password using PBKDF2."""
        pw_bytes = password.encode("latin-1", errors="strict")
        salt_bytes = salt_str.encode("utf-8")
        dk = hashlib.pbkdf2_hmac("sha512", pw_bytes, salt_bytes, 99999, dklen=512)
        return dk.hex()

    async def async_login(self) -> None:
        """Login to Schulmanager Online."""
        sess = async_get_clientsession(self.hass)
        salt = await self._fetch_salt(self.username)
        hash_hex = self._pbkdf2_hash_hex(self.password, salt)

        headers = common_headers() | {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json;charset=UTF-8",
        }
        body = {
            "emailOrUsername": self.username,
            "password": self.password,
            "hash": hash_hex,
            "mobileApp": False,
            "userId": None,
            "twoFactorCode": None,
            "institutionId": self._institution_id,
        }

        await self._dump(
            "login_request.json",
            {
                "url": LOGIN_URL,
                "headers": sanitize_for_log(headers),
                "payload": sanitize_for_log(body),
            },
        )

        async with sess.post(LOGIN_URL, json=body, headers=headers) as resp:
            text = await resp.text()
            try:
                data = json.loads(text)
            except Exception:
                await self._dump(
                    "login_response.json", {"status": resp.status, "raw": text[:500]}
                )
                raise RuntimeError(f"login_failed:{resp.status}")

            await self._dump(
                "login_response.json",
                {"status": resp.status, "data": sanitize_for_log(data)},
            )

            if resp.status != 200:
                raise RuntimeError(f"login_failed:{resp.status}")

            # Check for multi-school accounts
            if "multipleAccounts" in data:
                self._multiple_accounts = data["multipleAccounts"]
                _LOGGER.debug(
                    "Multi-school account detected with %d schools",
                    len(self._multiple_accounts),
                )
                # Store but don't fail - caller must handle school selection
                return

            # Normal single-school login
            if "jwt" not in data:
                raise RuntimeError(f"login_failed:no_jwt:{resp.status}")

            self._token = data["jwt"]
            user = data.get("user") or {}

            # Extract and store institutionId if not already set
            if self._institution_id is None:
                self._institution_id = user.get("institutionId")
                if self._institution_id:
                    _LOGGER.debug("Extracted institutionId from login: %s", self._institution_id)

            parents = user.get("associatedParents") or []
            self._students = []

            for p in parents:
                st = (p or {}).get("student") or {}
                sid = st.get("id")
                if not sid:
                    continue
                name = (
                    f"{st.get('firstname', '')} {st.get('lastname', '')}".strip()
                    or "Schüler"
                )
                self._students.append(
                    {"id": str(sid), "classId": st.get("classId"), "name": name}
                )

            await self._dump("students_extracted.json", self._students)

    async def _discover_bundle_version(self) -> str | None:
        """Discover bundle version from JavaScript files."""
        if self._bundle_version:
            return self._bundle_version

        sess = async_get_clientsession(self.hass)
        headers_html = common_headers() | {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        scripts: list[str] = []
        async with sess.get(INDEX_URL, headers=headers_html) as resp:
            html = await resp.text()
            await self._dump(
                "index_meta.json", {"status": resp.status, "length": len(html)}
            )

            # Find script tags
            for m in re.finditer(
                r'<script[^>]+src=["\']([^"\']+\.js)[^>]*>', html, re.IGNORECASE
            ):
                src = m.group(1)
                if src.startswith("/"):
                    src = INDEX_URL.rstrip("/") + src
                elif src.startswith("http"):
                    pass
                else:
                    src = INDEX_URL + src.lstrip("./")
                scripts.append(src)

            # Find modulepreload links
            for m in re.finditer(
                r'<link[^>]+rel=["\']modulepreload["\'][^>]+href=["\']([^"\']+\.js)["\']',
                html,
                re.IGNORECASE,
            ):
                src = m.group(1)
                if src.startswith("/"):
                    src = INDEX_URL.rstrip("/") + src
                elif src.startswith("http"):
                    pass
                else:
                    src = INDEX_URL + src.lstrip("./")
                scripts.append(src)

        await self._dump("index_scripts.json", scripts)

        # Search patterns for bundle version
        literal_pat = re.compile(r'bundleVersion\s*:\s*["\']([a-f0-9]{10})["\']', re.IGNORECASE)
        ident_pat = re.compile(r"bundleVersion\s*:\s*([A-Za-z_$][\w$]*)")
        near_pat = re.compile(
            r'bundleVersion[\s\S]{0,120}?["\']([a-f0-9]{10})["\']', re.IGNORECASE
        )

        for url in scripts:
            try:
                async with sess.get(url, headers=common_headers()) as r2:
                    js = await r2.text()

                # Try literal pattern
                m_lit = literal_pat.search(js)
                if m_lit:
                    val = m_lit.group(1)
                    self._bundle_version = val
                    await self._dump(
                        "script_probe_hit.json",
                        {"url": url, "mode": "literal", "value": val},
                    )
                    return val

                # Try identifier pattern
                m_ident = ident_pat.search(js)
                if m_ident:
                    ident = m_ident.group(1)
                    def_pat = re.compile(
                        rf'\b(?:const|let|var)\s+{re.escape(ident)}\s*=\s*["\']([a-f0-9]{{10}})["\']'
                    )
                    m_def = def_pat.search(js)
                    if m_def:
                        val = m_def.group(1)
                        self._bundle_version = val
                        await self._dump(
                            "script_probe_hit.json",
                            {"url": url, "mode": f"ident:{ident}", "value": val},
                        )
                        return val

                # Try near pattern
                m_near = near_pat.search(js)
                if m_near:
                    val = m_near.group(1)
                    self._bundle_version = val
                    await self._dump(
                        "script_probe_hit.json",
                        {"url": url, "mode": "near", "value": val},
                    )
                    return val

                await self._dump("script_probe_no_value.json", {"url": url})
            except Exception as e:
                _LOGGER.debug("Error processing script %s: %s", url, e)
                continue

        return None

    async def _api_call(
        self, module: str, endpoint: str, parameters: dict, tag: str
    ) -> Any:
        """Make API call to Schulmanager."""
        await ensure_authenticated(self)

        headers = common_headers() | {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {self._token}",
        }

        payload: dict[str, Any] = {
            "requests": [
                {
                    "moduleName": module,
                    "endpointName": endpoint,
                    "parameters": parameters,
                }
            ]
        }

        if self._bundle_version:
            payload["bundleVersion"] = self._bundle_version

        await self._dump(
            f"calls_request_{tag}.json",
            {"headers": sanitize_for_log(headers), "payload": payload},
        )

        sess = async_get_clientsession(self.hass)
        async with sess.post(CALLS_URL, json=payload, headers=headers) as resp:
            status = resp.status
            text = await resp.text()
            try:
                data = json.loads(text)
            except Exception:
                data = {
                    "raw_text": text[:500],
                    "content_type": resp.headers.get("Content-Type"),
                }

            await self._dump(
                f"calls_response_{tag}.json",
                {"status": status, "headers": dict(resp.headers), "body": data},
            )

            if status != 200:
                # Log more details for debugging
                _LOGGER.warning(
                    "API call failed: %s/%s -> %s, Response: %s",
                    module,
                    endpoint,
                    status,
                    data,
                )
                raise RuntimeError(f"/api/calls {module}/{endpoint} -> {status}")

            results = data.get("results") or []
            if not results:
                _LOGGER.warning(
                    "No results in API response for %s/%s", module, endpoint
                )
                return []

            result = results[0]

            # Check if the individual request failed (status 500, etc.)
            if isinstance(result, dict) and "status" in result:
                if result["status"] != 200:
                    _LOGGER.warning(
                        "API request failed: %s/%s -> status %s, id: %s",
                        module,
                        endpoint,
                        result.get("status"),
                        result.get("id"),
                    )
                    return []

            return (
                result.get("data", [])
                if isinstance(result, dict) and "data" in result
                else data
            )

    async def fetch_homework(self, student_id: str) -> list[dict]:
        """Fetch homework for a student."""
        params = {"student": {"id": int(student_id)}}
        data = await self._api_call(
            "classbook",
            "get-homework",
            params,
            f"homework_{student_id}_classbook_get-homework",
        )
        await self._dump(f"hausaufgaben_{student_id}.json", data)
        return data if isinstance(data, list) else []

    async def fetch_exams(
        self, student_id: str, class_id: int | None = None, date_range_config: dict[str, int] | None = None
    ) -> list[dict]:
        """Fetch exams for a student using the proper exams API with user-configured date range."""
        # Get student info for complete API call
        student_info = None
        for student in self._students:
            if student["id"] == student_id:
                student_info = student
                break

        if not student_info:
            _LOGGER.warning("Student info not found for ID %s", student_id)
            return []

        # Get bundle version
        bundle_version = await self._discover_bundle_version()
        if not bundle_version:
            raise RuntimeError("Could not discover bundle version")

        # Calculate date range based on user preferences
        today = dt_util.now().date()
        if date_range_config:
            past_days = date_range_config.get("past_days", 30)
            future_days = date_range_config.get("future_days", 180)
            start_date = today - timedelta(days=past_days)
            end_date = today + timedelta(days=future_days)
            _LOGGER.debug("Using user-configured date range for exams: %s to %s (%d past days, %d future days)",
                         start_date.isoformat(), end_date.isoformat(), past_days, future_days)
        else:
            # Default fallback to current week if no config provided
            start_date = today - timedelta(days=today.weekday())
            end_date = start_date + timedelta(days=6)
            _LOGGER.debug("Using default current week range for exams: %s to %s",
                         start_date.isoformat(), end_date.isoformat())

        # Prepare student object as required by API
        student_obj = {
            "id": int(student_id),
            "firstname": student_info["name"].split()[0] if student_info["name"] else "",
            "lastname": " ".join(student_info["name"].split()[1:]) if len(student_info["name"].split()) > 1 else "",
            "sex": "Male",  # Default for now, could be enhanced
            "classId": student_info.get("classId", 0)
        }

        # Create request payload using the proper exams API
        batch_payload = {
            "bundleVersion": bundle_version,
            "requests": [
                {
                    "moduleName": "exams",
                    "endpointName": "get-exams",
                    "parameters": {
                        "student": student_obj,
                        "start": start_date.isoformat(),
                        "end": end_date.isoformat()
                    }
                }
            ]
        }

        # Make API call
        sess = async_get_clientsession(self.hass)
        headers = common_headers() | {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {self._token}",
        }

        await self._dump(f"exams_request_{student_id}.json", batch_payload)

        async with sess.post(CALLS_URL, json=batch_payload, headers=headers) as resp:
            if resp.status != 200:
                _LOGGER.error("Exams API call failed with status %s", resp.status)
                return []

            response_data = await resp.json()
            await self._dump(f"exams_response_{student_id}.json", {
                "status": resp.status,
                "data": response_data
            })

            # Parse response
            results = response_data.get("results", [])
            for result in results:
                if result.get("status") == 200 and "data" in result:
                    exams = result["data"]
                    if isinstance(exams, list):
                        _LOGGER.debug("Found %d exams for student %s", len(exams), student_id)
                        return exams

            _LOGGER.debug("No exams found for student %s", student_id)
            return []



    async def fetch_schedule_today_tomorrow(
        self, student_id: str, class_id: int | None = None, weeks: int = 2
    ) -> SchedulePayload:
        """Optimized schedule fetching using bundle version and browser API calls."""
        return await self._fetch_schedule_optimized(student_id, weeks)

    async def _fetch_schedule_optimized(self, student_id: str, weeks: int = 2) -> SchedulePayload:
        """Optimized schedule fetching using exact browser API call pattern."""
        sid = int(student_id)
        today = dt_util.now().date()

        # Get student info for complete API call
        student_info = None
        for student in self._students:
            if student["id"] == student_id:
                student_info = student
                break

        if not student_info:
            _LOGGER.warning("Student info not found for ID %s", student_id)
            return {
                "today": [],
                "tomorrow": [],
                "week": {},
                "changes": {"today": [], "tomorrow": [], "summary": "Keine Stundenplanänderungen für heute und morgen"},
            }

        # Get bundle version
        bundle_version = await self._discover_bundle_version()
        if not bundle_version:
            raise RuntimeError("Could not discover bundle version")

        # Calculate range: current week plus N-1 upcoming weeks
        start_of_week = today - timedelta(days=today.weekday())
        weeks = max(weeks, 1)
        weeks = min(weeks, 3)
        end_of_range = start_of_week + timedelta(days=(7 * weeks) - 1)

        # Create request payload exactly like the browser
        batch_payload = {
            "bundleVersion": bundle_version,
            "requests": [
                {
                    "moduleName": "schedules",
                    "endpointName": "get-actual-lessons",
                    "parameters": {
                        "student": {
                            "id": sid,
                            "firstname": (
                                student_info["name"].split()[0]
                                if student_info["name"]
                                else ""
                            ),
                            "lastname": (
                                " ".join(student_info["name"].split()[1:])
                                if len(student_info["name"].split()) > 1
                                else ""
                            ),
                            "classId": student_info.get("classId"),
                            "class": {
                                "id": student_info.get("classId"),
                                "name": None,  # We don't have class name
                                "gradeLevels": None,
                                "isCourseSystem": None
                            }
                        },
                        "start": start_of_week.isoformat(),
                        "end": end_of_range.isoformat()
                    }
                }
            ]
        }

        # Make single batch API call
        sess = async_get_clientsession(self.hass)
        headers = common_headers() | {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {self._token}",
        }

        await self._dump(f"schedule_batch_request_{sid}.json", batch_payload)

        async with sess.post(CALLS_URL, json=batch_payload, headers=headers) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Batch API call failed with status {resp.status}")

            response_data = await resp.json()
            await self._dump(f"schedule_batch_response_{sid}.json", {
                "status": resp.status,
                "data": response_data
            })

            # Parse batch response
            return self._parse_batch_schedule_response(response_data, today)

    def _parse_batch_schedule_response(
        self, response_data: dict[str, Any], reference_date: date
    ) -> SchedulePayload:
        """Parse batch response from optimized get-actual-lessons call."""
        today_iso = reference_date.isoformat()
        tomorrow_iso = (reference_date + timedelta(days=1)).isoformat()

        tlist: list[dict[str, Any]] = []
        nlist: list[dict[str, Any]] = []
        week_map: dict[str, list[dict[str, Any]]] = {}
        changes_today: list[ScheduleChange] = []
        changes_tomorrow: list[ScheduleChange] = []

        # Process results from batch response
        results = response_data.get("results", [])
        for result in results:
            if result.get("status") == 200 and "data" in result:
                lessons = result["data"]

                # Handle lessons array directly
                if isinstance(lessons, list):
                    for lesson in lessons:
                        if not isinstance(lesson, dict):
                            continue

                        # Extract lesson date (could be in different formats)
                        lesson_date = None
                        for date_field in ["date", "start", "day"]:
                            if date_field in lesson:
                                lesson_date_str = lesson[date_field]
                                if isinstance(lesson_date_str, str):
                                    lesson_date = lesson_date_str[
                                        :10
                                    ]  # Extract YYYY-MM-DD
                                    break

                        # Group by date for calendar usage
                        if lesson_date:
                            week_map.setdefault(lesson_date, []).append(lesson)

                        if lesson_date == today_iso:
                            tlist.append(lesson)
                            # Check for changes and add to structured changes
                            change = self._detect_lesson_change(lesson)
                            if change:
                                changes_today.append(change)
                        elif lesson_date == tomorrow_iso:
                            nlist.append(lesson)
                            # Check for changes and add to structured changes
                            change = self._detect_lesson_change(lesson)
                            if change:
                                changes_tomorrow.append(change)

        return {
            "today": tlist,
            "tomorrow": nlist,
            "week": week_map,
            "changes": {
                "today": changes_today,
                "tomorrow": changes_tomorrow,
                "summary": self._generate_changes_summary(changes_today, changes_tomorrow)
            }
        }


    def _parse_schedule_data(self, data: Any, reference_date: date) -> SchedulePayload:
        """Parse verschiedene Datenformate für Stundenpläne."""
        today_iso = reference_date.isoformat()
        tomorrow_iso = (reference_date + timedelta(days=1)).isoformat()

        tlist: list[dict[str, Any]] = []
        nlist: list[dict[str, Any]] = []
        week_map: dict[str, list[dict[str, Any]]] = {}

        # Handle verschiedene Datenstrukturen
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            # Verschiedene Schlüssel probieren
            items = (
                data.get("lessons")
                or data.get("data")
                or data.get("schedule")
                or data.get("timetable")
                or []
            )
        else:
            return {
                "today": [],
                "tomorrow": [],
                "week": {},
                "changes": {"today": [], "tomorrow": [], "summary": "Keine Stundenplanänderungen für heute und morgen"},
            }

        for it in items:
            if not isinstance(it, dict):
                continue

            # Verschiedene Datumsformate probieren
            date_str = None
            for date_field in ["date", "day", "start"]:
                if date_field in it:
                    date_val = it[date_field]
                    if isinstance(date_val, str):
                        date_str = date_val[:10]  # Ersten 10 Zeichen (YYYY-MM-DD)
                        break

            if not date_str:
                continue

            # Fill week map for calendar usage
            week_map.setdefault(date_str, []).append(it)

            if date_str == today_iso:
                tlist.append(it)
            elif date_str == tomorrow_iso:
                nlist.append(it)

        return {
            "today": tlist,
            "tomorrow": nlist,
            "week": week_map,
            "changes": {
                "today": [],
                "tomorrow": [],
                "summary": "Keine Stundenplanänderungen für heute und morgen"
            }
        }

    def _detect_lesson_change(self, lesson: dict[str, Any]) -> ScheduleChange | None:
        """Detect if a lesson represents a schedule change and structure it for LLM processing."""
        lesson_type = lesson.get("type", "")
        actual_lesson = lesson.get("actualLesson", {})

        # Different lesson types that indicate changes (German translations)
        change_types = {
            "substitution": "Vertretung",
            "cancelledLesson": "Entfall",
            "specialLesson": "Sonderstunde",
            "roomChange": "Raumänderung",
            "teacherChange": "Lehrervertretung",
            "irregularLesson": "Unregelmäßige Stunde",
            "exam": "Prüfung",
            "event": "Veranstaltung"
        }

        # Basic change detection - this can be enhanced with more sophisticated logic
        change_info: ScheduleChange | None = None

        if lesson_type != "regularLesson":
            # Non-regular lessons are potential changes
            change_info = {
                "type": change_types.get(lesson_type, lesson_type),
                "hour": lesson.get("classHour", {}).get("number", "?"),
                "date": lesson.get("date", ""),
                "original_subject": "",
                "new_subject": "",
                "original_teacher": "",
                "new_teacher": "",
                "original_room": "",
                "new_room": "",
                "reason": lesson.get("substitutionText", ""),
                "note": lesson.get("comment", "")
            }

            # For cancelled lessons, get original lesson info
            if lesson_type == "cancelledLesson" and "originalLessons" in lesson:
                original_lessons = lesson.get("originalLessons", [])
                if original_lessons:
                    original = original_lessons[0]  # Take first original lesson
                    change_info["original_subject"] = original.get("subject", {}).get("abbreviation", "")
                    original_teachers = original.get("teachers", [])
                    if original_teachers:
                        change_info["original_teacher"] = original_teachers[0].get("abbreviation", "")
                    change_info["original_room"] = original.get("room", {}).get("name", "")

            # For special/substitute lessons, get new lesson info
            if actual_lesson:
                change_info["new_subject"] = actual_lesson.get("subject", {}).get("abbreviation", "")
                new_teachers = actual_lesson.get("teachers", [])
                if new_teachers:
                    change_info["new_teacher"] = new_teachers[0].get("abbreviation", "")
                change_info["new_room"] = actual_lesson.get("room", {}).get("name", "")

        # Check for room changes within regular lessons (if room seems unusual)
        # This could be enhanced with baseline data comparison in the future

        return change_info

    def _generate_changes_summary(self, today_changes: list, tomorrow_changes: list) -> str:
        """Generate a structured summary of changes for LLM processing in German."""
        if not today_changes and not tomorrow_changes:
            return "Keine Stundenplanänderungen für heute und morgen"

        summary_parts = []

        if today_changes:
            count_text = "Änderung" if len(today_changes) == 1 else "Änderungen"
            summary_parts.append(f"Heute ({len(today_changes)} {count_text}):")
            for change in today_changes:
                hour = change.get("hour", "?")
                change_type = change.get("type", "Unbekannt")
                original_subject = change.get("original_subject", "")
                new_subject = change.get("new_subject", "")
                original_teacher = change.get("original_teacher", "")
                new_teacher = change.get("new_teacher", "")
                new_room = change.get("new_room", "")
                reason = change.get("reason", "")

                change_desc = f"  {hour}. Stunde: {change_type}"

                # Format based on change type
                if change_type == "Entfall" and original_subject:
                    change_desc += f" - {original_subject} entfällt"
                    if original_teacher:
                        change_desc += f" ({original_teacher})"
                elif change_type == "Sonderstunde" and new_subject:
                    change_desc += f" - {new_subject}"
                    if new_teacher:
                        change_desc += f" ({new_teacher})"
                    if new_room:
                        change_desc += f" in Raum {new_room}"
                else:
                    # Generic format
                    if new_subject:
                        change_desc += f" - {new_subject}"
                    if new_teacher:
                        change_desc += f" ({new_teacher})"
                    if new_room:
                        change_desc += f" in Raum {new_room}"

                if reason:
                    change_desc += f" - {reason}"

                summary_parts.append(change_desc)

        if tomorrow_changes:
            count_text = "Änderung" if len(tomorrow_changes) == 1 else "Änderungen"
            summary_parts.append(f"Morgen ({len(tomorrow_changes)} {count_text}):")
            for change in tomorrow_changes:
                hour = change.get("hour", "?")
                change_type = change.get("type", "Unbekannt")
                original_subject = change.get("original_subject", "")
                new_subject = change.get("new_subject", "")
                original_teacher = change.get("original_teacher", "")
                new_teacher = change.get("new_teacher", "")
                new_room = change.get("new_room", "")
                reason = change.get("reason", "")

                change_desc = f"  {hour}. Stunde: {change_type}"

                # Format based on change type
                if change_type == "Entfall" and original_subject:
                    change_desc += f" - {original_subject} entfällt"
                    if original_teacher:
                        change_desc += f" ({original_teacher})"
                elif change_type == "Sonderstunde" and new_subject:
                    change_desc += f" - {new_subject}"
                    if new_teacher:
                        change_desc += f" ({new_teacher})"
                    if new_room:
                        change_desc += f" in Raum {new_room}"
                else:
                    # Generic format
                    if new_subject:
                        change_desc += f" - {new_subject}"
                    if new_teacher:
                        change_desc += f" ({new_teacher})"
                    if new_room:
                        change_desc += f" in Raum {new_room}"

                if reason:
                    change_desc += f" - {reason}"

                summary_parts.append(change_desc)

        return "\n".join(summary_parts)

    async def _fetch_subjects(self) -> dict[int, dict[str, Any]]:
        """Fetch subject mappings from the API and cache them."""
        if self._subjects_cache:
            return self._subjects_cache

        await ensure_authenticated(self)

        request_data = {
            "bundleVersion": self._bundle_version or "7aa63feca5",
            "requests": [{
                "moduleName": "grades",
                "endpointName": "poqa",
                "parameters": {
                    "action": {
                        "model": "main/subject",
                        "action": "findAll",
                        "parameters": [{
                            "attributes": ["id", "name", "abbreviation", "orderIndex", "officialKey"]
                        }]
                    },
                    "uiState": "main.modules.grades.student"
                }
            }]
        }

        session = async_get_clientsession(self.hass)
        headers = common_headers()
        headers["Authorization"] = f"Bearer {self._token}"
        headers["Content-Type"] = "application/json"

        try:
            async with session.post(
                CALLS_URL,
                json=request_data,
                headers=headers,
            ) as response:
                if response.status != 200:
                    _LOGGER.error("Failed to fetch subjects: HTTP %d", response.status)
                    return {}

                data = await response.json()
                await self._dump("subjects_response", data)

                results = data.get("results", [])
                if not results:
                    _LOGGER.warning("No results in subjects response")
                    return {}

                result = results[0]
                if result.get("status") != 200:
                    _LOGGER.error("API error fetching subjects: %s", result)
                    return {}

                subjects_list = result.get("data", [])
                subjects_cache = {}

                for subject in subjects_list:
                    subject_id = subject.get("id")
                    if subject_id:
                        subjects_cache[subject_id] = {
                            "name": subject.get("name", f"Fach {subject_id}"),
                            "abbreviation": subject.get("abbreviation", f"F{subject_id}"),
                            "officialKey": subject.get("officialKey"),
                            "orderIndex": subject.get("orderIndex")
                        }

                self._subjects_cache = subjects_cache
                _LOGGER.debug("Cached %d subjects", len(subjects_cache))
                return subjects_cache

        except Exception as err:
            _LOGGER.error("Exception fetching subjects: %s", err)
            return {}

    async def _derive_subject_info(self, course_name: str, subject_id: int) -> tuple[str, str]:
        """Derive human-readable subject name and abbreviation using API data."""
        # First try to get from API cache
        subjects_cache = await self._fetch_subjects()

        if subject_id in subjects_cache:
            subject_data = subjects_cache[subject_id]
            name = subject_data["name"]
            abbreviation = subject_data["abbreviation"]

            # Use the API data
            return name, abbreviation

        # Fallback to course name if API data unavailable
        if course_name:
            return course_name, course_name[:3].upper()

        # Last resort: create a generic name
        return f"Fach {subject_id}", f"F{str(subject_id)[-2:]}"

    def _parse_german_grade(self, grade_value: str | float) -> float | None:
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
                # Treat both 4+ and 4- as 4.0 (ignore plus/minus for simplicity)
                return float(grade_str[:-1])
            except ValueError:
                return None

        # Handle decimal grades like "2.5", "3.7"
        try:
            return float(grade_str)
        except ValueError:
            return None

    def _calculate_subject_average(self, grade_categories: dict[str, list[dict[str, Any]]]) -> float | None:
        """Calculate simple average of all grades in a subject."""
        if not grade_categories:
            return None

        all_grades = []

        # Collect all numeric grades from all categories
        for grades_list in grade_categories.values():
            if not grades_list:
                continue

            for grade in grades_list:
                grade_value = grade.get("value", "")

                # Extract numeric value from German grade format
                numeric_grade = self._parse_german_grade(grade_value)

                # Validate German grade range (1.0 - 6.0)
                if numeric_grade is not None and 1.0 <= numeric_grade <= 6.0:
                    all_grades.append(numeric_grade)

        if not all_grades:
            return None

        # Calculate simple average and round to 2 decimal places
        average = sum(all_grades) / len(all_grades)
        return round(average, 2)

    async def fetch_grades(self, student_id: str, class_id: int | None = None) -> GradesPayload:
        """Fetch grades for a student using the proper grades API."""
        sid = int(student_id)

        # Get bundle version
        bundle_version = await self._discover_bundle_version()
        if not bundle_version:
            raise RuntimeError("Could not discover bundle version")

        # Calculate full academic year range (August to July)
        today = dt_util.now().date()
        if today.month >= 8:
            # Current school year: August YYYY to July YYYY+1
            start_date = today.replace(month=8, day=1)
            end_date = today.replace(year=today.year + 1, month=7, day=31)
        else:
            # Previous school year: August YYYY-1 to July YYYY
            start_date = today.replace(year=today.year - 1, month=8, day=1)
            end_date = today.replace(month=7, day=31)

        # For now, we'll use a fixed termId - this might need to be discovered
        # Based on the API response, termId seems to be related to the school term
        term_id = 28592  # This should ideally be discovered from the API

        # Create request payload exactly like the browser
        grades_payload = {
            "bundleVersion": bundle_version,
            "requests": [
                {
                    "moduleName": "grades",
                    "endpointName": "get-grading-information-for-student",
                    "parameters": {
                        "studentId": sid,
                        "termId": term_id,
                        "start": start_date.isoformat(),
                        "end": end_date.isoformat(),
                        "gradingPeriodType": "entireYear"
                    }
                }
            ]
        }

        sess = async_get_clientsession(self.hass)
        headers = common_headers() | {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._token}",
        }

        _LOGGER.debug("Fetching grades for student %s (term %s)", student_id, term_id)

        async with sess.post(CALLS_URL, json=grades_payload, headers=headers) as response:
            if response.status != 200:
                _LOGGER.error("Grades fetch failed with status %d", response.status)
                return {
                    "subjects": {},
                    "overall_average": None,
                    "total_subjects": 0,
                    "subjects_with_grades": 0,
                }

            response_data = await response.json()
            await self._dump(f"grades_response_{student_id}.json", response_data)

            # Parse response
            results = response_data.get("results", [])
            for result in results:
                if result.get("status") == 200 and "data" in result:
                    grades_data = result["data"]
                    return await self._process_grades_data(grades_data)

            _LOGGER.debug("No grades found for student %s", student_id)
            return {
                "subjects": {},
                "overall_average": None,
                "total_subjects": 0,
                "subjects_with_grades": 0,
            }

    async def _process_grades_data(self, grades_data: dict) -> GradesPayload:
        """Process raw grades data into structured format by subject."""
        courses: list[dict[str, Any]] = grades_data.get("courses", [])
        grading_events: list[dict[str, Any]] = grades_data.get("gradingEvents", [])
        type_presets: list[dict[str, Any]] = grades_data.get("typePresets", [])

        # Create mapping from course ID to course info
        course_map: dict[int, dict[str, Any]] = {
            int(course["id"]): course for course in courses if "id" in course
        }

        # Create mapping from gradeTypeId to type info
        type_map: dict[int, dict[str, Any]] = {}
        for preset in type_presets:
            if "gradeType" in preset:
                grade_type = preset["gradeType"]
                type_map[grade_type["id"]] = grade_type

        # Group grades by subject using subjectId as the key
        subjects: dict[int, dict[str, Any]] = {}
        subject_info: dict[int, tuple[str, str]] = {}  # subjectId -> (name, abbr)

        # Create human-readable subject names and abbreviations from course data
        for course in courses:
            subject_id = course.get("subjectId")
            if not subject_id:
                continue

            # Try to derive subject name and abbreviation from course name patterns
            course_name = course.get("name", "")
            subject_name, subject_abbrev = await self._derive_subject_info(course_name, subject_id)

            if subject_id not in subject_info or (course_name and len(course_name) > 3):
                subject_info[subject_id] = (subject_name, subject_abbrev)

        # Process grading events (actual grades)
        for event in grading_events:
            course_id = event.get("courseId")
            if course_id not in course_map:
                continue

            course = course_map[course_id]
            subject_id = course.get("subjectId")
            if not subject_id:
                continue

            # Initialize subject if not exists
            if subject_id not in subjects:
                # Get readable subject name and abbreviation
                subject_name, subject_abbrev = subject_info.get(subject_id, (f"Fach {subject_id}", f"F{subject_id}"))

                subjects[subject_id] = {
                    "name": subject_name,
                    "abbreviation": subject_abbrev,
                    "average": None,  # No average provided in API, would need calculation
                    "grades": {}
                }

            # Process grades in this event
            for grade_data in event.get("grades", []):
                grade_value = grade_data.get("value")
                if not grade_value:
                    continue

                # Get grade type info
                grade_type_id = event.get("gradeTypeId")
                grade_type_info = type_map.get(grade_type_id if isinstance(grade_type_id, int) else -1, {})
                grade_type_name = grade_type_info.get("name", "Sonstige")

                # Create grade entry
                # Normalize grade value: map formats like "0~2" -> 2.0, "4+" -> 4.0
                parsed_value = self._parse_german_grade(grade_value)
                tendency = None
                if isinstance(grade_value, str):
                    if grade_value.endswith("+"):
                        tendency = "plus"
                    elif grade_value.endswith("-"):
                        tendency = "minus"

                grade_entry = {
                    # Store normalized numeric where possible
                    "value": parsed_value if parsed_value is not None else grade_value,
                    "original_value": grade_value,
                    "tendency": tendency,
                    "date": event.get("date"),
                    "topic": event.get("topic", ""),
                    "weighting": event.get("weighting", 1),
                    "duration": event.get("durationInMinutes"),
                    "type_abbreviation": grade_type_info.get("abbreviation", ""),
                    "is_repeat_exam": grade_data.get("isRepeatExam", False),
                }

                # Add to appropriate category (only create categories that have grades)
                if grade_type_name not in subjects[subject_id]["grades"]:
                    subjects[subject_id]["grades"][grade_type_name] = []
                subjects[subject_id]["grades"][grade_type_name].append(grade_entry)

        # Calculate averages for each subject
        all_subject_averages: list[float] = []
        for subject_data in subjects.values():
            avg = self._calculate_subject_average(subject_data["grades"])
            subject_data["average"] = avg
            if avg is not None:
                all_subject_averages.append(avg)

        # Calculate overall student average from all subject averages
        overall_average = None
        if all_subject_averages:
            overall_average = round(sum(all_subject_averages) / len(all_subject_averages), 2)

        return cast(
            GradesPayload,
            {
                "subjects": subjects,
                "overall_average": overall_average,
                "total_subjects": len(subjects),
                "subjects_with_grades": len(all_subject_averages),
            },
        )

    async def async_update(self, enabled_features: dict[str, bool] | None = None, date_range_config: dict[str, int] | None = None) -> dict[str, Any]:
        """Pull latest data for all students and return structured dict with optional feature filtering."""
        # Make sure logged in and bundle known
        if not self._token:
            await self.async_login()
        if not self._bundle_version:
            await self._discover_bundle_version()

        # Default to all enabled if no preferences provided
        if enabled_features is None:
            enabled_features = {
                "homework": True,
                "schedule": True,
                "exams": True,
                "grades": True,
            }

        result: dict[str, Any] = {
            "students": list(self._students),
            "homework": {},
            "schedule": {},
            "exams": {},
            "grades": {},
        }

        # Fetch per student only for enabled features
        for st in self._students:
            sid = st["id"]
            cid = st.get("classId")

            # Only fetch homework if enabled
            if enabled_features.get("homework", True):
                try:
                    hw = await self.fetch_homework(sid)
                    result["homework"][sid] = hw
                except Exception as err:
                    _LOGGER.warning(
                        "Schulmanager: homework fetch failed for %s: %s", sid, err
                    )
                    result["homework"][sid] = []
            else:
                result["homework"][sid] = []

            # Only fetch schedule if enabled
            if enabled_features.get("schedule", True):
                try:
                    # Use weeks parameter if provided via date_range_config under key 'schedule_weeks'
                    weeks = 2
                    try:
                        weeks = int((date_range_config or {}).get("schedule_weeks", 2))
                    except Exception:
                        weeks = 2
                    sch = await self.fetch_schedule_today_tomorrow(sid, cid, weeks)
                    result["schedule"][sid] = sch
                except Exception as err:
                    _LOGGER.warning(
                        "Schulmanager: schedule fetch failed for %s: %s", sid, err
                    )
                    result["schedule"][sid] = {
                        "today": [],
                        "tomorrow": [],
                        "week": {},
                        "changes": {
                            "today": [],
                            "tomorrow": [],
                            "summary": "Keine Stundenplanänderungen für heute und morgen",
                        },
                    }
            else:
                result["schedule"][sid] = {
                    "today": [],
                    "tomorrow": [],
                    "week": {},
                    "changes": {
                        "today": [],
                        "tomorrow": [],
                        "summary": "Keine Stundenplanänderungen für heute und morgen",
                    },
                }

            # Only fetch exams if enabled
            if enabled_features.get("exams", True):
                try:
                    ex = await self.fetch_exams(sid, cid, date_range_config)
                    result["exams"][sid] = ex
                except Exception as err:
                    _LOGGER.warning("Schulmanager: exams fetch failed for %s: %s", sid, err)
                    result["exams"][sid] = []
            else:
                result["exams"][sid] = []

            # Only fetch grades if enabled
            if enabled_features.get("grades", True):
                try:
                    grades = await self.fetch_grades(sid, cid)
                    result["grades"][sid] = grades
                except Exception as err:
                    _LOGGER.warning("Schulmanager: grades fetch failed for %s: %s", sid, err)
                    result["grades"][sid] = {"subjects": {}}
            else:
                result["grades"][sid] = {"subjects": {}}

        # Save for other platforms
        self.data = result
        # Optional dump
        await self._dump("hub_data.json", result)
        return result
