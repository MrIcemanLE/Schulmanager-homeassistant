# custom_components/schulmanager/const.py
from __future__ import annotations
from typing import Final
import json
from pathlib import Path

DOMAIN: Final = "schulmanager"

# Version aus manifest.json laden
def _get_version() -> str:
    """Load version from manifest.json."""
    try:
        manifest_path = Path(__file__).parent / "manifest.json"
        with manifest_path.open() as f:
            manifest = json.load(f)
            return manifest.get("version", "unknown")
    except Exception:
        return "unknown"

VERSION: Final = _get_version()

# Credentials
CONF_USERNAME: Final = "username"
CONF_PASSWORD: Final = "password"

# Options / Settings
OPT_AUTO_UPDATE_INTERVAL: Final = "auto_update_interval"  # Hours (1-6)
OPT_ENABLE_SCHEDULE: Final = "enable_schedule"
OPT_ENABLE_HOMEWORK: Final = "enable_homework"
OPT_ENABLE_EXAMS: Final = "enable_exams"
OPT_ENABLE_GRADES: Final = "enable_grades"
OPT_RANGE_PAST_DAYS: Final = "range_past_days"
OPT_RANGE_FUTURE_DAYS: Final = "range_future_days"
OPT_REFRESH_COOLDOWN: Final = "refresh_cooldown"  # Minutes (5-30)

# Legacy option name (kept for backward compatibility)
OPT_POLL_INTERVAL: Final = "poll_interval"  # Deprecated - use AUTO_UPDATE_INTERVAL

# NEU: Debug-Dumps Toggle (wird in __init__ importiert)
OPT_DEBUG_DUMPS: Final = "debug_dumps"

# Defaults
DEFAULT_AUTO_UPDATE_INTERVAL: Final = 1  # 1 hour default
DEFAULT_ENABLE_SCHEDULE: Final = True
DEFAULT_ENABLE_HOMEWORK: Final = True
DEFAULT_ENABLE_EXAMS: Final = True
DEFAULT_ENABLE_GRADES: Final = True
DEFAULT_RANGE_PAST_DAYS: Final = 30
DEFAULT_RANGE_FUTURE_DAYS: Final = 180
DEFAULT_REFRESH_COOLDOWN: Final = 5  # 5 minutes cooldown between manual refreshes

# Legacy defaults (for backward compatibility)
DEFAULT_POLL_INTERVAL: Final = DEFAULT_AUTO_UPDATE_INTERVAL * 3600  # Convert hours to seconds
DEFAULT_DEBUG_DUMPS: Final = True  # während der Entwicklung AN

# Validation ranges
MIN_AUTO_UPDATE_INTERVAL: Final = 1  # Minimum 1 hour
MAX_AUTO_UPDATE_INTERVAL: Final = 6  # Maximum 6 hours
MIN_REFRESH_COOLDOWN: Final = 5  # Minimum 5 minutes
MAX_REFRESH_COOLDOWN: Final = 30  # Maximum 30 minutes

# NEU: Alias, weil __init__.py DEFAULT_SCAN_INTERVAL importiert
DEFAULT_SCAN_INTERVAL: Final = DEFAULT_POLL_INTERVAL

# Paket mit Defaults (praktisch für ConfigFlow/Setup)
DEFAULT_OPTIONS: Final = {
    OPT_AUTO_UPDATE_INTERVAL: DEFAULT_AUTO_UPDATE_INTERVAL,
    OPT_ENABLE_SCHEDULE: DEFAULT_ENABLE_SCHEDULE,
    OPT_ENABLE_HOMEWORK: DEFAULT_ENABLE_HOMEWORK,
    OPT_ENABLE_EXAMS: DEFAULT_ENABLE_EXAMS,
    OPT_ENABLE_GRADES: DEFAULT_ENABLE_GRADES,
    OPT_RANGE_PAST_DAYS: DEFAULT_RANGE_PAST_DAYS,
    OPT_RANGE_FUTURE_DAYS: DEFAULT_RANGE_FUTURE_DAYS,
    OPT_REFRESH_COOLDOWN: DEFAULT_REFRESH_COOLDOWN,
    OPT_DEBUG_DUMPS: DEFAULT_DEBUG_DUMPS,
    # Legacy option (for backward compatibility)
    OPT_POLL_INTERVAL: DEFAULT_POLL_INTERVAL,
}

# Plattformen
PLATFORMS: Final = ["sensor", "todo", "calendar", "button"]

# Debug-Verzeichnisname
DUMP_DIR_NAME: Final = "debug"

# API URLs
CALLS_URL: Final = "https://login.schulmanager-online.de/api/calls"
