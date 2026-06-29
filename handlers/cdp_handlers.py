"""CDP handlers — direct imports via cdpv116 + fetch_page2 (no subprocess)."""

from typing import Any, Optional

from agent.registry import register_handler, register_subscriber
from agent.events import Event
from agent.chrome_service import (
    ensure_session,
    stop_session,
    list_sessions,
    get_browser,
    browser_session,
)
from agent.script_manager import get_script_manager


def _session_name(payload: dict) -> str:
    return payload.get("name", "agent")


def _default_url(payload: dict) -> str:
    return payload.get("url") or "about:blank"


def _port_from_payload(payload: dict, after_navigate: bool = False) -> int:
    if payload.get("port"):
        return int(payload["port"])
    name = _session_name(payload)
    for s in list_sessions():
        if s["name"] == name and s["status"] == "running":
            return s["port"]
    if after_navigate:
        for s in list_sessions():
            if s["name"] == name:
                return s["port"]
    raise ValueError(f"No running session '{name}'. Use session_start or browser_navigate first.")


# --- Session tools ---

def handle_session_start(payload: dict) -> dict:
    name = payload.get("name", "agent")
    url = payload.get("url")
    if not url:
        raise ValueError("url is required")
    return ensure_session(
        name=name,
        url=url,
        port=payload.get("port"),
        stabilize=float(payload.get("wait", 5)),
    )


def handle_session_stop(payload: dict) -> dict:
    return stop_session(name=payload.get("name"), session_id=payload.get("session_id"))


def handle_session_list(payload: dict) -> dict:
    sessions = list_sessions()
    return {"sessions": sessions, "count": len(sessions)}


def handle_browser_navigate(payload: dict) -> dict:
    url = payload.get("url")
    if not url:
        raise ValueError("url is required")
    name = _session_name(payload)
    info = ensure_session(name, _default_url(payload), port=payload.get("port"))
    browser = get_browser(info["port"])
    result = browser.navigate(url, wait=float(payload.get("wait", 3)))
    return {"session": info, "navigation": result}


def handle_browser_get_content_on_browser(browser, fmt: str, max_chars: int) -> dict:
    return browser.get_content(fmt=fmt, max_chars=max_chars)


def handle_browser_get_content(payload: dict) -> dict:
    fmt = payload.get("format", "text")
    if payload.get("url"):
        handle_browser_navigate({**payload, "wait": payload.get("wait", 3)})
    port = _port_from_payload(payload, after_navigate=bool(payload.get("url")))
    browser = get_browser(port)
    return browser.get_content(fmt=fmt, max_chars=payload.get("max_chars", 50000))


def handle_browser_execute_js(payload: dict) -> dict:
    script = payload.get("script") or payload.get("js")
    if not script:
        raise ValueError("script is required")
    if payload.get("url"):
        handle_browser_navigate(payload)
    port = _port_from_payload(payload, after_navigate=bool(payload.get("url")))
    browser = get_browser(port)
    result = browser.execute_js(script, await_promise=payload.get("await_promise", False))
    return {"port": port, "result": result}


def handle_browser_click(payload: dict) -> dict:
    selector = payload.get("selector")
    if not selector:
        raise ValueError("selector is required")
    browser = get_browser(_port_from_payload(payload))
    return browser.click(selector)


def handle_browser_fill(payload: dict) -> dict:
    selector = payload.get("selector")
    value = payload.get("value", "")
    if not selector:
        raise ValueError("selector is required")
    browser = get_browser(_port_from_payload(payload))
    return browser.fill(selector, value)


def handle_browser_extract(payload: dict) -> dict:
    if payload.get("url"):
        handle_browser_navigate(payload)
    browser = get_browser(_port_from_payload(payload, after_navigate=bool(payload.get("url"))))
    return browser.extract()


def handle_browser_run_script(payload: dict) -> dict:
    script_name = payload.get("script")
    if not script_name:
        raise ValueError("script is required")
    if payload.get("url"):
        handle_browser_navigate(payload)
    port = _port_from_payload(payload, after_navigate=bool(payload.get("url")))
    browser = get_browser(port)
    sm = get_script_manager()
    result = sm.execute(script_name, browser, payload.get("params"))
    return {
        "script": script_name,
        "port": port,
        "result": result,
        "available_scripts": sm.list_scripts(),
    }


def handle_echo(payload: dict) -> dict:
    return {"echo": payload, "status": "ok", "mode": "cdp-direct"}


def _log_failures(event: Event) -> None:
    if event.event_type in ("task.failed", "task.timeout"):
        print(f"[cdp-agent] {event.event_type}: {event.payload}")


# Session
register_handler("session_start", handle_session_start)
register_handler("session_stop", handle_session_stop)
register_handler("session_list", handle_session_list)

# Browser (MCP tools)
register_handler("browser_navigate", handle_browser_navigate)
register_handler("browser_get_content", handle_browser_get_content)
register_handler("browser_execute_js", handle_browser_execute_js)
register_handler("browser_click", handle_browser_click)
register_handler("browser_fill", handle_browser_fill)
register_handler("browser_extract", handle_browser_extract)
register_handler("browser_run_script", handle_browser_run_script)

# Legacy aliases → new handlers
register_handler("launch_chrome", lambda p: handle_session_start({
    **p, "url": p.get("url", "about:blank"),
}))
register_handler("fetch_page", handle_browser_get_content)
register_handler("fetch_page2", handle_browser_get_content)
register_handler("fetch_page_llm", handle_browser_get_content)
register_handler("run_js", handle_browser_execute_js)
register_handler("unstop_list", lambda p: handle_browser_navigate({
    **p,
    "url": p.get("url", "https://unstop.com/internships"),
    "name": p.get("name", "unstop"),
}))
register_handler("web_scrape", handle_browser_get_content)
register_handler("dynamic_js", handle_browser_execute_js)
register_handler("cdp", handle_session_start)
register_handler("shell", handle_browser_execute_js)
register_handler("echo", handle_echo)

register_subscriber("task.failed", _log_failures)
register_subscriber("task.timeout", _log_failures)
