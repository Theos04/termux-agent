#!/usr/bin/env python3
"""
Enhanced Chrome Automation System - Self-contained
Builds on cdpv119.py, api.py, and workflow4.py
Supports: JS execution → Store → Execute more JS → Save → Trigger → Metadata
"""

import os
import sys
import json
import time
import asyncio
import logging
import hashlib
import uuid
import re
import threading
import queue
import subprocess
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Union
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import defaultdict

# ============================================================================
# Dependency Installation
# ============================================================================

def install_dependencies():
    """Install required dependencies"""
    deps = ['requests', 'rich']
    for dep in deps:
        try:
            __import__(dep)
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "install", dep])

install_dependencies()

# ============================================================================
# Imports after dependency check
# ============================================================================

try:
    import requests
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich.syntax import Syntax
    from rich import box
    from rich.progress import Progress, SpinnerColumn, TextColumn
    console = Console()
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "rich"])
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich.syntax import Syntax
    from rich import box
    from rich.progress import Progress, SpinnerColumn, TextColumn
    console = Console()

# ============================================================================
# Configuration
# ============================================================================

@dataclass
class WorkflowConfig:
    base_dir: str = os.path.expanduser("~/chrome-workflows")
    scripts_library: str = os.path.expanduser("~/chrome-workflows/scripts-library")
    workflows_dir: str = os.path.expanduser("~/chrome-workflows/workflows")
    results_dir: str = os.path.expanduser("~/chrome-workflows/results")
    executions_dir: str = os.path.expanduser("~/chrome-workflows/executions")
    api_base_url: str = "http://127.0.0.1:5000"
    cli_show_full_id: bool = False

# ============================================================================
# Data Models
# ============================================================================

class ExecutionStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"

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
    execution_count: int = 0
    avg_duration: Optional[float] = None

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'Workflow':
        return cls(**data)

    def get_display_id(self, show_full: bool = False) -> str:
        return self.id if show_full else self.id[:8]

@dataclass
class WorkflowExecution:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str = ""
    workflow_name: str = ""
    session_name: str = "unstop"
    status: str = "pending"
    current_step: int = 0
    total_steps: int = 0
    steps: List[Dict] = field(default_factory=list)
    results: List[Dict] = field(default_factory=list)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    metadata: Dict = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'WorkflowExecution':
        return cls(**data)

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
    target_workflow: str = ""  # For trigger steps

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'WorkflowStep':
        return cls(**data)

# ============================================================================
# Workflow Registry
# ============================================================================

class WorkflowRegistry:
    def __init__(self, config: WorkflowConfig):
        self.config = config
        self._workflows: Dict[str, Workflow] = {}
        self._loaded = False
        self._lock = threading.RLock()

    def load(self, force: bool = False) -> int:
        if self._loaded and not force:
            return len(self._workflows)

        with self._lock:
            workflows_dir = Path(self.config.workflows_dir)
            if not workflows_dir.exists():
                workflows_dir.mkdir(parents=True, exist_ok=True)
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

    def get(self, identifier: str) -> Optional[Workflow]:
        self.load()

        with self._lock:
            # Exact ID match
            if identifier in self._workflows:
                return self._workflows[identifier]

            # Partial ID match
            matches = [w for w in self._workflows.values() if w.id.startswith(identifier)]
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                raise ValueError(f"Multiple workflows match '{identifier}'")

            # Name match
            for wf in self._workflows.values():
                if wf.name.lower() == identifier.lower():
                    return wf

            # Name contains
            matches = [w for w in self._workflows.values() if identifier.lower() in w.name.lower()]
            if len(matches) == 1:
                return matches[0]

            return None

    def list_all(self, sort_by: str = 'name', status_filter: Optional[str] = None) -> List[Workflow]:
        self.load()

        with self._lock:
            workflows = list(self._workflows.values())

            if status_filter:
                workflows = [w for w in workflows if w.status == status_filter]

            if sort_by == 'name':
                workflows.sort(key=lambda w: w.name.lower())
            elif sort_by == 'created':
                workflows.sort(key=lambda w: w.created_at, reverse=True)
            elif sort_by == 'updated':
                workflows.sort(key=lambda w: w.updated_at, reverse=True)

            return workflows

    def save(self, workflow: Workflow) -> None:
        with self._lock:
            self._workflows[workflow.id] = workflow
            workflow.updated_at = datetime.now().isoformat()

            workflow_dir = Path(self.config.workflows_dir) / workflow.id
            workflow_dir.mkdir(parents=True, exist_ok=True)

            with open(workflow_dir / 'workflow.json', 'w') as f:
                json.dump(workflow.to_dict(), f, indent=2, default=str)

            # Save steps
            for i, step_data in enumerate(workflow.steps):
                step_file = workflow_dir / f"step_{i:03d}_{step_data.get('id', '')}.json"
                with open(step_file, 'w') as f:
                    json.dump(step_data, f, indent=2, default=str)

    def delete(self, workflow_id: str) -> bool:
        with self._lock:
            if workflow_id not in self._workflows:
                return False

            del self._workflows[workflow_id]

            workflow_dir = Path(self.config.workflows_dir) / workflow_id
            if workflow_dir.exists():
                shutil.rmtree(workflow_dir)

            return True

    def search(self, query: str) -> List[Workflow]:
        self.load()
        query_lower = query.lower()

        with self._lock:
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
# Script Library
# ============================================================================

class ScriptLibrary:
    def __init__(self, config: WorkflowConfig):
        self.config = config
        self.scripts_dir = Path(config.scripts_library)
        self.scripts_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_structure()

    def _ensure_structure(self):
        for subdir in ['workflows', 'scripts', 'templates', 'shared']:
            (self.scripts_dir / subdir).mkdir(exist_ok=True)

    def save_script(self, workflow_name: str, step: WorkflowStep) -> str:
        workflow_dir = self.scripts_dir / 'workflows' / workflow_name
        workflow_dir.mkdir(parents=True, exist_ok=True)

        safe_name = step.name.lower().replace(' ', '_') if step.name else f"step_{step.id}"
        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '', safe_name)

        filename = f"{safe_name}_{step.type}_{step.id}.js"
        filepath = workflow_dir / filename

        script_content = f"""/**
 * Script: {step.name}
 * ID: {step.id}
 * Type: {step.type}
 * Workflow: {workflow_name}
 * Created: {datetime.now().isoformat()}
 * Description: {step.description}
 */

// ============================================================================
// Main Execution Function
// ============================================================================

async function execute(api, context) {{
    console.log(`🔧 Executing step: {step.name} (ID: {step.id})`);

    try {{
        {step.code if step.code else '// Your code here'}
    }} catch (error) {{
        console.error(`❌ Step failed: ${{error.message}}`);
        throw error;
    }}
}}

// Export for workflow engine
if (typeof module !== 'undefined' && module.exports) {{
    module.exports = {{ execute }};
}}
"""
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

    def get_script(self, workflow_name: str, step_id: str) -> Optional[str]:
        workflow_dir = self.scripts_dir / 'workflows' / workflow_name
        if not workflow_dir.exists():
            return None

        for js_file in workflow_dir.glob(f"*_{step_id}.js"):
            with open(js_file, 'r') as f:
                return f.read()
        return None

    def get_all_scripts(self, workflow_name: str) -> List[Dict]:
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

# ============================================================================
# Workflow Manager
# ============================================================================

class WorkflowManager:
    def __init__(self, config: WorkflowConfig = None):
        self.config = config or WorkflowConfig()
        self.registry = WorkflowRegistry(self.config)
        self.script_library = ScriptLibrary(self.config)
        self._ensure_directories()

    def _ensure_directories(self):
        Path(self.config.base_dir).mkdir(parents=True, exist_ok=True)
        Path(self.config.workflows_dir).mkdir(parents=True, exist_ok=True)
        Path(self.config.results_dir).mkdir(parents=True, exist_ok=True)
        Path(self.config.executions_dir).mkdir(parents=True, exist_ok=True)

    def create_workflow(self, data: Dict) -> Workflow:
        workflow = Workflow.from_dict(data)
        self.registry.save(workflow)
        return workflow

    def get_workflow(self, identifier: str) -> Optional[Workflow]:
        return self.registry.get(identifier)

    def list_workflows(self, **kwargs) -> List[Workflow]:
        return self.registry.list_all(**kwargs)

    def search_workflows(self, query: str) -> List[Workflow]:
        return self.registry.search(query)

    def delete_workflow(self, workflow_id: str) -> bool:
        return self.registry.delete(workflow_id)

    def add_step(self, workflow_id: str, step_data: Dict) -> Workflow:
        workflow = self.get_workflow(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        step = WorkflowStep.from_dict(step_data)
        workflow.steps.append(step.to_dict())
        workflow.updated_at = datetime.now().isoformat()
        self.registry.save(workflow)
        return workflow

# ============================================================================
# Enhanced Execution Engine
# ============================================================================

class EnhancedExecutionEngine:
    def __init__(self, api_base_url: str = "http://127.0.0.1:5000"):
        self.api_base_url = api_base_url
        self.executions: Dict[str, WorkflowExecution] = {}
        self._lock = threading.RLock()
        self._execution_threads: Dict[str, threading.Thread] = {}
        self._stop_events: Dict[str, threading.Event] = {}

        self.base_dir = Path.home() / "chrome-workflows" / "executions"
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self.logger = logging.getLogger("EnhancedExecutionEngine")

    def _make_api_call(self, endpoint: str, method: str = "POST", data: Dict = None) -> Dict:
        url = f"{self.api_base_url}{endpoint}"
        try:
            if method.upper() == "GET":
                response = requests.get(url, timeout=30)
            else:
                response = requests.post(url, json=data or {}, timeout=30)

            if response.status_code == 200:
                return response.json()
            return {"error": f"API error: {response.status_code}", "detail": response.text}
        except Exception as e:
            return {"error": str(e)}

    def execute_javascript(self, session_name: str, script_code: str, context: Dict = None) -> Dict:
        if context:
            context_vars = []
            for k, v in context.items():
                try:
                    json.dumps(v)
                    context_vars.append(f"const {k} = {json.dumps(v)};")
                except:
                    context_vars.append(f"const {k} = '{str(v)}';")

            wrapped_code = f"""
            (function() {{
                {' '.join(context_vars)}
                return (function() {{
                    {script_code}
                }})();
            }})()
            """
        else:
            wrapped_code = script_code

        result = self._make_api_call(
            f"/session/{session_name}/evaluate",
            method="POST",
            data={"expression": wrapped_code}
        )
        return result

    def execute_step(self, step: Dict, session_name: str, context: Dict) -> Dict:
        step_type = step.get('type', 'js_execute')
        step_name = step.get('name', 'unnamed')

        result = {
            'step_id': step.get('id', str(uuid.uuid4())[:8]),
            'step_name': step_name,
            'step_type': step_type,
            'status': 'running',
            'started_at': datetime.now().isoformat(),
            'result': None,
            'error': None,
            'metadata': {}
        }

        try:
            if step_type == 'js_execute':
                script_code = step.get('code', '')
                if not script_code:
                    wf_name = step.get('workflow_name', 'default')
                    script_lib = ScriptLibrary(WorkflowConfig())
                    script_code = script_lib.get_script(wf_name, step.get('id', ''))

                if not script_code:
                    raise ValueError(f"No script found for step {step.get('id', 'unknown')}")

                exec_result = self.execute_javascript(session_name, script_code, context)
                result['result'] = exec_result

                var_name = step.get('variable_name')
                if var_name:
                    context[var_name] = exec_result
                    self.logger.info(f"📝 Stored result in context: {var_name}")

                result['status'] = 'completed'

            elif step_type == 'navigate':
                url = step.get('url')
                if not url:
                    raise ValueError("URL required for navigate step")

                nav_result = self._make_api_call(
                    f"/session/{session_name}/navigate",
                    method="POST",
                    data={"url": url}
                )
                result['result'] = nav_result
                result['status'] = 'completed'

            elif step_type == 'click':
                selector = step.get('selector')
                if not selector:
                    raise ValueError("Selector required for click step")

                click_result = self._make_api_call(
                    f"/session/{session_name}/click",
                    method="POST",
                    data={"selector": selector}
                )
                result['result'] = click_result
                result['status'] = 'completed'

            elif step_type == 'screenshot':
                screenshot_result = self._make_api_call(
                    f"/session/{session_name}/screenshot",
                    method="GET"
                )
                result['result'] = screenshot_result
                result['status'] = 'completed'

            elif step_type == 'wait':
                wait_time = step.get('wait_time', 1)
                time.sleep(wait_time)
                result['result'] = {'waited': wait_time}
                result['status'] = 'completed'

            elif step_type == 'extract':
                expression = step.get('expression', step.get('code', ''))
                if not expression:
                    raise ValueError("Expression required for extract step")

                extract_result = self.execute_javascript(session_name, expression, context)
                result['result'] = extract_result

                var_name = step.get('variable_name')
                if var_name:
                    context[var_name] = extract_result
                    self.logger.info(f"📝 Extracted data stored in: {var_name}")

                result['status'] = 'completed'

            elif step_type == 'store':
                var_name = step.get('variable_name')
                var_value = step.get('variable_value')
                if var_name:
                    context[var_name] = var_value
                    result['result'] = {'stored': var_name, 'value': var_value}
                    result['status'] = 'completed'
                else:
                    raise ValueError("variable_name required for store step")

            elif step_type == 'api_call':
                api_config = step.get('api_config', {})
                method = api_config.get('method', 'GET')
                url = api_config.get('url')
                headers = api_config.get('headers', {})
                body = api_config.get('body', {})

                if not url:
                    raise ValueError("URL required for API call")

                if method.upper() == 'GET':
                    resp = requests.get(url, headers=headers, timeout=step.get('timeout', 30))
                else:
                    resp = requests.request(method, url, headers=headers, json=body, timeout=step.get('timeout', 30))

                result['result'] = {
                    'status_code': resp.status_code,
                    'headers': dict(resp.headers),
                    'body': resp.json() if resp.headers.get('content-type', '').startswith('application/json') else resp.text
                }
                result['status'] = 'completed'

            elif step_type == 'assert':
                assert_config = step.get('assert_config', {})
                condition = assert_config.get('condition')
                expected = assert_config.get('expected')
                operator = assert_config.get('operator', 'equals')

                if condition:
                    assert_result = self.execute_javascript(session_name, condition, context)
                    actual = assert_result.get('result')

                    if operator == 'equals':
                        assert str(actual) == str(expected), f"Assertion failed: {actual} != {expected}"
                    elif operator == 'contains':
                        assert str(expected) in str(actual), f"Assertion failed: {expected} not in {actual}"
                    elif operator == 'greater':
                        assert float(actual) > float(expected), f"Assertion failed: {actual} <= {expected}"

                    result['result'] = {'assertion_passed': True, 'actual': actual, 'expected': expected}
                    result['status'] = 'completed'

            elif step_type == 'trigger':
                target_workflow = step.get('target_workflow')
                if not target_workflow:
                    raise ValueError("target_workflow required for trigger step")

                wm = WorkflowManager()
                target = wm.get_workflow(target_workflow)
                if not target:
                    raise ValueError(f"Target workflow '{target_workflow}' not found")

                result['result'] = {'triggered': target_workflow, 'status': 'queued'}
                result['status'] = 'completed'
                result['metadata']['triggered_workflow'] = target_workflow

            else:
                raise ValueError(f"Unknown step type: {step_type}")

        except Exception as e:
            result['status'] = 'failed'
            result['error'] = str(e)
            self.logger.error(f"❌ Step failed: {e}")

        result['completed_at'] = datetime.now().isoformat()
        return result

    def execute_workflow(self, workflow: Dict, session_name: str = None) -> WorkflowExecution:
        workflow_id = workflow.get('id', str(uuid.uuid4()))
        session_name = session_name or workflow.get('session_name', 'unstop')

        execution = WorkflowExecution(
            id=workflow_id,
            workflow_id=workflow_id,
            workflow_name=workflow.get('name', 'unnamed'),
            session_name=session_name,
            status='running',
            total_steps=len(workflow.get('steps', [])),
            steps=workflow.get('steps', []),
            started_at=datetime.now().isoformat()
        )

        with self._lock:
            self.executions[workflow_id] = execution

        context = {}

        try:
            steps = workflow.get('steps', [])
            for i, step in enumerate(steps):
                execution.current_step = i
                self.logger.info(f"▶️ Executing step {i+1}/{len(steps)}: {step.get('name', 'unnamed')}")

                step_result = self.execute_step(step, session_name, context)
                execution.results.append(step_result)

                if step_result['status'] == 'failed':
                    if not step.get('continue_on_error', False):
                        execution.status = 'failed'
                        execution.error = f"Step {i+1} failed: {step_result.get('error')}"
                        self.logger.error(f"❌ Workflow failed at step {i+1}")
                        break

            if execution.status == 'running':
                execution.status = 'completed'
                self.logger.info(f"✅ Workflow completed successfully")

            execution.metadata['context_snapshot'] = context

        except Exception as e:
            execution.status = 'failed'
            execution.error = str(e)
            self.logger.error(f"❌ Workflow execution failed: {e}")

        execution.completed_at = datetime.now().isoformat()

        with self._lock:
            self.executions[workflow_id] = execution

        self._save_execution(execution)
        return execution

    def _save_execution(self, execution: WorkflowExecution):
        exec_dir = self.base_dir / execution.id
        exec_dir.mkdir(parents=True, exist_ok=True)

        with open(exec_dir / 'execution.json', 'w') as f:
            json.dump(execution.to_dict(), f, indent=2, default=str)

        for i, result in enumerate(execution.results):
            with open(exec_dir / f'step_{i+1:03d}_result.json', 'w') as f:
                json.dump(result, f, indent=2, default=str)

        if execution.metadata.get('context_snapshot'):
            with open(exec_dir / 'context.json', 'w') as f:
                json.dump(execution.metadata['context_snapshot'], f, indent=2, default=str)

    def get_execution(self, execution_id: str) -> Optional[WorkflowExecution]:
        with self._lock:
            if execution_id in self.executions:
                return self.executions[execution_id]

        exec_dir = self.base_dir / execution_id
        if exec_dir.exists():
            try:
                with open(exec_dir / 'execution.json', 'r') as f:
                    data = json.load(f)
                    return WorkflowExecution.from_dict(data)
            except:
                pass

        return None

    def get_execution_status(self, execution_id: str) -> Dict:
        execution = self.get_execution(execution_id)
        if not execution:
            return {'exists': False, 'id': execution_id}

        return {
            'exists': True,
            'id': execution.id,
            'workflow_name': execution.workflow_name,
            'status': execution.status,
            'current_step': execution.current_step,
            'total_steps': execution.total_steps,
            'started_at': execution.started_at,
            'completed_at': execution.completed_at,
            'error': execution.error,
            'result_count': len(execution.results)
        }

# ============================================================================
# Workflow Builder
# ============================================================================

class WorkflowBuilder:
    def __init__(self, name: str, description: str = ""):
        self.workflow = {
            'id': str(uuid.uuid4()),
            'name': name,
            'description': description,
            'version': '1.0.0',
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'session_name': 'unstop',
            'session_url': 'https://unstop.com/',
            'steps': [],
            'metadata': {},
            'status': 'draft',
            'tags': []
        }
        self._engine = EnhancedExecutionEngine()

    def session(self, name: str, url: str = None) -> 'WorkflowBuilder':
        self.workflow['session_name'] = name
        if url:
            self.workflow['session_url'] = url
        return self

    def set_metadata(self, key: str, value: Any) -> 'WorkflowBuilder':
        self.workflow['metadata'][key] = value
        return self

    def add_tag(self, tag: str) -> 'WorkflowBuilder':
        if tag not in self.workflow['tags']:
            self.workflow['tags'].append(tag)
        return self

    def js(self, name: str, code: str, variable_name: str = None, continue_on_error: bool = False) -> 'WorkflowBuilder':
        step = {
            'id': str(uuid.uuid4())[:8],
            'type': 'js_execute',
            'name': name,
            'code': code,
            'variable_name': variable_name,
            'continue_on_error': continue_on_error,
            'timeout': 30,
            'retry_count': 0
        }
        self.workflow['steps'].append(step)
        return self

    def navigate(self, url: str, name: str = "Navigate") -> 'WorkflowBuilder':
        step = {
            'id': str(uuid.uuid4())[:8],
            'type': 'navigate',
            'name': name,
            'url': url,
            'timeout': 30
        }
        self.workflow['steps'].append(step)
        return self

    def click(self, selector: str, name: str = "Click") -> 'WorkflowBuilder':
        step = {
            'id': str(uuid.uuid4())[:8],
            'type': 'click',
            'name': name,
            'selector': selector,
            'timeout': 30
        }
        self.workflow['steps'].append(step)
        return self

    def extract(self, name: str, expression: str, variable_name: str = None) -> 'WorkflowBuilder':
        step = {
            'id': str(uuid.uuid4())[:8],
            'type': 'extract',
            'name': name,
            'expression': expression,
            'variable_name': variable_name,
            'timeout': 30
        }
        self.workflow['steps'].append(step)
        return self

    def store(self, variable_name: str, value: Any, name: str = "Store") -> 'WorkflowBuilder':
        step = {
            'id': str(uuid.uuid4())[:8],
            'type': 'store',
            'name': name,
            'variable_name': variable_name,
            'variable_value': value
        }
        self.workflow['steps'].append(step)
        return self

    def wait(self, seconds: int, name: str = "Wait") -> 'WorkflowBuilder':
        step = {
            'id': str(uuid.uuid4())[:8],
            'type': 'wait',
            'name': name,
            'wait_time': seconds
        }
        self.workflow['steps'].append(step)
        return self

    def screenshot(self, name: str = "Screenshot") -> 'WorkflowBuilder':
        step = {
            'id': str(uuid.uuid4())[:8],
            'type': 'screenshot',
            'name': name
        }
        self.workflow['steps'].append(step)
        return self

    def api_call(self, method: str, url: str, headers: Dict = None, body: Dict = None, name: str = "API Call") -> 'WorkflowBuilder':
        step = {
            'id': str(uuid.uuid4())[:8],
            'type': 'api_call',
            'name': name,
            'api_config': {
                'method': method,
                'url': url,
                'headers': headers or {},
                'body': body or {}
            },
            'timeout': 30
        }
        self.workflow['steps'].append(step)
        return self

    def assert_equals(self, expression: str, expected: Any, name: str = "Assert Equals") -> 'WorkflowBuilder':
        step = {
            'id': str(uuid.uuid4())[:8],
            'type': 'assert',
            'name': name,
            'assert_config': {
                'condition': expression,
                'expected': expected,
                'operator': 'equals'
            }
        }
        self.workflow['steps'].append(step)
        return self

    def trigger(self, target_workflow: str, name: str = "Trigger") -> 'WorkflowBuilder':
        step = {
            'id': str(uuid.uuid4())[:8],
            'type': 'trigger',
            'name': name,
            'target_workflow': target_workflow
        }
        self.workflow['steps'].append(step)
        return self

    def build(self) -> Dict:
        self.workflow['updated_at'] = datetime.now().isoformat()
        return self.workflow

    def save(self, workflow_manager: WorkflowManager = None) -> str:
        workflow = self.build()

        if workflow_manager is None:
            workflow_manager = WorkflowManager()

        wf_obj = Workflow.from_dict(workflow)
        workflow_manager.registry.save(wf_obj)
        return wf_obj.id

    def execute(self, session_name: str = None) -> WorkflowExecution:
        workflow = self.build()
        return self._engine.execute_workflow(workflow, session_name)

# ============================================================================
# Context Manager
# ============================================================================

class WorkflowContext:
    def __init__(self):
        self._data = {}
        self._history = []
        self._lock = threading.RLock()

    def set(self, key: str, value: Any, metadata: Dict = None):
        with self._lock:
            self._data[key] = value
            self._history.append({
                'key': key,
                'value': value,
                'timestamp': datetime.now().isoformat(),
                'metadata': metadata or {}
            })

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)

    def get_all(self) -> Dict:
        with self._lock:
            return self._data.copy()

    def get_history(self, limit: int = None) -> List[Dict]:
        with self._lock:
            if limit:
                return self._history[-limit:]
            return self._history.copy()

    def clear(self):
        with self._lock:
            self._data.clear()
            self._history.clear()

# ============================================================================
# Enhanced CLI
# ============================================================================

class EnhancedCLI:
    def __init__(self):
        self.config = WorkflowConfig()
        self.engine = EnhancedExecutionEngine()
        self.workflow_manager = WorkflowManager(self.config)
        self.context = WorkflowContext()
        self._running = True

    def run(self):
        while self._running:
            if console:
                console.clear()
                self._show_header()

                menu = Table(show_header=False, box=box.MINIMAL)
                menu.add_column("Option", style="cyan", width=8)
                menu.add_column("Action", style="white")
                menu.add_column("Description", style="dim")

                menu.add_row("1", "[green]Execute JS[/green]", "Execute JavaScript and see results")
                menu.add_row("2", "[blue]Store Result[/blue]", "Store execution result with metadata")
                menu.add_row("3", "[yellow]Execute More JS[/yellow]", "Execute JS using stored data")
                menu.add_row("4", "[magenta]Save Data[/magenta]", "Save results and metadata")
                menu.add_row("5", "[cyan]Trigger Workflow[/cyan]", "Trigger another workflow")
                menu.add_row("6", "[white]View Context[/white]", "View stored context data")
                menu.add_row("7", "[red]Build Workflow[/red]", "Build a workflow interactively")
                menu.add_row("8", "[bright_blue]Run Workflow[/bright_blue]", "Run a saved workflow")
                menu.add_row("9", "[bright_magenta]List Workflows[/bright_magenta]", "List all workflows")
                menu.add_row("0", "[red]Exit[/red]", "Exit")

                console.print(menu)
                choice = Prompt.ask("Select option", choices=["0","1","2","3","4","5","6","7","8","9"])
            else:
                print("\n=== Enhanced Chrome Automation CLI ===")
                print("1. Execute JS")
                print("2. Store Result")
                print("3. Execute More JS")
                print("4. Save Data")
                print("5. Trigger Workflow")
                print("6. View Context")
                print("7. Build Workflow")
                print("8. Run Workflow")
                print("9. List Workflows")
                print("0. Exit")
                choice = input("Select option: ")

            if choice == "0":
                self._running = False
                break
            elif choice == "1":
                self._execute_js_interactive()
            elif choice == "2":
                self._store_result_interactive()
            elif choice == "3":
                self._execute_more_js_interactive()
            elif choice == "4":
                self._save_data_interactive()
            elif choice == "5":
                self._trigger_workflow_interactive()
            elif choice == "6":
                self._view_context()
            elif choice == "7":
                self._build_workflow_interactive()
            elif choice == "8":
                self._run_workflow_interactive()
            elif choice == "9":
                self._list_workflows()

            if choice != "0" and console:
                Prompt.ask("Press Enter to continue...")

    def _show_header(self):
        workflows = self.workflow_manager.list_workflows()
        context_count = len(self.context.get_all())

        header = f"""
╔══════════════════════════════════════════════════════════════╗
║     🌐 Enhanced Chrome Automation System                    ║
║     Build: Execute JS → Store → Execute More → Trigger     ║
╠══════════════════════════════════════════════════════════════╣
║  📋 Workflows: {len(workflows)}  |  🎯 Context: {context_count} items  ║
╚══════════════════════════════════════════════════════════════╝
        """
        console.print(Panel(header, border_style="cyan"))

    def _execute_js_interactive(self):
        console.print(Panel("[bold green]⚡ Execute JavaScript[/bold green]", border_style="green"))

        session_name = Prompt.ask("Session name", default="unstop")
        console.print("[yellow]Enter JavaScript code (press Ctrl+D when done):[/yellow]")

        lines = []
        try:
            while True:
                line = input()
                if line == "":  # Allow empty lines
                    lines.append("")
                else:
                    lines.append(line)
        except EOFError:
            pass

        code = "\n".join(lines)

        if not code.strip():
            console.print("[red]No code entered[/red]")
            return

        result = self.engine.execute_javascript(session_name, code, self.context.get_all())

        console.print("\n[bold]Result:[/bold]")
        console.print_json(json.dumps(result, default=str, indent=2))

        if Confirm.ask("Store this result in context?", default=True):
            key = Prompt.ask("Variable name")
            if key:
                self.context.set(key, result)
                console.print(f"[green]✅ Stored in context: {key}[/green]")

    def _store_result_interactive(self):
        console.print(Panel("[bold blue]💾 Store Result[/bold blue]", border_style="blue"))

        key = Prompt.ask("Variable name")
        value = Prompt.ask("Value (JSON or string)")
        metadata_str = Prompt.ask("Metadata (JSON, optional)", default="{}")

        try:
            try:
                parsed_value = json.loads(value)
            except:
                parsed_value = value

            metadata = json.loads(metadata_str) if metadata_str else {}

            self.context.set(key, parsed_value, metadata)
            console.print(f"[green]✅ Stored '{key}' with metadata[/green]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

    def _execute_more_js_interactive(self):
        console.print(Panel("[bold yellow]🔄 Execute More JS (with context)[/bold yellow]", border_style="yellow"))

        context_data = self.context.get_all()
        if context_data:
            console.print("[dim]Available context variables:[/dim]")
            for key, value in context_data.items():
                val_str = str(value)[:50] + "..." if len(str(value)) > 50 else str(value)
                console.print(f"  [cyan]{key}[/cyan]: {val_str}")
        else:
            console.print("[dim]No context variables available[/dim]")

        session_name = Prompt.ask("Session name", default="unstop")

        console.print("[yellow]Enter JavaScript code (use context variables):[/yellow]")
        console.print("[dim]Example: const title = context.page_title; return title;[/dim]")

        lines = []
        try:
            while True:
                line = input()
                lines.append(line)
        except EOFError:
            pass

        custom_code = "\n".join(lines)

        if not custom_code.strip():
            console.print("[red]No code entered[/red]")
            return

        context_vars = self.context.get_all()
        context_js = "\n".join([f"const {k} = {json.dumps(v, default=str)};" for k, v in context_vars.items()])

        full_code = f"""
        (function() {{
            {context_js}
            {custom_code}
        }})()
        """

        result = self.engine.execute_javascript(session_name, full_code, {})

        console.print("\n[bold]Result:[/bold]")
        console.print_json(json.dumps(result, default=str, indent=2))

        if Confirm.ask("Store this result?", default=True):
            key = Prompt.ask("Variable name")
            if key:
                self.context.set(key, result)
                console.print(f"[green]✅ Stored in context: {key}[/green]")

    def _save_data_interactive(self):
        console.print(Panel("[bold magenta]💾 Save Data[/bold magenta]", border_style="magenta"))

        context_data = self.context.get_all()
        metadata = {
            'saved_at': datetime.now().isoformat(),
            'context_size': len(context_data),
            'workflow': 'manual'
        }

        if not context_data:
            console.print("[yellow]No data in context[/yellow]")
            return

        data_to_save = {}
        for key, value in context_data.items():
            if Confirm.ask(f"Save '{key}'?"):
                data_to_save[key] = value

        if not data_to_save:
            console.print("[yellow]No data selected to save[/yellow]")
            return

        filename = Prompt.ask("Filename", default=f"data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")

        save_dir = Path.home() / "chrome-workflows" / "saved_data"
        save_dir.mkdir(parents=True, exist_ok=True)

        with open(save_dir / filename, 'w') as f:
            json.dump({
                'data': data_to_save,
                'metadata': metadata,
                'context_history': self.context.get_history(10)
            }, f, indent=2, default=str)

        console.print(f"[green]✅ Data saved to: {save_dir / filename}[/green]")

    def _trigger_workflow_interactive(self):
        console.print(Panel("[bold cyan]🔗 Trigger Workflow[/bold cyan]", border_style="cyan"))

        workflows = self.workflow_manager.list_workflows()
        if not workflows:
            console.print("[yellow]No workflows available[/yellow]")
            return

        table = Table(title="Available Workflows", box=box.ROUNDED)
        table.add_column("Name", style="green")
        table.add_column("Status", style="magenta")
        table.add_column("Steps", style="yellow")
        table.add_column("ID", style="dim")

        for wf in workflows:
            table.add_row(wf.name, wf.status, str(len(wf.steps)), wf.get_display_id())
        console.print(table)

        target = Prompt.ask("Workflow name or ID to trigger")
        session_name = Prompt.ask("Session name", default="unstop")

        builder = WorkflowBuilder(
            name=f"Trigger_{target}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            description=f"Triggered workflow: {target}"
        )
        builder.session(session_name)
        builder.trigger(target, "Trigger Workflow")
        builder.set_metadata("triggered_by", "interactive")
        builder.set_metadata("triggered_at", datetime.now().isoformat())
        builder.set_metadata("context_snapshot", self.context.get_all())
        builder.add_tag("triggered")

        wf_id = builder.save(self.workflow_manager)
        console.print(f"[green]✅ Trigger workflow created: {wf_id}[/green]")

        if Confirm.ask("Execute now?"):
            execution = builder.execute(session_name)
            console.print(f"[green]✅ Execution completed: {execution.status}[/green]")
            console.print(f"   Results: {len(execution.results)} steps")

    def _view_context(self):
        console.print(Panel("[bold white]📋 Context Data[/bold white]", border_style="white"))

        context_data = self.context.get_all()

        if context_data:
            table = Table(title="Context Variables", box=box.ROUNDED)
            table.add_column("Key", style="cyan")
            table.add_column("Value", style="white")
            table.add_column("Type", style="dim")

            for key, value in context_data.items():
                val_str = str(value)[:100] + "..." if len(str(value)) > 100 else str(value)
                table.add_row(key, val_str, type(value).__name__)

            console.print(table)
        else:
            console.print("[dim]No context data available[/dim]")

        history = self.context.get_history(5)
        if history:
            console.print("\n[bold dim]Recent History:[/bold dim]")
            for entry in history:
                console.print(f"  {entry['timestamp'][:19]} - {entry['key']} = {str(entry['value'])[:50]}")

    def _build_workflow_interactive(self):
        console.print(Panel("[bold red]🏗️ Build Workflow[/bold red]", border_style="red"))

        name = Prompt.ask("Workflow name")
        if not name:
            console.print("[red]Name required[/red]")
            return

        description = Prompt.ask("Description", default="")

        builder = WorkflowBuilder(name, description)

        session_name = Prompt.ask("Session name", default="unstop")
        session_url = Prompt.ask("Session URL", default="https://unstop.com/")

        builder.session(session_name, session_url)

        while True:
            console.print("\n[bold]Add a step:[/bold]")
            console.print("1. JS Execute")
            console.print("2. Navigate")
            console.print("3. Click")
            console.print("4. Extract")
            console.print("5. Store")
            console.print("6. Wait")
            console.print("7. Screenshot")
            console.print("8. API Call")
            console.print("9. Assert")
            console.print("10. Trigger")
            console.print("0. Done")

            step_type = Prompt.ask("Select step type", choices=["0","1","2","3","4","5","6","7","8","9","10"])

            if step_type == "0":
                break

            step_name = Prompt.ask("Step name", default=f"Step_{len(builder.workflow['steps']) + 1}")

            if step_type == "1":
                console.print("[yellow]Enter JavaScript code (press Ctrl+D when done):[/yellow]")
                lines = []
                try:
                    while True:
                        line = input()
                        lines.append(line)
                except EOFError:
                    pass
                code = "\n".join(lines)
                var_name = Prompt.ask("Store result in variable (optional)", default="")
                continue_on_error = Confirm.ask("Continue on error?", default=False)
                builder.js(step_name, code, var_name if var_name else None, continue_on_error)

            elif step_type == "2":
                url = Prompt.ask("URL")
                builder.navigate(url, step_name)

            elif step_type == "3":
                selector = Prompt.ask("CSS selector")
                builder.click(selector, step_name)

            elif step_type == "4":
                expression = Prompt.ask("JavaScript expression")
                var_name = Prompt.ask("Store in variable", default="")
                builder.extract(step_name, expression, var_name if var_name else None)

            elif step_type == "5":
                var_name = Prompt.ask("Variable name")
                value = Prompt.ask("Value")
                try:
                    value = json.loads(value)
                except:
                    pass
                builder.store(var_name, value, step_name)

            elif step_type == "6":
                seconds = int(Prompt.ask("Seconds", default="1"))
                builder.wait(seconds, step_name)

            elif step_type == "7":
                builder.screenshot(step_name)

            elif step_type == "8":
                method = Prompt.ask("Method", default="GET")
                url = Prompt.ask("URL")
                builder.api_call(method, url, name=step_name)

            elif step_type == "9":
                expression = Prompt.ask("JavaScript condition")
                expected = Prompt.ask("Expected value")
                try:
                    expected = json.loads(expected)
                except:
                    pass
                builder.assert_equals(expression, expected, step_name)

            elif step_type == "10":
                target = Prompt.ask("Target workflow name or ID")
                builder.trigger(target, step_name)

            console.print("[green]✅ Step added[/green]")

        tags = Prompt.ask("Tags (comma-separated)", default="")
        if tags:
            for tag in tags.split(','):
                builder.add_tag(tag.strip())

        wf_id = builder.save(self.workflow_manager)
        console.print(f"[green]✅ Workflow '{name}' saved! ID: {wf_id}[/green]")

        if Confirm.ask("Execute now?"):
            execution = builder.execute()
            console.print(f"[green]✅ Execution completed: {execution.status}[/green]")
            console.print(f"   Steps: {len(execution.results)} / {execution.total_steps}")
            if execution.error:
                console.print(f"   Error: {execution.error}")

    def _run_workflow_interactive(self):
        console.print(Panel("[bold bright_blue]🚀 Run Workflow[/bold bright_blue]", border_style="bright_blue"))

        workflows = self.workflow_manager.list_workflows()
        if not workflows:
            console.print("[yellow]No workflows available[/yellow]")
            return

        table = Table(title="Workflows", box=box.ROUNDED)
        table.add_column("#", style="cyan", width=4)
        table.add_column("Name", style="green")
        table.add_column("Status", style="magenta")
        table.add_column("Steps", style="yellow")
        table.add_column("ID", style="dim")

        for i, wf in enumerate(workflows, 1):
            table.add_row(str(i), wf.name, wf.status, str(len(wf.steps)), wf.get_display_id())
        console.print(table)

        choice = Prompt.ask("Select workflow (number or name)")

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(workflows):
                workflow = workflows[idx]
            else:
                workflow = self.workflow_manager.get_workflow(choice)
        except ValueError:
            workflow = self.workflow_manager.get_workflow(choice)

        if not workflow:
            console.print("[red]Workflow not found[/red]")
            return

        session_name = Prompt.ask("Session name", default=workflow.session_name)

        if Confirm.ask(f"Run workflow '{workflow.name}'?"):
            engine = EnhancedExecutionEngine()
            wf_dict = workflow.to_dict()
            wf_dict['steps'] = workflow.steps

            execution = engine.execute_workflow(wf_dict, session_name)
            console.print(f"[green]✅ Execution completed: {execution.status}[/green]")
            console.print(f"   Results: {len(execution.results)} steps")

            table = Table(title="Step Results", box=box.ROUNDED)
            table.add_column("Step", style="cyan")
            table.add_column("Status", style="magenta")
            table.add_column("Result", style="dim")

            for i, result in enumerate(execution.results, 1):
                status_color = "green" if result['status'] == 'completed' else "red"
                result_str = str(result.get('result', ''))[:50]
                table.add_row(
                    f"{i}. {result['step_name']}",
                    f"[{status_color}]{result['status']}[/{status_color}]",
                    result_str
                )
            console.print(table)

    def _list_workflows(self):
        console.print(Panel("[bold cyan]📋 Workflows[/bold cyan]", border_style="cyan"))

        workflows = self.workflow_manager.list_workflows()
        if not workflows:
            console.print("[yellow]No workflows found[/yellow]")
            return

        table = Table(title=f"Workflows ({len(workflows)})", box=box.ROUNDED)
        table.add_column("#", style="cyan", width=4)
        table.add_column("Name", style="green")
        table.add_column("Status", style="magenta")
        table.add_column("Steps", style="yellow")
        table.add_column("Executions", style="blue")
        table.add_column("ID", style="dim")

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
                str(wf.execution_count),
                wf.get_display_id()
            )

        console.print(table)

        # Show summary
        status_counts = defaultdict(int)
        for wf in workflows:
            status_counts[wf.status] += 1
        summary = " | ".join([f"{status}: {count}" for status, count in status_counts.items()])
        console.print(f"[dim]Summary: {summary}[/dim]")

# ============================================================================
# Main Entry
# ============================================================================

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(os.path.expanduser("~/chrome-workflows/enhanced.log"))
        ]
    )

def main():
    setup_logging()

    # Ensure directories exist
    for d in ["~/chrome-workflows", "~/chrome-workflows/workflows", "~/chrome-workflows/executions"]:
        Path(os.path.expanduser(d)).mkdir(parents=True, exist_ok=True)

    try:
        cli = EnhancedCLI()
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
