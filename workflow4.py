#!/usr/bin/env python3
# workflow4.py - Enhanced workflow management with improved CLI

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
from collections import defaultdict

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
    from rich.layout import Layout
    from rich.columns import Columns
    from rich.live import Live
    from rich.progress import Progress, SpinnerColumn, TextColumn
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
    cli_show_full_id: bool = False  # Show full UUIDs in CLI

# ============================================================================
# Step Types (same as before)
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
# Workflow Model (enhanced)
# ============================================================================

@dataclass
class Workflow:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
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
    last_execution: Optional[str] = None
    last_status: Optional[str] = None
    execution_count: int = 0
    avg_duration: Optional[float] = None

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'Workflow':
        return cls(**data)

    def get_display_id(self, show_full: bool = False) -> str:
        """Get display-friendly ID"""
        return self.id if show_full else self.id[:8]

# ============================================================================
# Workflow Registry (enhanced with better querying)
# ============================================================================

class WorkflowRegistry:
    """Enhanced workflow registry with better lookup and management"""
    
    def __init__(self, config: WorkflowConfig):
        self.config = config
        self._workflows = {}
        self._loaded = False
        self._load_lock = False
        
    def load(self, force: bool = False) -> int:
        """Load all workflows from disk"""
        if self._loaded and not force:
            return len(self._workflows)
        
        if self._load_lock:
            return len(self._workflows)
        
        self._load_lock = True
        try:
            workflows_dir = Path(self.config.workflows_dir)
            if not workflows_dir.exists():
                return 0
            
            loaded = 0
            for wf_dir in workflows_dir.iterdir():
                if not wf_dir.is_dir():
                    continue
                    
                wf_file = wf_dir / 'workflow.json'
                if not wf_file.exists():
                    continue
                
                try:
                    with open(wf_file, 'r') as f:
                        data = json.load(f)
                        workflow = Workflow.from_dict(data)
                        self._workflows[workflow.id] = workflow
                        loaded += 1
                except Exception as e:
                    logging.error(f"Failed to load workflow {wf_dir.name}: {e}")
            
            self._loaded = True
            return loaded
        finally:
            self._load_lock = False
    
    def get(self, identifier: str) -> Optional[Workflow]:
        """Get workflow by ID or name with partial matching"""
        self.load()
        
        # Try exact ID match first
        if identifier in self._workflows:
            return self._workflows[identifier]
        
        # Try partial ID match
        matches = []
        for wf in self._workflows.values():
            if wf.id.startswith(identifier):
                matches.append(wf)
        
        if len(matches) == 1:
            return matches[0]
        
        if len(matches) > 1:
            raise ValueError(f"Multiple workflows match '{identifier}': {[w.id[:8] for w in matches]}")
        
        # Try name match (case-insensitive)
        for wf in self._workflows.values():
            if wf.name.lower() == identifier.lower():
                return wf
        
        # Try name contains
        matches = []
        for wf in self._workflows.values():
            if identifier.lower() in wf.name.lower():
                matches.append(wf)
        
        if len(matches) == 1:
            return matches[0]
        
        if len(matches) > 1:
            raise ValueError(f"Multiple workflows match name '{identifier}': {[w.name for w in matches]}")
        
        return None
    
    def list_all(self, sort_by: str = 'name', status_filter: Optional[str] = None) -> List[Workflow]:
        """List all workflows with filtering and sorting"""
        self.load()
        
        workflows = list(self._workflows.values())
        
        if status_filter:
            workflows = [w for w in workflows if w.status == status_filter]
        
        if sort_by == 'name':
            workflows.sort(key=lambda w: w.name.lower())
        elif sort_by == 'created':
            workflows.sort(key=lambda w: w.created_at, reverse=True)
        elif sort_by == 'updated':
            workflows.sort(key=lambda w: w.updated_at, reverse=True)
        elif sort_by == 'status':
            workflows.sort(key=lambda w: w.status)
        
        return workflows
    
    def save(self, workflow: Workflow) -> None:
        """Save workflow to disk and update registry"""
        self._workflows[workflow.id] = workflow
        workflow.updated_at = datetime.now().isoformat()
        
        workflow_dir = Path(self.config.workflows_dir) / workflow.id
        workflow_dir.mkdir(parents=True, exist_ok=True)
        
        with open(workflow_dir / 'workflow.json', 'w') as f:
            json.dump(workflow.to_dict(), f, indent=2, default=str)
        
        # Save steps
        for i, step_data in enumerate(workflow.steps):
            step_file = workflow_dir / f"step_{i:03d}_{step_data['id']}.json"
            with open(step_file, 'w') as f:
                json.dump(step_data, f, indent=2, default=str)
    
    def delete(self, workflow_id: str) -> bool:
        """Delete workflow from disk and registry"""
        workflow = self.get(workflow_id)
        if not workflow:
            return False
        
        # Remove from registry
        if workflow.id in self._workflows:
            del self._workflows[workflow.id]
        
        # Remove from disk
        import shutil
        workflow_dir = Path(self.config.workflows_dir) / workflow.id
        if workflow_dir.exists():
            shutil.rmtree(workflow_dir)
        
        return True
    
    def search(self, query: str) -> List[Workflow]:
        """Search workflows by name, description, or tags"""
        self.load()
        query_lower = query.lower()
        
        results = []
        for wf in self._workflows.values():
            if query_lower in wf.name.lower():
                results.append(wf)
            elif query_lower in wf.description.lower():
                results.append(wf)
            elif any(query_lower in tag.lower() for tag in wf.tags):
                results.append(wf)
        
        return results

# ============================================================================
# Script Library Manager (same as before)
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
# Celery App (same as before)
# ============================================================================

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
# Execution Manager (enhanced with better status tracking)
# ============================================================================

class ExecutionManager:
    def __init__(self, config: WorkflowConfig, redis_client=None):
        self.config = config
        self.redis = redis_client
        
    def get_status(self, workflow_id: str) -> Dict:
        """Get enhanced execution status"""
        if not self.redis:
            return {"error": "Redis not available"}
        
        status = self.redis.hgetall(f"workflow:execution:{workflow_id}")
        if not status:
            return {"status": "not_found", "workflow_id": workflow_id}
        
        # Add derived fields
        status['is_running'] = status.get('status') == 'running'
        status['is_queued'] = status.get('status') == 'queued'
        status['is_completed'] = status.get('status') == 'completed'
        status['is_failed'] = status.get('status') == 'failed'
        
        return status
    
    def get_all_statuses(self) -> Dict[str, Dict]:
        """Get status for all executions"""
        if not self.redis:
            return {}
        
        statuses = {}
        try:
            keys = self.redis.keys("workflow:execution:*")
            for key in keys:
                workflow_id = key.replace("workflow:execution:", "")
                statuses[workflow_id] = self.get_status(workflow_id)
        except Exception as e:
            logging.error(f"Failed to get execution statuses: {e}")
        
        return statuses
    
    def get_running_count(self) -> int:
        """Get number of running executions"""
        if not self.redis:
            return 0
        
        try:
            keys = self.redis.keys("workflow:execution:*")
            running = 0
            for key in keys:
                status = self.redis.hgetall(key)
                if status.get('status') == 'running':
                    running += 1
            return running
        except Exception:
            return 0
    
    def get_queued_count(self) -> int:
        """Get number of queued executions"""
        if not self.redis:
            return 0
        
        try:
            keys = self.redis.keys("workflow:execution:*")
            queued = 0
            for key in keys:
                status = self.redis.hgetall(key)
                if status.get('status') == 'queued':
                    queued += 1
            return queued
        except Exception:
            return 0

# ============================================================================
# Workflow Manager (enhanced)
# ============================================================================

class WorkflowManager:
    def __init__(self, config: WorkflowConfig = None):
        self.config = config or WorkflowConfig()
        self.registry = WorkflowRegistry(self.config)
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

        self.execution = ExecutionManager(self.config, self.redis)
        self.celery_app = celery_app

    def _ensure_directories(self):
        """Create necessary directories"""
        Path(self.config.base_dir).mkdir(parents=True, exist_ok=True)
        Path(self.config.workflows_dir).mkdir(parents=True, exist_ok=True)

    def create_workflow(self, data: Dict) -> Workflow:
        """Create a new workflow"""
        workflow = Workflow.from_dict(data)
        self.registry.save(workflow)
        return workflow

    def get_workflow(self, identifier: str) -> Optional[Workflow]:
        """Get workflow by ID or name with partial matching"""
        return self.registry.get(identifier)

    def list_workflows(self, **kwargs) -> List[Workflow]:
        """List workflows with filtering"""
        return self.registry.list_all(**kwargs)

    def search_workflows(self, query: str) -> List[Workflow]:
        """Search workflows"""
        return self.registry.search(query)

    def add_step_to_workflow(self, workflow_id: str, step_data: Dict) -> Workflow:
        """Add a step to an existing workflow"""
        workflow = self.get_workflow(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        step = WorkflowStep.from_dict(step_data)
        workflow.steps.append(step.to_dict())
        workflow.updated_at = datetime.now().isoformat()
        self.registry.save(workflow)
        return workflow

    def queue_workflow(self, workflow_id: str, session_name: str = None) -> str:
        """Queue a workflow for execution via Celery"""
        if not self.celery_app:
            raise RuntimeError("Celery not configured. Install celery and redis.")

        workflow = self.get_workflow(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        workflow.status = "queued"
        workflow.last_execution = datetime.now().isoformat()
        workflow.execution_count += 1
        self.registry.save(workflow)

        # Use the module-level task
        from workflow4 import execute_workflow_task
        task = execute_workflow_task.delay(workflow_id, session_name or workflow.session_name)

        if self.redis:
            self.redis.hset(
                f"workflow:execution:{workflow_id}",
                mapping={
                    "task_id": task.id,
                    "status": "queued",
                    "queued_at": datetime.now().isoformat(),
                    "session": session_name or workflow.session_name,
                    "workflow_name": workflow.name
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
        start_time = time.time()

        if self.redis:
            self.redis.hset(
                f"workflow:execution:{workflow_id}",
                mapping={
                    "status": "running",
                    "started_at": datetime.now().isoformat()
                }
            )

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

        duration = time.time() - start_time
        workflow.status = "completed" if all(r['status'] == 'success' for r in results) else "failed"
        workflow.last_status = workflow.status
        if workflow.avg_duration:
            workflow.avg_duration = (workflow.avg_duration + duration) / 2
        else:
            workflow.avg_duration = duration
        
        self.registry.save(workflow)

        result_file = Path(self.config.workflows_dir) / workflow_id / 'execution_results.json'
        with open(result_file, 'w') as f:
            json.dump({
                'workflow_id': workflow_id,
                'workflow_name': workflow.name,
                'executed_at': datetime.now().isoformat(),
                'session': session_name,
                'results': results,
                'status': workflow.status,
                'duration': duration
            }, f, indent=2, default=str)

        if self.redis:
            self.redis.hset(
                f"workflow:execution:{workflow_id}",
                mapping={
                    "status": workflow.status,
                    "completed_at": datetime.now().isoformat(),
                    "result_count": len(results),
                    "duration": duration
                }
            )
            
            # Remove from active after completion
            if workflow.status in ['completed', 'failed']:
                self.redis.srem("workflows:active", workflow_id)

        return {
            'workflow_id': workflow_id,
            'status': workflow.status,
            'results': results,
            'duration': duration
        }

    def _execute_step(self, step: WorkflowStep, session_name: str, context: Dict) -> Any:
        """Execute a single step (same as before)"""
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
        """Get execution status"""
        return self.execution.get_status(workflow_id)

    def get_execution_summary(self) -> Dict:
        """Get summary of all executions"""
        statuses = self.execution.get_all_statuses()
        
        summary = {
            'total': len(statuses),
            'queued': 0,
            'running': 0,
            'completed': 0,
            'failed': 0,
            'by_workflow': defaultdict(int)
        }
        
        for wf_id, status in statuses.items():
            status_type = status.get('status', 'unknown')
            if status_type == 'queued':
                summary['queued'] += 1
            elif status_type == 'running':
                summary['running'] += 1
            elif status_type == 'completed':
                summary['completed'] += 1
            elif status_type == 'failed':
                summary['failed'] += 1
            
            wf_name = status.get('workflow_name', wf_id[:8])
            summary['by_workflow'][wf_name] += 1
        
        return summary

# ============================================================================
# Celery Tasks
# ============================================================================

@celery_app.task(bind=True, max_retries=3, name='workflow4.execute_workflow')
def execute_workflow_task(self, workflow_id: str, session_name: str = None):
    """Celery task to execute a workflow"""
    manager = WorkflowManager()
    return manager._execute_workflow_task(workflow_id, session_name)

# ============================================================================
# Enhanced CLI
# ============================================================================

class WorkflowCLI:
    def __init__(self):
        self.config = WorkflowConfig()
        self.manager = WorkflowManager(self.config)
        self.selection_context = {}  # For tracking selections

    def run(self):
        while True:
            if console:
                console.clear()
                self._show_dashboard()
                
                menu = Table(show_header=False, box=box.MINIMAL)
                menu.add_column("Option", style="cyan", width=8)
                menu.add_column("Action", style="white")
                menu.add_column("Description", style="dim")

                menu.add_row("1", "[green]Create Workflow[/green]", "Create a new workflow")
                menu.add_row("2", "[blue]Add Step[/blue]", "Add a step to existing workflow")
                menu.add_row("3", "[yellow]List Workflows[/yellow]", "List all workflows")
                menu.add_row("4", "[magenta]View Workflow[/magenta]", "View workflow details")
                menu.add_row("5", "[cyan]Execute Workflow[/cyan]", "Queue workflow for execution")
                menu.add_row("6", "[orange1]Execution Status[/orange1]", "View execution status")
                menu.add_row("7", "[red]Delete Workflow[/red]", "Delete a workflow")
                menu.add_row("8", "[white]Script Library[/white]", "Manage JavaScript scripts")
                menu.add_row("0", "[red]Exit[/red]", "Exit")

                console.print(menu)
                choice = Prompt.ask("Select option", choices=["0","1","2","3","4","5","6","7","8"])
            else:
                self._show_dashboard_simple()
                print("\n1. Create Workflow")
                print("2. Add Step")
                print("3. List Workflows")
                print("4. View Workflow")
                print("5. Execute Workflow")
                print("6. Execution Status")
                print("7. Delete Workflow")
                print("8. Script Library")
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
                self.view_execution_status()
            elif choice == "7":
                self.delete_workflow()
            elif choice == "8":
                self.manage_scripts()

            if choice != "0" and console:
                Prompt.ask("Press Enter to continue...")

    def _show_dashboard(self):
        """Show enhanced dashboard with status overview"""
        if not console:
            return
        
        # Get stats
        workflows = self.manager.list_workflows()
        total = len(workflows)
        
        status_counts = defaultdict(int)
        for wf in workflows:
            status_counts[wf.status] += 1
        
        execution_summary = self.manager.get_execution_summary()
        
        # Create dashboard layout
        layout = Layout()
        layout.split(
            Layout(name="header", size=3),
            Layout(name="body"),
        )
        layout["body"].split_row(
            Layout(name="left", ratio=1),
            Layout(name="right", ratio=1),
        )
        
        # Header
        header_text = f"[bold cyan]📋 Workflow Management Dashboard[/bold cyan]"
        if total > 0:
            header_text += f"  [dim]({total} workflows)[/dim]"
        layout["header"].update(Panel(header_text, border_style="cyan"))
        
        # Left panel - Workflow stats
        stats_table = Table(title="Workflow Status", box=box.ROUNDED)
        stats_table.add_column("Status", style="cyan")
        stats_table.add_column("Count", style="white")
        
        status_colors = {
            'draft': 'dim',
            'active': 'green',
            'queued': 'yellow',
            'running': 'blue',
            'completed': 'green',
            'failed': 'red'
        }
        
        for status, count in sorted(status_counts.items()):
            color = status_colors.get(status, 'white')
            stats_table.add_row(f"[{color}]{status}[/{color}]", str(count))
        
        layout["left"].update(Panel(stats_table, border_style="blue"))
        
        # Right panel - Execution summary
        exec_table = Table(title="Execution Summary", box=box.ROUNDED)
        exec_table.add_column("Status", style="cyan")
        exec_table.add_column("Count", style="white")
        
        exec_statuses = [
            ('queued', 'yellow'),
            ('running', 'blue'),
            ('completed', 'green'),
            ('failed', 'red')
        ]
        
        for status, color in exec_statuses:
            count = execution_summary.get(status, 0)
            exec_table.add_row(f"[{color}]{status}[/{color}]", str(count))
        
        if execution_summary.get('total', 0) > 0:
            exec_table.add_section()
            exec_table.add_row("Total", str(execution_summary.get('total', 0)))
        
        layout["right"].update(Panel(exec_table, border_style="green"))
        
        console.print(layout)

    def _show_dashboard_simple(self):
        """Simple dashboard for non-rich environments"""
        workflows = self.manager.list_workflows()
        total = len(workflows)
        
        status_counts = defaultdict(int)
        for wf in workflows:
            status_counts[wf.status] += 1
        
        print("\n" + "="*50)
        print(f"📋 Workflow Dashboard - {total} workflows")
        print("-"*50)
        for status, count in sorted(status_counts.items()):
            print(f"  {status}: {count}")
        print("="*50)

    def _select_workflow_interactive(self, prompt: str = "Select workflow") -> Optional[Workflow]:
        """Interactive workflow selection with numbered menu"""
        workflows = self.manager.list_workflows()
        if not workflows:
            if console:
                console.print("[red]No workflows found[/red]")
            else:
                print("No workflows found")
            return None
        
        if console:
            table = Table(title="📋 Available Workflows", box=box.ROUNDED)
            table.add_column("#", style="cyan", width=4)
            table.add_column("Name", style="green")
            table.add_column("Status", style="magenta")
            table.add_column("Steps", style="yellow", width=6)
            table.add_column("ID", style="dim", width=10)
            
            status_colors = {
                'draft': 'dim',
                'active': 'green',
                'queued': 'yellow',
                'running': 'blue',
                'completed': 'green',
                'failed': 'red'
            }
            
            for i, wf in enumerate(workflows, 1):
                color = status_colors.get(wf.status, 'white')
                table.add_row(
                    str(i),
                    wf.name,
                    f"[{color}]{wf.status}[/{color}]",
                    str(len(wf.steps)),
                    wf.get_display_id()
                )
            
            console.print(table)
            choice = Prompt.ask(
                f"{prompt} (enter number or name/ID)",
                default=""
            )
        else:
            print("\nAvailable Workflows:")
            for i, wf in enumerate(workflows, 1):
                print(f"  {i}. {wf.name} ({wf.status}) - {len(wf.steps)} steps")
            choice = input(f"{prompt} (enter number or name/ID): ").strip()
        
        if not choice:
            return None
        
        # Try to select by number
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(workflows):
                return workflows[idx]
        except ValueError:
            pass
        
        # Try to find by name/ID
        return self.manager.get_workflow(choice)

    def create_workflow_interactive(self):
        """Enhanced workflow creation"""
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

        self.manager.registry.save(workflow)
        if console:
            console.print(f"[green]✅ Workflow '{name}' saved! ID: {workflow.id}[/green]")
            console.print(f"[dim]You can reference it by name '{name}' or ID prefix '{workflow.id[:8]}'[/dim]")
        else:
            print(f"✅ Workflow '{name}' saved! ID: {workflow.id}")
            print(f"   You can reference it by name '{name}' or ID prefix '{workflow.id[:8]}'")

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
        """Enhanced workflow listing"""
        workflows = self.manager.list_workflows()
        if not workflows:
            if console:
                console.print("[yellow]No workflows found[/yellow]")
            else:
                print("No workflows found")
            return

        if console:
            table = Table(title="📋 Workflows", box=box.ROUNDED)
            table.add_column("#", style="cyan", width=4)
            table.add_column("Name", style="green")
            table.add_column("Status", style="magenta")
            table.add_column("Steps", style="yellow", width=6)
            table.add_column("ID", style="dim", width=10)
            table.add_column("Created", style="dim", width=16)
            table.add_column("Executions", style="blue", width=10)

            status_colors = {
                'draft': 'dim',
                'active': 'green',
                'queued': 'yellow',
                'running': 'blue',
                'completed': 'green',
                'failed': 'red'
            }

            for i, wf in enumerate(workflows, 1):
                color = status_colors.get(wf.status, 'white')
                table.add_row(
                    str(i),
                    wf.name,
                    f"[{color}]{wf.status}[/{color}]",
                    str(len(wf.steps)),
                    wf.get_display_id(),
                    wf.created_at[:16] if wf.created_at else 'N/A',
                    str(wf.execution_count)
                )
            console.print(table)
            
            # Show summary
            status_counts = defaultdict(int)
            for wf in workflows:
                status_counts[wf.status] += 1
            summary = " | ".join([f"{status}: {count}" for status, count in status_counts.items()])
            console.print(f"[dim]Summary: {summary}[/dim]")
        else:
            print("\n📋 Workflows:")
            for i, wf in enumerate(workflows, 1):
                print(f"  {i}. {wf.name} ({wf.status}) - {len(wf.steps)} steps [ID: {wf.get_display_id()}]")

    def view_workflow(self):
        """Enhanced workflow viewing"""
        workflow = self._select_workflow_interactive("Select workflow to view")
        if not workflow:
            return

        # Show detailed workflow information
        content = f"""
[bold cyan]📊 Workflow: {workflow.name}[/bold cyan]
[bold]ID:[/bold] {workflow.id}
[bold]Status:[/bold] {workflow.status}
[bold]Description:[/bold] {workflow.description or 'N/A'}
[bold]Version:[/bold] {workflow.version}
[bold]Session:[/bold] {workflow.session_name}
[bold]URL:[/bold] {workflow.session_url}
[bold]Steps:[/bold] {len(workflow.steps)}
[bold]Executions:[/bold] {workflow.execution_count}
[bold]Avg Duration:[/bold] {f'{workflow.avg_duration:.2f}s' if workflow.avg_duration else 'N/A'}
[bold]Created:[/bold] {workflow.created_at}
[bold]Updated:[/bold] {workflow.updated_at}
[bold]Tags:[/bold] {', '.join(workflow.tags) if workflow.tags else 'None'}

[bold cyan]Steps:[/bold cyan]
"""
        for i, step_data in enumerate(workflow.steps, 1):
            step = WorkflowStep.from_dict(step_data)
            content += f"""
  [{i}] {step.name} ({step.type})
      ID: {step.id}
      Description: {step.description or 'N/A'}
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
            elif step.type == "extract":
                content += f"      Expression: {step.expression[:50]}...\n"
                if step.variable_name:
                    content += f"      Store in: {step.variable_name}\n"
            elif step.type == "api_call":
                config = step.api_config
                content += f"      Method: {config.get('method', 'GET')}\n"
                content += f"      URL: {config.get('url', 'N/A')}\n"

        if console:
            console.print(Panel(content, title="📊 Workflow Details", border_style="blue"))
        else:
            print(content)

    def execute_workflow(self):
        """Enhanced workflow execution"""
        workflow = self._select_workflow_interactive("Select workflow to execute")
        if not workflow:
            return

        session_name = Prompt.ask("Session name (enter for default)", default=workflow.session_name) if console else input(f"Session name [{workflow.session_name}]: ") or workflow.session_name

        if console:
            console.print(f"[yellow]📤 Queuing workflow '{workflow.name}'...[/yellow]")
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                transient=True,
            ) as progress:
                progress.add_task(description="Queuing...", total=None)
                try:
                    task_id = self.manager.queue_workflow(workflow.id, session_name)
                    console.print(f"[green]✅ Workflow queued! Task ID: {task_id}[/green]")
                except Exception as e:
                    console.print(f"[red]Failed to queue workflow: {e}[/red]")
        else:
            print(f"📤 Queuing workflow '{workflow.name}'...")
            try:
                task_id = self.manager.queue_workflow(workflow.id, session_name)
                print(f"✅ Workflow queued! Task ID: {task_id}")
            except Exception as e:
                print(f"Failed to queue workflow: {e}")

    def view_execution_status(self):
        """View execution status dashboard"""
        if console:
            console.print(Panel("[bold cyan]📊 Execution Status[/bold cyan]", border_style="cyan"))
        else:
            print("\n📊 Execution Status")

        summary = self.manager.get_execution_summary()
        
        if console:
            # Show summary
            summary_table = Table(title="Execution Summary", box=box.ROUNDED)
            summary_table.add_column("Status", style="cyan")
            summary_table.add_column("Count", style="white")
            
            status_emojis = {
                'queued': '⏳',
                'running': '🔄',
                'completed': '✅',
                'failed': '❌'
            }
            
            for status, emoji in status_emojis.items():
                count = summary.get(status, 0)
                summary_table.add_row(f"{emoji} {status}", str(count))
            
            summary_table.add_section()
            summary_table.add_row("Total", str(summary.get('total', 0)))
            console.print(summary_table)
            
            # Show by workflow if any
            if summary.get('by_workflow'):
                wf_table = Table(title="By Workflow", box=box.ROUNDED)
                wf_table.add_column("Workflow", style="green")
                wf_table.add_column("Executions", style="yellow")
                
                for wf_name, count in sorted(summary['by_workflow'].items(), key=lambda x: x[1], reverse=True):
                    wf_table.add_row(wf_name, str(count))
                
                console.print(wf_table)
        else:
            print(f"\nQueued: {summary.get('queued', 0)}")
            print(f"Running: {summary.get('running', 0)}")
            print(f"Completed: {summary.get('completed', 0)}")
            print(f"Failed: {summary.get('failed', 0)}")
            print(f"Total: {summary.get('total', 0)}")

    def delete_workflow(self):
        """Enhanced workflow deletion"""
        workflow = self._select_workflow_interactive("Select workflow to delete")
        if not workflow:
            return

        if console:
            confirm = Confirm.ask(f"Delete workflow '{workflow.name}' (ID: {workflow.id[:8]})?")
        else:
            confirm = input(f"Delete workflow '{workflow.name}'? (y/n): ").lower() == 'y'

        if confirm:
            if self.manager.registry.delete(workflow.id):
                if self.manager.redis:
                    self.manager.redis.delete(f"workflow:{workflow.id}")
                    self.manager.redis.srem("workflows:active", workflow.id)
                    self.manager.redis.delete(f"workflow:execution:{workflow.id}")
                
                if console:
                    console.print(f"[green]✅ Workflow '{workflow.name}' deleted[/green]")
                else:
                    print(f"✅ Workflow '{workflow.name}' deleted")
            else:
                if console:
                    console.print(f"[red]Failed to delete workflow[/red]")
                else:
                    print("Failed to delete workflow")

    def manage_scripts(self):
        """Script management (same as before)"""
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
        if console:
            console.print("\n[yellow]Interrupted[/yellow]")
        else:
            print("\nInterrupted")
    except Exception as e:
        logging.exception("Fatal error")
        if console:
            console.print(f"[red]Error: {e}[/red]")
        else:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()
