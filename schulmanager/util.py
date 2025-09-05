
from __future__ import annotations

import re
import unicodedata

GERMAN_MAP = {
    "ä": "ae",
    "ö": "oe",
    "ü": "ue",
    "Ä": "Ae",
    "Ö": "Oe",
    "Ü": "Ue",
    "ß": "ss",
}

def normalize_student_slug(name: str) -> str:
    for k,v in GERMAN_MAP.items():
        name = name.replace(k, v)
    name = unicodedata.normalize("NFKD", name)
    name = "".join(ch for ch in name if not unicodedata.combining(ch))
    name = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").lower()
    if not name:
        name = "schueler"
    return name[:60]
