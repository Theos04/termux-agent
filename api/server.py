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

    @app.route("/api/tools")
    def tools():
        from agent.tools import list_tools
        return jsonify(list_tools())

    @app.route("/api/sessions")
    def sessions():
        try:
            from agent.chrome_service import list_sessions
            return jsonify({"sessions": list_sessions()})
        except Exception as exc:
            return jsonify({"sessions": [], "error": str(exc)})

    @app.route("/")
    def index():
        return DASHBOARD_HTML

    return app


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Chrome CDP Agent</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, sans-serif; background: #0f1117; color: #e1e4e8; padding: 1.5rem; max-width: 1100px; margin: 0 auto; }
  h1 { font-size: 1.4rem; margin-bottom: 0.5rem; }
  .sub { color: #8b949e; font-size: 0.85rem; margin-bottom: 1rem; }
  h2 { font-size: 1rem; color: #8b949e; margin: 1.2rem 0 0.5rem; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 0.75rem; }
  .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1rem; margin-bottom: 0.75rem; }
  .card .val { font-size: 1.6rem; font-weight: 700; }
  .card .lbl { font-size: 0.75rem; color: #8b949e; margin-top: 0.25rem; }
  table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  th, td { text-align: left; padding: 0.5rem 0.75rem; border-bottom: 1px solid #21262d; }
  th { color: #8b949e; font-weight: 500; }
  .failed { color: #f85149; } .completed { color: #3fb950; }
  .running { color: #d29922; } .pending { color: #58a6ff; }
  button, .btn { background: #238636; color: #fff; border: none; padding: 0.45rem 0.9rem;
    border-radius: 6px; cursor: pointer; font-size: 0.85rem; margin: 0.2rem 0.2rem 0.2rem 0; }
  button.secondary { background: #21262d; border: 1px solid #30363d; }
  button.warn { background: #9e6a03; }
  input, select, textarea { background: #0d1117; border: 1px solid #30363d; color: #e1e4e8;
    padding: 0.45rem 0.6rem; border-radius: 6px; font-size: 0.85rem; width: 100%; }
  .row { display: flex; gap: 0.5rem; flex-wrap: wrap; align-items: center; margin-bottom: 0.5rem; }
  .row > * { flex: 1; min-width: 140px; }
  #msg { margin: 0.5rem 0; font-size: 0.85rem; color: #3fb950; }
  pre { background: #0d1117; padding: 0.75rem; border-radius: 6px; overflow: auto; max-height: 200px; font-size: 0.75rem; }
</style>
</head>
<body>
<h1>Chrome CDP Agent</h1>
<p class="sub">Task queue + cdpv116 session manager — submit tasks below</p>

<div class="row">
  <button onclick="load()">Refresh</button>
  <button class="warn" onclick="quick('session_start',{name:'unstop',url:'https://unstop.com/internships'})">Start Unstop Chrome</button>
  <button class="secondary" onclick="quick('browser_get_content',{name:'unstop',format:'text'})">Get Page Text</button>
  <button class="secondary" onclick="quick('agent_act',{context:'unstop_jobs',name:'unstop'})">Extract Jobs</button>
  <button class="secondary" onclick="quick('echo',{test:true})">Health Check</button>
</div>
<div id="msg"></div>
<div class="grid" id="stats"></div>

<h2>Submit Task</h2>
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
  <div class="row"><textarea id="payload" rows="4">{"name": "unstop", "url": "https://unstop.com/internships"}</textarea></div>
  <button onclick="submitTask()">Submit to Queue</button>
</div>

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
async function quick(type, payload) {
  const r = await fetch('/api/tasks', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({task_type: type, payload, timeout_seconds: 600})});
  const d = await r.json();
  document.getElementById('msg').textContent = r.ok ? `Task #${d.task_id} queued (${type})` : `Error: ${JSON.stringify(d)}`;
  setTimeout(load, 1000);
}

async function submitTask() {
  let payload = {};
  try { payload = JSON.parse(document.getElementById('payload').value); } catch(e) {
    document.getElementById('msg').textContent = 'Invalid JSON payload'; return;
  }
  await quick(document.getElementById('task_type').value, payload);
}

async function load() {
  const [dash, sess] = await Promise.all([
    fetch('/api/dashboard').then(r=>r.json()),
    fetch('/api/sessions').then(r=>r.json())
  ]);
  const s = dash.tasks.by_status;
  document.getElementById('stats').innerHTML = [
    ['Total', dash.tasks.total], ['Pending', s.pending||0], ['Running', s.running||0],
    ['Completed', s.completed||0], ['Failed', s.failed||0]
  ].map(([l,v]) => `<div class="card"><div class="val">${v}</div><div class="lbl">${l}</div></div>`).join('');

  document.getElementById('sessions').innerHTML = (sess.sessions||[]).map(x =>
    `<tr><td>${x.id}</td><td>${x.name}</td><td>${(x.url||'').slice(0,40)}</td><td>${x.port}</td><td>${x.status}</td></tr>`
  ).join('') || '<tr><td colspan="5">No sessions — click Start Unstop Chrome</td></tr>';

  document.getElementById('tasks').innerHTML = (dash.recent_tasks||[]).map(t => {
    const info = t.error || (t.result ? JSON.stringify(t.result).slice(0,80) : '-');
    return `<tr><td>${t.id}</td><td>${t.task_type}</td><td class="${t.status}">${t.status}</td><td>${info}</td></tr>`;
  }).join('') || '<tr><td colspan="4">No tasks yet</td></tr>';

  document.getElementById('failed').innerHTML = (dash.recent_failed||[]).map(t =>
    `<tr><td>${t.id}</td><td>${t.task_type}</td><td class="failed">${(t.error||'').slice(0,100)}</td></tr>`
  ).join('') || '<tr><td colspan="3">None</td></tr>';
}
load();
setInterval(load, 5000);
</script>
</body>
</html>"""
