"""Monitoring API for the chrome agent."""

import json
from typing import Optional

from flask import Flask, jsonify, request

from agent.agent import Agent


def create_app(agent: Optional[Agent] = None) -> Flask:
    app = Flask(__name__)
    _agent = agent or Agent()

    @app.route("/health")
    def health():
        return jsonify({"status": "ok", "running": _agent._running})

    @app.route("/api/dashboard")
    def dashboard():
        return jsonify(_agent.monitor.dashboard())

    @app.route("/api/stats")
    def stats():
        return jsonify(_agent.monitor.stats())

    @app.route("/api/tasks", methods=["GET"])
    def list_tasks():
        status = request.args.get("status")
        limit = int(request.args.get("limit", 50))
        offset = int(request.args.get("offset", 0))
        return jsonify(_agent.queue.list_tasks(status, limit, offset))

    @app.route("/api/tasks/<int:task_id>")
    def get_task(task_id):
        detail = _agent.monitor.task_detail(task_id)
        if not detail:
            return jsonify({"error": "not found"}), 404
        return jsonify(detail)

    @app.route("/api/tasks", methods=["POST"])
    def submit_task():
        data = request.get_json(force=True)
        task_type = data.get("task_type")
        if not task_type:
            return jsonify({"error": "task_type required"}), 400
        task_id = _agent.submit(
            task_type=task_type,
            payload=data.get("payload"),
            priority=data.get("priority", 5),
            scheduled_at=data.get("scheduled_at"),
            timeout_seconds=data.get("timeout_seconds"),
        )
        return jsonify({"task_id": task_id}), 201

    @app.route("/api/tasks/failed")
    def failed_tasks():
        limit = int(request.args.get("limit", 50))
        offset = int(request.args.get("offset", 0))
        return jsonify(_agent.monitor.failed_tasks(limit, offset))

    @app.route("/api/events")
    def events():
        event_type = request.args.get("type")
        limit = int(request.args.get("limit", 100))
        offset = int(request.args.get("offset", 0))
        return jsonify(
            _agent.monitor.event_history(event_type, limit, offset)
        )

    @app.route("/api/schedules", methods=["GET"])
    def list_schedules():
        return jsonify(_agent.scheduler.list_schedules())

    @app.route("/api/schedules", methods=["POST"])
    def add_schedule():
        data = request.get_json(force=True)
        required = ("name", "task_type", "cron_expr")
        for field in required:
            if not data.get(field):
                return jsonify({"error": f"{field} required"}), 400
        schedule_id = _agent.add_schedule(
            name=data["name"],
            task_type=data["task_type"],
            cron_expr=data["cron_expr"],
            payload=data.get("payload"),
            priority=data.get("priority", 5),
        )
        return jsonify({"schedule_id": schedule_id}), 201

    @app.route("/api/schedules/<name>/enable", methods=["POST"])
    def enable_schedule(name):
        _agent.scheduler.enable_schedule(name)
        return jsonify({"enabled": True})

    @app.route("/api/schedules/<name>/disable", methods=["POST"])
    def disable_schedule(name):
        _agent.scheduler.disable_schedule(name)
        return jsonify({"enabled": False})

    @app.route("/")
    def index():
        return DASHBOARD_HTML

    return app


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Chrome Agent Monitor</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, sans-serif; background: #0f1117; color: #e1e4e8; padding: 1.5rem; }
  h1 { font-size: 1.4rem; margin-bottom: 1rem; }
  h2 { font-size: 1rem; color: #8b949e; margin: 1.2rem 0 0.5rem; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 0.75rem; }
  .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1rem; }
  .card .val { font-size: 1.8rem; font-weight: 700; }
  .card .lbl { font-size: 0.75rem; color: #8b949e; margin-top: 0.25rem; }
  table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  th, td { text-align: left; padding: 0.5rem 0.75rem; border-bottom: 1px solid #21262d; }
  th { color: #8b949e; font-weight: 500; }
  .failed { color: #f85149; }
  .completed { color: #3fb950; }
  .running { color: #d29922; }
  .pending { color: #58a6ff; }
  #refresh { background: #238636; color: #fff; border: none; padding: 0.4rem 1rem;
             border-radius: 6px; cursor: pointer; margin-bottom: 1rem; }
</style>
</head>
<body>
<h1>Chrome Agent Monitor</h1>
<button id="refresh" onclick="load()">Refresh</button>
<div class="grid" id="stats"></div>
<h2>Recent Failed Tasks</h2>
<div class="card"><table><thead><tr><th>ID</th><th>Type</th><th>Error</th><th>Time</th></tr></thead>
<tbody id="failed"></tbody></table></div>
<h2>Recent Events</h2>
<div class="card"><table><thead><tr><th>Type</th><th>Source</th><th>Time</th></tr></thead>
<tbody id="events"></tbody></table></div>
<script>
async function load() {
  const r = await fetch('/api/dashboard');
  const d = await r.json();
  const s = d.tasks.by_status;
  document.getElementById('stats').innerHTML = [
    ['Total', d.tasks.total], ['Pending', s.pending||0], ['Running', s.running||0],
    ['Completed', s.completed||0], ['Failed', s.failed||0], ['Timeout', s.timeout||0],
    ['Schedules', d.schedules.enabled + '/' + d.schedules.total]
  ].map(([l,v]) => `<div class="card"><div class="val">${v}</div><div class="lbl">${l}</div></div>`).join('');
  document.getElementById('failed').innerHTML = (d.recent_failed||[]).map(t =>
    `<tr><td>${t.id}</td><td>${t.task_type}</td><td class="failed">${(t.error||'').slice(0,80)}</td><td>${(t.completed_at||'').slice(0,19)}</td></tr>`
  ).join('') || '<tr><td colspan="4">None</td></tr>';
  document.getElementById('events').innerHTML = (d.recent_events||[]).map(e =>
    `<tr><td>${e.event_type}</td><td>${e.source||'-'}</td><td>${(e.created_at||'').slice(0,19)}</td></tr>`
  ).join('');
}
load();
setInterval(load, 10000);
</script>
</body>
</html>"""
