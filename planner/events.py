"""Event bus for inter-component communication"""
from typing import Dict, List, Any, Callable, Optional
from datetime import datetime
from dataclasses import dataclass, field
import uuid

@dataclass
class Event:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    type: str = ""
    source: str = ""
    payload: Any = None
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "source": self.source,
            "payload": str(self.payload)[:200] if self.payload else None,
            "timestamp": self.timestamp.isoformat()
        }

class EventBus:
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._events: List[Event] = []
        self._max_events = 1000
    
    def subscribe(self, event_type: str, callback: Callable) -> None:
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)
    
    def publish(self, event: Event) -> None:
        self._events.append(event)
        if len(self._events) > self._max_events:
            self._events = self._events[-self._max_events:]
        
        if event.type in self._subscribers:
            for callback in self._subscribers[event.type]:
                try:
                    callback(event)
                except Exception as e:
                    print(f"Error in subscriber: {e}")
    
    def get_events(self, event_type: Optional[str] = None, limit: int = 100) -> List[Event]:
        if event_type:
            return [e for e in self._events[-limit:] if e.type == event_type]
        return self._events[-limit:]

_event_bus = EventBus()
def get_event_bus() -> EventBus:
    return _event_bus
