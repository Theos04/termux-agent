import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from .database import Database


@dataclass
class Event:
    event_type: str
    payload: dict = field(default_factory=dict)
    source: Optional[str] = None
    id: Optional[int] = None
    created_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "event_type": self.event_type,
            "source": self.source,
            "payload": self.payload,
            "created_at": self.created_at,
        }


EventHandler = Callable[[Event], None]


class EventBus:
    """Thread-safe event bus with database persistence."""

    def __init__(self, db: Database):
        self._db = db
        self._subscribers: dict[str, list[EventHandler]] = {}
        self._global_subscribers: list[EventHandler] = []
        self._lock = threading.Lock()

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        with self._lock:
            self._subscribers.setdefault(event_type, []).append(handler)

    def subscribe_all(self, handler: EventHandler) -> None:
        with self._lock:
            self._global_subscribers.append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        with self._lock:
            handlers = self._subscribers.get(event_type, [])
            if handler in handlers:
                handlers.remove(handler)

    def emit(
        self,
        event_type: str,
        payload: Optional[dict] = None,
        source: Optional[str] = None,
    ) -> Event:
        payload = payload or {}
        event_id = self._db.insert_event(event_type, payload, source)
        now = datetime.now(timezone.utc).isoformat()
        event = Event(
            event_type=event_type,
            payload=payload,
            source=source,
            id=event_id,
            created_at=now,
        )

        with self._lock:
            handlers = list(self._global_subscribers)
            handlers.extend(self._subscribers.get(event_type, []))
            handlers.extend(self._subscribers.get("*", []))

        for handler in handlers:
            try:
                handler(event)
            except Exception as exc:
                self._db.insert_event(
                    "handler.error",
                    {"event_type": event_type, "error": str(exc)},
                    source="event_bus",
                )

        return event

    def get_history(
        self,
        event_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        return self._db.get_events(event_type, limit, offset)
