This is the SOP — hand it to me at the start of a new module request and I'll build straight from §6's template. Key things it locks in: modules only talk to the daemon (never Chrome directly), sessions resolved by name/port at call time (§2), all reusable JS goes in scripts-library as single IIFEs that never throw (§3), and every module returns {success, data, error} with one API route delegating to it (§4/§7).

# Chrome CDP Module SOP

Standard operating procedure for building wrapper modules on top of the
Chrome automation stack. Read this before writing a new module. It defines
the contract every module must follow, how to target a **user-declared
port**, how to run JS from the shared **scripts-library**, and a
copy-paste template to start from.

---

## 1. Stack recap

```
Chrome (--remote-debugging-port=PORT)
        │  DevTools Protocol (CDP) over WebSocket
        ▼
Session Manager (cdpv119.py)   → launches/tracks Chrome, writes session_info.json
Daemon (daemon.py)             → owns the WS connection per session, exposes
                                  navigate / evaluate / click / screenshot /
                                  execute_cdp_command
API (api.py)                   → aiohttp REST layer, routes keyed by
                                  /session/{name}/...
Your Module                    → thin wrapper, talks ONLY to the daemon
```

**A module never talks to Chrome directly.** It always goes through
`ChromeDaemon.execute_cdp_command(session_name, method, params)` (or the
helpers `navigate` / `evaluate` / `click` / `get_html` / `get_url` /
`screenshot`), either:

- **in-process** — import `ChromeDaemon` and call it directly, or
- **over HTTP** — call the running `api.py` server.

Use in-process when your module lives in the same daemon/worker process. Use
HTTP when your module is a separate script, cron job, or external service.

---

## 2. Targeting a user-declared port / session

Sessions are identified by **name**, not by a fixed port — `cdpv119.py`
reassigns ports dynamically if the configured one is busy. A module should
therefore:

1. Accept a **session name** (or, if you truly need to bind to an arbitrary
   already-running Chrome, a **port**) as a parameter — never hardcode either.
2. Resolve the current port/`ws_id` at call time from `session_info.json`, via
   `daemon.get_session(name)` or `GET /session/{name}/status`.
3. If the caller supplies a raw port instead of a session name (e.g. "attach
   to whatever's on 9235"), resolve it to a session by scanning
   `session_info.json` for a matching `port`, or fall back to hitting
   `http://127.0.0.1:{port}/json` directly to enumerate tabs — don't assume
   the port maps to CDP session `"default"`.

```python
def resolve_session_by_port(daemon, port: int) -> str | None:
    """Find the session name currently bound to a given port."""
    data = daemon.load_session_info()
    for _, session in data.get("sessions", {}).items():
        if session.get("port") == port and session.get("status") == "running":
            return session.get("name")
    return None
```

`session_info.json` location:
`/data/data/com.termux/files/home/chrome-sessions/session_info.json`

---

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
     // args is injected by the caller as a JSON literal, or {} if none
     try {
       // ... do work against `document` / `window` ...
       return { success: true, data: /* ... */ };
     } catch (e) {
       return { success: false, error: String(e) };
     }
   })(%%ARGS%%)
   ```
3. Scripts must **never** throw uncaught — always resolve to
   `{success, data|error}` so the module layer can branch without wrapping a
   try/catch around JSON parsing.
4. Scripts must be **idempotent** and **safe to re-run** on the same page.
5. Keep scripts DOM-only. No `fetch` to third-party origins from page
   context unless that's explicitly the script's job (CORS/CSP will bite) —
   do network calls from the Python module instead.
6. Scripts should be **selector-defensive**: prefer multiple fallback
   selectors, and always null-check before calling methods on a queried
   element.

---

## 4. Module contract

Every wrapper module must expose the same shape so modules stay
interchangeable and composable:

```python
class MyModule:
    """One line description of what this module automates."""

    def __init__(self, daemon: "ChromeDaemon", session_name: str = "default"):
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

- **Never raise out of `run()`.** Catch everything, return
  `{"success": False, "error": str(e)}`.
- **Always return plain JSON-serializable data** — the API layer wraps your
  return value directly in `web.json_response(...)`.
- **Timeouts**: rely on the daemon's built-in ~30s CDP timeout. If a flow
  needs longer (waiting on a slow page action), poll in a loop with short
  interval checks rather than raising the underlying CDP timeout.
- **No global state.** A module instance is scoped to one session. For
  multi-session orchestration, instantiate one module per session and fan
  out with `asyncio.gather`.
- **Session resolution happens once**, at the top of `run()` — don't
  re-resolve the port/ws_id mid-method unless recovering from a dropped
  connection.

---

## 5. Running a script from the library

Standard helper every module should reuse — put it in a shared `lib.py`,
don't duplicate it:

```python
# lib.py
import json
from pathlib import Path

SCRIPTS_DIR = Path(
    "/data/data/com.termux/files/home/automation/chrome-launcher/scripts-library"
)

async def run_library_script(
    daemon, session_name: str, script_name: str, args: dict | None = None
) -> dict:
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
inlining JS strings. Inline JS is only acceptable for one-off glue that isn't
reusable enough to belong in the library.

---

## 6. Module template (copy this to start a new module)

`modules/my_module.py`:

```python
from lib import run_library_script

class MyModule:
    """<one-line description of what this automates>"""

    SCRIPT = "my_module_script"  # matches scripts-library/my_module_script.js

    def __init__(self, daemon, session_name: str = "default"):
        self.daemon = daemon
        self.session = session_name

    async def run(self, **kwargs) -> dict:
        try:
            return await run_library_script(self.daemon, self.session, self.SCRIPT, kwargs)
        except Exception as e:
            return {"success": False, "error": str(e)}
```

Companion script, `scripts-library/my_module_script.js`:

```js
(function(args) {
  try {
    // args.<whatever you passed from Python>
    return { success: true, data: null };
  } catch (e) {
    return { success: false, error: String(e) };
  }
})(%%ARGS%%)
```

---

## 7. Exposing a module over the API

Add exactly one route in `api.py`, delegating to the module — don't put
module logic inside `api.py` itself:

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

For an out-of-process module (a standalone script hitting the HTTP API
instead of importing the daemon), call it the same way `curl` would:

```python
import requests

resp = requests.post(
    f"http://127.0.0.1:5000/session/{session_name}/my-module",
    json={"some_arg": "value"},
    timeout=35,
)
result = resp.json()
```

---

## 8. Common CDP methods you'll reuse

| Purpose            | Method                   | Notes                                                  |
|---------------------|--------------------------|---------------------------------------------------------|
| Navigate            | `Page.navigate`          | wrapped by `daemon.navigate`                             |
| Run JS              | `Runtime.evaluate`       | wrapped by `daemon.evaluate` / `run_library_script`       |
| Screenshot          | `Page.captureScreenshot` | wrapped by `daemon.screenshot`                            |
| Get cookies         | `Network.getCookies`     | call via `execute_cdp_command`                            |
| Set cookies         | `Network.setCookie`      | call via `execute_cdp_command`                            |
| Wait for load event | `Page.loadEventFired`    | needs event subscription — build a dedicated listener, not a simple round-trip |

For anything not already wrapped in `daemon.py`, call
`daemon.execute_cdp_command(session_name, method, params)` directly rather
than adding a one-off wrapper method to `ChromeDaemon`, unless it will be
reused by 2+ modules.

---

## 9. Checklist before merging a new module

- [ ] Module class follows the `run(**kwargs) -> dict` contract (§4)
- [ ] No hardcoded ports; session resolved by name (or resolved from a
      supplied port via §2) at call time
- [ ] Uses `run_library_script`, not inline JS strings, for anything reusable
- [ ] Corresponding `.js` file added to `scripts-library/`, single IIFE,
      never throws, always resolves `{success, data|error}`
- [ ] `run()` never raises — all errors caught and returned as
      `{"success": False, "error": ...}`
- [ ] Added exactly one route in `api.py` that delegates to the module
- [ ] Manually tested against a live session:
      `curl -X POST http://127.0.0.1:5000/session/<name>/<route> -d '{...}'`

---

## 10. Quick test loop

```bash
# API alive?
curl http://127.0.0.1:5000/health

# What sessions exist / what port are they on?
curl http://127.0.0.1:5000/sessions

# Sanity-check the session your module targets
curl http://127.0.0.1:5000/session/<name>/status

# Exercise your new module route
curl -X POST http://127.0.0.1:5000/session/<name>/<your-route> \
  -H "Content-Type: application/json" \
  -d '{"key": "value"}'
```

If a module fails, check in this order: (1) is the session `running` in
`session_info.json`, (2) does it have a `current_ws_id`, (3) does the
`.js` file exist and parse as valid JS on its own, (4) did `run_library_script`
receive an `{"error": ...}` envelope from `daemon.evaluate` (CDP-level
failure) vs. `{"success": false, "error": ...}` from the script itself
(page-level failure) — these are two different failure classes and should be
logged distinctly.
