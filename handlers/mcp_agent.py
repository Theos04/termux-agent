"""MCP-style context agent — multi-step Chrome actions based on context."""

from typing import Any

from agent.registry import register_handler
from agent.chrome_service import ensure_session, get_browser
from handlers.cdp_handlers import (
    handle_browser_get_content_on_browser,
    handle_browser_navigate,
    handle_browser_run_script,
)


# Context presets: goal → action sequence
CONTEXT_PRESETS: dict[str, dict] = {
    "fetch_page": {
        "url": None,  # must be provided in payload
        "actions": [
            {"type": "navigate"},
            {"type": "get_content", "format": "text"},
        ],
    },
    "fetch_html": {
        "url": None,
        "actions": [
            {"type": "navigate"},
            {"type": "get_content", "format": "html"},
        ],
    },
    "fetch_links": {
        "url": None,
        "actions": [
            {"type": "navigate"},
            {"type": "get_content", "format": "links"},
        ],
    },
    "unstop_jobs": {
        "url": "https://unstop.com/internships",
        "name": "unstop",
        "actions": [
            {"type": "navigate"},
            {"type": "wait", "selector": "a", "timeout": 10},
            {"type": "get_content", "format": "text"},
            {"type": "extract"},
        ],
    },
    "unstop_hackathons": {
        "url": "https://unstop.com/hackathons",
        "name": "unstop",
        "actions": [
            {"type": "navigate"},
            {"type": "get_content", "format": "text"},
            {"type": "extract"},
        ],
    },
    "unstop_opportunities": {
        "url": "https://unstop.com/opportunities",
        "name": "unstop",
        "actions": [
            {"type": "navigate"},
            {"type": "run_script", "script": "unstop/get-job-list"},
        ],
    },
}


def _execute_action(action: dict, payload: dict, browser, port: int) -> dict:
    atype = action["type"]

    if atype == "navigate":
        url = action.get("url") or payload.get("url")
        if not url:
            raise ValueError("navigate requires url in action or payload")
        return browser.navigate(url, wait=float(action.get("wait", 3)))

    if atype == "get_content":
        fmt = action.get("format", "text")
        return handle_browser_get_content_on_browser(
            browser, fmt, action.get("max_chars", 50000)
        )

    if atype == "extract":
        return browser.extract()

    if atype == "execute_js":
        script = action.get("script") or action.get("js")
        return {"result": browser.execute_js(script, action.get("await_promise", False))}

    if atype == "click":
        return browser.click(action["selector"])

    if atype == "fill":
        return browser.fill(action["selector"], action.get("value", ""))

    if atype == "wait":
        return browser.wait_for(action["selector"], float(action.get("timeout", 15)))

    if atype == "run_script":
        from agent.script_manager import get_script_manager
        sm = get_script_manager()
        result = sm.execute(action["script"], browser, action.get("params"))
        return {"script": action["script"], "result": result}

    raise ValueError(f"Unknown action type: {atype}")


def handle_agent_act(payload: dict) -> dict:
    """
    MCP agent entry point.

    payload:
      context: preset name (fetch_page, unstop_jobs, ...)
      url: override URL
      name: session name
      port: CDP port
      actions: explicit action list (overrides preset)
    """
    context = payload.get("context", "custom")
    preset = CONTEXT_PRESETS.get(context, {})
    name = payload.get("name") or preset.get("name", "agent")
    url = payload.get("url") or preset.get("url")

    if not url and context in ("fetch_page", "fetch_html", "fetch_links", "custom"):
        raise ValueError(f"context '{context}' requires url in payload")

    url = url or "about:blank"
    actions = payload.get("actions") or preset.get("actions", [])

    if not actions:
        raise ValueError("No actions defined — provide actions[] or a known context")

    session = ensure_session(name, url, port=payload.get("port"))
    browser = get_browser(session["port"])

    # Navigate to start URL if first action isn't navigate
    if actions and actions[0].get("type") != "navigate" and url != "about:blank":
        browser.navigate(url, wait=float(payload.get("wait", 3)))

    results = []
    for i, action in enumerate(actions):
        step = {"step": i + 1, "action": action["type"]}
        try:
            step["result"] = _execute_action(action, payload, browser, session["port"])
            step["ok"] = True
        except Exception as exc:
            step["ok"] = False
            step["error"] = str(exc)
            results.append(step)
            return {
                "context": context,
                "session": session,
                "steps": results,
                "success": False,
                "failed_at": i + 1,
            }
        results.append(step)

    return {
        "context": context,
        "session": session,
        "steps": results,
        "success": True,
        "page": browser.page_info(),
    }


register_handler("agent_act", handle_agent_act)
register_handler("discovery", lambda p: handle_agent_act({
    **p,
    "context": p.get("context", "unstop_jobs"),
    "name": p.get("name", "unstop"),
}))
