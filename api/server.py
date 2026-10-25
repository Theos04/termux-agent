"""FastAPI server for the Chrome CDP agent.

Replaces the previous Flask implementation while keeping 100 % API surface
compatibility.  New additions:

  WS  /ws/tasks/{task_id}   — live stream of events for a single task
  WS  /ws/agent             — global all-events stream (TUI connects here)
  GET /api/heal/status      — HealLoop status snapshot
  SSE /api/tasks/{id}/stream — Server-Sent Events fallback (non-WS clients)

All blocking agent calls are executed in a thread-pool via asyncio.to_thread()
so the async event loop is never blocked.
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional

from fastapi import FastAPI, HTTPException, Query, WebSocket
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from agent.agent import Agent
from agent.config import AgentConfig
from api.ws_hub import hub

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# GCalPoller singleton (started in lifespan)
# ──────────────────────────────────────────────────────────────────────────────

try:
    from handlers.gcal_sync import GCalPoller  # noqa: PLC0415
    _gcal_poller = GCalPoller()
except ImportError:
    _gcal_poller = None  # type: ignore[assignment]

# ──────────────────────────────────────────────────────────────────────────────
# Pydantic request / response models
# ──────────────────────────────────────────────────────────────────────────────


class TaskRequest(BaseModel):
    """Submit any task — either by explicit task_type or by free-form goal."""

    task_type: Optional[str] = Field(
        None,
        description="Registered task type (e.g. 'browser_navigate'). "
        "Omit to use 'goal' with the Universal Planner (Phase 2).",
    )
    goal: Optional[str] = Field(
        None,
        description="Natural-language goal — routed through UniversalPlanner.",
    )
    payload: Optional[dict] = None
    priority: int = Field(5, ge=1, le=10)
    scheduled_at: Optional[str] = None
    timeout_seconds: Optional[int] = None


class ScheduleRequest(BaseModel):
    name: str
    task_type: str
    cron_expr: str
    payload: Optional[dict] = None
    priority: int = Field(5, ge=1, le=10)


class WhatsAppMessageRequest(BaseModel):
    phone: str
    message: str
    port: Optional[int] = None


class WhatsAppDispatchRequest(BaseModel):
    phone: str
    message: str
    port: Optional[int] = None



# ──────────────────────────────────────────────────────────────────────────────
# Application factory
# ──────────────────────────────────────────────────────────────────────────────


def create_app(agent: Optional[Agent] = None) -> FastAPI:  # noqa: C901
    _agent = agent or Agent()
    _loop: asyncio.AbstractEventLoop | None = None

    # ── Lifespan: start agent + hub, wire EventBus → WSHub ────────────────
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        nonlocal _loop
        _loop = asyncio.get_running_loop()

        # Start the agent (workers + scheduler)
        await asyncio.to_thread(_agent.start)

        # Start WebSocket hub
        await hub.start()

        # Bridge: every EventBus event → WSHub broadcast
        def _eb_to_ws(event) -> None:
            if _loop is None:
                return
            payload = event.to_dict()
            task_id: int | None = (
                payload.get("payload", {}) or {}
            ).get("task_id")
            if task_id:
                hub.publish_threadsafe(_loop, task_id, payload)
            # Always push to the global "all" channel
            hub.publish_threadsafe(_loop, "all", payload)

        _agent.event_bus.subscribe_all(_eb_to_ws)
        logger.info("FastAPI server started, agent running")

        # Start Google Calendar poller (if available)
        if _gcal_poller is not None:
            try:
                await asyncio.to_thread(_gcal_poller.start, _agent)
                logger.info("GCalPoller started")
            except Exception as _exc:
                logger.warning("GCalPoller failed to start: %s", _exc)

        yield  # ← app is serving

        # Graceful shutdown
        if _gcal_poller is not None:
            try:
                await asyncio.to_thread(_gcal_poller.stop)
            except Exception:
                pass
        await asyncio.to_thread(_agent.stop)
        logger.info("Agent stopped")

    app = FastAPI(
        title="Termux CDP Agent",
        version="2.0.0",
        description="Chrome automation agent with FastAPI + WebSocket streaming",
        lifespan=lifespan,
    )

    # ──────────────────────────────────────────────────────────────────────
    # REST endpoints  (all paths preserved from Flask version)
    # ──────────────────────────────────────────────────────────────────────

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "running": _agent._running}

    # ── Dashboard / Stats ────────────────────────────────────────────────

    @app.get("/api/dashboard")
    async def dashboard() -> dict:
        return await asyncio.to_thread(_agent.monitor.dashboard)

    @app.get("/api/stats")
    async def stats() -> dict:
        return await asyncio.to_thread(_agent.monitor.stats)

    # ── Tasks ─────────────────────────────────────────────────────────────

    @app.get("/api/tasks")
    async def list_tasks(
        status: Optional[str] = Query(None),
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ) -> list:
        return await asyncio.to_thread(
            _agent.queue.list_tasks, status, limit, offset
        )

    @app.get("/api/tasks/failed")
    async def failed_tasks(
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ) -> list:
        return await asyncio.to_thread(_agent.monitor.failed_tasks, limit, offset)

    @app.get("/api/tasks/{task_id}")
    async def get_task(task_id: int) -> dict:
        detail = await asyncio.to_thread(_agent.monitor.task_detail, task_id)
        if not detail:
            raise HTTPException(status_code=404, detail="Task not found")
        return detail

    @app.post("/api/tasks", status_code=202)
    async def submit_task(req: TaskRequest) -> dict:
        """Submit a task.

        - Provide ``task_type`` for a known handler.
        - Provide ``goal`` (natural language) to use the Universal Planner
          (Phase 2 — if planner not yet loaded, falls back to ``agent_act``).
        """
        task_type = req.task_type
        payload = req.payload or {}

        if not task_type:
            if not req.goal:
                raise HTTPException(
                    status_code=400, detail="task_type or goal required"
                )
            # Phase 2 hook: try UniversalPlanner; fall back gracefully
            try:
                from agent.planner import UniversalPlanner  # noqa: PLC0415

                planner = UniversalPlanner(_agent)
                dag = await asyncio.to_thread(planner.plan, req.goal)
                task_type = "execute_dag"
                payload = {"dag": dag.to_dict(), "goal": req.goal}
            except ImportError:
                # Planner not yet implemented — route as generic agent_act
                task_type = "agent_act"
                payload = {"goal": req.goal}

        task_id = await asyncio.to_thread(
            _agent.submit,
            task_type,
            payload,
            req.priority,
            req.scheduled_at,
            req.timeout_seconds,
        )
        return {"task_id": task_id, "task_type": task_type}

    # ── Events ────────────────────────────────────────────────────────────

    @app.get("/api/events")
    async def events(
        type: Optional[str] = Query(None, alias="type"),
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
    ) -> list:
        return await asyncio.to_thread(
            _agent.monitor.event_history, type, limit, offset
        )

    # ── Schedules ─────────────────────────────────────────────────────────

    @app.get("/api/schedules")
    async def list_schedules() -> list:
        return await asyncio.to_thread(_agent.scheduler.list_schedules)

    @app.post("/api/schedules", status_code=201)
    async def add_schedule(req: ScheduleRequest) -> dict:
        schedule_id = await asyncio.to_thread(
            _agent.add_schedule,
            req.name,
            req.task_type,
            req.cron_expr,
            req.payload,
            req.priority,
        )
        return {"schedule_id": schedule_id}

    @app.post("/api/schedules/{name}/enable")
    async def enable_schedule(name: str) -> dict:
        await asyncio.to_thread(_agent.scheduler.enable_schedule, name)
        return {"enabled": True}

    @app.post("/api/schedules/{name}/disable")
    async def disable_schedule(name: str) -> dict:
        await asyncio.to_thread(_agent.scheduler.disable_schedule, name)
        return {"enabled": False}

    # ── Google Calendar integration ────────────────────────────────────────

    @app.post("/api/gcal/sync")
    async def gcal_sync() -> dict:
        """Push all schedules to Google Calendar (idempotent)."""
        if _gcal_poller is None:
            raise HTTPException(status_code=503, detail="GCalPoller not available")
        result = await asyncio.to_thread(_gcal_poller.trigger_sync, _agent)
        if not result.get("ok"):
            raise HTTPException(status_code=503, detail=result.get("error", "sync failed"))
        return result

    @app.post("/api/gcal/poll")
    async def gcal_poll(
        since_minutes: int = Query(5, ge=1, le=60),
    ) -> dict:
        """Manually trigger a Google Calendar poll for incoming commands."""
        if _gcal_poller is None:
            raise HTTPException(status_code=503, detail="GCalPoller not available")
        result = await asyncio.to_thread(_gcal_poller.trigger_poll, since_minutes, _agent)
        if not result.get("ok"):
            raise HTTPException(status_code=503, detail=result.get("error", "poll failed"))
        return result

    @app.get("/api/gcal/status")
    async def gcal_status() -> dict:
        """Return Google Calendar integration status."""
        if _gcal_poller is None:
            return {
                "available": False,
                "poller_running": False,
                "last_poll": None,
                "last_sync": None,
                "note": "GCalPoller not loaded — check handlers.gcal_sync import",
            }
        return await asyncio.to_thread(_gcal_poller.status)

    @app.post("/api/gcal/push/{name}")
    async def gcal_push_schedule(name: str) -> dict:
        """Push a single schedule by name to Google Calendar."""
        schedule = await asyncio.to_thread(_agent.db.get_schedule_by_name, name)
        if not schedule:
            raise HTTPException(status_code=404, detail=f"Schedule '{name}' not found")

        if _gcal_poller is None:
            raise HTTPException(status_code=503, detail="GCalPoller not available")

        gcal = _gcal_poller._get_gcal()
        if gcal is None:
            try:
                from agent.skills.gcal_scheduler import GCalScheduler  # noqa: PLC0415
                gcal = GCalScheduler(_agent)
            except ImportError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc

        if not gcal.available():
            raise HTTPException(status_code=503, detail="Google Calendar credentials not available")

        event_id = await asyncio.to_thread(gcal.push_schedule_to_calendar, schedule)
        if not event_id:
            raise HTTPException(status_code=500, detail="Failed to push schedule to calendar")

        return {"schedule_name": name, "gcal_event_id": event_id}

    # ── Tools / Sessions ──────────────────────────────────────────────────

    @app.get("/api/tools")
    async def tools() -> list:
        from agent.tools import list_tools  # noqa: PLC0415

        return list_tools()

    @app.get("/api/sessions")
    async def sessions() -> dict:
        try:
            from agent.chrome_service import list_sessions  # noqa: PLC0415

            sess = await asyncio.to_thread(list_sessions)
            return {"sessions": sess}
        except Exception as exc:
            return {"sessions": [], "error": str(exc)}

    # ── Heal status ───────────────────────────────────────────────────────

    @app.get("/api/heal/status")
    async def heal_status() -> dict:
        try:
            return _agent.heal_loop.status  # type: ignore[attr-defined]
        except AttributeError:
            return {"running": False, "note": "heal loop not attached"}

    # ── WhatsApp CDP Agent & Pharmacy Trading ──────────────────────────────

    @app.get("/api/whatsapp/status")
    async def whatsapp_status(port: Optional[int] = None) -> dict:
        from agent.whatsapp import WhatsAppCDPClient
        cfg = AgentConfig()
        cdp = WhatsAppCDPClient(port=port or cfg.whatsapp_cdp_port)
        return await asyncio.to_thread(cdp.get_status)

    @app.post("/api/whatsapp/launch")
    async def whatsapp_launch(port: Optional[int] = None) -> dict:
        from agent.whatsapp import WhatsAppCDPClient
        cfg = AgentConfig()
        cdp = WhatsAppCDPClient(port=port or cfg.whatsapp_cdp_port)
        return await asyncio.to_thread(cdp.launch_browser)

    @app.post("/api/whatsapp/dispatch")
    async def whatsapp_dispatch(req: WhatsAppDispatchRequest) -> dict:
        from agent.whatsapp import WhatsAppCDPClient, WhatsAppRouter
        cfg = AgentConfig()
        cdp = WhatsAppCDPClient(port=req.port or cfg.whatsapp_cdp_port)
        router = WhatsAppRouter(_agent.db, cdp)
        res = await asyncio.to_thread(router.dispatch, req.phone, req.message)
        return {
            "ok": res.ok,
            "intent": res.intent.value,
            "response": res.response_text,
            "action_taken": res.action_taken,
            "trace": res.execution_trace,
            "requires_human_review": res.requires_human_review,
            "details": res.details,
        }

    @app.post("/api/whatsapp/send")
    async def whatsapp_send(req: WhatsAppMessageRequest) -> dict:
        from agent.whatsapp import WhatsAppCDPClient, WhatsAppRouter
        cfg = AgentConfig()
        cdp = WhatsAppCDPClient(port=req.port or cfg.whatsapp_cdp_port)
        router = WhatsAppRouter(_agent.db, cdp)
        return await asyncio.to_thread(router.action.send_whatsapp_message, req.phone, req.message)

    @app.post("/api/whatsapp/sync")
    async def whatsapp_sync(limit: int = Query(500, ge=1, le=2000)) -> dict:
        from agent.whatsapp.google_sheet_sync import GoogleSheetPharmacySync
        sync = GoogleSheetPharmacySync(_agent.db)
        return await asyncio.to_thread(sync.sync_all, limit, limit)

    @app.get("/api/whatsapp/catalog")
    async def whatsapp_catalog(q: str = Query("", description="Search medicine")) -> list:
        if q:
            return await asyncio.to_thread(_agent.db.search_products, q)
        rows = await asyncio.to_thread(
            lambda: [dict(r) for r in _agent.db.conn.execute("SELECT * FROM products WHERE active = 1 LIMIT 50").fetchall()]
        )
        return rows

    @app.get("/api/whatsapp/audit")
    async def whatsapp_audit(limit: int = Query(50, ge=1, le=200)) -> list:
        return await asyncio.to_thread(_agent.db.get_audit_events, limit)


    # ── WS: single-task stream ─────────────────────────────────────────────

    @app.websocket("/ws/tasks/{task_id}")
    async def ws_task_stream(ws: WebSocket, task_id: int) -> None:
        """Stream all events for a specific task."""
        # Send current task state immediately
        detail = await asyncio.to_thread(_agent.monitor.task_detail, task_id)
        if detail:
            await ws.accept()
            await ws.send_text(
                json.dumps({"type": "task.snapshot", "data": detail}, default=str)
            )
            # Reuse hub.connect but skip accept (already accepted)
            from api.ws_hub import WSHub  # noqa: PLC0415
            import api.ws_hub as _hub_mod  # noqa: PLC0415

            # Manually add and serve
            async with hub._lock:
                hub._clients[task_id].add(ws)
            try:
                from fastapi import WebSocketDisconnect  # noqa: PLC0415

                while True:
                    data = await ws.receive_text()
                    try:
                        msg = json.loads(data)
                        if msg.get("ping"):
                            await ws.send_text(json.dumps({"pong": True}))
                    except Exception:
                        pass
            except Exception:
                pass
            finally:
                async with hub._lock:
                    hub._clients[task_id].discard(ws)
        else:
            await ws.accept()
            await ws.send_text(json.dumps({"error": "task not found"}))
            await ws.close()

    # ── WS: global agent stream (TUI + dashboards) ─────────────────────────

    @app.websocket("/ws/agent")
    async def ws_agent(ws: WebSocket) -> None:
        """Stream all agent events — TUI connects here for live updates.

        Accepts JSON messages from the client:
          {"ping": true}                    → {"pong": true}
          {"submit": {task_type, payload}}  → enqueues task, returns task_id
        """
        await ws.accept()
        await ws.send_text(json.dumps({"type": "connected", "channel": "all"}))

        async with hub._lock:
            hub._clients["all"].add(ws)

        async def _reader() -> None:
            """Handle inbound messages from this client."""
            try:
                while True:
                    raw = await ws.receive_text()
                    try:
                        msg = json.loads(raw)
                    except Exception:
                        continue

                    if msg.get("ping"):
                        await ws.send_text(json.dumps({"pong": True}))

                    elif "submit" in msg:
                        req_data = msg["submit"]
                        try:
                            task_id = await asyncio.to_thread(
                                _agent.submit,
                                req_data.get("task_type", "agent_act"),
                                req_data.get("payload") or {},
                                req_data.get("priority", 5),
                                req_data.get("scheduled_at"),
                                req_data.get("timeout_seconds"),
                            )
                            await ws.send_text(
                                json.dumps(
                                    {
                                        "type": "task.submitted",
                                        "task_id": task_id,
                                        "task_type": req_data.get("task_type"),
                                    }
                                )
                            )
                        except Exception as exc:
                            await ws.send_text(
                                json.dumps({"type": "error", "message": str(exc)})
                            )
            except Exception:
                pass

        try:
            await _reader()
        finally:
            async with hub._lock:
                hub._clients["all"].discard(ws)

    # ── SSE fallback: /api/tasks/{id}/stream ──────────────────────────────

    @app.get("/api/tasks/{task_id}/stream")
    async def sse_task_stream(task_id: int) -> StreamingResponse:
        """Server-Sent Events stream for environments that can't use WS."""
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)

        async def _enqueue(event: dict) -> None:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

        # Register a temporary SSE subscriber
        _task_channel_subs: dict[int, list] = {}
        _task_channel_subs.setdefault(task_id, []).append(_enqueue)

        async def _generate() -> AsyncIterator[str]:
            # Flush existing task detail immediately
            detail = await asyncio.to_thread(_agent.monitor.task_detail, task_id)
            if detail:
                yield f"data: {json.dumps({'type': 'task.snapshot', 'data': detail}, default=str)}\n\n"

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"data: {json.dumps(event, default=str)}\n\n"
                    if (event.get("payload") or {}).get("status") in (
                        "completed",
                        "failed",
                    ):
                        break
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"

        return StreamingResponse(
            _generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    # ── WS hub meta ───────────────────────────────────────────────────────

    @app.get("/api/ws/status")
    async def ws_status() -> dict:
        return {
            "active_channels": hub.all_channels(),
            "client_counts": {
                ch: hub.client_count(ch) for ch in hub.all_channels()
            },
        }

    # ── Dashboard HTML ─────────────────────────────────────────────────────

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        return HTMLResponse(content=DASHBOARD_HTML)

    return app


# ──────────────────────────────────────────────────────────────────────────────
# Queue maxsize constant (also used by SSE stream)
# ──────────────────────────────────────────────────────────────────────────────
_QUEUE_MAXSIZE = 256

# ──────────────────────────────────────────────────────────────────────────────
# Dashboard HTML  (preserved + enhanced with WS live-update + goal input)
# ──────────────────────────────────────────────────────────────────────────────

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Termux CDP Agent v2</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, sans-serif; background: #0f1117; color: #e1e4e8;
         padding: 1.5rem; max-width: 1200px; margin: 0 auto; }
  h1 { font-size: 1.4rem; margin-bottom: 0.25rem; }
  .sub { color: #8b949e; font-size: 0.85rem; margin-bottom: 1rem; }
  h2 { font-size: 1rem; color: #8b949e; margin: 1.2rem 0 0.5rem; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 0.75rem; }
  .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px;
          padding: 1rem; margin-bottom: 0.75rem; }
  .card .val { font-size: 1.6rem; font-weight: 700; }
  .card .lbl { font-size: 0.75rem; color: #8b949e; margin-top: 0.25rem; }
  table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
  th, td { text-align: left; padding: 0.4rem 0.6rem; border-bottom: 1px solid #21262d; }
  th { color: #8b949e; }
  .pending  { color: #e3b341; }
  .running  { color: #58a6ff; }
  .completed{ color: #3fb950; }
  .failed   { color: #f85149; }
  button { background: #238636; border: none; color: #fff; padding: 0.45rem 0.9rem;
           border-radius: 6px; cursor: pointer; font-size: 0.85rem; margin: 0.2rem; }
  button.secondary { background: #21262d; border: 1px solid #30363d; }
  button.warn { background: #9e6a03; }
  button.danger { background: #6e1a1a; }
  input, select, textarea { background: #0d1117; border: 1px solid #30363d;
    color: #e1e4e8; padding: 0.45rem 0.6rem; border-radius: 6px;
    font-size: 0.85rem; width: 100%; }
  .row { display: flex; gap: 0.5rem; flex-wrap: wrap; align-items: center; margin-bottom: 0.5rem; }
  .row > * { flex: 1; min-width: 140px; }
  #msg { margin: 0.5rem 0; font-size: 0.85rem; color: #3fb950; }
  pre { background: #0d1117; padding: 0.75rem; border-radius: 6px;
        overflow: auto; max-height: 200px; font-size: 0.75rem; }
  #ws-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%;
             background: #f85149; margin-right: 6px; }
  #ws-dot.ok { background: #3fb950; }
  .event-stream { background: #0d1117; border: 1px solid #30363d; border-radius: 6px;
                  height: 180px; overflow-y: auto; padding: 0.5rem;
                  font-size: 0.75rem; font-family: monospace; }
  .ev-task\\.completed { color: #3fb950; }
  .ev-task\\.failed    { color: #f85149; }
  .ev-task\\.claimed   { color: #58a6ff; }
  /* goal input */
  #goal-input { font-size: 1rem; padding: 0.6rem; }
</style>
</head>
<body>
<h1>Termux CDP Agent <span style="color:#58a6ff;font-size:0.8rem">v2</span></h1>
<p class="sub">
  <span id="ws-dot"></span><span id="ws-label">Connecting…</span>
  &nbsp;·&nbsp; FastAPI + WebSocket live dashboard
</p>

<!-- ── Quick actions ── -->
<div class="row">
  <button onclick="load()">↻ Refresh</button>
  <button class="warn" onclick="quick('session_start',{name:'agent',url:'https://google.com'})">Start Chrome</button>
  <button class="secondary" onclick="quick('browser_get_content',{name:'agent',format:'text'})">Get Page</button>
  <button class="secondary" onclick="quick('echo',{test:true})">Echo Test</button>
</div>
<div id="msg"></div>

<!-- ── Natural-language goal ── -->
<h2>Submit Goal (natural language)</h2>
<div class="card">
  <div class="row">
    <input id="goal-input" placeholder='e.g. "get phone numbers of all bars in Pune"' />
    <button onclick="submitGoal()" style="flex:0 0 auto">→ Go</button>
  </div>
</div>

<!-- ── Stats ── -->
<h2>Task Stats</h2>
<div class="grid" id="stats"></div>

<!-- ── Live event stream ── -->
<h2>Live Events <small style="color:#8b949e">(WebSocket)</small></h2>
<div class="event-stream" id="events-log"></div>

<!-- ── Manual task submit ── -->
<h2>Submit Task (structured)</h2>
<div class="card">
  <div class="row">
    <select id="task_type">
      <option value="session_start">session_start</option>
      <option value="browser_navigate">browser_navigate</option>
      <option value="browser_get_content">browser_get_content</option>
      <option value="browser_execute_js">browser_execute_js</option>
      <option value="browser_extract">browser_extract</option>
      <option value="agent_act">agent_act</option>
      <option value="session_list">session_list</option>
    </select>
  </div>
  <div class="row">
    <textarea id="payload" rows="4">{"name": "agent", "url": "https://google.com"}</textarea>
  </div>
  <button onclick="submitTask()">Submit to Queue</button>
</div>

<!-- ── Sessions + Tasks ── -->
<h2>Chrome Sessions</h2>
<div class="card"><table><thead><tr><th>ID</th><th>Name</th><th>URL</th><th>Port</th><th>Status</th></tr></thead>
<tbody id="sessions"></tbody></table></div>

<h2>Recent Tasks</h2>
<div class="card"><table><thead><tr><th>ID</th><th>Type</th><th>Status</th><th>Result/Error</th></tr></thead>
<tbody id="tasks"></tbody></table></div>

<h2>Recent Failed</h2>
<div class="card"><table><thead><tr><th>ID</th><th>Type</th><th>Error</th></tr></thead>
<tbody id="failed"></tbody></table></div>

<script>
// ── WebSocket setup ────────────────────────────────────────────────────────
const dot   = document.getElementById('ws-dot');
const wslbl = document.getElementById('ws-label');
const evlog = document.getElementById('events-log');

let ws;
function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws/agent`);

  ws.onopen = () => {
    dot.className = 'ok';
    wslbl.textContent = 'Live';
  };
  ws.onclose = () => {
    dot.className = '';
    wslbl.textContent = 'Disconnected — reconnecting…';
    setTimeout(connectWS, 3000);
  };
  ws.onerror = () => ws.close();

  ws.onmessage = (e) => {
    const ev = JSON.parse(e.data);
    if (ev.type === 'connected') return;
    if (ev.pong) return;

    const line = document.createElement('div');
    const ts = new Date().toLocaleTimeString();
    const cls = (ev.event_type || '').replace(/\\./g, '\\\\.').replace(/[^a-z0-9_\\-\\.]/gi, '');
    line.className = 'ev-' + cls;
    line.textContent = `[${ts}] ${ev.event_type || ev.type || 'event'} ${JSON.stringify(ev.payload || {}).slice(0, 120)}`;
    evlog.prepend(line);
    // Keep log bounded
    while (evlog.children.length > 80) evlog.removeChild(evlog.lastChild);

    // Refresh stats panel on task state changes
    if ((ev.event_type || '').startsWith('task.')) load();
  };
}
connectWS();

// ── Goal submit ───────────────────────────────────────────────────────────
async function submitGoal() {
  const goal = document.getElementById('goal-input').value.trim();
  if (!goal) return;
  const r = await fetch('/api/tasks', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({goal})
  });
  const d = await r.json();
  document.getElementById('msg').textContent = r.ok
    ? `Task #${d.task_id} queued (${d.task_type})`
    : `Error: ${JSON.stringify(d)}`;
}

// ── Quick task submit ─────────────────────────────────────────────────────
async function quick(type, payload) {
  const r = await fetch('/api/tasks', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({task_type: type, payload, timeout_seconds: 600})
  });
  const d = await r.json();
  document.getElementById('msg').textContent = r.ok
    ? `Task #${d.task_id} queued (${type})`
    : `Error: ${JSON.stringify(d)}`;
  setTimeout(load, 800);
}

async function submitTask() {
  let payload = {};
  try { payload = JSON.parse(document.getElementById('payload').value); }
  catch(e) { document.getElementById('msg').textContent = 'Invalid JSON payload'; return; }
  await quick(document.getElementById('task_type').value, payload);
}

// ── Periodic load ─────────────────────────────────────────────────────────
async function load() {
  const [dash, sess] = await Promise.all([
    fetch('/api/dashboard').then(r=>r.json()).catch(()=>({})),
    fetch('/api/sessions').then(r=>r.json()).catch(()=>({sessions:[]}))
  ]);
  const s = (dash.tasks || {}).by_status || {};
  document.getElementById('stats').innerHTML = [
    ['Total', (dash.tasks||{}).total||0],
    ['Pending', s.pending||0],
    ['Running', s.running||0],
    ['Completed', s.completed||0],
    ['Failed', s.failed||0]
  ].map(([l,v]) => `<div class="card"><div class="val">${v}</div><div class="lbl">${l}</div></div>`).join('');

  document.getElementById('sessions').innerHTML = (sess.sessions||[]).map(x =>
    `<tr><td>${x.id}</td><td>${x.name}</td><td>${(x.url||'').slice(0,40)}</td><td>${x.port}</td><td>${x.status}</td></tr>`
  ).join('') || '<tr><td colspan="5">No sessions</td></tr>';

  document.getElementById('tasks').innerHTML = (dash.recent_tasks||[]).map(t => {
    const info = t.error || (t.result ? JSON.stringify(t.result).slice(0,90) : '-');
    return `<tr><td>${t.id}</td><td>${t.task_type}</td><td class="${t.status}">${t.status}</td><td>${info}</td></tr>`;
  }).join('') || '<tr><td colspan="4">No tasks yet</td></tr>';

  document.getElementById('failed').innerHTML = (dash.recent_failed||[]).map(t =>
    `<tr><td>${t.id}</td><td>${t.task_type}</td><td class="failed">${(t.error||'').slice(0,100)}</td></tr>`
  ).join('') || '<tr><td colspan="3">None</td></tr>';
}

load();
setInterval(load, 10000);  // fallback poll — WS handles live updates
</script>
</body>
</html>"""
