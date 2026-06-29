from typing import Any, Callable, Optional

from .events import Event, EventBus
from .workers import TaskHandler

_handlers: dict[str, TaskHandler] = {}
_subscribers: list[tuple[str, Callable[[Event], None]]] = []


def register_handler(task_type: str, handler: TaskHandler) -> None:
    """Register a task handler (plugin entry point)."""
    _handlers[task_type] = handler


def register_subscriber(
    event_type: str, handler: Callable[[Event], None]
) -> None:
    """Register an event subscriber (plugin entry point)."""
    _subscribers.append((event_type, handler))


def get_handlers() -> dict[str, TaskHandler]:
    return dict(_handlers)


def apply_subscribers(event_bus: EventBus) -> None:
    for event_type, handler in _subscribers:
        event_bus.subscribe(event_type, handler)


def load_plugins() -> list[str]:
    """Discover and import handler modules from handlers/ package."""
    loaded = []
    try:
        import pkgutil
        import importlib
        import handlers as handlers_pkg

        for _finder, name, _ispkg in pkgutil.iter_modules(handlers_pkg.__path__):
            if name.startswith("_"):
                continue
            importlib.import_module(f"handlers.{name}")
            loaded.append(name)
    except ImportError:
        pass
    return loaded
