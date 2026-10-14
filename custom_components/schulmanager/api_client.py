"""HTTP client and API helpers for Schulmanager Online service.

Note: Some broad exception handling is left intentionally due to the
variability of upstream responses. Where appropriate, we dump sanitized
payloads for diagnostics. Ruff warnings for BLE001/B904 can be tuned
later if we further constrain error types upstream.
"""

# ruff: noqa: BLE001, B904

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import date, timedelta
import hashlib
import json
import logging
from pathlib import Path
import re
from typing import Any, Final, cast

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from . import grading
from .lesson_info import extract_original_info
from .types import GradesPayload, ScheduleChange, SchedulePayload
from .utils import common_headers, ensure_authenticated, sanitize_for_log

LOGIN_URL = "https://login.schulmanager-online.de/api/login"
GET_SALT_URL = "https://login.schulmanager-online.de/api/get-salt"
CALLS_URL = "https://login.schulmanager-online.de/api/calls"
INDEX_URL = "https://login.schulmanager-online.de/"

# Pre-fix hardcoded termId for grades requests. The grades endpoint is the
# only one in this API that ever needed a termId; every other endpoint
# (homework, exams, schedule) works from start/end dates alone. Kept only
# as a last-resort fallback if omitting termId stops working.
LEGACY_TERM_ID: Final = 28592

_LOGGER = logging.getLogger(__name__)


class ModuleUnavailableError(RuntimeError):
    """The school has not enabled a portal module (e.g. messenger) for this account."""


class SchulmanagerClient:
    """Service client for communicating with Schulmanager Online."""

    def __init__(
        self,
        hass: HomeAssistant,
        username: str,
        password: str,
        debug_dumps: bool = False,
        institution_id: int | None = None,
        user_id: int | None = None,
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
        self._user_id: int | None = user_id
        self._multiple_accounts: list[dict[str, Any]] | None = None
        # Optional modules that answered 403; not requested again until reload
        self._unavailable_modules: set[str] = set()

    async def _dump(self, name: str, data: Any) -> None:
        """Save debug data to file if debug dumps are enabled."""
        if not self.debug_dumps:
            return
        lname = name.lower()
        if "response" not in lname:
            return
        base = Path(self.hass.config.path("custom_components", "schulmanager", "debug"))
        if self._institution_id is not None:
            base = base / f"school_{self._institution_id}"
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

    @staticmethod
    def _student_from_record(record: dict[str, Any]) -> dict[str, Any] | None:
        """Build a student dict from a raw student record, or None if unusable."""
        sid = record.get("id")
        if not sid:
            return None
        name = (
            f"{record.get('firstname', '')} {record.get('lastname', '')}".strip()
            or "Schüler"
        )
        return {"id": str(sid), "classId": record.get("classId"), "name": name}

    @classmethod
    def _extract_students(cls, user: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract students from a login response's user object.

        Parent accounts list their children under "associatedParents". Student
        accounts have no parents module, so their own record lives directly on
        the user object instead - either as a singular "associatedStudent"
        dict, or (for some school configurations) a plural
        "associatedStudents" list.
        """
        students: list[dict[str, Any]] = []

        for p in user.get("associatedParents") or []:
            st = (p or {}).get("student") or {}
            student = cls._student_from_record(st)
            if student is not None:
                students.append(student)

        if not students:
            student_records: list[dict[str, Any]] = []
            single = user.get("associatedStudent")
            if isinstance(single, dict):
                student_records.append(single)
            student_records.extend(
                record
                for record in user.get("associatedStudents") or []
                if isinstance(record, dict)
            )

            for record in student_records:
                student = cls._student_from_record(record)
                if student is not None:
                    students.append(student)

        return students

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

    def get_user_id(self) -> int | None:
        """Return the user ID if available."""
        return self._user_id

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
        payload = {
            "emailOrUsername": email,
            "userId": self._user_id,
            "institutionId": self._institution_id,
        }

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
        # ~0.5 s of CPU work (99999 PBKDF2 rounds); keep it off the event loop
        hash_hex = await self.hass.async_add_executor_job(
            self._pbkdf2_hash_hex, self.password, salt
        )

        headers = common_headers() | {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json;charset=UTF-8",
        }
        body = {
            "emailOrUsername": self.username,
            "password": self.password,
            "hash": hash_hex,
            "mobileApp": False,
            "userId": self._user_id,
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
            _LOGGER.debug("Schulmanager: authentication successful")
            user = data.get("user") or {}

            if self._user_id is None and user.get("id") is not None:
                self._user_id = user.get("id")

            # Extract and store institutionId if not already set
            if self._institution_id is None:
                self._institution_id = user.get("institutionId")
                if self._institution_id:
                    _LOGGER.debug("Extracted institutionId from login: %s", self._institution_id)

            self._students = self._extract_students(user)

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

        # Fallback: Use dummy bundleVersion if discovery fails
        # Based on https://github.com/Alpakat/schulmanager-online-api-client
        # The API accepts dummy values when the actual version cannot be determined
        dummy_version = "0000000000"
        _LOGGER.info(
            "Could not discover bundleVersion from JavaScript files, using dummy value '%s'. "
            "This is expected and should work fine.",
            dummy_version
        )
        self._bundle_version = dummy_version
        return dummy_version

    async def _api_call(
        self,
        module: str | None,
        endpoint: str,
        parameters: dict,
        tag: str,
        *,
        optional_module: bool = False,
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
                if result["status"] == 403 and optional_module:
                    raise ModuleUnavailableError(f"{module}/{endpoint}")
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

    async def fetch_institution_info(self) -> dict[str, Any] | None:
        """Fetch the school's master data (real name, address, ...)."""
        data = await self._api_call(None, "get-institution", {}, "institution_info")
        return data if isinstance(data, dict) else None

    async def fetch_unread_letters(self) -> list[dict[str, Any]]:
        """Fetch unread parent letters (Elternbriefe) of the account.

        Uses the same endpoint as the dashboard widget of the web app. Only the list of
        unread letters is requested; no letter is opened, so nothing is marked as read.
        """
        data = await self._api_call(
            "letters",
            "get-unread-letters-for-widget",
            {},
            "letters_unread",
            optional_module=True,
        )
        return (
            [x for x in data if isinstance(x, dict)] if isinstance(data, list) else []
        )

    async def fetch_unread_messages(self) -> tuple[int, list[dict[str, Any]]]:
        """Fetch the unread messenger count and conversations with unread messages.

        Only metadata is requested (count and subscriptions/threads). Message bodies are
        intentionally not fetched, because opening a thread may create read receipts.
        """
        count_raw = await self._api_call(
            "messenger",
            "count-new-messages",
            {},
            "messenger_count",
            optional_module=True,
        )
        subs = await self._api_call(
            "messenger",
            "get-subscriptions",
            {"all": False, "includeArchived": False},
            "messenger_subscriptions",
            optional_module=True,
        )
        unread = [
            x
            for x in (subs if isinstance(subs, list) else [])
            if isinstance(x, dict) and (x.get("unreadCount") or 0) > 0
        ]
        if isinstance(count_raw, (int, float)):
            return int(count_raw), unread
        # Count endpoint unavailable: derive the total from the conversations
        return sum(int(x["unreadCount"]) for x in unread), unread

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

    @staticmethod
    def _convert_calendar_event_to_exam(event: dict[str, Any]) -> dict[str, Any] | None:
        """Convert a school-wide calendar event (real UTC timestamps) into exam-shaped data.

        The calendar/events endpoint returns genuinely UTC timestamps (e.g.
        "2026-08-28T11:30:00.000Z"), unlike every other schedule/exam time in
        this API which is already naive local wall-clock time. Some
        Schulmanager instances omit the "Z"/offset suffix, so
        `dt_util.parse_datetime()` returns a naive datetime even though the
        value is still UTC; assume UTC explicitly for a naive result instead
        of relying on the string carrying a timezone marker. Converting to
        local *before* deriving the date/time strings is required - otherwise
        the raw UTC digits get treated as local further downstream
        (calendar.py's `as_local()` only tags naive datetimes as local, it
        does not convert them), producing a 1-2h display offset.

        `allDay` events are exempt from this: their midnight timestamp is a
        calendar-date marker, not a real moment in time, so UTC-converting it
        can push it onto the wrong side of midnight and/or attach a spurious
        time-of-day (e.g. 02:00) to what should render as a full-day entry.
        For those, no `startClassHour` is emitted at all - calendar.py's
        `_exam_times()` already falls back to a full local day when the key
        is absent, which is exactly the desired all-day rendering.
        """
        start_dt = dt_util.parse_datetime(event.get("start", ""))
        end_dt = dt_util.parse_datetime(event.get("end", ""))
        if start_dt is None:
            return None

        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=dt_util.UTC)
        if end_dt is not None and end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=dt_util.UTC)

        start_dt = dt_util.as_local(start_dt)
        if end_dt is not None:
            end_dt = dt_util.as_local(end_dt)

        result: dict[str, Any] = {
            "id": event.get("id"),
            "date": start_dt.date().isoformat(),
            "subject": {
                "name": event.get("summary", "Prüfung"),
                "abbreviation": event.get("summary", "")[:3].upper(),
            },
            "subjectText": event.get("summary"),
            "comment": event.get("description"),
            "type": {
                "name": "Schul-Event",
                "color": "#ff0000",
                "visibleForStudents": True,
            },
            "createdAt": event.get("createdAt"),
            "updatedAt": event.get("updatedAt"),
            "_isCalendarEvent": True,  # Flag to identify source
        }

        if not event.get("allDay"):
            start_time = start_dt.strftime("%H:%M:%S")
            end_time = end_dt.strftime("%H:%M:%S") if end_dt is not None else start_time
            result["startClassHour"] = {"from": start_time, "until": end_time, "number": "X"}
            result["endClassHour"] = {"from": end_time, "until": end_time, "number": "X"}

        return result

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

        # Get bundle version (with fallback to dummy value)
        bundle_version = await self._discover_bundle_version()

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

        # Create request payload with BOTH get-exams AND calendar events (school-wide)
        # The website queries two data sources:
        # 1. get-exams: Normal class exams
        # 2. calendar/events: School-wide events (BLF, school events, etc.)
        batch_payload = {
            "requests": [
                # Regular exams
                {
                    "moduleName": "exams",
                    "endpointName": "get-exams",
                    "parameters": {
                        "student": student_obj,
                        "start": start_date.isoformat(),
                        "end": end_date.isoformat()
                    }
                },
                # School-wide events (BLF, school events, etc.)
                {
                    "moduleName": "exams",
                    "endpointName": "poqa",
                    "parameters": {
                        "action": {
                            "model": "modules/calendar/event",
                            "action": "findAll",
                            "parameters": [
                                {
                                    "where": {
                                        "start": {"$lte": (end_date + timedelta(days=1)).isoformat() + "T00:00:00.000Z"},
                                        "end": {"$gte": (start_date - timedelta(days=1)).isoformat() + "T00:00:00.000Z"}
                                    },
                                    "include": [
                                        {
                                            "association": "visibleForGroups",
                                            "required": True,
                                            "attributes": ["id"],
                                            "include": [
                                                {
                                                    "association": "students",
                                                    "required": True,
                                                    "attributes": ["id"],
                                                    "where": {"id": int(student_id)}
                                                }
                                            ]
                                        }
                                    ]
                                }
                            ]
                        },
                        "uiState": "main.modules.exams.view"
                    }
                }
            ]
        }

        # Add bundleVersion only if available
        if bundle_version:
            batch_payload["bundleVersion"] = bundle_version

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

            # Parse both responses
            results = response_data.get("results", [])
            all_exams = []

            # Result 0: Regular exams from get-exams
            if len(results) > 0 and results[0].get("status") == 200:
                regular_exams = results[0].get("data", [])
                if isinstance(regular_exams, list):
                    all_exams.extend(regular_exams)
                    _LOGGER.debug("Found %d regular exams for student %s", len(regular_exams), student_id)

            # Result 1: Calendar events (BLF, school-wide events)
            if len(results) > 1 and results[1].get("status") == 200:
                calendar_events = results[1].get("data", [])
                if isinstance(calendar_events, list):
                    for event in calendar_events:
                        exam_event = self._convert_calendar_event_to_exam(event)
                        if exam_event is not None:
                            all_exams.append(exam_event)

                    _LOGGER.debug("Found %d calendar exam events for student %s", len(calendar_events), student_id)

            _LOGGER.debug("Total %d exams (regular + calendar) for student %s", len(all_exams), student_id)
            return all_exams



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

        # Get bundle version (with fallback to dummy value)
        bundle_version = await self._discover_bundle_version()

        # Calculate range: current week plus N-1 upcoming weeks
        start_of_week = today - timedelta(days=today.weekday())
        weeks = max(weeks, 1)
        weeks = min(weeks, 3)
        end_of_range = start_of_week + timedelta(days=(7 * weeks) - 1)

        # Create request payload exactly like the browser
        batch_payload = {
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
                },
                # Fetch school-specific class hour times (start/end per period)
                {
                    "moduleName": "schedules",
                    "endpointName": "get-class-hours",
                },
            ]
        }

        # Add bundleVersion only if available
        if bundle_version:
            batch_payload["bundleVersion"] = bundle_version

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

        # First pass: extract class hour time map {id -> {from, until}}
        # Items with "from"/"until" keys are class hour entries (not lessons).
        class_hours_map: dict[int, dict[str, Any]] = {}
        for result in results:
            if result.get("status") == 200 and isinstance(result.get("data"), list):
                first = result["data"][0] if result["data"] else {}
                if isinstance(first, dict) and "from" in first and "until" in first:
                    for ch in result["data"]:
                        ch_id = ch.get("id")
                        if ch_id is not None:
                            class_hours_map[ch_id] = ch

        for result in results:
            if result.get("status") == 200 and "data" in result:
                lessons = result["data"]

                # Skip the class-hours result (already processed above)
                if isinstance(lessons, list) and lessons and isinstance(lessons[0], dict) and "from" in lessons[0]:
                    continue

                # Handle lessons array directly
                if isinstance(lessons, list):
                    for lesson in lessons:
                        if not isinstance(lesson, dict):
                            continue

                        # Extract lesson date first (needed for day-specific times)
                        lesson_date = None
                        for date_field in ["date", "start", "day"]:
                            if date_field in lesson:
                                lesson_date_str = lesson[date_field]
                                if isinstance(lesson_date_str, str):
                                    lesson_date = lesson_date_str[:10]  # YYYY-MM-DD
                                    break

                        # Enrich classHour with school-specific start/end times.
                        # fromByDay/untilByDay use JS weekday convention (0=Sun..6=Sat).
                        ch = lesson.get("classHour")
                        if isinstance(ch, dict) and ch.get("id") in class_hours_map:
                            ch_data = class_hours_map[ch["id"]]
                            from_time = ch_data.get("from")
                            until_time = ch_data.get("until")
                            if lesson_date:
                                try:
                                    py_wd = date.fromisoformat(lesson_date).weekday()
                                    js_day = (py_wd + 1) % 7  # Mon=1..Sun=0
                                    from_by_day = ch_data.get("fromByDay") or []
                                    until_by_day = ch_data.get("untilByDay") or []
                                    if js_day < len(from_by_day) and from_by_day[js_day]:
                                        from_time = from_by_day[js_day]
                                    if js_day < len(until_by_day) and until_by_day[js_day]:
                                        until_time = until_by_day[js_day]
                                except (ValueError, TypeError):
                                    pass
                            ch["from"] = from_time
                            ch["until"] = until_time

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
            "changedLesson": "Geänderter Unterricht",
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
                "hour": (lesson.get("classHour") or {}).get("number", "?"),
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

            # Same lookup as the schedule sensors, for every change type
            original = extract_original_info(lesson)
            change_info["original_subject"] = original["subject"]
            change_info["original_teacher"] = original["teacher"]
            change_info["original_room"] = original["room"]

            # For special/substitute lessons, get new lesson info
            if actual_lesson:
                change_info["new_subject"] = (actual_lesson.get("subject") or {}).get("abbreviation", "")
                new_teachers = actual_lesson.get("teachers", [])
                if new_teachers:
                    change_info["new_teacher"] = new_teachers[0].get("abbreviation", "")
                change_info["new_room"] = (actual_lesson.get("room") or {}).get("name", "")

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

        # Add bundleVersion only if available
        if self._bundle_version:
            request_data["bundleVersion"] = self._bundle_version

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

    @staticmethod
    def _school_year_range(today: date) -> tuple[date, date]:
        """Return the (start, end) dates spanning the current school year (Aug-Jul)."""
        if today.month >= 8:
            return (
                today.replace(month=8, day=1),
                today.replace(year=today.year + 1, month=7, day=31),
            )
        return (
            today.replace(year=today.year - 1, month=8, day=1),
            today.replace(month=7, day=31),
        )

    @staticmethod
    def _grades_request_params(
        sid: int, start_date: date, end_date: date, term_id: int | None
    ) -> dict[str, Any]:
        """Build grades endpoint parameters for a given termId (None omits it)."""
        params: dict[str, Any] = {
            "studentId": sid,
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "gradingPeriodType": "entireYear",
        }
        if term_id is not None:
            params["termId"] = term_id
        return params

    @staticmethod
    def _courses_cover_date(courses: list[dict[str, Any]], target: date) -> bool:
        """Check whether any course's start/end window covers the target date.

        An empty course list is not treated as stale - it just means no
        courses/grades are available (yet), not that the wrong term was fetched.
        """
        if not courses:
            return True
        for course in courses:
            try:
                start = date.fromisoformat(course["start"])
                end = date.fromisoformat(course["end"])
            except (KeyError, TypeError, ValueError):
                continue
            if start <= target <= end:
                return True
        return False

    async def _fetch_grades_data(
        self,
        sid: int,
        student_id: str,
        start_date: date,
        end_date: date,
        term_id: int | None,
        bundle_version: str | None,
    ) -> dict[str, Any] | None:
        """POST the grades request for one termId and return raw grades data."""
        grades_payload: dict[str, Any] = {
            "requests": [
                {
                    "moduleName": "grades",
                    "endpointName": "get-grading-information-for-student",
                    "parameters": self._grades_request_params(
                        sid, start_date, end_date, term_id
                    ),
                }
            ]
        }

        # Add bundleVersion only if available
        if bundle_version:
            grades_payload["bundleVersion"] = bundle_version

        sess = async_get_clientsession(self.hass)
        headers = common_headers() | {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._token}",
        }

        _LOGGER.debug("Fetching grades for student %s (termId %s)", student_id, term_id)

        async with sess.post(CALLS_URL, json=grades_payload, headers=headers) as response:
            if response.status != 200:
                _LOGGER.error("Grades fetch failed with status %d", response.status)
                return None

            response_data = await response.json()
            await self._dump(f"grades_response_{student_id}.json", response_data)

            for result in response_data.get("results", []):
                if result.get("status") == 200 and "data" in result:
                    return cast(dict[str, Any], result["data"])

            _LOGGER.debug("No grades found for student %s", student_id)
            return None

    async def _discover_term_id(
        self, class_id: int, bundle_version: str | None
    ) -> int | None:
        """Discover the current termId via the class record's termId field.

        Schulmanager exposes no dedicated "current term" endpoint, but the
        generic query endpoint ("poqa": perform-object-query-action) used
        elsewhere for e.g. subjects can look up "main/class" by id, and that
        record carries the school's current termId. This was confirmed by
        live-testing against the real API (2026-09-20): querying a class
        returns e.g. {"name": "9b", "termId": 33883, ...} where 33883 is the
        actual current-year term, as opposed to a stale hardcoded value.
        """
        payload: dict[str, Any] = {
            "requests": [
                {
                    "moduleName": "grades",
                    "endpointName": "poqa",
                    "parameters": {
                        "action": {
                            "model": "main/class",
                            "action": "findAll",
                            "parameters": [{"where": {"id": class_id}}],
                        },
                        "uiState": "main.modules.grades.student",
                    },
                }
            ]
        }
        # The poqa endpoint rejects requests without a bundleVersion (HTTP 400).
        payload["bundleVersion"] = bundle_version or "0000000000"

        sess = async_get_clientsession(self.hass)
        headers = common_headers() | {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._token}",
        }

        async with sess.post(CALLS_URL, json=payload, headers=headers) as response:
            if response.status != 200:
                return None
            response_data = await response.json()

        for result in response_data.get("results", []):
            if result.get("status") == 200:
                classes = result.get("data") or []
                if classes:
                    term_id = classes[0].get("termId")
                    if isinstance(term_id, int):
                        return term_id
        return None

    async def fetch_grades(self, student_id: str, class_id: int | None = None) -> GradesPayload:
        """Fetch grades for a student using the proper grades API."""
        sid = int(student_id)

        # Get bundle version (with fallback to dummy value)
        bundle_version = await self._discover_bundle_version()

        today = dt_util.now().date()
        start_date, end_date = self._school_year_range(today)

        term_id: int | None = None
        if class_id is not None:
            term_id = await self._discover_term_id(class_id, bundle_version)
        if term_id is None:
            term_id = LEGACY_TERM_ID
            _LOGGER.warning(
                "Could not discover current termId for class %s; "
                "falling back to legacy termId=%s",
                class_id,
                LEGACY_TERM_ID,
            )

        grades_data = await self._fetch_grades_data(
            sid, student_id, start_date, end_date, term_id, bundle_version
        )

        if grades_data is not None and not self._courses_cover_date(
            grades_data.get("courses", []), today
        ):
            _LOGGER.warning(
                "Grades for student %s look stale: no course covers %s "
                "(termId=%s likely belongs to a previous school year)",
                student_id,
                today.isoformat(),
                term_id,
            )

        if grades_data is None:
            return {
                "subjects": {},
                "overall_average": None,
                "total_subjects": 0,
                "subjects_with_grades": 0,
            }

        return await self._process_grades_data(grades_data)

    @staticmethod
    def _split_grade_value(
        grade_value: str | float, grading_system: int
    ) -> tuple[float | int | str, str | float | int, str | None]:
        """Parse a raw grade value into (numeric-or-raw value, display value, tendency)."""
        parsed_value = grading.parse_grade_value(grade_value, grading_system)
        tendency = None
        display_value: str | float | int = grade_value

        if isinstance(grade_value, str):
            if grade_value.endswith("+"):
                tendency = "plus"
            elif grade_value.endswith("-"):
                tendency = "minus"
            if "~" in grade_value:
                # "0~3+" -> "3+", "1~5" -> "5"
                display_value = grade_value.split("~")[1]

        value = parsed_value if parsed_value is not None else grade_value
        return value, display_value, tendency

    @staticmethod
    def _build_block_weighting(
        block_presets: list[dict[str, Any]],
    ) -> tuple[dict[int, dict[int, float]], dict[int, str]]:
        """Build (courseId -> blockId -> weighting) and (blockId -> name) from blockPresets.

        Per-course block weighting (e.g. Klassenarbeiten 50% / Sonstige 50%)
        feeds grading.calculate_average; block names drive the (coarser)
        display category grouping.
        """
        course_block_weighting: dict[int, dict[int, float]] = {}
        block_names: dict[int, str] = {}
        for block_preset in block_presets:
            course_id = block_preset.get("courseId")
            block = block_preset.get("gradingBlock") or {}
            block_id = block.get("id")
            if course_id is None or block_id is None:
                continue
            course_block_weighting.setdefault(course_id, {})[block_id] = block_preset.get(
                "weighting", 1
            )
            if block_id not in block_names:
                block_names[block_id] = block.get("name") or f"Block {block_id}"
        return course_block_weighting, block_names

    def _process_grading_events(
        self,
        grading_events: list[dict[str, Any]],
        course_map: dict[int, dict[str, Any]],
        type_map: dict[int, dict[str, Any]],
        course_block_weighting: dict[int, dict[int, float]],
        block_names: dict[int, str],
        ensure_subject: Callable[[int, int], dict[str, Any]],
    ) -> dict[tuple[int, int], list[dict[str, Any]]]:
        """Process gradingEvents (actual grades) into each subject's grade categories.

        Returns the (courseId, gradeTypeId) -> entries groups, used afterwards
        to apply repeat-exam overrides across the exact same exam slot.
        """
        repeat_groups: dict[tuple[int, int], list[dict[str, Any]]] = {}

        for event in grading_events:
            course_id = event.get("courseId")
            if course_id not in course_map:
                continue

            course = course_map[course_id]
            subject_id = course.get("subjectId")
            if not subject_id:
                continue

            subject = ensure_subject(subject_id, course_id)
            grading_system = subject["grading_system"]

            grade_type_id = event.get("gradeTypeId")
            grade_type_info = type_map.get(grade_type_id if isinstance(grade_type_id, int) else -1, {})

            block_id = event.get("gradingBlockId")
            block_weighting = course_block_weighting.get(course_id, {}).get(block_id, 1.0)
            # Fall back to the fine-grained type name if the block isn't known
            # (e.g. blockPresets missing for a just-created course).
            category_name = block_names.get(block_id, grade_type_info.get("name", "Sonstige"))

            for grade_data in event.get("grades", []):
                grade_value = grade_data.get("value")
                if grade_value is None or grade_value == "":
                    continue

                value, display_value, tendency = self._split_grade_value(grade_value, grading_system)

                grade_entry: dict[str, Any] = {
                    "value": value,
                    "display_value": display_value,  # Clean notation for display (e.g. "3+", "2-", "5")
                    "original_value": grade_value,  # Keep API format for debugging
                    "tendency": tendency,  # "plus", "minus", or None
                    "date": event.get("date"),
                    "topic": event.get("topic", ""),
                    "weighting": event.get("weighting", 1),
                    "duration": event.get("durationInMinutes"),
                    "type_abbreviation": grade_type_info.get("abbreviation", ""),
                    "is_repeat_exam": grade_data.get("isRepeatExam", False),
                    "grading_block_id": block_id,
                    "block_weighting": block_weighting,
                }

                # Add to appropriate category (only create categories that have grades)
                if category_name not in subject["grades"]:
                    subject["grades"][category_name] = []
                subject["grades"][category_name].append(grade_entry)

                if isinstance(grade_type_id, int):
                    repeat_groups.setdefault((course_id, grade_type_id), []).append(grade_entry)

        return repeat_groups

    @staticmethod
    def _apply_repeat_exam_overrides(
        repeat_groups: dict[tuple[int, int], list[dict[str, Any]]],
    ) -> None:
        """A repeat exam (isRepeatExam=True) replaces the grade(s) it retakes.

        Excludes the non-repeat entries of the same exam slot from the
        average (mutates them in place), but keeps them visible for
        transparency.
        """
        for group in repeat_groups.values():
            if any(entry["is_repeat_exam"] for entry in group):
                for entry in group:
                    if not entry["is_repeat_exam"]:
                        entry["counts_toward_average"] = False

    def _process_final_grades(
        self,
        final_grades: list[dict[str, Any]],
        course_map: dict[int, dict[str, Any]],
        ensure_subject: Callable[[int, int], dict[str, Any]],
    ) -> None:
        """Process finalGrades (Tendenz) into each subject's grade categories.

        At the start of a school year, before individual gradingEvents
        exist, this is the only source of a current grade. Shown to the
        user but excluded from notifications and averaging (see
        grading.calculate_average's docstring).
        """
        for final_grade in final_grades:
            course_id = final_grade.get("courseId")
            if course_id not in course_map:
                continue

            course = course_map[course_id]
            subject_id = course.get("subjectId")
            if not subject_id:
                continue

            grade_value = final_grade.get("value")
            if grade_value is None or grade_value == "":
                continue

            subject = ensure_subject(subject_id, course_id)
            grading_system = subject["grading_system"]

            value, display_value, tendency = self._split_grade_value(grade_value, grading_system)

            grade_entry = {
                "value": value,
                "display_value": display_value,
                "original_value": grade_value,
                "tendency": tendency,
                "date": None,
                "topic": "",
                "weighting": 1,
                "duration": None,
                "type_abbreviation": "",
                "is_repeat_exam": False,
                "fires_event": False,
                "counts_toward_average": False,
            }

            subject["grades"].setdefault(grading.FINAL_GRADE_CATEGORY, []).append(grade_entry)

    async def _process_grades_data(self, grades_data: dict) -> GradesPayload:
        """Process raw grades data into structured format by subject."""
        courses: list[dict[str, Any]] = grades_data.get("courses", [])
        grading_events: list[dict[str, Any]] = grades_data.get("gradingEvents", [])
        final_grades: list[dict[str, Any]] = grades_data.get("finalGrades", [])
        type_presets: list[dict[str, Any]] = grades_data.get("typePresets", [])
        block_presets: list[dict[str, Any]] = grades_data.get("blockPresets", [])

        # Create mapping from course ID to course info
        course_map: dict[int, dict[str, Any]] = {
            int(course["id"]): course for course in courses if "id" in course
        }
        # gradingPreset can be missing entirely (not just gradingSystem=0),
        # which also means the classic scale applies.
        course_grading_system: dict[int, int] = {
            course_id: (course.get("gradingPreset") or {}).get(
                "gradingSystem", grading.GRADING_SYSTEM_CLASSIC
            )
            for course_id, course in course_map.items()
        }

        # Create mapping from gradeTypeId to type info
        type_map: dict[int, dict[str, Any]] = {}
        for preset in type_presets:
            if "gradeType" in preset:
                grade_type = preset["gradeType"]
                type_map[grade_type["id"]] = grade_type

        course_block_weighting, block_names = self._build_block_weighting(block_presets)

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

        def ensure_subject(subject_id: int, course_id: int) -> dict[str, Any]:
            if subject_id not in subjects:
                subject_name, subject_abbrev = subject_info.get(
                    subject_id, (f"Fach {subject_id}", f"F{subject_id}")
                )
                subjects[subject_id] = {
                    "name": subject_name,
                    "abbreviation": subject_abbrev,
                    "average": None,  # Calculated below, once all grades are collected
                    "grades": {},
                    "grading_system": course_grading_system.get(
                        course_id, grading.GRADING_SYSTEM_CLASSIC
                    ),
                }
            return subjects[subject_id]

        repeat_groups = self._process_grading_events(
            grading_events, course_map, type_map, course_block_weighting, block_names, ensure_subject
        )
        self._apply_repeat_exam_overrides(repeat_groups)
        self._process_final_grades(final_grades, course_map, ensure_subject)

        # Calculate averages for each subject
        all_subject_averages: list[float] = []
        for subject_data in subjects.values():
            avg = grading.calculate_average(subject_data["grades"], subject_data["grading_system"])
            subject_data["average"] = avg
            if avg is not None:
                all_subject_averages.append(avg)

        # Calculate overall student average, blending only subjects that share
        # a grading system - averaging a 0-15 points-scale subject together
        # with a 1-6 subject would be numerically meaningless. A student uses
        # a single grading system in practice (Sek I: classic, Sek II: points),
        # so group by system and use whichever group has graded subjects.
        averages_by_system: dict[int, list[float]] = {}
        for subject_data in subjects.values():
            if subject_data["average"] is not None:
                averages_by_system.setdefault(subject_data["grading_system"], []).append(
                    subject_data["average"]
                )

        overall_average = None
        if averages_by_system:
            # Ties (e.g. exactly one graded subject on each scale) favor the
            # classic scale, since it is the far more common case.
            dominant_averages = max(
                averages_by_system.items(),
                key=lambda system_averages: (
                    len(system_averages[1]),
                    system_averages[0] == grading.GRADING_SYSTEM_CLASSIC,
                ),
            )[1]
            overall_average = round(sum(dominant_averages) / len(dominant_averages), 1)

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
        # Always re-authenticate to ensure the JWT is fresh (tokens expire server-side
        # after ~1 hour, matching the default update interval).
        _LOGGER.debug("Schulmanager: refreshing authentication token")
        await self.async_login()
        if not self._token:
            # async_login() may return without a token for multi-school accounts
            # (API returns multipleAccounts instead of JWT). Raise so the coordinator
            # can mark the update as failed instead of silently returning empty data.
            _LOGGER.error(
                "Schulmanager: authentication failed – no valid token after login attempt"
            )
            raise RuntimeError(
                "Authentication failed: no token after login "
                "(account may require institutionId – check integration configuration)"
            )
        if not self._bundle_version:
            await self._discover_bundle_version()

        # Default to all enabled if no preferences provided
        if enabled_features is None:
            enabled_features = {
                "homework": True,
                "schedule": True,
                "exams": True,
                "grades": True,
                "letters": True,
                "messages": True,
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

        # Account-level data (not per student)
        # Keys stay absent on failure so the sensors become unavailable
        if (
            enabled_features.get("letters", True)
            and "letters" not in self._unavailable_modules
        ):
            try:
                result["letters_unread"] = await self.fetch_unread_letters()
            except ModuleUnavailableError:
                _LOGGER.info("Schulmanager: letters module not enabled, skipping")
                self._unavailable_modules.add("letters")
            except Exception as err:
                _LOGGER.warning("Schulmanager: letters fetch failed: %s", err)

        if (
            enabled_features.get("messages", True)
            and "messenger" not in self._unavailable_modules
        ):
            try:
                count, unread = await self.fetch_unread_messages()
            except ModuleUnavailableError:
                _LOGGER.info("Schulmanager: messenger module not enabled, skipping")
                self._unavailable_modules.add("messenger")
            except Exception as err:
                _LOGGER.warning("Schulmanager: messenger fetch failed: %s", err)
            else:
                result["messages_unread_count"] = count
                result["messages_unread"] = unread

        # Save for other platforms
        self.data = result
        # Optional dump
        await self._dump("hub_data.json", result)
        return result


class SchulmanagerHubClient:
    """Unified hub client for both single-school and multi-school Schulmanager accounts.

    Automatically detects the account type on first login and handles both cases
    transparently. Single-school accounts use exactly one internal SchulmanagerClient;
    multi-school accounts use one per school, with parallel login and aggregated data.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        username: str,
        password: str,
        debug_dumps: bool = False,
    ) -> None:
        """Initialize unified hub client."""
        self.hass = hass
        self.username = username
        self.password = password
        self.debug_dumps = debug_dumps
        self._clients: dict[Any, SchulmanagerClient] = {}  # key -> client
        self._school_names: dict[Any, str] = {}  # key -> school name
        self._all_students: list[dict[str, Any]] = []
        self._detected_schools: list[dict[str, Any]] | None = None

    async def async_login(
        self,
        schools: list[dict[str, Any]] | None = None,
        institution_id: int | None = None,
    ) -> None:
        """Login to all schools.

        Login priority:
        1. If schools provided (stored in config entry) → login to each school directly.
        2. Otherwise → probe login to auto-detect account type:
           - JWT response → single-school, use the probe client directly.
           - multipleAccounts response → multi-school, login to each detected school.
        """
        if schools:
            # Known schools from stored config – skip probe, login directly
            await self._login_to_schools(schools)
        else:
            # Probe login: auto-detect single vs multi-school
            probe = SchulmanagerClient(
                self.hass,
                self.username,
                self.password,
                debug_dumps=self.debug_dumps,
                institution_id=institution_id,
            )
            await probe.async_login()

            if probe.has_token():
                # Single-school account
                inst_key: Any = probe.get_institution_id() or institution_id or 0
                self._clients[inst_key] = probe
                try:
                    info = await probe.fetch_institution_info()
                except Exception as err:
                    _LOGGER.debug("Fetching institution info failed: %s", err)
                    info = None
                school_name = (info or {}).get("name") or ""
                self._school_names[inst_key] = school_name
                self._all_students = []
                for student in probe.get_students():
                    student_with_school = student.copy()
                    student_with_school["school_id"] = inst_key
                    student_with_school["school_name"] = school_name
                    self._all_students.append(student_with_school)
                _LOGGER.debug(
                    "Single-school account: %d students found",
                    len(self._all_students),
                )
            else:
                # Multi-school account detected from probe response
                detected = probe.get_multiple_accounts() or []
                if not detected:
                    raise RuntimeError(
                        "Login failed: no token and no multiple accounts in response"
                    )
                self._detected_schools = detected
                _LOGGER.info(
                    "Multi-school account detected with %d schools - logging into all",
                    len(detected),
                )
                await self._login_to_schools(detected)

    async def _login_to_schools(self, schools: list[dict[str, Any]]) -> None:
        """Login to a list of schools in parallel and collect students."""
        _LOGGER.info("Logging into %d schools in parallel", len(schools))

        def _build_login_candidates(school: dict[str, Any]) -> list[dict[str, int | None]]:
            """Build possible login parameter combinations from a school record."""
            inst_ids: list[int] = []
            user_ids: list[int] = []

            def _add_unique(target: list[int], value: Any) -> None:
                if isinstance(value, str) and value.isdigit():
                    value = int(value)
                if isinstance(value, int) and value not in target:
                    target.append(value)

            _add_unique(inst_ids, school.get("institutionId"))
            _add_unique(inst_ids, school.get("institution_id"))
            _add_unique(user_ids, school.get("userId"))
            _add_unique(user_ids, school.get("user_id"))

            raw_id = school.get("id")
            _add_unique(user_ids, raw_id)
            if not inst_ids:
                _add_unique(inst_ids, raw_id)

            combos: list[dict[str, int | None]] = []
            for inst in inst_ids:
                combos.append({"institution_id": inst, "user_id": None})
            for user in user_ids:
                combos.append({"institution_id": None, "user_id": user})
            for inst in inst_ids:
                for user in user_ids:
                    combos.append({"institution_id": inst, "user_id": user})

            # Deduplicate
            seen: set[tuple[int | None, int | None]] = set()
            unique: list[dict[str, int | None]] = []
            for c in combos:
                key = (c["institution_id"], c["user_id"])
                if key in seen:
                    continue
                seen.add(key)
                unique.append(c)
            return unique

        async def login_to_school(school: dict[str, Any]) -> tuple[Any, str, SchulmanagerClient]:
            """Login to a single school and return (key, name, client)."""
            login_label = school.get("label") or "Schule"
            candidates = _build_login_candidates(school)
            if not candidates:
                raise RuntimeError("No login candidates for school")

            last_err: Exception | None = None
            for params in candidates:
                inst_id = params["institution_id"]
                user_id = params["user_id"]
                _LOGGER.debug(
                    "Logging into school: %s (institution_id=%s, user_id=%s)",
                    login_label,
                    inst_id,
                    user_id,
                )
                client = SchulmanagerClient(
                    self.hass,
                    self.username,
                    self.password,
                    debug_dumps=self.debug_dumps,
                    institution_id=inst_id,
                    user_id=user_id,
                )
                try:
                    await client.async_login()
                except Exception as err:
                    last_err = err
                    continue

                if client.has_token():
                    school_key: Any = inst_id if inst_id is not None else (user_id or 0)
                    try:
                        info = await client.fetch_institution_info()
                    except Exception as info_err:
                        _LOGGER.debug("Fetching institution info failed: %s", info_err)
                        info = None
                    school_name = (info or {}).get("name") or login_label
                    return school_key, school_name, client

                last_err = RuntimeError("Login returned no token")

            raise RuntimeError(f"Login failed for {login_label}: {last_err!r}")

        # Login to all schools in parallel
        login_tasks = [login_to_school(school) for school in schools]
        results = await asyncio.gather(*login_tasks, return_exceptions=True)

        # Process results
        summary: list[dict[str, Any]] = []

        for school, result in zip(schools, results, strict=True):
            if isinstance(result, Exception):
                _LOGGER.error("Failed to login to school: %s", result)
                summary.append(
                    {
                        "school_id": school.get("id"),
                        "school_name": school.get("label"),
                        "status": "error",
                        "error": repr(result),
                    }
                )
                continue

            school_id, school_name, client = result
            self._clients[school_id] = client
            self._school_names[school_id] = school_name

            # Collect students from this school and add school info
            students = client.get_students()
            for student in students:
                student_with_school = student.copy()
                student_with_school["school_id"] = school_id
                student_with_school["school_name"] = school_name
                self._all_students.append(student_with_school)

            _LOGGER.info(
                "Logged into school '%s': %d students found",
                school_name,
                len(students),
            )
            masked_student_ids = [
                self._mask_identifier(student.get("id")) for student in students
            ]
            summary.append(
                {
                    "school_id": school_id,
                    "school_name": school_name,
                    "status": "success",
                    "student_count": len(students),
                    "student_ids": masked_student_ids,
                }
            )

        _LOGGER.info(
            "Multi-school login complete: %d schools, %d total students",
            len(self._clients),
            len(self._all_students),
        )

        await self._dump_summary("multi_school_login_summary.json", summary)

    def get_all_students(self) -> list[dict[str, Any]]:
        """Return all students with school context (school_name=None for single-school)."""
        return list(self._all_students)

    def get_detected_schools(self) -> list[dict[str, Any]] | None:
        """Return the schools list detected during probe login (for config storage).

        Returns None for single-school accounts or when schools were provided directly.
        """
        return self._detected_schools

    def get_institution_id(self) -> int | None:
        """Return institution ID for single-school accounts (for config storage)."""
        if len(self._clients) == 1:
            client = next(iter(self._clients.values()))
            return client.get_institution_id()
        return None

    def get_client(self, school_id: Any) -> SchulmanagerClient | None:
        """Get the internal client for a specific school key."""
        return self._clients.get(school_id)

    def get_school_name(self, school_id: Any) -> str:
        """Get the school name for a specific school key."""
        return self._school_names.get(school_id, f"School {school_id}")

    def has_token(self) -> bool:
        """Return True if at least one internal client has a token."""
        return any(client.has_token() for client in self._clients.values())

    def has_bundle_version(self) -> bool:
        """Return True if at least one internal client has a bundle version."""
        return any(client.has_bundle_version() for client in self._clients.values())

    def clear_auth_cache(self) -> None:
        """Clear auth cache for all internal clients."""
        for client in self._clients.values():
            client.clear_auth_cache()

    async def async_update(
        self,
        enabled_features: dict[str, bool] | None = None,
        date_range_config: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        """Update data from all schools and aggregate results.

        Returns:
            Aggregated data dict with students from all schools.
        """
        result: dict[str, Any] = {
            "students": list(self._all_students),
            "homework": {},
            "schedule": {},
            "exams": {},
            "grades": {},
        }

        if not self._clients:
            raise RuntimeError(
                "No authenticated school clients available; "
                "async_login() may have failed"
            )

        # Update all clients in parallel
        async def update_client(client: SchulmanagerClient) -> dict[str, Any]:
            """Update a single client."""
            return await client.async_update(enabled_features, date_range_config)

        update_tasks = [update_client(client) for client in self._clients.values()]
        client_results = await asyncio.gather(*update_tasks, return_exceptions=True)

        # Aggregate results from all schools
        for client_result in client_results:
            if isinstance(client_result, BaseException):
                _LOGGER.error("Failed to update school data: %s", client_result)
                continue

            # Merge student data from this school
            for key in ["homework", "schedule", "exams", "grades"]:
                if key in client_result:
                    result[key].update(client_result[key])

            # Merge account-level data (letters/messages) across schools
            if "letters_unread" in client_result:
                result.setdefault("letters_unread", []).extend(
                    client_result.get("letters_unread") or []
                )
            if "messages_unread" in client_result:
                result.setdefault("messages_unread", []).extend(
                    client_result.get("messages_unread") or []
                )
                result["messages_unread_count"] = result.get(
                    "messages_unread_count", 0
                ) + client_result.get("messages_unread_count", 0)

        return result

    @staticmethod
    def _mask_identifier(raw_value: Any) -> str:
        """Return a privacy-safe representation of an identifier."""
        if raw_value is None:
            return ""

        value = str(raw_value)
        if not value:
            return ""

        if len(value) <= 4:
            return "***"

        return f"{value[0]}***{value[-1]}"

    async def _dump_summary(self, filename: str, entries: list[dict[str, Any]]) -> None:
        """Write multi-school debug summary if dumps are enabled."""
        if not self.debug_dumps:
            return

        base = Path(self.hass.config.path("custom_components", "schulmanager", "debug"))
        file_path = base / filename

        def _write() -> None:
            base.mkdir(parents=True, exist_ok=True)
            with file_path.open("w", encoding="utf-8") as f:
                json.dump(
                    {
                        "fetched_at": dt_util.utcnow().isoformat(),
                        "entries": entries,
                        "total_students": len(self._all_students),
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )

        await self.hass.async_add_executor_job(_write)


# Backward-compatibility alias – remove in a future version
MultiSchoolClient = SchulmanagerHubClient
