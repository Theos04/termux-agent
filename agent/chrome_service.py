"""Chrome session service — singleton cdpv116 manager + browser connections."""

import os
import threading
import time
from contextlib import contextmanager
from typing import Any, Generator, Optional

from agent.cdp_browser import CDPBrowser

_manager = None
_manager_lock = threading.Lock()
_browsers: dict[int, CDPBrowser] = {}
_browsers_lock = threading.Lock()


def get_session_manager():
    """Lazy singleton ChromeSessionManager from cdpv116."""
    global _manager
    with _manager_lock:
        if _manager is None:
            from cdpv116 import ChromeSessionManager
            _manager = ChromeSessionManager()
        return _manager


def ensure_session(
    name: str,
    url: str,
    port: Optional[int] = None,
    start: bool = True,
    stabilize: float = 5.0,
) -> dict[str, Any]:
    """Create or resume a Chrome session with the given name and start URL."""
    mgr = get_session_manager()
    session = mgr.db.get_session_by_name(name)

    if session:
        sid = session["id"]
        if start and session["status"] != "running":
            mgr.start_session(sid)
            time.sleep(stabilize)
        session = mgr.db.get_session(sid)
    else:
        assigned_port = port or mgr._get_next_port()
        profile_dir = os.path.join(mgr.config.base_profile_dir, name)
        os.makedirs(profile_dir, exist_ok=True)
        sid = mgr.db.create_session(name, url, assigned_port, profile_dir)
        if start:
            mgr.start_session(sid)
            time.sleep(stabilize)
        session = mgr.db.get_session(sid)

    return {
        "session_id": session["id"],
        "name": session["name"],
        "port": session["port"],
        "url": session["url"],
        "status": session["status"],
    }


def stop_session(name: Optional[str] = None, session_id: Optional[int] = None) -> dict:
    mgr = get_session_manager()
    if session_id:
        session = mgr.db.get_session(session_id)
    elif name:
        session = mgr.db.get_session_by_name(name)
    else:
        raise ValueError("name or session_id required")

    if not session:
        raise ValueError("Session not found")

    with _browsers_lock:
        _browsers.pop(session["port"], None)

    mgr.stop_session(session["id"])
    return {"stopped": session["id"], "name": session["name"]}


def list_sessions() -> list[dict]:
    mgr = get_session_manager()
    return mgr.db.list_sessions()


def get_browser(port: int, reconnect: bool = False) -> CDPBrowser:
    with _browsers_lock:
        browser = _browsers.get(port)
        if browser and browser.connected and not reconnect:
            return browser

        browser = CDPBrowser(port)
        if not browser.connect():
            raise RuntimeError(f"Cannot connect to Chrome on port {port}")
        _browsers[port] = browser
        return browser


@contextmanager
def browser_session(
    name: str,
    url: str,
    port: Optional[int] = None,
) -> Generator[tuple[dict, CDPBrowser], None, None]:
    """Context: ensure session running, yield (session_info, browser)."""
    info = ensure_session(name, url, port=port)
    browser = get_browser(info["port"])
    try:
        yield info, browser
    finally:
        pass  # keep session alive for reuse
