"""MCP-style tool definitions for the Chrome CDP agent."""

TOOLS = [
    {
        "name": "session_start",
        "task_type": "session_start",
        "description": "Create/start a Chrome session with name and URL",
        "parameters": {
            "name": "Session name",
            "url": "Start URL (required)",
            "port": "CDP port (optional, auto-assigned)",
        },
    },
    {
        "name": "session_stop",
        "task_type": "session_stop",
        "description": "Stop a Chrome session",
        "parameters": {"name": "Session name", "session_id": "Or session ID"},
    },
    {
        "name": "session_list",
        "task_type": "session_list",
        "description": "List all Chrome sessions",
        "parameters": {},
    },
    {
        "name": "browser_navigate",
        "task_type": "browser_navigate",
        "description": "Navigate to URL (starts session if needed)",
        "parameters": {
            "url": "Target URL (required)",
            "name": "Session name (default: agent)",
            "port": "CDP port if session exists",
            "wait": "Seconds to wait after navigation",
        },
    },
    {
        "name": "browser_get_content",
        "task_type": "browser_get_content",
        "description": "Get page content (text, html, or links)",
        "parameters": {
            "port": "CDP port",
            "name": "Session name",
            "format": "text | html | links",
            "url": "Navigate first if provided",
        },
    },
    {
        "name": "browser_execute_js",
        "task_type": "browser_execute_js",
        "description": "Execute JavaScript in the page",
        "parameters": {
            "script": "JS code (required)",
            "port": "CDP port",
            "name": "Session name",
            "await_promise": "Wait for async result",
        },
    },
    {
        "name": "browser_click",
        "task_type": "browser_click",
        "description": "Click an element by CSS selector",
        "parameters": {"selector": "CSS selector", "port": "CDP port", "name": "Session name"},
    },
    {
        "name": "browser_fill",
        "task_type": "browser_fill",
        "description": "Fill an input by CSS selector",
        "parameters": {
            "selector": "CSS selector",
            "value": "Value to fill",
            "port": "CDP port",
            "name": "Session name",
        },
    },
    {
        "name": "browser_extract",
        "task_type": "browser_extract",
        "description": "Extract structured job/page data from current page",
        "parameters": {"port": "CDP port", "name": "Session name", "url": "Navigate first"},
    },
    {
        "name": "browser_run_script",
        "task_type": "browser_run_script",
        "description": "Run a scripts-library JS file",
        "parameters": {
            "script": "Script name e.g. unstop/get-job-list",
            "params": "Optional params dict",
            "port": "CDP port",
            "name": "Session name",
        },
    },
    {
        "name": "agent_act",
        "task_type": "agent_act",
        "description": "Context-driven multi-step Chrome actions (MCP agent)",
        "parameters": {
            "context": "Preset: fetch_page | unstop_jobs | unstop_hackathons | custom",
            "url": "Override URL",
            "name": "Session name",
            "port": "CDP port",
            "actions": "Explicit action list (overrides context preset)",
        },
    },
]


def list_tools() -> list[dict]:
    return TOOLS
