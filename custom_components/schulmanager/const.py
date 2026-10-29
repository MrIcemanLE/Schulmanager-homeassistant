# custom_components/schulmanager/const.py
"""Constants for the Schulmanager integration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

DOMAIN: Final = "schulmanager"

# Version aus manifest.json laden
def _get_version() -> str:
    """Load version from manifest.json."""
    try:
        manifest_path = Path(__file__).parent / "manifest.json"
        with manifest_path.open() as f:
            manifest = json.load(f)
            version = manifest.get("version", "unknown")
            return str(version)
    except Exception:  # noqa: BLE001 - fall back to unknown version on any read error
        return "unknown"

VERSION: Final = _get_version()

# Credentials
CONF_USERNAME: Final = "username"
CONF_PASSWORD: Final = "password"
# Remembered devices of 2FA accounts, one per school account
CONF_USER_DEVICES: Final = "user_devices"

"""Options / Settings."""
OPT_ENABLE_SCHEDULE: Final = "enable_schedule"
OPT_ENABLE_HOMEWORK: Final = "enable_homework"
OPT_ENABLE_EXAMS: Final = "enable_exams"
OPT_ENABLE_GRADES: Final = "enable_grades"
OPT_ENABLE_LETTERS: Final = "enable_letters"  # Unread parent letters (Elternbriefe)
OPT_ENABLE_MESSAGES: Final = "enable_messages"  # Unread messenger conversations
OPT_RANGE_PAST_DAYS: Final = "range_past_days"
OPT_RANGE_FUTURE_DAYS: Final = "range_future_days"
OPT_REFRESH_COOLDOWN: Final = "refresh_cooldown"  # Minutes (5-30)
OPT_SCHEDULE_WEEKS: Final = "schedule_weeks"  # Weeks ahead to fetch (1-3)
OPT_SCHEDULE_HIGHLIGHT: Final = "schedule_highlight"  # Use emoji highlighting in calendar
OPT_SCHEDULE_HIDE_CANCELLED_NO_HIGHLIGHT: Final = (
    "schedule_hide_cancelled_no_highlight"
)  # Hide cancellations when highlight is off

# Defaults
DEFAULT_AUTO_UPDATE_INTERVAL: Final = 1  # hours, fixed (not user-configurable)
DEFAULT_ENABLE_SCHEDULE: Final = True
DEFAULT_ENABLE_HOMEWORK: Final = True
DEFAULT_ENABLE_EXAMS: Final = True
DEFAULT_ENABLE_GRADES: Final = True
DEFAULT_ENABLE_LETTERS: Final = True
DEFAULT_ENABLE_MESSAGES: Final = True
DEFAULT_RANGE_PAST_DAYS: Final = 30
DEFAULT_RANGE_FUTURE_DAYS: Final = 180
DEFAULT_REFRESH_COOLDOWN: Final = 5  # 5 minutes cooldown between manual refreshes
DEFAULT_SCHEDULE_WEEKS: Final = 2  # current week + N-1 upcoming weeks
DEFAULT_SCHEDULE_HIGHLIGHT: Final = True
DEFAULT_SCHEDULE_HIDE_CANCELLED_NO_HIGHLIGHT: Final = False

MIN_REFRESH_COOLDOWN: Final = 5  # Minimum 5 minutes
MAX_REFRESH_COOLDOWN: Final = 30  # Maximum 30 minutes

# Paket mit Defaults (praktisch für ConfigFlow/Setup)
DEFAULT_OPTIONS: Final = {
    OPT_ENABLE_SCHEDULE: DEFAULT_ENABLE_SCHEDULE,
    OPT_ENABLE_HOMEWORK: DEFAULT_ENABLE_HOMEWORK,
    OPT_ENABLE_EXAMS: DEFAULT_ENABLE_EXAMS,
    OPT_ENABLE_GRADES: DEFAULT_ENABLE_GRADES,
    OPT_ENABLE_LETTERS: DEFAULT_ENABLE_LETTERS,
    OPT_ENABLE_MESSAGES: DEFAULT_ENABLE_MESSAGES,
    OPT_RANGE_PAST_DAYS: DEFAULT_RANGE_PAST_DAYS,
    OPT_RANGE_FUTURE_DAYS: DEFAULT_RANGE_FUTURE_DAYS,
    OPT_REFRESH_COOLDOWN: DEFAULT_REFRESH_COOLDOWN,
    OPT_SCHEDULE_WEEKS: DEFAULT_SCHEDULE_WEEKS,
    OPT_SCHEDULE_HIGHLIGHT: DEFAULT_SCHEDULE_HIGHLIGHT,
    OPT_SCHEDULE_HIDE_CANCELLED_NO_HIGHLIGHT: DEFAULT_SCHEDULE_HIDE_CANCELLED_NO_HIGHLIGHT,
}

# Plattformen
PLATFORMS: Final = ["sensor", "todo", "calendar", "button"]

# Debug-Verzeichnisname
DUMP_DIR_NAME: Final = "debug"

# API URLs
CALLS_URL: Final = "https://login.schulmanager-online.de/api/calls"
