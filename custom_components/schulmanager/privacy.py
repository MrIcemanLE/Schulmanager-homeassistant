"""Pseudonymize personal data in logs, debug dumps and diagnostics.

After login, the account's own identifiers (parent, children, school) are
registered and consistently replaced by placeholders such as "<Kind 1>", so
logs stay useful for troubleshooting without naming anyone. Free text (letters,
homework, messages) can still mention other people; diagnostics drop it.
"""

from collections.abc import Mapping
import logging
import re
from typing import Any

from .util import normalize_student_slug

_PACKAGE_LOGGER = logging.getLogger(__name__.rpartition(".")[0])

# Redacted in structured data regardless of the value; address fields come
# from the school's master data, dumped before they can be registered
SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "city",
        "email",
        "fax",
        "firstname",
        "hash",
        "jwt",
        "lastname",
        "ldapusername",
        "localusername",
        "logodidactusername",
        "password",
        "phone",
        "sex",
        "street",
        "token",
        "username",
        "website",
        "zipcode",
    }
)
# Free text that may name other people; dropped from diagnostics
FREE_TEXT_KEYS = frozenset(
    {
        "body",
        "comment",
        "content",
        "description",
        "informationtext",
        "message",
        "note",
        "substitutiontext",
        "text",
    }
)
_ADDRESS_KEYS = frozenset({"street", "zipcode", "city"})
REDACTED = "**REDACTED**"
_MIN_NAME_LENGTH = 3
# Letters that make up a word; "_" and "." count as separators (entity ids, file names)
_WORD_CHARS = "A-Za-z0-9ÄÖÜäöüß"


class _Registry:
    """Known identifiers of all set up accounts, mapped to stable placeholders."""

    def __init__(self) -> None:
        self.placeholders: dict[str, str] = {}
        self.ids: dict[int, str] = {}
        self._student_numbers: dict[int, int] = {}
        self._pattern: re.Pattern[str] | None = None

    def clear(self) -> None:
        self.placeholders.clear()
        self.ids.clear()
        self._student_numbers.clear()
        self._pattern = None

    def add(self, value: Any, placeholder: str) -> None:
        text = str(value).strip() if value is not None else ""
        min_length = 3 if text.isdigit() else _MIN_NAME_LENGTH
        if len(text) < min_length or text.lower() in self.placeholders:
            return
        self.placeholders[text.lower()] = placeholder
        if text.isdigit():
            self.ids[int(text)] = placeholder
        self._pattern = None

    def student_number(self, student_id: int) -> int:
        return self._student_numbers.setdefault(
            student_id, len(self._student_numbers) + 1
        )

    @property
    def pattern(self) -> re.Pattern[str] | None:
        if self._pattern is None and self.placeholders:
            # Longest first, so "Max Mustermann" wins over "Max"
            alternatives = sorted(self.placeholders, key=len, reverse=True)
            self._pattern = re.compile(
                rf"(?<![{_WORD_CHARS}])(?:"
                + "|".join(re.escape(value) for value in alternatives)
                + rf")(?![{_WORD_CHARS}])",
                re.IGNORECASE,
            )
        return self._pattern


_registry = _Registry()


def debug_enabled() -> bool:
    """Return True while debug logging is enabled for the integration.

    Follows Home Assistant's "Enable debug logging" toggle and the `logger:`
    configuration, without needing a reload.
    """
    return _PACKAGE_LOGGER.isEnabledFor(logging.DEBUG)


def _student_records(user: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    records = [
        parent["student"]
        for parent in user.get("associatedParents") or []
        if isinstance(parent, Mapping) and isinstance(parent.get("student"), Mapping)
    ]
    if isinstance(user.get("associatedStudent"), Mapping):
        records.append(user["associatedStudent"])
    records.extend(
        record
        for record in user.get("associatedStudents") or []
        if isinstance(record, Mapping)
    )
    return records


def _add_person(record: Mapping[str, Any], name_placeholder: str) -> None:
    firstname = record.get("firstname")
    lastname = record.get("lastname")
    if firstname and lastname:
        full_name = f"{firstname} {lastname}"
        _registry.add(full_name, name_placeholder)
        # Entity ids and device slugs, e.g. "joerg_mueller"
        _registry.add(normalize_student_slug(full_name), name_placeholder)
    for value, placeholder in ((firstname, name_placeholder), (lastname, "<Nachname>")):
        if value:
            _registry.add(value, placeholder)
            _registry.add(normalize_student_slug(str(value)), placeholder)


def register_account(user: Mapping[str, Any]) -> None:
    """Register the parent/student identifiers of a login response's user object."""
    students = sorted(
        (record for record in _student_records(user) if record.get("id") is not None),
        key=lambda record: int(record["id"]),
    )
    for record in students:
        number = _registry.student_number(int(record["id"]))
        _add_person(record, f"<Kind {number}>")
        _registry.add(record["id"], f"<Kind {number} ID>")

    own_id = user.get("id")
    is_student_login = any(
        own_id is not None and str(own_id) == str(record.get("id"))
        for record in students
    )
    if not is_student_login:
        _add_person(user, "<Elternteil>")
        _registry.add(own_id, "<Eltern-ID>")
    _registry.add(user.get("email"), "<E-Mail>")
    _registry.add(user.get("username"), "<Benutzername>")


# Institution master data fields (get-institution) that reveal where the family lives
_SCHOOL_DETAIL_PLACEHOLDERS = {
    "street": "<Schuladresse>",
    "zipcode": "<PLZ>",
    "city": "<Schulort>",
    "website": "<Schul-Website>",
    "email": "<Schul-E-Mail>",
    "phone": "<Schul-Telefon>",
    "fax": "<Schul-Telefon>",
}


def register_school(
    institution_id: Any,
    name: Any = None,
    details: Mapping[str, Any] | None = None,
) -> None:
    """Register a school's id, name and address details."""
    _registry.add(institution_id, "<Schul-ID>")
    _registry.add(name, "<Schule>")
    for key, placeholder in _SCHOOL_DETAIL_PLACEHOLDERS.items():
        value = (details or {}).get(key)
        _registry.add(value, placeholder)
        if key == "website" and isinstance(value, str):
            _registry.add(value.removeprefix("www."), placeholder)


def register_user_id(user_id: Any) -> None:
    """Register an account id known before login (multi-school accounts)."""
    _registry.add(user_id, "<Eltern-ID>")


def clear_registry() -> None:
    """Forget all registered identifiers (used by tests)."""
    _registry.clear()


def redact_text(text: str) -> str:
    """Replace all registered identifiers in a text by their placeholders."""
    pattern = _registry.pattern
    if pattern is None or not text:
        return text
    return pattern.sub(
        lambda match: _registry.placeholders[match.group(0).lower()], text
    )


def redact_data(data: Any, *, drop_free_text: bool = False) -> Any:
    """Return a copy of JSON-like data with personal data pseudonymized."""
    if isinstance(data, Mapping):
        # A record with an address (the school's master data) is named by "name"
        is_address = any(str(key).lower() in _ADDRESS_KEYS for key in data)
        redacted: dict[Any, Any] = {}
        for key, value in data.items():
            lower_key = str(key).lower()
            if (
                lower_key in SENSITIVE_KEYS or (is_address and lower_key == "name")
            ) and value not in (None, ""):
                redacted[key] = REDACTED
            elif drop_free_text and lower_key in FREE_TEXT_KEYS and value:
                redacted[key] = f"<Text, {len(str(value))} Zeichen>"
            else:
                redacted[key] = redact_data(value, drop_free_text=drop_free_text)
        return redacted
    if isinstance(data, (list, tuple)):
        return [redact_data(item, drop_free_text=drop_free_text) for item in data]
    if isinstance(data, str):
        return redact_text(data)
    if isinstance(data, int) and not isinstance(data, bool):
        return _registry.ids.get(data, data)
    return data


def safe_filename(name: str) -> str:
    """Pseudonymize a dump file or folder name and keep it filesystem-friendly."""
    return re.sub(r"[<> ]", "", redact_text(name))


class RedactingFilter(logging.Filter):
    """Pseudonymize log messages of the integration."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Rewrite the message in place; never drops a record."""
        if _registry.pattern is None:
            return True
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - a broken log call must not break logging
            return True
        redacted = redact_text(message)
        if redacted != message:
            record.msg = redacted
            record.args = None
        return True


_FILTER = RedactingFilter()


def get_logger(name: str) -> logging.Logger:
    """Return a module logger with pseudonymization.

    Logger filters only apply to records of that exact logger, not its
    children, so every module needs its own.
    """
    logger = logging.getLogger(name)
    if _FILTER not in logger.filters:
        logger.addFilter(_FILTER)
    return logger
