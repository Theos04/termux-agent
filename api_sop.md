# Chrome CDP Module SOP

Standard operating procedure for building wrapper modules on top of the existing
Chrome session stack (`cdpv119.py` → `daemon.py` → `api.py`). Read this before
writing a new module. It defines the architecture, the contract every module
must follow, and a copy-paste template.

---

## 1. Architecture recap

```
cdpv119.py   Session lifecycle (create/start/stop/list/health), SQLite (SessionDB),
             VNC/X11 display, writes session_info.json (port, pid, current_ws_id).

daemon.py    ChromeDaemon — reads session_info.json, owns the WebSocket connection
             to Chrome per session name, exposes async CDP primitives
             (navigate, evaluate, click, screenshot, execute_cdp_command).

api.py       ChromeAPI — aiohttp REST layer over ChromeDaemon.
             Routes are keyed by session {name}, e.g. /session/{name}/evaluate.
```

**A module never talks to Chrome directly.** It always goes through
`ChromeDaemon.execute_cdp_command(session_name, method, params)` (or the
higher-level helpers `navigate` / `evaluate` / `click` / `get_html` /
`get_url` / `screenshot`), either:

- **in-process**, by importing `ChromeDaemon` and calling it directly, or
- **over HTTP**, by calling the running `api.py` server on its port.

Use in-process when your module lives inside the same daemon/worker. Use HTTP
when your module is a separate script, cron job, or external service.

## 2. Ports and session identity

- Sessions are identified by **name**, not port. Ports are dynamic —
  `cdpv119.py` reassigns them if the configured port is busy.
- Always resolve the current port/`ws_id` at call time from
  `session_info.json` (via `daemon.get_session(name)` or
  `GET /session/{name}/status`). Never hardcode a port in a module.
- A module should accept the **session name** as a parameter (default it if
  the module is single-purpose, e.g. `"unstop"`), not a port number.
- `session_info.json` location:
  `/data/data/com.termux/files/home/chrome-sessions/session_info.json`

## 3. The scripts-library convention

All reusable browser-side JavaScript lives in:

```
/data/data/com.termux/files/home/automation/chrome-launcher/scripts-library/
```

Rules for anything placed there:

1. **One file per script**, named `snake_case.js`.
2. The file's contents must be a **single IIFE expression** that CDP's
   `Runtime.evaluate` can evaluate and that returns a JSON-serializable value:
   ```js
   (function(args) {
     // args is injected by the caller as a JSON literal, or undefined
     try {
       // ... do work against `document` / `window` ...
       return { success: true, data: /* ... */ };
     } catch (e) {
       return { success: false, error: String(e) };
     }
   })(%%ARGS%%)
   ```
3. Scripts must **never** `throw` uncaught — always resolve to
   `{success, data|error}` so the module layer can branch on it without a
   try/catch around JSON parsing.
4. Scripts must be **idempotent** and **side-effect aware** — assume they can
   be run more than once on the same page.
5. Keep scripts DOM-only. No `fetch` to third-party origins from inside page
   context unless that's explicitly the script's job (CORS/CSP will bite you
   otherwise) — prefer doing network calls from the Python module.

## 4. Module contract

Every wrapper module must expose the same shape so modules are interchangeable
and composable:

```python
class MyModule:
    """One line description of what this module automates."""

    def __init__(self, daemon: "ChromeDaemon", session_name: str = "unstop"):
        self.daemon = daemon
        self.session = session_name

    async def run(self, **kwargs) -> dict:
        """
        Returns:
            {"success": bool, "data": <json-serializable> | None, "error": str | None}
        """
        raise NotImplementedError
```

Requirements:

- **Never** raise out of `run()`. Catch everything, return
  `{"success": False, "error": str(e)}`.
- **Always** return plain JSON-serializable data — the API layer wraps your
  return value directly in `web.json_response(...)`.
- **Timeouts**: rely on `ChromeDaemon.execute_cdp_command`'s built-in 30s
  timeout. If your flow needs longer (e.g. waiting on a slow page action),
  poll in a loop with your own short-interval checks rather than raising the
  underlying CDP timeout.
- **No global state.** A module instance is scoped to one session name. If you
  need multi-session orchestration, instantiate one module per session and
  fan out with `asyncio.gather`.

## 5. Running a script from the library

Standard helper every module should reuse (put it in a shared `lib.py`, don't
duplicate it):

```python
import json
from pathlib import Path

SCRIPTS_DIR = Path("/data/data/com.termux/files/home/automation/chrome-launcher/scripts-library")

async def run_library_script(daemon, session_name: str, script_name: str, args: dict | None = None) -> dict:
    """Load a .js file from scripts-library, inject args, evaluate it in the page."""
    path = SCRIPTS_DIR / f"{script_name}.js"
    if not path.exists():
        return {"success": False, "error": f"script not found: {path}"}

    js = path.read_text()
    js = js.replace("%%ARGS%%", json.dumps(args or {}))

    result = await daemon.evaluate(session_name, js)

    # Unwrap CDP's Runtime.evaluate envelope
    try:
        value = result["result"]["result"]["value"]
    except (KeyError, TypeError):
        return {"success": False, "error": f"unexpected CDP response: {result}"}

    if isinstance(value, dict) and "success" in value:
        return value
    return {"success": True, "data": value}
```

Every module's `run()` should call `run_library_script(...)` rather than
inlining JS strings — inline JS is only acceptable for one-off glue that isn't
reusable enough to belong in the library.

## 6. Module template (copy this to start a new module)

```python
# modules/my_module.py
from lib import run_library_script

class MyModule:
    """<one-line description>"""

    SCRIPT = "my_module_script"  # matches scripts-library/my_module_script.js

    def __init__(self, daemon, session_name: str = "unstop"):
        self.daemon = daemon
        self.session = session_name

    async def run(self, **kwargs) -> dict:
        try:
            result = await run_library_script(self.daemon, self.session, self.SCRIPT, kwargs)
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}
```

Companion script:

```js
// scripts-library/my_module_script.js
(function(args) {
  try {
    // args.<whatever you passed from Python>
    return { success: true, data: null };
  } catch (e) {
    return { success: false, error: String(e) };
  }
})(%%ARGS%%)
```

## 7. Exposing a module over the API

Add one route in `api.py`, delegating to the module — don't put module logic
in `api.py` itself:

```python
from modules.my_module import MyModule

# in setup_routes():
self.app.router.add_post('/session/{name}/my-module', self.run_my_module)

# handler:
async def run_my_module(self, request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    name = request.match_info['name']
    module = MyModule(self.daemon, name)
    result = await module.run(**data)
    status = 200 if result.get('success') else 500
    return web.json_response(result, status=status)
```

## 8. Checklist before merging a new module

- [ ] Module class follows the `run(**kwargs) -> dict` contract (§4)
- [ ] No hardcoded ports; session resolved by name
- [ ] Uses `run_library_script`, not inline JS strings, for anything reusable
- [ ] Corresponding `.js` file added to `scripts-library/`, IIFE, never throws
- [ ] `run()` never raises — all errors caught and returned as
      `{"success": False, "error": ...}`
- [ ] Added exactly one route in `api.py` that delegates to the module
- [ ] Manually tested against a live session: `curl -X POST
      http://127.0.0.1:5000/session/<name>/<route>`

## 9. Common CDP methods you'll reuse

| Purpose            | Method                     | Notes                              |
|---------------------|----------------------------|-------------------------------------|
| Navigate            | `Page.navigate`            | wrapped by `daemon.navigate`        |
| Run JS              | `Runtime.evaluate`         | wrapped by `daemon.evaluate`        |
| Screenshot          | `Page.captureScreenshot`   | wrapped by `daemon.screenshot`      |
| Get cookies         | `Network.getCookies`       | call via `execute_cdp_command`      |
| Set cookies         | `Network.setCookie`        | call via `execute_cdp_command`      |
| Wait for load event | `Page.loadEventFired`      | requires event subscription, not a simple round-trip — build a dedicated listener if needed |

For anything not already wrapped in `daemon.py`, call
`daemon.execute_cdp_command(session_name, method, params)` directly rather
than adding a one-off wrapper method to `ChromeDaemon` unless it will be
reused by 2+ modules.
