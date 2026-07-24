#!/usr/bin/env python3
# workflow3.py - Complete workflow management with Celery integration

import os
import json
import hashlib
import uuid
import re
import time
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum

# Try importing optional dependencies
try:
    import redis
    from redis.exceptions import ConnectionError
except ImportError:
    redis = None
    ConnectionError = Exception

try:
    from celery import Celery
except ImportError:
    Celery = None

try:
    import requests
except ImportError:
    requests = None

# For rich console
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich.syntax import Syntax
    from rich import box
    console = Console()
except ImportError:
    console = None
    print("Warning: rich not installed. Install with: pip install rich")

# ============================================================================
# Configuration
# ============================================================================

@dataclass
class WorkflowConfig:
    base_dir: str = os.path.expanduser("~/chrome-workflows")
    scripts_library: str = os.path.expanduser("~/chrome-workflows/scripts-library")
    workflows_dir: str = os.path.expanduser("~/chrome-workflows/workflows")
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None
    celery_broker: str = "redis://localhost:6379/0"
    celery_backend: str = "redis://localhost:6379/0"
    api_base_url: str = "http://127.0.0.1:5000"
    script_library_enabled: bool = True

# ============================================================================
# Step Types
# ============================================================================

class StepType(Enum):
    JS_EXECUTE = "js_execute"
    NAVIGATE = "navigate"
    CLICK = "click"
    SCREENSHOT = "screenshot"
    WAIT = "wait"
    EXTRACT = "extract"
    CDP_COMMAND = "cdp_command"
    CONDITIONAL = "conditional"
    LOOP = "loop"
    API_CALL = "api_call"
    ASSERT = "assert"
    STORE = "store"
    RETRY = "retry"
    SCROLL = "scroll"
    FILL = "fill"
    SELECT = "select"

@dataclass
class WorkflowStep:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    type: str = "js_execute"
    name: str = ""
    description: str = ""
    code: str = ""
    selector: str = ""
    url: str = ""
    expression: str = ""
    timeout: int = 30
    retry_count: int = 0
    retry_delay: int = 1
    wait_time: int = 1
    variable_name: str = ""
    variable_value: Any = None
    condition: Dict = field(default_factory=dict)
    loop_config: Dict = field(default_factory=dict)
    api_config: Dict = field(default_factory=dict)
    assert_config: Dict = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    continue_on_error: bool = False

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'WorkflowStep':
        return cls(**data)

# ============================================================================
# Workflow Model
# ============================================================================

@dataclass
class Workflow:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    session_name: str = "unstop"
    session_url: str = "https://unstop.com/"
    steps: List[Dict] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    status: str = "draft"
    tags: List[str] = field(default_factory=list)
    schedule: Optional[str] = None
    queue_name: str = "default"
    priority: int = 0
    max_retries: int = 3
    timeout_seconds: int = 300

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'Workflow':
        return cls(**data)

# ============================================================================
# Script Library Manager
# ============================================================================

class ScriptLibrary:
    def __init__(self, config: WorkflowConfig):
        self.config = config
        self.scripts_dir = Path(config.scripts_library)
        self.scripts_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_structure()

    def _ensure_structure(self):
        """Create directory structure"""
        for subdir in ['workflows', 'scripts', 'templates', 'shared']:
            (self.scripts_dir / subdir).mkdir(exist_ok=True)

    def save_script(self, workflow_name: str, step: WorkflowStep) -> str:
        """Save a JavaScript file to the scripts library"""
        workflow_dir = self.scripts_dir / 'workflows' / workflow_name
        workflow_dir.mkdir(parents=True, exist_ok=True)

        safe_name = step.name.lower().replace(' ', '_') if step.name else f"step_{step.id}"
        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '', safe_name)

        filename = f"{safe_name}_{step.type}_{step.id}.js"
        filepath = workflow_dir / filename

        script_content = self._build_script_content(step, workflow_name)

        with open(filepath, 'w') as f:
            f.write(script_content)

        metadata_file = workflow_dir / f"{filename}.meta.json"
        with open(metadata_file, 'w') as f:
            json.dump({
                'step_id': step.id,
                'step_name': step.name,
                'step_type': step.type,
                'created_at': datetime.now().isoformat(),
                'workflow': workflow_name,
                'description': step.description,
                'metadata': step.metadata
            }, f, indent=2)

        return str(filepath)

    def _build_script_content(self, step: WorkflowStep, workflow_name: str) -> str:
        """Build JavaScript content with metadata header"""
        header = f"""/**
 * Script: {step.name}
 * ID: {step.id}
 * Type: {step.type}
 * Workflow: {workflow_name}
 * Created: {datetime.now().isoformat()}
 * Description: {step.description}
 */

// ============================================================================
// Step Configuration
// ============================================================================

const stepConfig = {{
    id: '{step.id}',
    name: '{step.name}',
    type: '{step.type}',
    timeout: {step.timeout},
    retryCount: {step.retry_count},
    retryDelay: {step.retry_delay},
    continueOnError: {str(step.continue_on_error).lower()},
    metadata: {json.dumps(step.metadata, indent=2)}
}};

// ============================================================================
// Main Execution Function
// ============================================================================

async function execute(api, context) {{
    console.log(`🔧 Executing step: ${{stepConfig.name}} (ID: ${{stepConfig.id}})`);
    
    try {{
"""
        code = step.code if step.code else "// Your code here"
        code_lines = code.split('\n')
        indented_code = '\n'.join(f'        {line}' for line in code_lines)
        
        footer = f"""
    }} catch (error) {{
        console.error(`❌ Step failed: ${{error.message}}`);
        if (stepConfig.continueOnError) {{
            console.warn(`⚠️ Continuing despite error`);
            return {{ error: error.message, step: stepConfig.name }};
        }}
        throw error;
    }}
}}

// Export for workflow engine
if (typeof module !== 'undefined' && module.exports) {{
    module.exports = {{ execute, stepConfig }};
}}
"""
        return header + indented_code + footer

    def get_script(self, workflow_name: str, step_id: str) -> Optional[str]:
        """Retrieve a script by workflow name and step ID"""
        workflow_dir = self.scripts_dir / 'workflows' / workflow_name
        if not workflow_dir.exists():
            return None

        for js_file in workflow_dir.glob(f"*_{step_id}.js"):
            with open(js_file, 'r') as f:
                return f.read()
        return None

    def get_all_scripts(self, workflow_name: str) -> List[Dict]:
        """List all scripts for a workflow"""
        workflow_dir = self.scripts_dir / 'workflows' / workflow_name
        if not workflow_dir.exists():
            return []

        scripts = []
        for js_file in workflow_dir.glob("*.js"):
            meta_file = js_file.with_suffix('.js.meta.json')
            metadata = {}
            if meta_file.exists():
                with open(meta_file, 'r') as f:
                    metadata = json.load(f)

            scripts.append({
                'filename': js_file.name,
                'path': str(js_file),
                'metadata': metadata,
                'size': js_file.stat().st_size,
                'modified': datetime.fromtimestamp(js_file.stat().st_mtime).isoformat()
            })
        return scripts

    def delete_script(self, workflow_name: str, step_id: str) -> bool:
        """Delete a script by workflow name and step ID"""
        workflow_dir = self.scripts_dir / 'workflows' / workflow_name
        if not workflow_dir.exists():
            return False

        deleted = False
        for js_file in workflow_dir.glob(f"*_{step_id}.js"):
            js_file.unlink()
            meta_file = js_file.with_suffix('.js.meta.json')
            if meta_file.exists():
                meta_file.unlink()
            deleted = True
        return deleted

    def list_workflow_scripts(self, workflow_name: str) -> List[str]:
        """List all script filenames for a workflow"""
        workflow_dir = self.scripts_dir / 'workflows' / workflow_name
        if not workflow_dir.exists():
            return []
        return [f.name for f in workflow_dir.glob("*.js")]

# ============================================================================
# Celery App - Defined at Module Level
# ============================================================================

# Create Celery app at module level so the worker can find it
celery_app = None
if Celery:
    celery_app = Celery(
        'workflow_tasks',
        broker='redis://localhost:6379/0',
        backend='redis://localhost:6379/0'
    )
    
    celery_app.conf.update(
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        timezone='UTC',
        enable_utc=True,
        task_track_started=True,
        task_time_limit=300,
        task_soft_time_limit=240,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        task_queue_max_priority=10,
        task_default_queue='default',
        task_default_priority=0,
        task_always_eager=False,
    )

# ============================================================================
# Workflow Manager
# ============================================================================

class WorkflowManager:
    def __init__(self, config: WorkflowConfig = None):
        self.config = config or WorkflowConfig()
        self.script_library = ScriptLibrary(self.config)
        self._ensure_directories()

        # Initialize Redis
        self.redis = None
        if redis:
            try:
                self.redis = redis.Redis(
                    host=self.config.redis_host,
                    port=self.config.redis_port,
                    db=self.config.redis_db,
                    password=self.config.redis_password,
                    decode_responses=True,
                    socket_connect_timeout=5
                )
                self.redis.ping()
                logging.info("✅ Redis connected")
            except Exception as e:
                logging.warning(f"⚠️ Redis connection failed: {e}")
                self.redis = None
        else:
            logging.warning("⚠️ Redis library not installed")

        # Use the module-level Celery app
        self.celery_app = celery_app

    def _ensure_directories(self):
        """Create necessary directories"""
        Path(self.config.base_dir).mkdir(parents=True, exist_ok=True)
        Path(self.config.workflows_dir).mkdir(parents=True, exist_ok=True)

    def create_workflow(self, data: Dict) -> Workflow:
        """Create a new workflow"""
        workflow = Workflow.from_dict(data)
        self._save_workflow(workflow)
        return workflow

    def _save_workflow(self, workflow: Workflow):
        """Save workflow to disk and Redis"""
        workflow_dir = Path(self.config.workflows_dir) / workflow.id
        workflow_dir.mkdir(parents=True, exist_ok=True)

        with open(workflow_dir / 'workflow.json', 'w') as f:
            json.dump(workflow.to_dict(), f, indent=2)

        for i, step_data in enumerate(workflow.steps):
            step = WorkflowStep.from_dict(step_data)
            step_file = workflow_dir / f"step_{i:03d}_{step.id}.json"
            with open(step_file, 'w') as f:
                json.dump(step.to_dict(), f, indent=2)
            if step.type == "js_execute" and step.code:
                self.script_library.save_script(workflow.name, step)

        if self.redis:
            try:
                workflow_dict = workflow.to_dict()
                redis_data = {}
                for key, value in workflow_dict.items():
                    if isinstance(value, (list, dict)):
                        redis_data[key] = json.dumps(value)
                    elif value is None:
                        redis_data[key] = ''
                    else:
                        redis_data[key] = str(value)
                
                self.redis.delete(f"workflow:{workflow.id}")
                self.redis.hset(f"workflow:{workflow.id}", mapping=redis_data)
                self.redis.sadd("workflows:active", workflow.id)
            except Exception as e:
                logging.error(f"Redis save failed: {e}")

        logging.info(f"✅ Workflow saved: {workflow.name} (ID: {workflow.id})")

    def get_workflow(self, workflow_id: str) -> Optional[Workflow]:
        """Get a workflow by ID (supports partial IDs)"""
        if len(workflow_id) < 12:
            full_id = self.find_workflow_by_partial_id(workflow_id)
            if full_id:
                workflow_id = full_id
            else:
                return None

        workflow_file = Path(self.config.workflows_dir) / workflow_id / 'workflow.json'
        if not workflow_file.exists():
            return self.get_workflow_from_redis(workflow_id)
        
        try:
            with open(workflow_file, 'r') as f:
                data = json.load(f)
                return Workflow.from_dict(data)
        except Exception as e:
            logging.error(f"Failed to load workflow {workflow_id}: {e}")
            return None

    def find_workflow_by_partial_id(self, partial_id: str) -> Optional[str]:
        """Find a workflow by partial ID"""
        workflows_dir = Path(self.config.workflows_dir)
        if not workflows_dir.exists():
            return None

        for wf_dir in workflows_dir.iterdir():
            if wf_dir.is_dir() and wf_dir.name.startswith(partial_id):
                return wf_dir.name
        return None

    def get_workflow_from_redis(self, workflow_id: str) -> Optional[Workflow]:
        """Get workflow from Redis"""
        if not self.redis:
            return None
        
        try:
            data = self.redis.hgetall(f"workflow:{workflow_id}")
            if not data:
                return None
            
            workflow_dict = {}
            for key, value in data.items():
                if key in ['steps', 'metadata', 'tags']:
                    try:
                        workflow_dict[key] = json.loads(value)
                    except:
                        workflow_dict[key] = [] if key == 'steps' else {}
                else:
                    workflow_dict[key] = value
            
            return Workflow.from_dict(workflow_dict)
        except Exception as e:
            logging.error(f"Redis read failed: {e}")
            return None

    def list_workflows(self) -> List[Dict]:
        """List all workflows"""
        workflows = []
        workflows_dir = Path(self.config.workflows_dir)

        if not workflows_dir.exists():
            return []

        for wf_dir in workflows_dir.iterdir():
            if wf_dir.is_dir():
                wf_file = wf_dir / 'workflow.json'
                if wf_file.exists():
                    try:
                        with open(wf_file, 'r') as f:
                            data = json.load(f)
                            workflows.append({
                                'id': data.get('id', wf_dir.name),
                                'name': data.get('name', 'Unknown'),
                                'description': data.get('description', ''),
                                'status': data.get('status', 'unknown'),
                                'version': data.get('version', '1.0.0'),
                                'steps': len(data.get('steps', [])),
                                'created_at': data.get('created_at', ''),
                                'updated_at': data.get('updated_at', '')
                            })
                    except Exception as e:
                        logging.error(f"Failed to read workflow {wf_dir}: {e}")
        return workflows

    def add_step_to_workflow(self, workflow_id: str, step_data: Dict) -> Workflow:
        """Add a step to an existing workflow"""
        workflow = self.get_workflow(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        step = WorkflowStep.from_dict(step_data)
        workflow.steps.append(step.to_dict())
        workflow.updated_at = datetime.now().isoformat()

        self._save_workflow(workflow)
        return workflow

    def queue_workflow(self, workflow_id: str, session_name: str = None) -> str:
        """Queue a workflow for execution via Celery"""
        if not self.celery_app:
            raise RuntimeError("Celery not configured. Install celery and redis.")

        workflow = self.get_workflow(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        workflow.status = "queued"
        self._save_workflow(workflow)

        # Use the module-level task
        from workflow3 import execute_workflow_task
        task = execute_workflow_task.delay(workflow_id, session_name or workflow.session_name)

        if self.redis:
            self.redis.hset(
                f"workflow:execution:{workflow_id}",
                mapping={
                    "task_id": task.id,
                    "status": "queued",
                    "queued_at": datetime.now().isoformat(),
                    "session": session_name or workflow.session_name
                }
            )

        logging.info(f"📤 Workflow {workflow.name} queued (Task: {task.id})")
        return task.id

    def _execute_workflow_task(self, workflow_id: str, session_name: str = None):
        """Execute a workflow (called by Celery)"""
        workflow = self.get_workflow(workflow_id)
        if not workflow:
            return {"error": f"Workflow {workflow_id} not found"}

        session_name = session_name or workflow.session_name
        results = []
        context = {}

        for step_data in workflow.steps:
            step = WorkflowStep.from_dict(step_data)
            try:
                result = self._execute_step(step, session_name, context)
                results.append({
                    'step_id': step.id,
                    'step_name': step.name,
                    'status': 'success',
                    'result': result,
                    'timestamp': datetime.now().isoformat()
                })
                if step.variable_name:
                    context[step.variable_name] = result
            except Exception as e:
                results.append({
                    'step_id': step.id,
                    'step_name': step.name,
                    'status': 'failed',
                    'error': str(e),
                    'timestamp': datetime.now().isoformat()
                })
                if not step.continue_on_error:
                    break

        workflow.status = "completed" if all(r['status'] == 'success' for r in results) else "failed"
        self._save_workflow(workflow)

        result_file = Path(self.config.workflows_dir) / workflow_id / 'execution_results.json'
        with open(result_file, 'w') as f:
            json.dump({
                'workflow_id': workflow_id,
                'workflow_name': workflow.name,
                'executed_at': datetime.now().isoformat(),
                'session': session_name,
                'results': results,
                'status': workflow.status
            }, f, indent=2)

        if self.redis:
            self.redis.hset(
                f"workflow:execution:{workflow_id}",
                mapping={
                    "status": workflow.status,
                    "completed_at": datetime.now().isoformat(),
                    "result_count": len(results)
                }
            )

        return {
            'workflow_id': workflow_id,
            'status': workflow.status,
            'results': results
        }

    def _execute_step(self, step: WorkflowStep, session_name: str, context: Dict) -> Any:
        """Execute a single step"""
        if not requests:
            raise RuntimeError("requests library not installed")

        if step.type == "js_execute":
            return self._execute_js(step, session_name, context)
        elif step.type == "navigate":
            return self._navigate(step, session_name)
        elif step.type == "click":
            return self._click(step, session_name)
        elif step.type == "screenshot":
            return self._screenshot(step, session_name)
        elif step.type == "wait":
            time.sleep(step.wait_time)
            return {"status": "waited", "duration": step.wait_time}
        elif step.type == "extract":
            return self._extract(step, session_name, context)
        elif step.type == "api_call":
            return self._api_call(step)
        elif step.type == "assert":
            return self._assert(step, session_name, context)
        elif step.type == "scroll":
            return self._scroll(step, session_name)
        elif step.type == "fill":
            return self._fill(step, session_name)
        elif step.type == "select":
            return self._select(step, session_name)
        else:
            raise ValueError(f"Unknown step type: {step.type}")

    def _execute_js(self, step: WorkflowStep, session_name: str, context: Dict) -> Any:
        """Execute JavaScript code"""
        script = self.script_library.get_script(session_name, step.id)
        expression = step.code if step.code else script
        
        if not expression:
            raise ValueError(f"No code found for step {step.id}")

        response = requests.post(
            f"{self.config.api_base_url}/session/{session_name}/evaluate",
            json={"expression": expression}
        )

        if response.status_code != 200:
            raise Exception(f"API error: {response.text}")

        return response.json()

    def _navigate(self, step: WorkflowStep, session_name: str) -> Dict:
        """Navigate to URL"""
        response = requests.post(
            f"{self.config.api_base_url}/session/{session_name}/navigate",
            json={"url": step.url}
        )
        return response.json()

    def _click(self, step: WorkflowStep, session_name: str) -> Dict:
        """Click element"""
        response = requests.post(
            f"{self.config.api_base_url}/session/{session_name}/click",
            json={"selector": step.selector}
        )
        return response.json()

    def _screenshot(self, step: WorkflowStep, session_name: str) -> Dict:
        """Take screenshot"""
        response = requests.get(
            f"{self.config.api_base_url}/session/{session_name}/screenshot"
        )
        return response.json()

    def _extract(self, step: WorkflowStep, session_name: str, context: Dict) -> Any:
        """Extract data from page"""
        expression = step.expression or step.code
        if not expression:
            raise ValueError(f"No expression found for step {step.id}")

        response = requests.post(
            f"{self.config.api_base_url}/session/{session_name}/evaluate",
            json={"expression": expression}
        )
        return response.json()

    def _api_call(self, step: WorkflowStep) -> Dict:
        """Make an API call"""
        config = step.api_config
        method = config.get('method', 'GET')
        url = config.get('url')
        headers = config.get('headers', {})
        body = config.get('body', {})

        if not url:
            raise ValueError("API URL required")

        if method.upper() == 'GET':
            response = requests.get(url, headers=headers, timeout=step.timeout)
        elif method.upper() == 'POST':
            response = requests.post(url, headers=headers, json=body, timeout=step.timeout)
        else:
            response = requests.request(method, url, headers=headers, json=body, timeout=step.timeout)

        return {
            'status_code': response.status_code,
            'headers': dict(response.headers),
            'body': response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text
        }

    def _assert(self, step: WorkflowStep, session_name: str, context: Dict) -> bool:
        """Assert a condition"""
        config = step.assert_config
        condition = config.get('condition')
        expected = config.get('expected')
        operator = config.get('operator', 'equals')

        if condition:
            response = requests.post(
                f"{self.config.api_base_url}/session/{session_name}/evaluate",
                json={"expression": condition}
            )
            actual = response.json()

            if operator == 'equals':
                assert str(actual) == str(expected), f"Assertion failed: {actual} != {expected}"
            elif operator == 'contains':
                assert str(expected) in str(actual), f"Assertion failed: {expected} not in {actual}"
            elif operator == 'regex':
                import re
                assert re.search(str(expected), str(actual)), f"Assertion failed: regex {expected} not matched"
            elif operator == 'greater':
                assert float(actual) > float(expected), f"Assertion failed: {actual} <= {expected}"
            elif operator == 'less':
                assert float(actual) < float(expected), f"Assertion failed: {actual} >= {expected}"

            return True

        return False

    def _scroll(self, step: WorkflowStep, session_name: str) -> Dict:
        """Scroll the page"""
        selector = step.selector or 'body'
        expression = f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (el) {{
                    el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                    return {{ success: true, element: '{selector}' }};
                }}
                return {{ success: false, error: 'Element not found: {selector}' }};
            }})()
        """
        response = requests.post(
            f"{self.config.api_base_url}/session/{session_name}/evaluate",
            json={"expression": expression}
        )
        return response.json()

    def _fill(self, step: WorkflowStep, session_name: str) -> Dict:
        """Fill an input field"""
        selector = step.selector
        value = step.variable_value or step.metadata.get('value', '')
        
        if not selector:
            raise ValueError("Selector required for fill step")

        expression = f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) {{
                    return {{ success: false, error: 'Element not found: {selector}' }};
                }}
                el.value = '{value}';
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                return {{ success: true, value: '{value}', selector: '{selector}' }};
            }})()
        """
        response = requests.post(
            f"{self.config.api_base_url}/session/{session_name}/evaluate",
            json={"expression": expression}
        )
        return response.json()

    def _select(self, step: WorkflowStep, session_name: str) -> Dict:
        """Select an option from a dropdown"""
        selector = step.selector
        value = step.variable_value or step.metadata.get('value', '')
        
        if not selector:
            raise ValueError("Selector required for select step")

        expression = f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) {{
                    return {{ success: false, error: 'Element not found: {selector}' }};
                }}
                if (el.tagName === 'SELECT') {{
                    el.value = '{value}';
                    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    return {{ success: true, value: '{value}', selector: '{selector}' }};
                }} else {{
                    const options = el.querySelectorAll('option, [role="option"]');
                    let found = false;
                    options.forEach(opt => {{
                        if (opt.textContent.trim() === '{value}' || opt.value === '{value}') {{
                            opt.selected = true;
                            opt.click();
                            found = true;
                        }}
                    }});
                    return {{ success: found, value: '{value}', selector: '{selector}' }};
                }}
            }})()
        """
        response = requests.post(
            f"{self.config.api_base_url}/session/{session_name}/evaluate",
            json={"expression": expression}
        )
        return response.json()

    def get_execution_status(self, workflow_id: str) -> Dict:
        """Get execution status from Redis"""
        if not self.redis:
            return {"error": "Redis not available"}

        status = self.redis.hgetall(f"workflow:execution:{workflow_id}")
        if not status:
            return {"status": "not_found", "workflow_id": workflow_id}
        return status

# ============================================================================
# Celery Tasks - Defined at Module Level
# ============================================================================

@celery_app.task(bind=True, max_retries=3, name='workflow3.execute_workflow')
def execute_workflow_task(self, workflow_id: str, session_name: str = None):
    """Celery task to execute a workflow"""
    manager = WorkflowManager()
    return manager._execute_workflow_task(workflow_id, session_name)

@celery_app.task(bind=True, max_retries=3, name='workflow3.execute_step')
def execute_step_task(self, workflow_id: str, step_id: str, session_name: str = None):
    """Celery task to execute a single step"""
    manager = WorkflowManager()
    return manager._execute_step_task(workflow_id, step_id, session_name)

# ============================================================================
# CLI Interface
# ============================================================================

class WorkflowCLI:
    def __init__(self):
        self.config = WorkflowConfig()
        self.manager = WorkflowManager(self.config)

    def run(self):
        while True:
            if console:
                console.clear()
                console.print(Panel("[bold cyan]📋 Workflow Management System[/bold cyan]", border_style="cyan"))
            else:
                print("\n" + "="*50)
                print("📋 Workflow Management System")
                print("="*50)

            if console:
                menu = Table(show_header=False, box=box.MINIMAL)
                menu.add_column("Option", style="cyan", width=8)
                menu.add_column("Action", style="white")
                menu.add_column("Description", style="dim")

                menu.add_row("1", "[green]Create Workflow[/green]", "Create a new workflow with steps")
                menu.add_row("2", "[blue]Add Step[/blue]", "Add a step to existing workflow")
                menu.add_row("3", "[yellow]List Workflows[/yellow]", "List all workflows")
                menu.add_row("4", "[magenta]View Workflow[/magenta]", "View workflow details")
                menu.add_row("5", "[cyan]Execute Workflow[/cyan]", "Queue workflow for execution")
                menu.add_row("6", "[red]Delete Workflow[/red]", "Delete a workflow")
                menu.add_row("7", "[white]Script Library[/white]", "Manage JavaScript scripts")
                menu.add_row("8", "[bold]Queue Status[/bold]", "View queue status")
                menu.add_row("0", "[red]Exit[/red]", "Exit")

                console.print(menu)
                choice = Prompt.ask("Select option", choices=["0","1","2","3","4","5","6","7","8"])
            else:
                print("1. Create Workflow")
                print("2. Add Step")
                print("3. List Workflows")
                print("4. View Workflow")
                print("5. Execute Workflow")
                print("6. Delete Workflow")
                print("7. Script Library")
                print("8. Queue Status")
                print("0. Exit")
                choice = input("Select option: ")

            if choice == "0":
                print("Goodbye! 👋")
                break
            elif choice == "1":
                self.create_workflow_interactive()
            elif choice == "2":
                self.add_step_interactive()
            elif choice == "3":
                self.list_workflows()
            elif choice == "4":
                self.view_workflow()
            elif choice == "5":
                self.execute_workflow()
            elif choice == "6":
                self.delete_workflow()
            elif choice == "7":
                self.manage_scripts()
            elif choice == "8":
                self.view_queue()

            if choice != "0" and console:
                Prompt.ask("Press Enter to continue...")

    def create_workflow_interactive(self):
        if console:
            console.print(Panel("[bold green]🆕 Create New Workflow[/bold green]", border_style="green"))
        else:
            print("\n🆕 Create New Workflow")

        name = Prompt.ask("Workflow name") if console else input("Workflow name: ")
        if not name:
            print("Name required")
            return

        description = Prompt.ask("Description", default="") if console else input("Description: ")
        session_name = Prompt.ask("Session name", default="unstop") if console else input("Session name [unstop]: ") or "unstop"
        session_url = Prompt.ask("Session URL", default="https://unstop.com/") if console else input("Session URL [https://unstop.com/]: ") or "https://unstop.com/"

        workflow = Workflow(
            name=name,
            description=description,
            session_name=session_name,
            session_url=session_url,
            status="draft"
        )

        if console:
            console.print("[green]✅ Workflow created! Now let's add steps.[/green]")
        else:
            print("✅ Workflow created! Now let's add steps.")

        while True:
            if console:
                console.print("\n[bold]Add a step:[/bold]")
                console.print("1. JavaScript Execution")
                console.print("2. Navigate to URL")
                console.print("3. Click Element")
                console.print("4. Wait")
                console.print("5. Extract Data")
                console.print("6. Screenshot")
                console.print("7. API Call")
                console.print("8. Assert")
                console.print("9. Scroll")
                console.print("10. Fill Input")
                console.print("11. Select Option")
                console.print("0. Done")
                step_type = Prompt.ask("Select step type", choices=["0","1","2","3","4","5","6","7","8","9","10","11"])
            else:
                print("\nAdd a step:")
                print("1. JavaScript Execution")
                print("2. Navigate to URL")
                print("3. Click Element")
                print("4. Wait")
                print("5. Extract Data")
                print("6. Screenshot")
                print("7. API Call")
                print("8. Assert")
                print("9. Scroll")
                print("10. Fill Input")
                print("11. Select Option")
                print("0. Done")
                step_type = input("Select step type: ")

            if step_type == "0":
                break

            step = self._create_step(step_type)
            if step:
                workflow.steps.append(step.to_dict())
                if console:
                    console.print(f"[green]✅ Step '{step.name}' added[/green]")
                else:
                    print(f"✅ Step '{step.name}' added")

        self.manager._save_workflow(workflow)
        if console:
            console.print(f"[green]✅ Workflow '{name}' saved! ID: {workflow.id}[/green]")
        else:
            print(f"✅ Workflow '{name}' saved! ID: {workflow.id}")

    def _create_step(self, step_type: str) -> Optional[WorkflowStep]:
        """Create a step interactively"""
        if console:
            step_name = Prompt.ask("Step name")
        else:
            step_name = input("Step name: ")
        if not step_name:
            step_name = f"step_{step_type}"

        if console:
            description = Prompt.ask("Description", default="")
            timeout = int(Prompt.ask("Timeout (seconds)", default="30"))
            retry_count = int(Prompt.ask("Retry count", default="0"))
            continue_on_error = Confirm.ask("Continue on error?", default=False)
        else:
            description = input("Description: ")
            timeout = int(input("Timeout (seconds) [30]: ") or "30")
            retry_count = int(input("Retry count [0]: ") or "0")
            continue_on_error = input("Continue on error? (y/n) [n]: ").lower() == 'y'

        step = WorkflowStep(
            name=step_name,
            description=description,
            timeout=timeout,
            retry_count=retry_count,
            continue_on_error=continue_on_error
        )

        type_map = {
            "1": "js_execute",
            "2": "navigate",
            "3": "click",
            "4": "wait",
            "5": "extract",
            "6": "screenshot",
            "7": "api_call",
            "8": "assert",
            "9": "scroll",
            "10": "fill",
            "11": "select"
        }

        step.type = type_map.get(step_type, "js_execute")

        if step.type == "js_execute":
            if console:
                console.print("[yellow]Enter JavaScript code (press Ctrl+D when done):[/yellow]")
            else:
                print("Enter JavaScript code (press Ctrl+D when done):")
            lines = []
            try:
                while True:
                    line = input()
                    lines.append(line)
            except EOFError:
                pass
            step.code = "\n".join(lines)
            if console:
                console.print("[green]✅ Script captured[/green]")
            else:
                print("✅ Script captured")

            workflow_name = Prompt.ask("Workflow name (for script library)", default="default") if console else input("Workflow name [default]: ") or "default"
            self.manager.script_library.save_script(workflow_name, step)
            if console:
                console.print(f"[green]✅ Script saved to library with ID: {step.id}[/green]")
            else:
                print(f"✅ Script saved to library with ID: {step.id}")

        elif step.type == "navigate":
            step.url = Prompt.ask("URL to navigate to") if console else input("URL to navigate to: ")

        elif step.type == "click":
            step.selector = Prompt.ask("CSS selector to click") if console else input("CSS selector to click: ")

        elif step.type == "wait":
            wait_time = int(Prompt.ask("Wait time (seconds)", default="1")) if console else int(input("Wait time (seconds) [1]: ") or "1")
            step.wait_time = wait_time

        elif step.type == "extract":
            step.expression = Prompt.ask("JavaScript expression to extract") if console else input("JavaScript expression to extract: ")
            step.variable_name = Prompt.ask("Store result in variable (optional)", default="") if console else input("Store result in variable (optional): ")

        elif step.type == "api_call":
            if console:
                step.api_config = {
                    "method": Prompt.ask("HTTP Method", default="GET"),
                    "url": Prompt.ask("API URL"),
                    "headers": {},
                    "body": {}
                }
            else:
                step.api_config = {
                    "method": input("HTTP Method [GET]: ") or "GET",
                    "url": input("API URL: "),
                    "headers": {},
                    "body": {}
                }

        elif step.type == "assert":
            if console:
                step.assert_config = {
                    "condition": Prompt.ask("JavaScript condition to evaluate"),
                    "expected": Prompt.ask("Expected value"),
                    "operator": Prompt.ask("Operator (equals/contains/regex/greater/less)", default="equals")
                }
            else:
                step.assert_config = {
                    "condition": input("JavaScript condition to evaluate: "),
                    "expected": input("Expected value: "),
                    "operator": input("Operator [equals]: ") or "equals"
                }

        elif step.type == "scroll":
            step.selector = Prompt.ask("CSS selector to scroll to", default="body") if console else input("CSS selector to scroll to [body]: ") or "body"

        elif step.type == "fill":
            step.selector = Prompt.ask("CSS selector for input") if console else input("CSS selector for input: ")
            step.variable_value = Prompt.ask("Value to fill") if console else input("Value to fill: ")

        elif step.type == "select":
            step.selector = Prompt.ask("CSS selector for select/dropdown") if console else input("CSS selector for select/dropdown: ")
            step.variable_value = Prompt.ask("Option to select") if console else input("Option to select: ")

        return step

    def list_workflows(self):
        workflows = self.manager.list_workflows()
        if not workflows:
            if console:
                console.print("[yellow]No workflows found[/yellow]")
            else:
                print("No workflows found")
            return

        if console:
            table = Table(title="📋 Workflows", box=box.ROUNDED)
            table.add_column("ID", style="cyan", width=12)
            table.add_column("Name", style="green")
            table.add_column("Status", style="magenta")
            table.add_column("Steps", style="yellow", width=8)
            table.add_column("Created", style="dim")
            table.add_column("Version", style="blue", width=8)

            for wf in workflows:
                status_color = "green" if wf['status'] == 'active' else "yellow" if wf['status'] == 'queued' else "dim"
                table.add_row(
                    wf['id'][:8] + "...",
                    wf['name'],
                    f"[{status_color}]{wf['status']}[/{status_color}]",
                    str(wf['steps']),
                    wf['created_at'][:16] if wf['created_at'] else 'N/A',
                    wf.get('version', '1.0.0')
                )
            console.print(table)
        else:
            print("\n📋 Workflows:")
            for wf in workflows:
                print(f"  {wf['id'][:8]}: {wf['name']} ({wf['status']}) - {wf['steps']} steps")

    def view_workflow(self):
        workflows = self.manager.list_workflows()
        if not workflows:
            if console:
                console.print("[red]No workflows found[/red]")
            else:
                print("No workflows found")
            return

        workflow_id = Prompt.ask("Enter workflow ID") if console else input("Enter workflow ID: ")
        workflow = self.manager.get_workflow(workflow_id)
        if not workflow:
            if console:
                console.print("[red]Workflow not found[/red]")
            else:
                print("Workflow not found")
            return

        content = f"""
[bold cyan]Workflow: {workflow.name}[/bold cyan]
[bold]ID:[/bold] {workflow.id}
[bold]Description:[/bold] {workflow.description}
[bold]Status:[/bold] {workflow.status}
[bold]Version:[/bold] {workflow.version}
[bold]Session:[/bold] {workflow.session_name}
[bold]URL:[/bold] {workflow.session_url}
[bold]Created:[/bold] {workflow.created_at}
[bold]Updated:[/bold] {workflow.updated_at}
[bold]Steps:[/bold] {len(workflow.steps)}

[bold cyan]Steps:[/bold cyan]
"""
        for i, step_data in enumerate(workflow.steps, 1):
            step = WorkflowStep.from_dict(step_data)
            content += f"""
  [{i}] {step.name} ({step.type})
      ID: {step.id}
      Description: {step.description}
      Timeout: {step.timeout}s
      Retry: {step.retry_count}
"""
            if step.type == "js_execute":
                content += f"      Code length: {len(step.code)} chars\n"
            elif step.type == "navigate":
                content += f"      URL: {step.url}\n"
            elif step.type == "click":
                content += f"      Selector: {step.selector}\n"
            elif step.type == "fill":
                content += f"      Selector: {step.selector}, Value: {step.variable_value}\n"

        if console:
            console.print(Panel(content, title="📊 Workflow Details", border_style="blue"))
        else:
            print(content)

    def execute_workflow(self):
        workflows = self.manager.list_workflows()
        if not workflows:
            if console:
                console.print("[red]No workflows found[/red]")
            else:
                print("No workflows found")
            return

        workflow_id = Prompt.ask("Enter workflow ID to execute") if console else input("Enter workflow ID to execute: ")
        
        full_id = self.manager.find_workflow_by_partial_id(workflow_id)
        if full_id:
            workflow_id = full_id
        
        workflow = self.manager.get_workflow(workflow_id)
        if not workflow:
            if console:
                console.print("[red]Workflow not found[/red]")
            else:
                print("Workflow not found")
            return

        session_name = Prompt.ask("Session name (enter for default)", default=workflow.session_name) if console else input(f"Session name [{workflow.session_name}]: ") or workflow.session_name

        if console:
            console.print(f"[yellow]📤 Queuing workflow '{workflow.name}'...[/yellow]")
        else:
            print(f"📤 Queuing workflow '{workflow.name}'...")

        try:
            task_id = self.manager.queue_workflow(workflow_id, session_name)
            if console:
                console.print(f"[green]✅ Workflow queued! Task ID: {task_id}[/green]")
            else:
                print(f"✅ Workflow queued! Task ID: {task_id}")
        except Exception as e:
            if console:
                console.print(f"[red]Failed to queue workflow: {e}[/red]")
            else:
                print(f"Failed to queue workflow: {e}")

    def delete_workflow(self):
        workflows = self.manager.list_workflows()
        if not workflows:
            if console:
                console.print("[red]No workflows found[/red]")
            else:
                print("No workflows found")
            return

        workflow_id = Prompt.ask("Enter workflow ID to delete") if console else input("Enter workflow ID to delete: ")
        workflow = self.manager.get_workflow(workflow_id)
        if not workflow:
            if console:
                console.print("[red]Workflow not found[/red]")
            else:
                print("Workflow not found")
            return

        if console:
            confirm = Confirm.ask(f"Delete workflow '{workflow.name}'?")
        else:
            confirm = input(f"Delete workflow '{workflow.name}'? (y/n): ").lower() == 'y'

        if confirm:
            import shutil
            wf_dir = Path(self.config.workflows_dir) / workflow_id
            if wf_dir.exists():
                shutil.rmtree(wf_dir)

            if self.manager.redis:
                self.manager.redis.delete(f"workflow:{workflow_id}")
                self.manager.redis.srem("workflows:active", workflow_id)

            if console:
                console.print(f"[green]✅ Workflow deleted[/green]")
            else:
                print("✅ Workflow deleted")

    def manage_scripts(self):
        if console:
            console.print(Panel("[bold cyan]📜 Script Library Manager[/bold cyan]", border_style="cyan"))
        else:
            print("\n📜 Script Library Manager")

        while True:
            if console:
                console.print("\n1. List scripts")
                console.print("2. View script")
                console.print("3. Delete script")
                console.print("4. Add script")
                console.print("0. Back")
                choice = Prompt.ask("Select", choices=["0","1","2","3","4"])
            else:
                print("\n1. List scripts")
                print("2. View script")
                print("3. Delete script")
                print("4. Add script")
                print("0. Back")
                choice = input("Select: ")

            if choice == "0":
                break
            elif choice == "1":
                workflow_name = Prompt.ask("Workflow name") if console else input("Workflow name: ")
                scripts = self.manager.script_library.get_all_scripts(workflow_name)
                if scripts:
                    if console:
                        console.print(f"\n[green]Found {len(scripts)} scripts:[/green]")
                        for script in scripts:
                            console.print(f"  📄 {script['filename']} ({script['metadata'].get('step_name', 'unknown')})")
                    else:
                        print(f"\nFound {len(scripts)} scripts:")
                        for script in scripts:
                            print(f"  📄 {script['filename']} ({script['metadata'].get('step_name', 'unknown')})")
                else:
                    if console:
                        console.print("[yellow]No scripts found[/yellow]")
                    else:
                        print("No scripts found")

            elif choice == "2":
                workflow_name = Prompt.ask("Workflow name") if console else input("Workflow name: ")
                step_id = Prompt.ask("Step ID") if console else input("Step ID: ")
                script = self.manager.script_library.get_script(workflow_name, step_id)
                if script:
                    if console:
                        syntax = Syntax(script, "javascript", theme="monokai", line_numbers=True)
                        console.print(syntax)
                    else:
                        print("\n" + "="*50)
                        print(script)
                        print("="*50)
                else:
                    if console:
                        console.print("[red]Script not found[/red]")
                    else:
                        print("Script not found")

            elif choice == "3":
                workflow_name = Prompt.ask("Workflow name") if console else input("Workflow name: ")
                step_id = Prompt.ask("Step ID") if console else input("Step ID: ")
                if self.manager.script_library.delete_script(workflow_name, step_id):
                    if console:
                        console.print("[green]✅ Script deleted[/green]")
                    else:
                        print("✅ Script deleted")
                else:
                    if console:
                        console.print("[red]Script not found[/red]")
                    else:
                        print("Script not found")

            elif choice == "4":
                workflow_name = Prompt.ask("Workflow name") if console else input("Workflow name: ")
                step_name = Prompt.ask("Step name") if console else input("Step name: ")
                if console:
                    console.print("[yellow]Enter JavaScript code (press Ctrl+D when done):[/yellow]")
                else:
                    print("Enter JavaScript code (press Ctrl+D when done):")
                lines = []
                try:
                    while True:
                        line = input()
                        lines.append(line)
                except EOFError:
                    pass

                step = WorkflowStep(
                    name=step_name,
                    type="js_execute",
                    code="\n".join(lines)
                )
                self.manager.script_library.save_script(workflow_name, step)
                if console:
                    console.print(f"[green]✅ Script saved! ID: {step.id}[/green]")
                else:
                    print(f"✅ Script saved! ID: {step.id}")

    def view_queue(self):
        if console:
            console.print(Panel("[bold cyan]📊 Queue Status[/bold cyan]", border_style="cyan"))
        else:
            print("\n📊 Queue Status")

        if not self.manager.redis:
            if console:
                console.print("[red]Redis not available[/red]")
            else:
                print("Redis not available")
            return

        queue_stats = {}
        for queue_name in ['default', 'high_priority', 'low_priority']:
            try:
                length = self.manager.redis.llen(f"celery_{queue_name}")
                if length > 0:
                    queue_stats[queue_name] = length
            except:
                pass

        if queue_stats:
            if console:
                console.print("\n[bold]Queue lengths:[/bold]")
                for q, count in queue_stats.items():
                    console.print(f"  {q}: {count} tasks")
            else:
                print("\nQueue lengths:")
                for q, count in queue_stats.items():
                    print(f"  {q}: {count} tasks")

        active_workflows = self.manager.redis.smembers("workflows:active")
        if active_workflows:
            if console:
                console.print(f"\n[bold]Active workflows:[/bold] {len(active_workflows)}")
                for wf_id in active_workflows:
                    wf_data = self.manager.redis.hgetall(f"workflow:{wf_id}")
                    if wf_data:
                        console.print(f"  📋 {wf_data.get('name', wf_id)} ({wf_data.get('status', 'unknown')})")
            else:
                print(f"\nActive workflows: {len(active_workflows)}")
                for wf_id in active_workflows:
                    wf_data = self.manager.redis.hgetall(f"workflow:{wf_id}")
                    if wf_data:
                        print(f"  📋 {wf_data.get('name', wf_id)} ({wf_data.get('status', 'unknown')})")

        try:
            execution_keys = self.manager.redis.keys("workflow:execution:*")
            if execution_keys:
                if console:
                    console.print(f"\n[bold]Running executions:[/bold] {len(execution_keys)}")
                    for key in execution_keys:
                        status = self.manager.redis.hgetall(key)
                        if status:
                            wf_id = key.replace("workflow:execution:", "")
                            wf_data = self.manager.redis.hgetall(f"workflow:{wf_id}")
                            wf_name = wf_data.get('name', wf_id) if wf_data else wf_id
                            console.print(f"  🔄 {wf_name}: {status.get('status', 'unknown')} (Task: {status.get('task_id', 'N/A')})")
                else:
                    print(f"\nRunning executions: {len(execution_keys)}")
                    for key in execution_keys:
                        status = self.manager.redis.hgetall(key)
                        if status:
                            wf_id = key.replace("workflow:execution:", "")
                            wf_data = self.manager.redis.hgetall(f"workflow:{wf_id}")
                            wf_name = wf_data.get('name', wf_id) if wf_data else wf_id
                            print(f"  🔄 {wf_name}: {status.get('status', 'unknown')}")
        except Exception as e:
            if console:
                console.print(f"[yellow]Could not get execution status: {e}[/yellow]")
            else:
                print(f"Could not get execution status: {e}")

# ============================================================================
# Setup and Main Entry
# ============================================================================

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(os.path.expanduser("~/chrome-workflows/workflow_manager.log"))
        ]
    )

def main():
    setup_logging()

    try:
        cli = WorkflowCLI()
        cli.run()
    except KeyboardInterrupt:
        print("\n[yellow]Interrupted[/yellow]")
    except Exception as e:
        logging.exception("Fatal error")
        print(f"[red]Error: {e}[/red]")

if __name__ == "__main__":
    main()
