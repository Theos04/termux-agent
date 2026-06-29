#!/usr/bin/env python3
"""
Flask API for Chrome Automation - Unstop Job Scraper
Uses specialized JavaScript scripts from scripts-library/unstop
"""

import os
import sys
import json
import time
import threading
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS

# Import your existing modules
from cdpv116 import ChromeSessionManager, Config
from fetch_page2 import ChromePage
from session_db import SessionDB

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# Flask App Initialization
# ============================================================================

app = Flask(__name__)
CORS(app)

# ============================================================================
# Global State
# ============================================================================

class JobState:
    """Store job data in memory"""
    def __init__(self):
        self.jobs = []
        self.current_job = None
        self.last_update = None
        self.session_id = None
        self.port = 9226
        self._lock = threading.Lock()
        
    def add_job(self, job_data: Dict):
        with self._lock:
            if 'timestamp' not in job_data:
                job_data['timestamp'] = datetime.now().isoformat()
            self.jobs.append(job_data)
            self.last_update = datetime.now().isoformat()
            
    def get_jobs(self) -> List[Dict]:
        with self._lock:
            return self.jobs.copy()
            
    def get_job_by_id(self, job_id: int) -> Optional[Dict]:
        with self._lock:
            for job in self.jobs:
                if job.get('id') == job_id:
                    return job
            return None
            
    def set_current_job(self, job_id: int) -> bool:
        with self._lock:
            job = self.get_job_by_id(job_id)
            if job:
                self.current_job = job
                return True
            return False
            
    def clear(self):
        with self._lock:
            self.jobs = []
            self.current_job = None
            
    def get_stats(self) -> Dict:
        with self._lock:
            return {
                'total_jobs': len(self.jobs),
                'paid_jobs': sum(1 for j in self.jobs if j.get('payment_status') == 'Paid'),
                'unpaid_jobs': sum(1 for j in self.jobs if j.get('payment_status') == 'Unpaid'),
                'last_update': self.last_update,
                'has_current': self.current_job is not None
            }

job_state = JobState()
chrome_manager = None
chrome_page = None

# ============================================================================
# JavaScript Script Manager
# ============================================================================

class ScriptManager:
    """Load and manage JavaScript scripts from scripts-library/unstop"""
    
    def __init__(self):
        self.script_dir = os.path.expanduser("~/automation/chrome-launcher/scripts-library/unstop")
        self.scripts = {}
        self.load_all_scripts()
        
    def load_all_scripts(self):
        """Load all .js files from the unstop directory"""
        if not os.path.exists(self.script_dir):
            logger.warning(f"Script directory not found: {self.script_dir}")
            return
            
        for filename in os.listdir(self.script_dir):
            if filename.endswith('.js'):
                script_path = os.path.join(self.script_dir, filename)
                try:
                    with open(script_path, 'r') as f:
                        script_content = f.read()
                    script_name = filename.replace('.js', '')
                    self.scripts[script_name] = script_content
                    logger.info(f"Loaded script: {script_name}")
                except Exception as e:
                    logger.error(f"Failed to load script {filename}: {e}")
                    
    def get_script(self, name: str) -> Optional[str]:
        """Get a script by name"""
        return self.scripts.get(name)
        
    def list_scripts(self) -> List[str]:
        """List all available script names"""
        return list(self.scripts.keys())
        
    def execute_script(self, name: str, chrome_page: ChromePage, params: Dict = None) -> Any:
        """Execute a script and return the result"""
        script = self.get_script(name)
        if not script:
            return {'error': f'Script not found: {name}'}
            
        # If params provided, inject them as a variable
        if params:
            param_js = f"const params = {json.dumps(params)};"
            chrome_page.js(param_js)
            
        # Execute the script
        result = chrome_page.js(script)
        return result

script_manager = ScriptManager()

# ============================================================================
# Chrome Session Management
# ============================================================================

def init_chrome_session(port: int = 9226):
    """Initialize a Chrome session on the specified port"""
    global chrome_manager, chrome_page
    
    try:
        logger.info(f"Initializing Chrome session on port {port}")
        
        # Check if we already have a session
        if chrome_manager:
            sessions = chrome_manager.db.list_sessions()
            for session in sessions:
                if session['port'] == port and session['status'] == 'running':
                    logger.info(f"Session already running on port {port}")
                    chrome_page = ChromePage(port)
                    if chrome_page.connect():
                        logger.info("Connected to existing Chrome session")
                        return True
                    else:
                        logger.warning("Could not connect to existing session, will create new")
        
        # Create a new session
        session_name = f"unstop_scraper_{int(time.time())}"
        url = "https://unstop.com/opportunities"
        
        config = Config()
        chrome_manager = ChromeSessionManager()
        
        # Check if we need to create a session on this port
        sessions = chrome_manager.db.list_sessions()
        existing = None
        for session in sessions:
            if session['port'] == port:
                existing = session
                break
                
        if existing:
            session_id = existing['id']
            if existing['status'] != 'running':
                chrome_manager.start_session(session_id)
                time.sleep(5)
        else:
            profile_dir = os.path.join(config.base_profile_dir, session_name)
            os.makedirs(profile_dir, exist_ok=True)
            
            session_id = chrome_manager.db.create_session(
                name=session_name,
                url=url,
                port=port,
                profile_dir=profile_dir
            )
            chrome_manager.start_session(session_id)
            time.sleep(5)
            
        # Connect to the page
        chrome_page = ChromePage(port)
        if chrome_page.connect():
            logger.info(f"Connected to Chrome on port {port}")
            job_state.session_id = session_id
            return True
        else:
            logger.error("Failed to connect to Chrome page")
            return False
            
    except Exception as e:
        logger.error(f"Failed to initialize Chrome session: {e}")
        return False

# ============================================================================
# Flask Routes
# ============================================================================

@app.route('/', methods=['GET'])
def index():
    """Home page with API documentation"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Chrome Automation API - Unstop</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }
            .container { max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            h1 { color: #333; border-bottom: 2px solid #4CAF50; padding-bottom: 10px; }
            h2 { color: #555; margin-top: 30px; }
            .endpoint { background: #e8f5e9; padding: 15px; margin: 10px 0; border-radius: 5px; border-left: 4px solid #4CAF50; }
            .method { display: inline-block; padding: 3px 10px; border-radius: 3px; font-weight: bold; margin-right: 10px; }
            .get { background: #4CAF50; color: white; }
            .post { background: #2196F3; color: white; }
            .delete { background: #f44336; color: white; }
            .code { background: #f4f4f4; padding: 15px; border-radius: 5px; font-family: monospace; overflow-x: auto; }
            .status { padding: 10px; margin: 10px 0; border-radius: 5px; }
            .running { background: #e8f5e9; border: 1px solid #4CAF50; }
            .script-list { background: #f9f9f9; padding: 15px; border-radius: 5px; margin: 10px 0; }
            .script-item { display: inline-block; background: #e3f2fd; padding: 5px 10px; margin: 5px; border-radius: 3px; font-family: monospace; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 Unstop Automation API</h1>
            <p>Using specialized JavaScript scripts from scripts-library/unstop</p>
            
            <div class="status running">
                <strong>Status:</strong> Running on port 9226
            </div>
            
            <h2>📜 Available Scripts</h2>
            <div class="script-list">
                <div id="scripts">
                    <span class="script-item">apply4jobs.js</span>
                    <span class="script-item">get-job-list.js</span>
                    <span class="script-item">get-hackathon-list.js</span>
                    <span class="script-item">register4hackathon.js</span>
                </div>
            </div>
            
            <h2>📊 Current Status</h2>
            <div id="status">
                <div class="job-card">
                    <p><strong>Total Jobs:</strong> <span id="total-jobs">0</span></p>
                    <p><strong>Last Update:</strong> <span id="last-update">Never</span></p>
                </div>
            </div>
            
            <h2>📋 API Endpoints</h2>
            
            <div class="endpoint">
                <span class="method get">GET</span>
                <strong>/api/status</strong>
                <p>Get API status and statistics</p>
            </div>
            
            <div class="endpoint">
                <span class="method post">POST</span>
                <strong>/api/init</strong>
                <p>Initialize Chrome session on port 9226</p>
            </div>
            
            <div class="endpoint">
                <span class="method post">POST</span>
                <strong>/api/execute/&lt;script_name&gt;</strong>
                <p>Execute a specific JavaScript script</p>
                <div class="code">
POST /api/execute/get-job-list
{
    "params": {"filter": "fresher"}  // optional
}
                </div>
            </div>
            
            <div class="endpoint">
                <span class="method post">POST</span>
                <strong>/api/scripts/list</strong>
                <p>List all available scripts</p>
            </div>
            
            <div class="endpoint">
                <span class="method post">POST</span>
                <strong>/api/jobs/list</strong>
                <p>Get all fetched jobs from memory</p>
            </div>
            
            <div class="endpoint">
                <span class="method post">POST</span>
                <strong>/api/jobs/apply</strong>
                <p>Apply to a job using apply4jobs.js</p>
                <div class="code">
{
    "job_id": 1,
    "params": {
        "name": "John Doe",
        "email": "john@example.com"
    }
}
                </div>
            </div>
            
            <div class="endpoint">
                <span class="method post">POST</span>
                <strong>/api/register/hackathon</strong>
                <p>Register for a hackathon using register4hackathon.js</p>
                <div class="code">
{
    "hackathon_id": "123",
    "params": {
        "team_name": "Team Alpha",
        "members": ["member1@email.com"]
    }
}
                </div>
            </div>
            
            <div class="endpoint">
                <span class="method post">POST</span>
                <strong>/api/clear</strong>
                <p>Clear all stored jobs</p>
            </div>
            
            <h2>🔄 Example Workflow</h2>
            <div class="code">
# 1. Initialize Chrome
curl -X POST http://localhost:5000/api/init

# 2. Get job list
curl -X POST http://localhost:5000/api/execute/get-job-list \\
  -H "Content-Type: application/json" \\
  -d '{"params": {"page": 1, "limit": 10}}'

# 3. Apply to a job
curl -X POST http://localhost:5000/api/jobs/apply \\
  -H "Content-Type: application/json" \\
  -d '{
    "job_id": 1,
    "params": {
        "name": "John Doe",
        "email": "john@example.com",
        "phone": "1234567890"
    }
}'

# 4. Get hackathon list
curl -X POST http://localhost:5000/api/execute/get-hackathon-list \\
  -H "Content-Type: application/json" \\
  -d '{"params": {"status": "open"}}'

# 5. Register for hackathon
curl -X POST http://localhost:5000/api/register/hackathon \\
  -H "Content-Type: application/json" \\
  -d '{
    "hackathon_id": "123",
    "params": {
        "team_name": "Team Alpha",
        "members": ["john@example.com"]
    }
}'
            </div>
            
            <h2>📤 Example Response</h2>
            <div class="code">
{
    "status": "success",
    "data": {
        "script": "get-job-list",
        "result": {
            "jobs": [
                {
                    "id": "123",
                    "title": "Software Engineer",
                    "company": "Google",
                    "stipend": "₹50,000/month",
                    "location": "Remote"
                }
            ]
        }
    }
}
            </div>
        </div>
    </body>
    </html>
    """
    return render_template_string(html)

# ============================================================================
# API Routes
# ============================================================================

@app.route('/api/status', methods=['GET'])
def api_status():
    """Get API status"""
    stats = job_state.get_stats()
    
    return jsonify({
        'status': 'success',
        'data': {
            **stats,
            'chrome_connected': chrome_page is not None and chrome_page.connected,
            'session_id': job_state.session_id,
            'port': 9226,
            'available_scripts': script_manager.list_scripts()
        }
    })

@app.route('/api/init', methods=['POST'])
def api_init():
    """Initialize Chrome session"""
    try:
        success = init_chrome_session(9226)
        
        if success:
            # Navigate to Unstop
            if chrome_page:
                chrome_page.js("window.location.href = 'https://unstop.com/opportunities'")
                time.sleep(3)
            
            return jsonify({
                'status': 'success',
                'message': 'Chrome session initialized on port 9226',
                'data': {
                    'port': 9226,
                    'session_id': job_state.session_id,
                    'connected': chrome_page is not None and chrome_page.connected,
                    'scripts': script_manager.list_scripts()
                }
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Failed to initialize Chrome session'
            }), 500
            
    except Exception as e:
        logger.error(f"Init error: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/scripts/list', methods=['POST'])
def api_list_scripts():
    """List all available scripts"""
    scripts = script_manager.list_scripts()
    
    return jsonify({
        'status': 'success',
        'data': {
            'scripts': scripts,
            'count': len(scripts),
            'directory': script_manager.script_dir
        }
    })

@app.route('/api/execute/<script_name>', methods=['POST'])
def api_execute_script(script_name: str):
    """Execute a specific script"""
    global chrome_page
    
    if not chrome_page:
        return jsonify({
            'status': 'error',
            'message': 'Chrome not initialized. Call /api/init first'
        }), 400
        
    try:
        data = request.get_json() or {}
        params = data.get('params', {})
        
        # Execute the script
        result = script_manager.execute_script(script_name, chrome_page, params)
        
        if result and isinstance(result, dict) and 'error' in result:
            return jsonify({
                'status': 'error',
                'message': result['error']
            }), 500
            
        # Store jobs if the script is get-job-list
        if script_name == 'get-job-list' and result:
            if isinstance(result, dict) and 'jobs' in result:
                for job in result['jobs']:
                    if not job_state.get_job_by_id(job.get('id')):
                        job_id = len(job_state.jobs) + 1
                        job['id'] = job_id
                        job_state.add_job(job)
                        
        return jsonify({
            'status': 'success',
            'data': {
                'script': script_name,
                'result': result,
                'timestamp': datetime.now().isoformat()
            }
        })
        
    except Exception as e:
        logger.error(f"Script execution error: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/jobs/list', methods=['POST'])
def api_get_jobs():
    """Get all stored jobs"""
    jobs = job_state.get_jobs()
    
    return jsonify({
        'status': 'success',
        'data': {
            'jobs': jobs,
            'count': len(jobs),
            'stats': job_state.get_stats()
        }
    })

@app.route('/api/jobs/apply', methods=['POST'])
def api_apply_job():
    """Apply to a job using apply4jobs.js script"""
    global chrome_page
    
    if not chrome_page:
        return jsonify({
            'status': 'error',
            'message': 'Chrome not initialized. Call /api/init first'
        }), 400
        
    try:
        data = request.get_json() or {}
        job_id = data.get('job_id')
        params = data.get('params', {})
        
        # Get the job
        job = job_state.get_job_by_id(job_id)
        if not job:
            return jsonify({
                'status': 'error',
                'message': f'Job with ID {job_id} not found'
            }), 404
            
        # Execute apply4jobs.js with the job data
        apply_params = {
            'job': job,
            'application_data': params
        }
        
        result = script_manager.execute_script('apply4jobs', chrome_page, apply_params)
        
        return jsonify({
            'status': 'success',
            'message': f'Applied to job: {job.get("title", "Untitled")}',
            'data': {
                'job': job,
                'application': params,
                'result': result,
                'applied_at': datetime.now().isoformat()
            }
        })
        
    except Exception as e:
        logger.error(f"Apply error: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/register/hackathon', methods=['POST'])
def api_register_hackathon():
    """Register for a hackathon using register4hackathon.js script"""
    global chrome_page
    
    if not chrome_page:
        return jsonify({
            'status': 'error',
            'message': 'Chrome not initialized. Call /api/init first'
        }), 400
        
    try:
        data = request.get_json() or {}
        hackathon_id = data.get('hackathon_id')
        params = data.get('params', {})
        
        if not hackathon_id:
            return jsonify({
                'status': 'error',
                'message': 'hackathon_id is required'
            }), 400
            
        # Execute register4hackathon.js
        register_params = {
            'hackathon_id': hackathon_id,
            'registration_data': params
        }
        
        result = script_manager.execute_script('register4hackathon', chrome_page, register_params)
        
        return jsonify({
            'status': 'success',
            'message': f'Registered for hackathon: {hackathon_id}',
            'data': {
                'hackathon_id': hackathon_id,
                'registration': params,
                'result': result,
                'registered_at': datetime.now().isoformat()
            }
        })
        
    except Exception as e:
        logger.error(f"Hackathon registration error: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/clear', methods=['POST'])
def api_clear():
    """Clear all stored jobs"""
    job_state.clear()
    
    return jsonify({
        'status': 'success',
        'message': 'All jobs cleared'
    })

# ============================================================================
# Background Worker
# ============================================================================

def background_fetcher():
    """Background thread to periodically fetch jobs"""
    while True:
        try:
            if chrome_page and chrome_page.connected:
                logger.info("Background: Fetching job list...")
                
                # Execute get-job-list script
                result = script_manager.execute_script('get-job-list', chrome_page, {'page': 1})
                
                if result and isinstance(result, dict) and 'jobs' in result:
                    for job in result['jobs']:
                        # Check if job already exists
                        existing = False
                        for stored_job in job_state.get_jobs():
                            if stored_job.get('title') == job.get('title') and \
                               stored_job.get('company') == job.get('company'):
                                existing = True
                                break
                                
                        if not existing:
                            job_id = len(job_state.jobs) + 1
                            job['id'] = job_id
                            job_state.add_job(job)
                            logger.info(f"Background: Found new job: {job.get('title')}")
            
            # Wait before next fetch
            time.sleep(300)  # 5 minutes
            
        except Exception as e:
            logger.error(f"Background fetcher error: {e}")
            time.sleep(60)

# ============================================================================
# Main Application
# ============================================================================

def main():
    """Main entry point"""
    print("""
╔═══════════════════════════════════════════════════════════╗
║           🤖 Unstop Automation API                        ║
║           Using Specialized JS Scripts                   ║
║           Port: 9226                                     ║
╚═══════════════════════════════════════════════════════════╝
    """)
    
    print(f"📜 Available scripts: {script_manager.list_scripts()}")
    print()
    
    # Initialize Chrome
    print("Initializing Chrome on port 9226...")
    init_chrome_session(9226)
    
    # Start background fetcher
    background_thread = threading.Thread(target=background_fetcher, daemon=True)
    background_thread.start()
    print("Background fetcher started")
    
    # Run Flask app
    print("\n🌐 API Server running at: http://localhost:5000")
    print("📋 API Documentation: http://localhost:5000/")
    print("\nPress Ctrl+C to stop\n")
    
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=False,
        threaded=True
    )

if __name__ == '__main__':
    main()
