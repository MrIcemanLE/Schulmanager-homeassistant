"""Class book entries (Klassenbucheinträge) of a student."""

from collections import Counter
from collections.abc import Iterable
import hashlib
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN

EVENT_CLASSBOOK_NEW = "schulmanager_classbook_new"

_STORE_VERSION = 1


def classbook_store(hass: HomeAssistant, entry_id: str) -> Store[dict[str, list[str]]]:
    """Return the store of the entries already announced for a config entry."""
    return Store(hass, _STORE_VERSION, f"{DOMAIN}.{entry_id}.classbook_seen")


def flatten_entries(entry_types: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the entries of all entry types, newest first."""
    entries = []
    for entry_type in entry_types:
        for entry in entry_type.get("entries") or []:
            subject = (entry.get("taughtLesson") or {}).get("subject") or {}
            teacher = entry.get("teacher") or {}
            name = " ".join(
                x for x in (teacher.get("firstname"), teacher.get("lastname")) if x
            )
            entries.append(
                {
                    "date": entry.get("date"),
                    "type": entry_type.get("name"),
                    "subject": subject.get("name"),
                    "subject_abbreviation": subject.get("abbreviation"),
                    "teacher": name or teacher.get("abbreviation"),
                    "text": entry.get("text") or "",
                }
            )
    entries.sort(key=lambda entry: entry["date"] or "", reverse=True)
    return entries


def entry_keys(entries: Iterable[dict[str, Any]]) -> list[str]:
    """Return a key per entry to recognize it in later updates.

    The API has no entry ids. Identical entries are numbered, and keys are hashed
    so the store does not hold a second copy of the texts.
    """
    occurrences: Counter[str] = Counter()
    keys = []
    for entry in entries:
        raw = "|".join(
            str(entry[field])
            for field in ("date", "type", "subject", "teacher", "text")
        )
        occurrences[raw] += 1
        keys.append(
            hashlib.sha256(f"{raw}|{occurrences[raw]}".encode()).hexdigest()[:16]
        )
    return keys
