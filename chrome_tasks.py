#!/usr/bin/env python3
"""
Chrome Automation Tasks for Celery
Complete working version with full logging
"""

import os
import sys
import json
import time
import logging
import traceback
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import requests
import redis

from celery import Task, group, chord
from celery.utils.log import get_task_logger
from celery.exceptions import Retry
from celery.result import AsyncResult

from celery_config import app

# ============================================================================
# Configuration
# ============================================================================

SCRIPT_LIBRARY_PATH = "/data/data/com.termux/files/home/automation/chrome-launcher/scripts-library"
LOG_DIR = Path("/data/data/com.termux/files/home/automation/chrome-launcher/logs/task_outputs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

API_BASE = "http://127.0.0.1:5000"
SESSION_NAME = "default"

logger = get_task_logger(__name__)

# ============================================================================
# Lazy Import for ChromeSessionManager
# ============================================================================

_manager = None

def get_manager():
    """Lazy initialize ChromeSessionManager"""
    global _manager
    if _manager is None:
        try:
            # Try cdpv119 first
            try:
                from cdpv119 import ChromeSessionManager
            except ImportError:
                # Fallback to cdpv117
                from cdpv117 import ChromeSessionManager
            _manager = ChromeSessionManager()
            logger.info("✅ ChromeSessionManager initialized")
        except Exception as e:
            logger.error(f"Failed to initialize ChromeSessionManager: {e}")
            raise
    return _manager

# ============================================================================
# Base Task Class
# ============================================================================

class ChromeTask(Task):
    """Base task with Chrome automation setup"""
    
    abstract = True
    
    def __init__(self):
        self.manager = None
        self.task_logger = None
    
    def setup(self):
        """Initialize manager"""
        if not self.manager:
            self.manager = get_manager()
        if not self.task_logger:
            self.task_logger = logger
    
    def log_output(self, task_name: str, result: Any, extra: Dict = None) -> str:
        """Log task output to file with full detail"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = LOG_DIR / f"{task_name}_{timestamp}.log"
        
        with open(log_file, 'w') as f:
            f.write("=" * 80 + "\n")
            f.write(f"TASK: {task_name}\n")
            f.write(f"TIMESTAMP: {datetime.now().isoformat()}\n")
            if extra:
                for key, value in extra.items():
                    f.write(f"{key.upper()}: {value}\n")
            f.write("=" * 80 + "\n\n")
            
            # Write full result with proper formatting
            if isinstance(result, (dict, list)):
                f.write(json.dumps(result, indent=2, default=str))
            else:
                f.write(str(result))
            
            f.write("\n\n")
            f.write("=" * 80 + "\n")
            f.write("END OF LOG\n")
        
        logger.info(f"📝 Output logged to: {log_file}")
        return str(log_file)
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log task failure"""
        error_log = LOG_DIR / f"error_{task_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        with open(error_log, 'w') as f:
            f.write(f"Task ID: {task_id}\n")
            f.write(f"Exception: {exc}\n")
            f.write(f"Args: {args}\n")
            f.write(f"Kwargs: {kwargs}\n")
            f.write("=" * 80 + "\n")
            f.write(einfo.traceback)
        
        logger.error(f"❌ Task {task_id} failed. Log: {error_log}")

# ============================================================================
# Session Management Tasks
# ============================================================================

@app.task(base=ChromeTask, bind=True, queue='chrome', max_retries=3)
def start_chrome_session(self, session_id: int, session_name: str = None):
    """Start a Chrome session by ID"""
    self.setup()
    logger.info(f"🚀 Starting session {session_id}")
    
    try:
        session = self.manager.db.get_session(session_id)
        
        if not session:
            error_msg = f'Session {session_id} not found'
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'session_id': session_id
            }
        
        if session['status'] == 'running':
            logger.info(f"Session {session_id} already running")
            return {
                'success': True,
                'status': 'already_running',
                'message': f'Session {session_id} is already running',
                'session': session
            }
        
        # Start the session
        self.manager.start_session(session_id)
        
        # Wait for session to stabilize
        time.sleep(5)
        
        # Get updated session info
        session = self.manager.db.get_session(session_id)
        
        # Get WebSocket URL if available
        ws_url = None
        try:
            devtools = self.manager._get_devtools(session['port'])
            ws_urls = devtools.get_ws_urls()
            if ws_urls:
                ws_url = ws_urls[0].get('ws_url')
        except:
            pass
        
        # Log output
        log_file = self.log_output(
            f"start_session_{session_id}",
            {
                'session_id': session_id,
                'session_name': session.get('name'),
                'port': session.get('port'),
                'pid': session.get('pid'),
                'status': session.get('status'),
                'ws_url': ws_url
            },
            {'session_name': session.get('name', 'unknown')}
        )
        
        return {
            'success': True,
            'status': 'started',
            'message': f'Session {session_id} started successfully',
            'session': session,
            'websocket_url': ws_url,
            'log_file': log_file
        }
        
    except Exception as e:
        logger.error(f"Failed to start session {session_id}: {e}")
        logger.error(traceback.format_exc())
        raise self.retry(exc=e, countdown=10, max_retries=3)

@app.task(base=ChromeTask, bind=True, queue='chrome', max_retries=3)
def stop_chrome_session(self, session_id: int):
    """Stop a Chrome session by ID"""
    self.setup()
    logger.info(f"⏹️ Stopping session {session_id}")
    
    try:
        session = self.manager.db.get_session(session_id)
        
        if not session:
            error_msg = f'Session {session_id} not found'
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'session_id': session_id
            }
        
        if session['status'] != 'running':
            logger.info(f"Session {session_id} already stopped")
            return {
                'success': True,
                'status': 'already_stopped',
                'message': f'Session {session_id} is already stopped',
                'session': session
            }
        
        self.manager.stop_session(session_id)
        
        # Log output
        log_file = self.log_output(
            f"stop_session_{session_id}",
            {
                'session_id': session_id,
                'session_name': session.get('name'),
                'status': 'stopped'
            },
            {'session_name': session.get('name', 'unknown')}
        )
        
        return {
            'success': True,
            'status': 'stopped',
            'message': f'Session {session_id} stopped successfully',
            'log_file': log_file
        }
        
    except Exception as e:
        logger.error(f"Failed to stop session {session_id}: {e}")
        logger.error(traceback.format_exc())
        raise self.retry(exc=e, countdown=10, max_retries=3)

@app.task(base=ChromeTask, bind=True, queue='chrome')
def restart_chrome_session(self, session_id: int):
    """Restart a Chrome session"""
    self.setup()
    logger.info(f"🔄 Restarting session {session_id}")
    
    try:
        # Stop first
        stop_result = stop_chrome_session.delay(session_id).get(timeout=60)
        
        if not stop_result.get('success', False) and stop_result.get('status') != 'already_stopped':
            return {
                'success': False,
                'error': f'Failed to stop session: {stop_result.get("error", "unknown")}',
                'stop_result': stop_result
            }
        
        # Wait before starting
        time.sleep(3)
        
        # Start again
        start_result = start_chrome_session.delay(session_id).get(timeout=60)
        
        # Log output
        log_file = self.log_output(
            f"restart_session_{session_id}",
            {
                'session_id': session_id,
                'stop_result': stop_result,
                'start_result': start_result
            },
            {'session_name': f'session_{session_id}'}
        )
        
        return {
            'success': start_result.get('success', False),
            'status': 'restarted',
            'message': f'Session {session_id} restarted successfully',
            'result': start_result,
            'log_file': log_file
        }
        
    except Exception as e:
        logger.error(f"Failed to restart session {session_id}: {e}")
        logger.error(traceback.format_exc())
        return {
            'success': False,
            'error': str(e),
            'session_id': session_id
        }

# ============================================================================
# Script Execution Tasks
# ============================================================================

@app.task(base=ChromeTask, bind=True, queue='chrome')
def execute_js_script(self, session_id: int, script_id: str, params: Dict = None):
    """Execute a JavaScript script on a Chrome session"""
    self.setup()
    logger.info(f"📝 Executing script {script_id} on session {session_id}")
    
    try:
        session = self.manager.db.get_session(session_id)
        
        if not session:
            return {
                'success': False,
                'error': f'Session {session_id} not found',
                'session_id': session_id
            }
        
        if session['status'] != 'running':
            return {
                'success': False,
                'error': f'Session {session_id} is not running',
                'session_id': session_id,
                'session_status': session['status']
            }
        
        # Get script from JavaScriptManager
        script = self.manager.js_manager.get_script(script_id)
        if not script:
            return {
                'success': False,
                'error': f'Script {script_id} not found',
                'script_id': script_id
            }
        
        # Get script code
        script_code = script.get('code', '')
        if not script_code:
            # Try to load from file if code not in script object
            script_file = Path(SCRIPT_LIBRARY_PATH) / f"{script_id}.js"
            if script_file.exists():
                with open(script_file, 'r') as f:
                    script_code = f.read()
            else:
                return {
                    'success': False,
                    'error': f'Script code not found for {script_id}',
                    'script_id': script_id
                }
        
        # Replace parameters if provided
        if params:
            for key, value in params.items():
                script_code = script_code.replace(f'{{{{{key}}}}}', str(value))
        
        # Execute script via WebSocket
        import websocket
        
        devtools = self.manager._get_devtools(session['port'])
        ws_urls = devtools.get_ws_urls()
        
        if not ws_urls:
            return {
                'success': False,
                'error': 'No WebSocket URL available',
                'session_id': session_id
            }
        
        ws_url = ws_urls[0]['ws_url']
        
        # Connect to WebSocket
        ws = websocket.create_connection(ws_url, timeout=30)
        
        # Send Runtime.evaluate command
        command = {
            'id': 1,
            'method': 'Runtime.evaluate',
            'params': {
                'expression': script_code,
                'returnByValue': True
            }
        }
        
        ws.send(json.dumps(command))
        response = json.loads(ws.recv())
        ws.close()
        
        # Parse result
        result_value = None
        if 'result' in response and 'result' in response['result']:
            result_value = response['result']['result'].get('value')
        elif 'result' in response:
            result_value = response['result']
        
        # Log output
        log_file = self.log_output(
            f"script_{script_id}_session_{session_id}",
            {
                'script_id': script_id,
                'params': params,
                'session_id': session_id,
                'session_name': session.get('name'),
                'result': result_value,
                'raw_response': response
            },
            {'script_id': script_id, 'session_name': session.get('name', 'unknown')}
        )
        
        return {
            'success': True,
            'status': 'executed',
            'message': f'Script {script_id} executed successfully',
            'result': result_value,
            'session': session,
            'log_file': log_file
        }
        
    except Exception as e:
        logger.error(f"Failed to execute script: {e}")
        logger.error(traceback.format_exc())
        return {
            'success': False,
            'error': str(e),
            'session_id': session_id,
            'script_id': script_id
        }

# ============================================================================
# DeepSeek Specific Tasks
# ============================================================================

@app.task(base=ChromeTask, bind=True, queue='chrome')
def deepseek_send_message(self, session_id: int, message: str = "Hello, how are you?"):
    """Send a message on DeepSeek"""
    self.setup()
    logger.info(f"💬 DeepSeek: Sending message on session {session_id}")
    
    # First ensure session is running
    session = self.manager.db.get_session(session_id)
    if not session or session['status'] != 'running':
        start_result = start_chrome_session.delay(session_id).get(timeout=60)
        if not start_result.get('success', False):
            return {
                'success': False,
                'error': 'Failed to start session',
                'start_result': start_result
            }
        time.sleep(5)
    
    # Execute the three scripts in sequence
    scripts = [
        'deepseek-writer/select-textarea-input.js',
        'deepseek-writer/deepseek-send-message.js',
        'deepseek-writer/send-enter-button.js'
    ]
    
    results = []
    all_success = True
    
    for i, script_name in enumerate(scripts, 1):
        params = {}
        if script_name == 'deepseek-writer/deepseek-send-message.js':
            params = {'promptText': message}
        
        logger.info(f"  [{i}/{len(scripts)}] Executing: {script_name}")
        result = execute_js_script.delay(session_id, script_name, params).get(timeout=60)
        results.append({
            'step': i,
            'script': script_name,
            'result': result
        })
        
        if not result.get('success', False):
            all_success = False
            logger.error(f"  ❌ Step {i} failed: {result.get('error', 'unknown')}")
            break
        
        logger.info(f"  ✅ Step {i} succeeded")
        time.sleep(2)  # Wait between steps
    
    # Log output
    log_file = self.log_output(
        f"deepseek_message_session_{session_id}",
        {
            'session_id': session_id,
            'message': message,
            'results': results,
            'all_success': all_success
        },
        {'session_name': session.get('name', 'unknown') if session else 'unknown'}
    )
    
    return {
        'success': all_success,
        'message': message,
        'session_id': session_id,
        'results': results,
        'log_file': log_file
    }

# ============================================================================
# Health Check Tasks
# ============================================================================

@app.task(base=ChromeTask, bind=True, queue='chrome')
def health_check_all_sessions(self):
    """Health check for all running sessions"""
    self.setup()
    logger.info("🏥 Running health check on all sessions")
    
    try:
        sessions = self.manager.db.list_sessions()
        running_sessions = [s for s in sessions if s['status'] == 'running']
        
        healthy = []
        unhealthy = []
        
        for session in running_sessions:
            try:
                devtools = self.manager._get_devtools(session['port'])
                if devtools._ensure_connection():
                    healthy.append(session['id'])
                else:
                    unhealthy.append(session['id'])
            except Exception:
                unhealthy.append(session['id'])
        
        # Auto-recover unhealthy sessions
        recovered = []
        for session_id in unhealthy:
            logger.warning(f"Session {session_id} is unhealthy, attempting recovery")
            try:
                self.manager._recover_session(session_id)
                recovered.append(session_id)
            except Exception as e:
                logger.error(f"Failed to recover session {session_id}: {e}")
        
        # Log output
        log_file = self.log_output(
            f"health_check_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            {
                'total_sessions': len(sessions),
                'running_sessions': len(running_sessions),
                'healthy_count': len(healthy),
                'unhealthy_count': len(unhealthy),
                'recovered_count': len(recovered),
                'healthy_sessions': healthy,
                'unhealthy_sessions': unhealthy,
                'recovered_sessions': recovered
            },
            {'check_type': 'health_check'}
        )
        
        return {
            'success': True,
            'status': 'completed',
            'timestamp': datetime.now().isoformat(),
            'healthy_count': len(healthy),
            'unhealthy_count': len(unhealthy),
            'recovered_count': len(recovered),
            'healthy_sessions': healthy,
            'unhealthy_sessions': unhealthy,
            'recovered_sessions': recovered,
            'log_file': log_file
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        logger.error(traceback.format_exc())
        return {
            'success': False,
            'error': str(e)
        }

# ============================================================================
# Scheduled Tasks (for Celery Beat)
# ============================================================================

@app.task(queue='chrome')
def scheduled_health_check():
    """Scheduled health check (runs every 5 minutes)"""
    result = health_check_all_sessions.delay()
    return {
        'status': 'scheduled',
        'task_id': result.id,
        'timestamp': datetime.now().isoformat()
    }

@app.task(queue='chrome')
def scheduled_deepseek_message():
    """Scheduled DeepSeek message (runs every hour)"""
    # Get first running session or create one
    manager = get_manager()
    sessions = manager.db.list_sessions()
    running = [s for s in sessions if s['status'] == 'running']
    
    if running:
        session_id = running[0]['id']
    else:
        # Create a session if none exists
        session_id = manager.db.create_session(
            "deepseek_auto",
            "https://deepseek.com",
            manager._get_next_port(),
            os.path.join(manager.config.base_profile_dir, "deepseek_auto")
        )
        # Start it
        start_chrome_session.delay(session_id).get(timeout=60)
        time.sleep(5)
    
    # Send message
    result = deepseek_send_message.delay(session_id, "Hello! This is a scheduled message.")
    return {
        'status': 'scheduled',
        'session_id': session_id,
        'task_id': result.id,
        'timestamp': datetime.now().isoformat()
    }

# ============================================================================
# Utility Tasks
# ============================================================================

@app.task(queue='chrome')
def list_all_sessions():
    """List all sessions"""
    manager = get_manager()
    sessions = manager.db.list_sessions()
    return {
        'success': True,
        'count': len(sessions),
        'sessions': sessions,
        'timestamp': datetime.now().isoformat()
    }

@app.task(queue='chrome')
def get_session_info(session_id: int):
    """Get detailed session info"""
    manager = get_manager()
    session = manager.db.get_session(session_id)
    if not session:
        return {
            'success': False,
            'error': f'Session {session_id} not found'
        }
    
    # Get tracked info
    tracked = manager.session_tracker.get_session_info(session_id)
    
    return {
        'success': True,
        'session': session,
        'tracked_info': tracked,
        'timestamp': datetime.now().isoformat()
    }

@app.task(queue='chrome')
def take_screenshot(session_id: int):
    """Take screenshot of a session"""
    manager = get_manager()
    session = manager.db.get_session(session_id)
    
    if not session or session['status'] != 'running':
        return {
            'success': False,
            'error': f'Session {session_id} is not running'
        }
    
    try:
        import websocket
        import base64
        
        devtools = manager._get_devtools(session['port'])
        ws_urls = devtools.get_ws_urls()
        
        if not ws_urls:
            return {
                'success': False,
                'error': 'No WebSocket URL available'
            }
        
        ws = websocket.create_connection(ws_urls[0]['ws_url'], timeout=30)
        
        command = {
            'id': 1,
            'method': 'Page.captureScreenshot',
            'params': {'format': 'png'}
        }
        
        ws.send(json.dumps(command))
        response = json.loads(ws.recv())
        ws.close()
        
        screenshot_data = response.get('result', {}).get('data', '')
        
        # Save screenshot
        screenshot_dir = Path("/data/data/com.termux/files/home/chrome-sessions/screenshots")
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        
        filename = screenshot_dir / f"session_{session_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        with open(filename, 'wb') as f:
            f.write(base64.b64decode(screenshot_data))
        
        return {
            'success': True,
            'session_id': session_id,
            'screenshot_file': str(filename),
            'timestamp': datetime.now().isoformat()
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }
