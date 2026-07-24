#!/usr/bin/env python3
"""Flask application for the planner system"""
import json
import os
import sys
from flask import Flask, request, jsonify, render_template_string, send_file
from flask_cors import CORS

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from planner.config import Config
from planner.planner import Planner
from planner.agents.browser import BrowserAgent
from planner.registry import get_registry
from daemon import ChromeDaemon

# Initialize Flask
app = Flask(__name__)
CORS(app)  # Enable CORS for all origins

# Initialize Planner with Chrome daemon
daemon = ChromeDaemon()
planner = Planner()

# Register agents with daemon
browser_agent = BrowserAgent(daemon)
get_registry().register(browser_agent)

# Dashboard HTML
DASHBOARD_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>Planner Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f7fafc; color: #1a202c; padding: 20px; }
        .container { max-width: 1400px; margin: 0 auto; }
        h1 { font-size: 28px; font-weight: 700; margin-bottom: 20px; }
        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 12px; margin-bottom: 30px; }
        .header h1 { margin: 0; color: white; }
        .header p { opacity: 0.9; margin-top: 5px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .card { background: white; padding: 20px; border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        .card h3 { font-size: 14px; text-transform: uppercase; color: #718096; letter-spacing: 0.5px; margin-bottom: 10px; }
        .card .value { font-size: 32px; font-weight: 700; }
        .card .label { color: #4a5568; margin-top: 5px; }
        .plan-card { background: white; border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); padding: 20px; margin-bottom: 15px; }
        .plan-card .title { font-weight: 600; font-size: 18px; }
        .plan-card .status { display: inline-block; padding: 2px 10px; border-radius: 20px; font-size: 12px; margin-left: 10px; }
        .plan-card .status.pending { background: #fef3c7; color: #92400e; }
        .plan-card .status.running { background: #dbeafe; color: #1e40af; }
        .plan-card .status.completed { background: #d1fae5; color: #065f46; }
        .plan-card .status.failed { background: #fee2e2; color: #991b1b; }
        .progress-bar { background: #e2e8f0; border-radius: 10px; height: 6px; margin: 10px 0; overflow: hidden; }
        .progress-bar .fill { background: #667eea; height: 100%; transition: width 0.3s; }
        .task-item { border-left: 3px solid #e2e8f0; padding: 8px 12px; margin: 5px 0; background: #f7fafc; border-radius: 0 5px 5px 0; }
        .task-item.completed { border-color: #48bb78; }
        .task-item.running { border-color: #4299e1; }
        .task-item.failed { border-color: #fc8181; }
        .task-item .task-name { font-weight: 500; }
        .task-item .task-status { font-size: 12px; color: #718096; margin-left: 10px; }
        .btn { background: #667eea; color: white; border: none; padding: 10px 20px; border-radius: 8px; cursor: pointer; font-weight: 500; }
        .btn:hover { background: #5a67d8; }
        .btn-danger { background: #fc8181; }
        .btn-danger:hover { background: #f56565; }
        .btn-success { background: #48bb78; }
        .btn-success:hover { background: #38a169; }
        textarea { width: 100%; padding: 12px; border: 1px solid #e2e8f0; border-radius: 8px; font-family: monospace; resize: vertical; }
        .action-row { display: flex; gap: 10px; margin: 10px 0; flex-wrap: wrap; }
        .agent-badge { display: inline-block; background: #e2e8f0; padding: 2px 8px; border-radius: 12px; font-size: 11px; margin: 2px; }
        @media (max-width: 768px) { .grid { grid-template-columns: 1fr; } }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🤖 Automation Planner</h1>
            <p>Orchestrating goals into plans, tasks, and actions</p>
            <div class="action-row" style="margin-top:15px;">
                <button class="btn" onclick="refreshDashboard()">🔄 Refresh</button>
                <button class="btn btn-success" onclick="createTestPlan()">🧪 Create Test Plan</button>
            </div>
        </div>

        <div class="grid" id="stats">
            <div class="card"><h3>Plans</h3><div class="value" id="planCount">0</div></div>
            <div class="card"><h3>Tasks</h3><div class="value" id="taskCount">0</div></div>
            <div class="card"><h3>Agents</h3><div class="value" id="agentCount">0</div></div>
            <div class="card"><h3>Status</h3><div class="value" id="runningStatus" style="font-size:20px;">⏹️</div></div>
        </div>

        <div style="margin-bottom:20px;">
            <div style="display:flex; gap:10px;">
                <input type="text" id="goalInput" placeholder="Enter a goal..." style="flex:1; padding:12px; border:1px solid #e2e8f0; border-radius:8px;">
                <button class="btn" onclick="createPlan()">🚀 Create Plan</button>
            </div>
        </div>

        <div id="plans">
            <h2 style="margin-bottom:15px;">📋 Plans</h2>
            <p id="loadingMessage">Loading plans...</p>
        </div>
    </div>

    <script>
        const API_BASE = window.location.origin;
        
        async function apiCall(endpoint, method = 'GET', data = null) {
            try {
                const opts = { method, headers: { 'Content-Type': 'application/json' } };
                if (data) opts.body = JSON.stringify(data);
                const resp = await fetch(API_BASE + '/api' + endpoint, opts);
                return await resp.json();
            } catch (e) {
                console.error('API Error:', e);
                return { error: e.message };
            }
        }

        async function refreshDashboard() {
            const status = await apiCall('/status');
            if (!status.error) {
                document.getElementById('planCount').textContent = status.plans || 0;
                document.getElementById('taskCount').textContent = status.tasks || 0;
                document.getElementById('agentCount').textContent = status.agents?.length || 0;
                document.getElementById('runningStatus').textContent = status.running ? '▶️ Running' : '⏹️ Stopped';
            }

            const plans = await apiCall('/plans');
            const container = document.getElementById('plans');
            if (plans.error) {
                container.innerHTML = `<p>⚠️ ${plans.error}</p>`;
                return;
            }

            if (!plans.plans || plans.plans.length === 0) {
                container.innerHTML = `<p style="color:#718096;">No plans yet. Create one above!</p>`;
                return;
            }

            let html = '';
            for (const plan of plans.plans) {
                const statusClass = plan.status || 'pending';
                const progress = Math.round(plan.progress * 100);
                html += `
                    <div class="plan-card">
                        <div>
                            <span class="title">🎯 ${plan.goal}</span>
                            <span class="status ${statusClass}">${statusClass}</span>
                        </div>
                        <div style="font-size:13px; color:#718096; margin:5px 0;">${plan.description || 'No description'}</div>
                        <div style="display:flex; justify-content:space-between; font-size:13px; color:#4a5568;">
                            <span>Tasks: ${plan.tasks_count || 0}</span>
                            <span>Progress: ${progress}%</span>
                            <span>Priority: ${plan.priority || 1}</span>
                        </div>
                        <div class="progress-bar"><div class="fill" style="width:${progress}%"></div></div>
                        <div style="font-size:12px; color:#718096; margin-top:5px;">
                            Created: ${plan.created_at ? new Date(plan.created_at).toLocaleString() : 'N/A'}
                        </div>
                        <div style="margin-top:10px;">
                            <button class="btn btn-danger" onclick="deletePlan('${plan.id}')" style="padding:4px 12px; font-size:12px;">Delete</button>
                        </div>
                    </div>
                `;
            }
            container.innerHTML = html;
        }

        async function createPlan() {
            const input = document.getElementById('goalInput');
            const goal = input.value.trim();
            if (!goal) { alert('Please enter a goal'); return; }
            
            const result = await apiCall('/plans', 'POST', { goal, description: 'Created from dashboard' });
            if (result.id) {
                input.value = '';
                refreshDashboard();
                alert(`✅ Plan created: ${result.id}`);
            } else {
                alert(`❌ Failed: ${result.error}`);
            }
        }

        async function createTestPlan() {
            const result = await apiCall('/plans/test', 'POST');
            if (result.id) {
                refreshDashboard();
                alert(`✅ Test plan created: ${result.id}`);
            } else {
                alert(`❌ Failed: ${result.error}`);
            }
        }

        async function deletePlan(planId) {
            if (!confirm('Delete this plan?')) return;
            const result = await apiCall(`/plans/${planId}`, 'DELETE');
            if (result.success) {
                refreshDashboard();
            } else {
                alert(`Failed: ${result.error}`);
            }
        }

        // Auto-refresh every 10 seconds
        refreshDashboard();
        setInterval(refreshDashboard, 10000);
    </script>
</body>
</html>
'''

# ============= Routes =============

@app.route('/')
def index():
    return render_template_string(DASHBOARD_HTML)

@app.route('/api/status')
def api_status():
    """Get planner status"""
    return jsonify(planner.get_status())

@app.route('/api/plans')
def api_plans():
    """List all plans"""
    plans = []
    for plan_id, plan in planner.plans.items():
        p = plan.to_dict()
        p['tasks_count'] = len(plan.tasks)
        p['tasks'] = [planner.tasks[t].to_dict() for t in plan.tasks if t in planner.tasks]
        plans.append(p)
    return jsonify({'plans': plans})

@app.route('/api/plans', methods=['POST'])
def api_create_plan():
    """Create a new plan"""
    data = request.get_json() or {}
    goal = data.get('goal', 'Untitled plan')
    description = data.get('description', '')
    
    plan = planner.create_plan(goal, description)
    return jsonify(plan.to_dict())

@app.route('/api/plans/test', methods=['POST'])
def api_create_test_plan():
    """Create a test plan with example tasks"""
    from planner.task import Task, TaskPriority
    
    plan = planner.create_plan(
        "Test Chrome Automation",
        "Scrape hackathons and analyze them"
    )
    
    # Add tasks
    tasks = [
        {"name": "Navigate to hackathons", "action": "browser.navigate", "params": {"url": "https://unstop.com/hackathons"}},
        {"name": "Get page title", "action": "browser.execute_js", "params": {"script": "document.title"}},
        {"name": "Get page text", "action": "browser.get_text", "params": {}},
        {"name": "Take screenshot", "action": "browser.screenshot", "params": {"path": "test_screenshot.png"}}
    ]
    
    for t in tasks:
        task = Task(
            name=t["name"],
            action=t["action"],
            parameters=t["params"],
            priority=TaskPriority.MEDIUM
        )
        planner.add_task(plan.id, task)
    
    # Build DAG
    planner.build_dag(plan.id)
    
    # Start the plan
    planner.scheduler.start()
    
    return jsonify(plan.to_dict())

@app.route('/api/plans/<plan_id>', methods=['DELETE'])
def api_delete_plan(plan_id):
    """Delete a plan"""
    from planner.task import TaskStatus
    
    if plan_id in planner.plans:
        # Cancel running tasks
        for task_id in planner.plans[plan_id].tasks:
            if task_id in planner.tasks:
                planner.tasks[task_id].status = TaskStatus.CANCELLED
        
        del planner.plans[plan_id]
        if plan_id in planner.contexts:
            del planner.contexts[plan_id]
        return jsonify({'success': True})
    return jsonify({'error': 'Plan not found'}), 404

@app.route('/api/tasks')
def api_tasks():
    """List all tasks"""
    tasks = [task.to_dict() for task in planner.tasks.values()]
    return jsonify({'tasks': tasks})

@app.route('/api/tasks/<task_id>')
def api_task(task_id):
    """Get a task"""
    task = planner.tasks.get(task_id)
    if task:
        return jsonify(task.to_dict())
    return jsonify({'error': 'Task not found'}), 404

@app.route('/api/agents')
def api_agents():
    """List all agents"""
    return jsonify({'agents': get_registry().list_agents()})

@app.route('/api/capabilities')
def api_capabilities():
    """List all capabilities"""
    return jsonify({'capabilities': get_registry().list_capabilities()})

# ============= Main =============

if __name__ == '__main__':
    import socket
    
    # Get local IP
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    
    print("""
    🤖 Automation Planner
    =====================
    
    Architecture:
    - Planner: Orchestrates goals -> plans -> tasks
    - Scheduler: Determines when tasks run
    - Executor: Dispatches tasks to agents
    - Agents: Execute specific capabilities
    
    Registered Agents:
    """)
    
    for agent in get_registry().list_agents():
        print(f"  • {agent['name']}: {', '.join(agent['capabilities'])}")
    
    print("""
    🌐 Access URLs:
    """)
    print(f"  📊 Local:     http://127.0.0.1:5000/")
    print(f"  📊 Network:   http://{local_ip}:5000/")
    print(f"  📊 External:  http://100.93.132.97:5000/")
    print("""
    📋 API Base: http://127.0.0.1:5000/api/
    
    Press Ctrl+C to stop
    """)
    
    # Start planner
    planner.start()
    
    # Run Flask on all interfaces (0.0.0.0)
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
