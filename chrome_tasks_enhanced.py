# chrome_tasks_enhanced.py - Complete fixed version with all methods
import os
import sys
import json
import time
import logging
import traceback
import asyncio
import base64
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from celery import Task
from celery.utils.log import get_task_logger
from celery_config import app

# Import Chrome daemon and Google Sheets DB
from daemon import ChromeDaemon

# Try to import Google Sheets DB
try:
    from google_sheets_db import get_db, GoogleSheetsDB
    HAS_SHEETS = True
except ImportError:
    HAS_SHEETS = False
    print("⚠️ Google Sheets DB not available")

logger = get_task_logger(__name__)

# ============================================================================
# Helper: Run async functions in sync context
# ============================================================================

def run_async(coro):
    """Run an async coroutine in a synchronous context"""
    try:
        # Try to get the current event loop
        loop = asyncio.get_event_loop()
    except RuntimeError:
        # If no event loop, create a new one
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_running():
        # If loop is running, create a new loop in a thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    else:
        # Run in the current loop
        return loop.run_until_complete(coro)

# ============================================================================
# Base Task with proper database handling
# ============================================================================

class ChromeTask(Task):
    abstract = True

    def __init__(self):
        self.daemon = None
        self.db = None
        self._db_initialized = False

    def setup(self):
        """Initialize daemon and database connections"""
        if self.daemon is None:
            self.daemon = ChromeDaemon()

        if self.db is None and HAS_SHEETS and not self._db_initialized:
            try:
                self.db = get_db(interactive=False)
                self._db_initialized = True
                logger.info("✅ Database initialized successfully")
            except Exception as e:
                logger.error(f"❌ Failed to initialize database: {e}")
                self.db = None

    def ensure_db(self):
        """Ensure database is available, reinitialize if needed"""
        if not HAS_SHEETS:
            return False

        if self.db is None:
            try:
                self.db = get_db(interactive=False)
                self._db_initialized = True
                return self.db is not None
            except Exception as e:
                logger.error(f"❌ Failed to reinitialize database: {e}")
                return False
        return True

    def log_to_sheet(self, tab_name: str, data: Dict):
        """Log data to Google Sheets with error handling"""
        if not self.ensure_db():
            logger.warning(f"⚠️ Database not available, skipping log to {tab_name}")
            return False

        try:
            # Ensure all values are JSON serializable
            clean_data = {}
            for key, value in data.items():
                if value is None:
                    clean_data[key] = ''
                elif isinstance(value, (dict, list)):
                    clean_data[key] = json.dumps(value, default=str)
                else:
                    clean_data[key] = str(value)

            self.db.insert_row(tab_name, clean_data)
            return True
        except Exception as e:
            logger.error(f"❌ Failed to log to Google Sheets: {e}")
            return False

    def log_output(self, task_name: str, result: Any, extra: Dict = None) -> str:
        """Log task output to file"""
        LOG_DIR = Path("/data/data/com.termux/files/home/automation/chrome-launcher/logs/task_outputs")
        LOG_DIR.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = LOG_DIR / f"{task_name}_{timestamp}.log"

        try:
            with open(log_file, 'w') as f:
                f.write("=" * 80 + "\n")
                f.write(f"TASK: {task_name}\n")
                f.write(f"TIMESTAMP: {datetime.now().isoformat()}\n")
                if extra:
                    for key, value in extra.items():
                        f.write(f"{key.upper()}: {value}\n")
                f.write("=" * 80 + "\n\n")
                if isinstance(result, (dict, list)):
                    f.write(json.dumps(result, indent=2, default=str))
                else:
                    f.write(str(result))
            return str(log_file)
        except Exception as e:
            logger.error(f"❌ Failed to log output: {e}")
            return ""

    def _extract_initial_data(self, name: str):
        """Extract initial data from page with proper error handling"""
        if not self.ensure_db():
            logger.warning(f"⚠️ Database not available for initial data extraction from {name}")
            return False

        try:
            # Extract page title
            title_result = run_async(self.daemon.evaluate(name, 'document.title'))
            if title_result.get('success') and title_result.get('result'):
                self.db.save_extracted_data(name, 'page_title', title_result['result'])
                logger.info(f"✅ Extracted page title: {title_result['result']}")

            # Extract current URL
            url_result = run_async(self.daemon.evaluate(name, 'window.location.href'))
            if url_result.get('success') and url_result.get('result'):
                self.db.save_extracted_data(name, 'current_url', url_result['result'])
                logger.info(f"✅ Extracted current URL: {url_result['result']}")

            # Extract meta data
            meta_script = """
            (function() {
                const meta = { title: document.title, description: '', keywords: '' };
                const metaTags = document.getElementsByTagName('meta');
                for (let tag of metaTags) {
                    if (tag.name === 'description') meta.description = tag.content;
                    if (tag.name === 'keywords') meta.keywords = tag.content;
                }
                return meta;
            })()
            """
            meta_result = run_async(self.daemon.evaluate(name, meta_script))
            if meta_result.get('success') and meta_result.get('result'):
                self.db.save_extracted_data(name, 'page_metadata', meta_result['result'])
                logger.info(f"✅ Extracted page metadata")
            
            return True

        except Exception as e:
            logger.error(f"❌ Error extracting initial data from {name}: {e}")
            logger.error(traceback.format_exc())
            return False

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle task failure with logging"""
        error_data = {
            'timestamp': datetime.now().isoformat(),
            'task_id': task_id,
            'task_name': self.name,
            'args': json.dumps(args, default=str),
            'kwargs': json.dumps(kwargs, default=str),
            'error': str(exc),
            'traceback': einfo.traceback
        }
        self.log_to_sheet('tasks_log', error_data)
        logger.error(f"❌ Task {task_id} failed: {exc}")

# ============================================================================
# SESSION TASKS - With proper async handling and database
# ============================================================================

@app.task(base=ChromeTask, bind=True, queue='chrome', max_retries=3)
def start_chrome_session_task(self, name: str, url: str = 'https://unstop.com/'):
    """Start a Chrome session with Google Sheets logging"""
    self.setup()
    logger.info(f"🚀 Starting session: {name}")

    # Log task start
    self.log_to_sheet('tasks_log', {
        'timestamp': datetime.now().isoformat(),
        'task_id': self.request.id,
        'task_name': 'start_chrome_session',
        'status': 'starting',
        'result': json.dumps({'name': name, 'url': url}, default=str),
        'error': ''
    })

    try:
        # Check if session exists (sync)
        session = self.daemon.get_session(name)
        if session:
            self.log_to_sheet('chrome_sessions', {
                'session_id': name,
                'name': name,
                'url': url,
                'status': 'already_running',
                'pid': session.get('pid', 0),
                'timestamp': datetime.now().isoformat(),
                'data': json.dumps(session, default=str)
            })
            return {
                'success': True,
                'status': 'already_running',
                'session': session,
                'session_name': name
            }

        # Start session - run async method synchronously
        result = run_async(self.daemon.start_session(name, url))

        if result.get('success'):
            self.log_to_sheet('chrome_sessions', {
                'session_id': name,
                'name': name,
                'url': url,
                'status': 'started',
                'pid': result.get('pid', 0),
                'timestamp': datetime.now().isoformat(),
                'data': json.dumps(result, default=str)
            })
            # Extract initial data - now with proper error handling
            self._extract_initial_data(name)

        # Log task completion
        self.log_to_sheet('tasks_log', {
            'timestamp': datetime.now().isoformat(),
            'task_id': self.request.id,
            'task_name': 'start_chrome_session',
            'status': 'completed' if result.get('success') else 'failed',
            'result': json.dumps(result, default=str),
            'error': '' if result.get('success') else result.get('error', 'Unknown error')
        })

        return result

    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Failed to start session {name}: {error_msg}")
        logger.error(traceback.format_exc())

        self.log_to_sheet('tasks_log', {
            'timestamp': datetime.now().isoformat(),
            'task_id': self.request.id,
            'task_name': 'start_chrome_session',
            'status': 'error',
            'result': '',
            'error': error_msg
        })

        raise self.retry(exc=e, countdown=10, max_retries=3)

@app.task(base=ChromeTask, bind=True, queue='chrome')
def stop_chrome_session_task(self, name: str):
    """Stop a Chrome session"""
    self.setup()
    logger.info(f"⏹️ Stopping session: {name}")

    try:
        # Run async method synchronously
        result = run_async(self.daemon.stop_session(name))

        if result.get('success') and self.ensure_db():
            self.log_to_sheet('chrome_sessions', {
                'session_id': name,
                'name': name,
                'status': 'stopped',
                'timestamp': datetime.now().isoformat(),
                'data': json.dumps(result, default=str)
            })
        return result
    except Exception as e:
        logger.error(f"❌ Failed to stop session {name}: {e}")
        return {'success': False, 'error': str(e), 'session_name': name}

@app.task(base=ChromeTask, bind=True, queue='chrome')
def restart_chrome_session_task(self, name: str):
    """Restart a Chrome session"""
    self.setup()
    logger.info(f"🔄 Restarting session: {name}")

    try:
        # Stop first
        stop_result = stop_chrome_session_task.delay(name).get(timeout=30)
        if not stop_result.get('success', False):
            return {'success': False, 'error': 'Failed to stop session', 'session_name': name}

        time.sleep(3)
        start_result = start_chrome_session_task.delay(name).get(timeout=30)

        return {
            'success': start_result.get('success', False),
            'status': 'restarted',
            'result': start_result,
            'session_name': name
        }
    except Exception as e:
        logger.error(f"❌ Failed to restart session {name}: {e}")
        return {'success': False, 'error': str(e), 'session_name': name}

# ============================================================================
# BROWSER TASKS - With proper async handling
# ============================================================================

@app.task(base=ChromeTask, bind=True, queue='chrome')
def navigate_task(self, name: str, url: str, extract_after: bool = True):
    """Navigate to URL"""
    self.setup()
    logger.info(f"🌐 Navigating {name} to {url}")

    try:
        # Check if session exists
        session = self.daemon.get_session(name)
        if not session:
            start_result = start_chrome_session_task.delay(name, url).get(timeout=30)
            if not start_result.get('success', False):
                return {'success': False, 'error': 'Session not found and failed to start', 'session_name': name}

        # Run async method synchronously
        result = run_async(self.daemon.navigate(name, url))

        if result.get('success') and extract_after:
            self._extract_initial_data(name)

        if self.ensure_db():
            self.log_to_sheet('automation_results', {
                'timestamp': datetime.now().isoformat(),
                'automation_id': f'navigate_{name}',
                'data': json.dumps({'url': url, 'result': result}, default=str),
                'status': 'success' if result.get('success') else 'error'
            })
        return result
    except Exception as e:
        logger.error(f"❌ Failed to navigate {name}: {e}")
        return {'success': False, 'error': str(e), 'session_name': name}

@app.task(base=ChromeTask, bind=True, queue='chrome')
def click_task(self, name: str, selector: str):
    """Click an element"""
    self.setup()
    logger.info(f"🖱️ Clicking {selector} on {name}")

    try:
        # Run async method synchronously
        result = run_async(self.daemon.click(name, selector))

        if self.ensure_db():
            self.log_to_sheet('automation_results', {
                'timestamp': datetime.now().isoformat(),
                'automation_id': f'click_{name}',
                'data': json.dumps({'selector': selector, 'result': result}, default=str),
                'status': 'success' if result.get('success') else 'error'
            })
        return result
    except Exception as e:
        logger.error(f"❌ Failed to click {selector} on {name}: {e}")
        return {'success': False, 'error': str(e), 'session_name': name}

@app.task(base=ChromeTask, bind=True, queue='chrome')
def evaluate_task(self, name: str, expression: str, save_key: Optional[str] = None):
    """Evaluate JavaScript expression"""
    self.setup()
    logger.info(f"📝 Evaluating on {name}")

    try:
        # Run async method synchronously
        result = run_async(self.daemon.evaluate(name, expression))

        if save_key and result.get('success') and result.get('result') is not None:
            if self.ensure_db():
                self.db.save_extracted_data(name, save_key, result['result'])
                logger.info(f"✅ Saved evaluation result with key: {save_key}")

        if self.ensure_db():
            self.log_to_sheet('automation_results', {
                'timestamp': datetime.now().isoformat(),
                'automation_id': f'evaluate_{name}',
                'data': json.dumps({
                    'expression': expression[:100],
                    'result': result.get('result')
                }, default=str),
                'status': 'success' if result.get('success') else 'error'
            })
        return result
    except Exception as e:
        logger.error(f"❌ Failed to evaluate on {name}: {e}")
        return {'success': False, 'error': str(e), 'session_name': name}

@app.task(base=ChromeTask, bind=True, queue='chrome')
def execute_js_task(self, name: str, script: str, save_key: Optional[str] = None):
    """Execute JavaScript with async support"""
    self.setup()
    logger.info(f"⚡ Executing JS on {name}")

    try:
        enhanced_script = f"""
        (async function() {{
            try {{
                const result = await (async () => {{
                    {script}
                }})();
                if (result === undefined) {{
                    return {{ success: true, result: null }};
                }}
                try {{
                    return {{ success: true, result: JSON.parse(JSON.stringify(result)) }};
                }} catch (e) {{
                    return {{ success: true, result: String(result) }};
                }}
            }} catch (error) {{
                return {{ success: false, error: error.message }};
            }}
        }})()
        """

        # Run async method synchronously
        result = run_async(self.daemon.evaluate(name, enhanced_script))

        if save_key and result.get('success') and result.get('result') is not None:
            if self.ensure_db():
                self.db.save_extracted_data(name, save_key, result['result'])
                logger.info(f"✅ Saved JS execution result with key: {save_key}")

        if self.ensure_db():
            self.log_to_sheet('automation_results', {
                'timestamp': datetime.now().isoformat(),
                'automation_id': f'execute_js_{name}',
                'data': json.dumps({'script': script[:200], 'result': result.get('result')}, default=str),
                'status': 'success' if result.get('success') else 'error'
            })
        return result
    except Exception as e:
        logger.error(f"❌ Failed to execute JS on {name}: {e}")
        return {'success': False, 'error': str(e), 'session_name': name}

@app.task(base=ChromeTask, bind=True, queue='chrome')
def screenshot_task(self, name: str, save: bool = True):
    """Take screenshot"""
    self.setup()
    logger.info(f"📸 Taking screenshot of {name}")

    try:
        # Run async method synchronously
        result = run_async(self.daemon.screenshot(name))

        if result.get('success') and save and result.get('screenshot') and self.ensure_db():
            filename = f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            self.db.save_screenshot(name, result['screenshot'], filename)
            result['saved_path'] = str(self.db.screenshots_dir / filename)
            logger.info(f"✅ Saved screenshot: {filename}")

        return result
    except Exception as e:
        logger.error(f"❌ Failed to screenshot {name}: {e}")
        return {'success': False, 'error': str(e), 'session_name': name}

@app.task(base=ChromeTask, bind=True, queue='chrome')
def cdp_command_task(self, name: str, method: str, params: Dict):
    """Execute CDP command"""
    self.setup()
    logger.info(f"🔧 CDP {method} on {name}")

    try:
        # Run async method synchronously
        result = run_async(self.daemon.execute_cdp_command(name, method, params))

        if self.ensure_db():
            self.log_to_sheet('automation_results', {
                'timestamp': datetime.now().isoformat(),
                'automation_id': f'cdp_{name}',
                'data': json.dumps({'method': method, 'params': params, 'result': result}, default=str),
                'status': 'success' if result.get('success') else 'error'
            })
        return result
    except Exception as e:
        logger.error(f"❌ Failed CDP {method} on {name}: {e}")
        return {'success': False, 'error': str(e), 'session_name': name}

# ============================================================================
# DATA EXTRACTION TASKS - Fixed JavaScript syntax
# ============================================================================

@app.task(base=ChromeTask, bind=True, queue='chrome')
def extract_data_task(self, name: str, selector: str, attribute: Optional[str] = None,
                      key: str = None):
    """Extract data using selector - Fixed JavaScript syntax"""
    self.setup()
    logger.info(f"📊 Extracting {selector} from {name}")

    try:
        # Build JavaScript with proper syntax - using single quotes to avoid escaping issues
        if attribute:
            script = f'''
                (function() {{
                    const el = document.querySelector("{selector}");
                    if (el) {{
                        return {{
                            value: el.getAttribute("{attribute}"),
                            selector: "{selector}",
                            attribute: "{attribute}"
                        }};
                    }}
                    return null;
                }})()
            '''
        else:
            script = f'''
                (function() {{
                    const el = document.querySelector("{selector}");
                    if (el) {{
                        return {{
                            text: el.textContent.trim(),
                            innerHTML: el.innerHTML,
                            selector: "{selector}"
                        }};
                    }}
                    return null;
                }})()
            '''

        # Execute the script
        result = run_async(self.daemon.evaluate(name, script))

        # Save extracted data if successful
        if result.get('success') and result.get('result') is not None:
            if self.ensure_db():
                save_key = key or f'extracted_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
                self.db.save_extracted_data(name, save_key, result['result'])
                logger.info(f"✅ Saved extracted data with key: {save_key}")

        return {
            'success': True,
            'data': result.get('result'),
            'key': key,
            'selector': selector
        }
    except Exception as e:
        logger.error(f"❌ Failed to extract from {name}: {e}")
        logger.error(traceback.format_exc())
        return {'success': False, 'error': str(e), 'session_name': name}

@app.task(base=ChromeTask, bind=True, queue='chrome')
def extract_multiple_task(self, name: str, selectors: Dict, save_key: str):
    """Extract multiple selectors - Fixed JavaScript syntax"""
    self.setup()
    logger.info(f"📊 Extracting multiple selectors from {name}")

    try:
        script_lines = ["(function() {", "const results = {};"]

        for key, selector_config in selectors.items():
            if isinstance(selector_config, str):
                script_lines.append(f"""
                    const el_{key} = document.querySelector('{selector_config}');
                    results['{key}'] = el_{key} ? el_{key}.textContent.trim() : null;
                """)
            else:
                sel = selector_config.get('selector')
                attr = selector_config.get('attribute')
                if attr:
                    script_lines.append(f"""
                        const el_{key} = document.querySelector('{sel}');
                        results['{key}'] = el_{key} ? el_{key}.getAttribute('{attr}') : null;
                    """)
                else:
                    script_lines.append(f"""
                        const el_{key} = document.querySelector('{sel}');
                        if (el_{key}) {{
                            results['{key}'] = {{
                                text: el_{key}.textContent.trim(),
                                html: el_{key}.innerHTML
                            }};
                        }} else {{
                            results['{key}'] = null;
                        }}
                    """)

        script_lines.append("return results;")
        script_lines.append("})()")
        script = "\n".join(script_lines)

        # Execute the script
        result = run_async(self.daemon.evaluate(name, script))

        if result.get('success') and result.get('result') and self.ensure_db():
            self.db.save_extracted_data(name, save_key, result['result'])
            # Also save individual values
            for key, value in result['result'].items():
                if value is not None:
                    self.db.save_extracted_data(name, f"{save_key}_{key}", value)
            logger.info(f"✅ Saved multiple extracted data with key: {save_key}")

        return {
            'success': True,
            'data': result.get('result', {}),
            'selectors': selectors,
            'key': save_key
        }
    except Exception as e:
        logger.error(f"❌ Failed to extract multiple from {name}: {e}")
        logger.error(traceback.format_exc())
        return {'success': False, 'error': str(e), 'session_name': name}

@app.task(base=ChromeTask, bind=True, queue='chrome')
def save_html_task(self, name: str, extract_title: bool = True, save_key: Optional[str] = None):
    """Save HTML content"""
    self.setup()
    logger.info(f"💾 Saving HTML from {name}")

    try:
        # Run async method synchronously
        html_result = run_async(self.daemon.get_html(name))
        if not html_result.get('success'):
            return html_result

        html_content = html_result.get('html', '')
        title = ''
        if extract_title:
            title_result = run_async(self.daemon.evaluate(name, 'document.title'))
            if title_result.get('success'):
                title = title_result.get('result', '')

        url_result = run_async(self.daemon.evaluate(name, 'window.location.href'))
        url = url_result.get('result', '') if url_result.get('success') else ''

        if self.ensure_db():
            filepath = self.db.save_page_data(name, url, title, html_content)
            response = {'success': True, 'filepath': filepath, 'url': url, 'title': title, 'size': len(html_content)}
            if save_key:
                self.db.save_extracted_data(name, save_key, response)
            return response
        else:
            return {'success': True, 'url': url, 'title': title, 'size': len(html_content)}
    except Exception as e:
        logger.error(f"❌ Failed to save HTML from {name}: {e}")
        return {'success': False, 'error': str(e), 'session_name': name}

# ============================================================================
# DATA RETRIEVAL TASKS
# ============================================================================

@app.task(base=ChromeTask, bind=True, queue='chrome')
def get_session_data_task(self, name: str):
    """Get all stored data for a session"""
    self.setup()
    try:
        if self.ensure_db():
            data = self.db.get_session_data(name)
            return {'success': True, 'session_name': name, 'data': data}
        else:
            return {'success': True, 'session_name': name, 'data': {'pages': [], 'extracted': [], 'screenshots': []}}
    except Exception as e:
        logger.error(f"❌ Failed to get session data for {name}: {e}")
        return {'success': False, 'error': str(e), 'session_name': name}

@app.task(base=ChromeTask, bind=True, queue='chrome')
def get_session_status_task(self, name: str):
    """Get session status"""
    self.setup()
    try:
        session = self.daemon.get_session(name)
        if not session:
            return {'exists': False, 'session_name': name}

        return {
            'exists': True,
            'session': session,
            'connected': name in self.daemon.active_connections,
            'session_name': name
        }
    except Exception as e:
        logger.error(f"❌ Failed to get session status for {name}: {e}")
        return {'success': False, 'error': str(e), 'session_name': name}

@app.task(base=ChromeTask, bind=True, queue='chrome')
def list_sessions_task(self):
    """List all sessions"""
    self.setup()
    try:
        sessions_data = self.daemon.load_session_info()
        sessions = []
        for session_id, session in sessions_data.get('sessions', {}).items():
            sessions.append({
                'id': session_id,
                'name': session.get('name', ''),
                'url': session.get('url', ''),
                'port': session.get('port', 0),
                'status': session.get('status', 'unknown'),
                'pid': session.get('pid', 0),
                'ws_id': session.get('current_ws_id', None)
            })
        return {'success': True, 'sessions': sessions, 'count': len(sessions)}
    except Exception as e:
        logger.error(f"❌ Failed to list sessions: {e}")
        return {'success': False, 'error': str(e)}

# ============================================================================
# BATCH AND HEALTH TASKS
# ============================================================================

@app.task(base=ChromeTask, bind=True, queue='chrome')
def batch_operations_task(self, name: str, operations: List[Dict], stop_on_error: bool = True):
    """Execute multiple operations in sequence"""
    self.setup()
    logger.info(f"📦 Batch operations on {name}: {len(operations)} operations")

    results = []
    all_success = True

    for i, op in enumerate(operations, 1):
        op_type = op.get('type')
        op_params = op.get('params', {})
        result = None

        try:
            if op_type == 'navigate':
                result = run_async(self.daemon.navigate(name, op_params.get('url')))
            elif op_type == 'click':
                result = run_async(self.daemon.click(name, op_params.get('selector')))
            elif op_type == 'evaluate':
                result = run_async(self.daemon.evaluate(name, op_params.get('expression')))
            elif op_type == 'execute_js':
                script = op_params.get('script')
                if script:
                    enhanced = f"""
                    (async function() {{
                        try {{
                            const result = await (async () => {{ {script} }})();
                            return {{ success: true, result: JSON.parse(JSON.stringify(result || null)) }};
                        }} catch (error) {{
                            return {{ success: false, error: error.message }};
                        }}
                    }})()
                    """
                    result = run_async(self.daemon.evaluate(name, enhanced))
            elif op_type == 'screenshot':
                result = run_async(self.daemon.screenshot(name))
            elif op_type == 'sleep':
                time.sleep(op_params.get('seconds', 1))
                result = {'success': True, 'message': f'Slept for {op_params.get("seconds", 1)} seconds'}
            else:
                result = {'success': False, 'error': f'Unknown operation type: {op_type}'}
        except Exception as e:
            result = {'success': False, 'error': str(e)}

        results.append({'step': i, 'type': op_type, 'result': result, 'success': result.get('success', False)})
        if not result.get('success', False) and stop_on_error:
            all_success = False
            break

    if self.ensure_db():
        self.log_to_sheet('automation_results', {
            'timestamp': datetime.now().isoformat(),
            'automation_id': f'batch_{name}',
            'data': json.dumps({'operations': len(operations), 'results': results}, default=str),
            'status': 'success' if all_success else 'partial'
        })

    return {
        'success': all_success,
        'operations_completed': len(results),
        'total_operations': len(operations),
        'results': results
    }

@app.task(base=ChromeTask, bind=True, queue='chrome')
def health_check_task(self):
    """Health check for all sessions"""
    self.setup()
    logger.info("🏥 Running health check")

    try:
        sessions = self.daemon.load_session_info().get('sessions', {})
        running = [s for s in sessions.values() if s.get('status') == 'running']

        healthy = []
        unhealthy = []
        for session in running:
            name = session.get('name')
            if name:
                # Try to get session - this is sync
                status = self.daemon.get_session(name)
                if status:
                    healthy.append(name)
                else:
                    unhealthy.append(name)

        return {
            'success': True,
            'total_sessions': len(sessions),
            'running_sessions': len(running),
            'healthy_count': len(healthy),
            'unhealthy_count': len(unhealthy)
        }
    except Exception as e:
        logger.error(f"❌ Health check failed: {e}")
        return {'success': False, 'error': str(e)}

# ============================================================================
# SCHEDULED TASKS
# ============================================================================

@app.task(queue='chrome')
def scheduled_health_check():
    """Scheduled health check task"""
    result = health_check_task.delay()
    return {'status': 'scheduled', 'task_id': result.id}

@app.task(queue='chrome')
def scheduled_deepseek_message():
    """Scheduled DeepSeek message task"""
    return {'status': 'scheduled', 'message': 'DeepSeek scheduled task'}

# ============================================================================
# ALIASES FOR BACKWARD COMPATIBILITY
# ============================================================================

# These aliases match the names expected by the API
start_chrome_session = start_chrome_session_task
stop_chrome_session = stop_chrome_session_task
restart_chrome_session = restart_chrome_session_task
get_session_status = get_session_status_task
list_all_sessions = list_sessions_task
get_session_info = get_session_status_task
health_check_all_sessions = health_check_task
take_screenshot = screenshot_task
execute_js_script = execute_js_task

# ============================================================================
# EXPORTS - FIXED: Added restart_chrome_session_task
# ============================================================================

__all__ = [
    'start_chrome_session_task',
    'stop_chrome_session_task',
    'restart_chrome_session_task',
    'navigate_task',
    'click_task',
    'evaluate_task',
    'execute_js_task',
    'screenshot_task',
    'cdp_command_task',
    'extract_data_task',
    'extract_multiple_task',
    'save_html_task',
    'get_session_data_task',
    'get_session_status_task',
    'list_sessions_task',
    'batch_operations_task',
    'health_check_task',
    'scheduled_health_check',
    'scheduled_deepseek_message',
    # Aliases
    'start_chrome_session',
    'stop_chrome_session',
    'restart_chrome_session',
    'get_session_status',
    'list_all_sessions',
    'get_session_info',
    'health_check_all_sessions',
    'take_screenshot',
    'execute_js_script'
]
