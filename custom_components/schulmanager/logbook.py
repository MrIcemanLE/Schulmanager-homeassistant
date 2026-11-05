"""Describe Schulmanager logbook events."""

from collections.abc import Callable

from homeassistant.components.logbook import (
    LOGBOOK_ENTRY_ENTITY_ID,
    LOGBOOK_ENTRY_MESSAGE,
    LOGBOOK_ENTRY_NAME,
)
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import Event, HomeAssistant, callback

from .classbook import EVENT_CLASSBOOK_NEW
from .const import DOMAIN


@callback
def async_describe_events(
    hass: HomeAssistant,
    async_describe_event: Callable[
        [str, str, Callable[[Event], dict[str, str | None]]], None
    ],
) -> None:
    """Describe logbook events."""

    @callback
    def async_describe_classbook_entry(event: Event) -> dict[str, str | None]:
        """Describe a new class book entry."""
        data = event.data
        source = ", ".join(x for x in (data.get("subject"), data.get("teacher")) if x)
        message = f"Klassenbuch: {data.get('type')}"
        if source:
            message += f" ({source})"
        if data.get("text"):
            message += f": {data['text']}"
        return {
            LOGBOOK_ENTRY_NAME: data.get("student_name"),
            LOGBOOK_ENTRY_MESSAGE: message,
            LOGBOOK_ENTRY_ENTITY_ID: data.get(ATTR_ENTITY_ID),
        }

    async_describe_event(DOMAIN, EVENT_CLASSBOOK_NEW, async_describe_classbook_entry)
