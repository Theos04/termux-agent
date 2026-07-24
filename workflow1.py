#!/usr/bin/env python3
"""
workflow1.py - Complete Workflow Template Engine (Fixed)
"""

import os
import sys
import json
import time
import subprocess
import shutil
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum
import hashlib
import threading
import queue
import logging
from logging.handlers import RotatingFileHandler

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich import box
    from rich.tree import Tree
    from rich.syntax import Syntax
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "rich"])
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich import box
    from rich.tree import Tree
    from rich.syntax import Syntax

try:
    import yaml
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyyaml"])
    import yaml

try:
    import requests
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

console = Console()

# ============================================================================
# Configuration
# ============================================================================

@dataclass
class WorkflowConfig:
    """Configuration for workflow engine"""
    workflows_dir: str = os.path.expanduser("~/workflows")
    scripts_dir: str = os.path.expanduser("~/chrome-scripts")
    logs_dir: str = os.path.expanduser("~/workflow-logs")
    api_host: str = "127.0.0.1"
    api_port: int = 5000
    max_retries: int = 3
    retry_delay: int = 5
    default_timeout: int = 300

# ============================================================================
# Script Library Manager
# ============================================================================

class ScriptLibrary:
    """Manages JavaScript scripts library for Chrome automation"""
    
    def __init__(self, scripts_dir: str):
        self.scripts_dir = Path(scripts_dir)
        self.scripts_dir.mkdir(parents=True, exist_ok=True)
        self.scripts: Dict[str, Dict] = {}
        self.categories: Dict[str, List[str]] = {}
        self._load_scripts()
    
    def _load_scripts(self):
        """Load all scripts from directory"""
        self.scripts = {}
        self.categories = {}
        
        # Look for script files and directories
        for item in self.scripts_dir.iterdir():
            if item.is_dir():
                # Category directory
                category = item.name
                self.categories[category] = []
                for script_file in item.glob("*.js"):
                    script_id = script_file.stem
                    script_data = self._load_script_file(script_file)
                    if script_data:
                        script_data['category'] = category
                        script_data['file_path'] = str(script_file)
                        self.scripts[script_id] = script_data
                        self.categories[category].append(script_id)
            
            elif item.suffix == '.js':
                # Standalone script
                script_id = item.stem
                script_data = self._load_script_file(item)
                if script_data:
                    script_data['category'] = 'standalone'
                    script_data['file_path'] = str(item)
                    self.scripts[script_id] = script_data
                    if 'standalone' not in self.categories:
                        self.categories['standalone'] = []
                    self.categories['standalone'].append(script_id)
        
        console.print(f"[green]📚 Loaded {len(self.scripts)} scripts from {len(self.categories)} categories[/green]")
    
    def _load_script_file(self, file_path: Path) -> Optional[Dict]:
        """Load a script file with metadata"""
        try:
            with open(file_path, 'r') as f:
                content = f.read()
            
            # Try to extract metadata from comments
            metadata = self._extract_metadata(content)
            
            return {
                'id': file_path.stem,
                'name': metadata.get('name', file_path.stem),
                'description': metadata.get('description', ''),
                'content': content,
                'file_path': str(file_path),
                'size': len(content),
                'lines': len(content.split('\n')),
                'metadata': metadata
            }
        except Exception as e:
            console.print(f"[red]Error loading {file_path}: {e}[/red]")
            return None
    
    def _extract_metadata(self, content: str) -> Dict:
        """Extract metadata from script comments"""
        metadata = {}
        lines = content.split('\n')
        
        for line in lines[:20]:  # Check first 20 lines
            if line.startswith('//'):
                # Format: // @key: value
                if '@' in line:
                    parts = line.split(':', 1)
                    if len(parts) == 2:
                        key = parts[0].replace('//', '').strip().replace('@', '').strip()
                        value = parts[1].strip()
                        metadata[key] = value
                # Format: // description: value
                elif ':' in line:
                    parts = line.split(':', 1)
                    key = parts[0].replace('//', '').strip()
                    value = parts[1].strip()
                    if key in ['name', 'description', 'author', 'version']:
                        metadata[key] = value
        
        return metadata
    
    def get_script(self, script_id: str) -> Optional[Dict]:
        """Get a script by ID"""
        return self.scripts.get(script_id)
    
    def get_scripts_by_category(self, category: str) -> List[Dict]:
        """Get all scripts in a category"""
        script_ids = self.categories.get(category, [])
        return [self.scripts[sid] for sid in script_ids if sid in self.scripts]
    
    def get_all_scripts(self) -> List[Dict]:
        """Get all scripts"""
        return list(self.scripts.values())
    
    def get_categories(self) -> List[str]:
        """Get all categories"""
        return list(self.categories.keys())
    
    def search_scripts(self, query: str) -> List[Dict]:
        """Search scripts by name or description"""
        query = query.lower()
        results = []
        for script in self.scripts.values():
            if query in script['name'].lower() or query in script.get('description', '').lower():
                results.append(script)
        return results
    
    def display_scripts(self):
        """Display scripts in a nice tree format"""
        if not self.scripts:
            console.print("[dim]No scripts found in library[/dim]")
            return
            
        tree = Tree("[bold cyan]📚 Script Library[/bold cyan]")
        
        for category in sorted(self.categories.keys()):
            category_tree = tree.add(f"[bold green]{category}[/bold green]")
            script_ids = self.categories.get(category, [])
            for script_id in script_ids:
                script = self.scripts.get(script_id)
                if script:
                    desc = f" - {script.get('description', '')}" if script.get('description') else ""
                    category_tree.add(f"[white]{script['name']}[/white][dim]{desc}[/dim]")
        
        console.print(tree)

# ============================================================================
# Workflow Step Types
# ============================================================================

class StepType(Enum):
    """Types of workflow steps"""
    START_SESSION = "start_session"
    STOP_SESSION = "stop_session"
    NAVIGATE = "navigate"
    CLICK = "click"
    FILL = "fill"
    EXECUTE_SCRIPT = "execute_script"
    WAIT = "wait"
    EXTRACT_DATA = "extract_data"
    SCREENSHOT = "screenshot"
    CONDITION = "condition"
    LOOP = "loop"
    PARALLEL = "parallel"
    WEBHOOK = "webhook"
    NOTIFY = "notify"

# ============================================================================
# Workflow Definition
# ============================================================================

@dataclass
class WorkflowStep:
    """A single step in a workflow"""
    id: str
    type: StepType
    name: str
    params: Dict[str, Any] = field(default_factory=dict)
    condition: Optional[str] = None
    retry_count: int = 0
    timeout: int = 300
    
    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'type': self.type.value,
            'name': self.name,
            'params': self.params,
            'condition': self.condition,
            'retry_count': self.retry_count,
            'timeout': self.timeout
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'WorkflowStep':
        return cls(
            id=data['id'],
            type=StepType(data['type']),
            name=data['name'],
            params=data.get('params', {}),
            condition=data.get('condition'),
            retry_count=data.get('retry_count', 0),
            timeout=data.get('timeout', 300)
        )

@dataclass
class Workflow:
    """Complete workflow definition"""
    id: str
    name: str
    description: str
    steps: List[WorkflowStep] = field(default_factory=list)
    schedule: Optional[str] = None  # Cron expression
    enabled: bool = True
    triggers: List[str] = field(default_factory=list)  # Script IDs that trigger this workflow
    triggered_scripts: List[str] = field(default_factory=list)  # Scripts triggered by this workflow
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'steps': [s.to_dict() for s in self.steps],
            'schedule': self.schedule,
            'enabled': self.enabled,
            'triggers': self.triggers,
            'triggered_scripts': self.triggered_scripts,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Workflow':
        steps = [WorkflowStep.from_dict(s) for s in data.get('steps', [])]
        return cls(
            id=data['id'],
            name=data['name'],
            description=data.get('description', ''),
            steps=steps,
            schedule=data.get('schedule'),
            enabled=data.get('enabled', True),
            triggers=data.get('triggers', []),
            triggered_scripts=data.get('triggered_scripts', []),
            created_at=data.get('created_at', datetime.now().isoformat()),
            updated_at=data.get('updated_at', datetime.now().isoformat())
        )

# ============================================================================
# Workflow Engine - Main Executor
# ============================================================================

class WorkflowEngine:
    """Main workflow execution engine"""
    
    def __init__(self, config: WorkflowConfig):
        self.config = config
        self.script_library = ScriptLibrary(config.scripts_dir)
        self.api_base = f"http://{config.api_host}:{config.api_port}"
        self.session = requests.Session()
        self.session.timeout = 30
        self.workflows: Dict[str, Workflow] = {}
        self.running_workflows: Dict[str, Dict] = {}
        self.execution_history: List[Dict] = []
        self.context: Dict[str, Any] = {}
        self._load_workflows()
    
    def _load_workflows(self):
        """Load all workflows from storage"""
        workflows_dir = Path(self.config.workflows_dir)
        workflows_dir.mkdir(parents=True, exist_ok=True)
        
        for file_path in workflows_dir.glob("*.yaml"):
            try:
                with open(file_path, 'r') as f:
                    data = yaml.safe_load(f)
                workflow = Workflow.from_dict(data)
                self.workflows[workflow.id] = workflow
                console.print(f"[dim]Loaded workflow: {workflow.name}[/dim]")
            except Exception as e:
                console.print(f"[red]Error loading {file_path}: {e}[/red]")
    
    def _save_workflow(self, workflow: Workflow):
        """Save workflow to storage"""
        workflow.updated_at = datetime.now().isoformat()
        file_path = Path(self.config.workflows_dir) / f"{workflow.id}.yaml"
        with open(file_path, 'w') as f:
            yaml.dump(workflow.to_dict(), f, default_flow_style=False)
    
    def create_workflow(self, name: str, description: str = "") -> Workflow:
        """Create a new workflow"""
        workflow_id = self._generate_id(name)
        workflow = Workflow(
            id=workflow_id,
            name=name,
            description=description
        )
        self.workflows[workflow_id] = workflow
        self._save_workflow(workflow)
        return workflow
    
    def _generate_id(self, name: str) -> str:
        """Generate a unique ID from name"""
        base = name.lower().replace(' ', '_')
        # Check if exists
        if any(w.id == base for w in self.workflows.values()):
            base = f"{base}_{hashlib.md5(str(time.time()).encode()).hexdigest()[:6]}"
        return base
    
    def add_step(self, workflow_id: str, step_type: StepType, name: str, 
                 params: Dict = None) -> WorkflowStep:
        """Add a step to a workflow"""
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")
        
        step_id = f"step_{len(workflow.steps) + 1}"
        step = WorkflowStep(
            id=step_id,
            type=step_type,
            name=name,
            params=params or {}
        )
        workflow.steps.append(step)
        self._save_workflow(workflow)
        return step
    
    def execute_workflow(self, workflow_id: str, context: Dict = None) -> Dict:
        """Execute a workflow"""
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")
        
        if not workflow.enabled:
            raise ValueError(f"Workflow {workflow.name} is disabled")
        
        # Initialize execution context
        execution_id = hashlib.md5(f"{workflow_id}_{time.time()}".encode()).hexdigest()[:8]
        execution_context = {
            'workflow_id': workflow_id,
            'workflow_name': workflow.name,
            'execution_id': execution_id,
            'started_at': datetime.now().isoformat(),
            'status': 'running',
            'steps': [],
            'context': context or {},
            'session_name': context.get('session_name') if context else None
        }
        
        self.running_workflows[execution_id] = execution_context
        
        console.print(f"\n[bold cyan]▶️ Executing Workflow: {workflow.name}[/bold cyan]")
        console.print(f"[dim]ID: {execution_id}[/dim]")
        console.print(f"[dim]Steps: {len(workflow.steps)}[/dim]\n")
        
        try:
            for i, step in enumerate(workflow.steps, 1):
                console.print(f"[bold]Step {i}/{len(workflow.steps)}: {step.name} ({step.type.value})[/bold]")
                
                step_result = self._execute_step(step, execution_context)
                execution_context['steps'].append({
                    'step_id': step.id,
                    'step_name': step.name,
                    'step_type': step.type.value,
                    'success': step_result['success'],
                    'result': step_result.get('result'),
                    'error': step_result.get('error'),
                    'duration': step_result.get('duration', 0)
                })
                
                if step_result['success']:
                    console.print(f"[green]✓ {step.name} completed[/green]")
                else:
                    console.print(f"[red]✗ {step.name} failed: {step_result.get('error', 'Unknown error')}[/red]")
                    # Check if should continue
                    if not step_result.get('continue_on_fail', False):
                        execution_context['status'] = 'failed'
                        break
                
                # Update context with results
                if step_result.get('result'):
                    execution_context['context'][step.id] = step_result['result']
        
        except Exception as e:
            console.print(f"[red]Workflow execution failed: {e}[/red]")
            execution_context['status'] = 'error'
            execution_context['error'] = str(e)
        
        finally:
            execution_context['completed_at'] = datetime.now().isoformat()
            if execution_context['status'] == 'running':
                execution_context['status'] = 'completed'
            
            # Calculate total duration
            start = datetime.fromisoformat(execution_context['started_at'])
            end = datetime.fromisoformat(execution_context['completed_at'])
            execution_context['duration'] = (end - start).total_seconds()
            
            self.execution_history.append(execution_context)
            
            # Save execution log
            self._save_execution_log(execution_context)
        
        return execution_context
    
    def _execute_step(self, step: WorkflowStep, context: Dict) -> Dict:
        """Execute a single step"""
        start_time = time.time()
        result = {
            'success': False,
            'duration': 0,
            'result': None,
            'error': None
        }
        
        try:
            # Check condition
            if step.condition and not self._evaluate_condition(step.condition, context):
                result['success'] = True
                result['result'] = {'skipped': True, 'reason': 'Condition not met'}
                return result
            
            # Execute based on type
            handler = {
                StepType.START_SESSION: self._handle_start_session,
                StepType.STOP_SESSION: self._handle_stop_session,
                StepType.NAVIGATE: self._handle_navigate,
                StepType.CLICK: self._handle_click,
                StepType.FILL: self._handle_fill,
                StepType.EXECUTE_SCRIPT: self._handle_execute_script,
                StepType.WAIT: self._handle_wait,
                StepType.EXTRACT_DATA: self._handle_extract_data,
                StepType.SCREENSHOT: self._handle_screenshot,
                StepType.WEBHOOK: self._handle_webhook,
                StepType.NOTIFY: self._handle_notify,
            }.get(step.type)
            
            if not handler:
                raise ValueError(f"Unknown step type: {step.type}")
            
            # Execute with retry
            for attempt in range(step.retry_count + 1):
                try:
                    result['result'] = handler(step, context)
                    result['success'] = True
                    break
                except Exception as e:
                    if attempt < step.retry_count:
                        console.print(f"[yellow]Retrying step {step.name} (attempt {attempt + 2}/{step.retry_count + 1})[/yellow]")
                        time.sleep(2 ** attempt)  # Exponential backoff
                    else:
                        raise e
        
        except Exception as e:
            result['error'] = str(e)
            result['success'] = False
        
        result['duration'] = time.time() - start_time
        return result
    
    def _evaluate_condition(self, condition: str, context: Dict) -> bool:
        """Evaluate a condition expression"""
        # Simple condition evaluation
        try:
            # Replace context variables
            for key, value in context.get('context', {}).items():
                condition = condition.replace(f"{{{{ {key} }}}}", str(value))
            
            # Evaluate using Python's eval (with safety)
            # In production, use a proper expression evaluator
            result = eval(condition, {"__builtins__": {}}, {})
            return bool(result)
        except:
            return False
    
    # ==========================================================================
    # Step Handlers
    # ==========================================================================
    
    def _handle_start_session(self, step: WorkflowStep, context: Dict) -> Dict:
        """Start a Chrome session"""
        params = step.params
        session_name = params.get('session_name', f"workflow_{context['execution_id']}")
        url = params.get('url', 'https://www.google.com')
        port = params.get('port', 9222)
        
        # Use Chrome launcher API
        response = self._api_call('POST', f'/session/{session_name}/start', {
            'url': url,
            'port': port
        })
        
        # Store session name in context
        context['context']['session_name'] = session_name
        context['session_name'] = session_name
        
        # Wait for session to be ready
        time.sleep(3)
        
        return {
            'session_name': session_name,
            'url': url,
            'port': port,
            'response': response
        }
    
    def _handle_stop_session(self, step: WorkflowStep, context: Dict) -> Dict:
        """Stop a Chrome session"""
        params = step.params
        session_name = params.get('session_name', context.get('session_name'))
        
        if not session_name:
            raise ValueError("Session name not found in context")
        
        response = self._api_call('POST', f'/session/{session_name}/stop')
        return response
    
    def _handle_navigate(self, step: WorkflowStep, context: Dict) -> Dict:
        """Navigate to a URL"""
        params = step.params
        session_name = params.get('session_name', context.get('session_name'))
        url = params.get('url')
        
        if not session_name or not url:
            raise ValueError("Session name and URL required")
        
        return self._api_call('POST', f'/session/{session_name}/navigate', {'url': url})
    
    def _handle_click(self, step: WorkflowStep, context: Dict) -> Dict:
        """Click an element"""
        params = step.params
        session_name = params.get('session_name', context.get('session_name'))
        selector = params.get('selector')
        
        if not session_name or not selector:
            raise ValueError("Session name and selector required")
        
        return self._api_call('POST', f'/session/{session_name}/click', {'selector': selector})
    
    def _handle_fill(self, step: WorkflowStep, context: Dict) -> Dict:
        """Fill an input field"""
        params = step.params
        session_name = params.get('session_name', context.get('session_name'))
        selector = params.get('selector')
        value = params.get('value')
        
        if not session_name or not selector or value is None:
            raise ValueError("Session name, selector, and value required")
        
        js = f"""
        document.querySelector('{selector}').value = '{value}';
        document.querySelector('{selector}').dispatchEvent(new Event('input', {{ bubbles: true }}));
        """
        
        return self._api_call('POST', f'/session/{session_name}/evaluate', {'expression': js})
    
    def _handle_execute_script(self, step: WorkflowStep, context: Dict) -> Dict:
        """Execute a JavaScript script from library"""
        params = step.params
        session_name = params.get('session_name', context.get('session_name'))
        script_id = params.get('script_id')
        
        if not session_name or not script_id:
            raise ValueError("Session name and script_id required")
        
        # Get script from library
        script = self.script_library.get_script(script_id)
        if not script:
            raise ValueError(f"Script '{script_id}' not found in library")
        
        # Execute script
        response = self._api_call('POST', f'/session/{session_name}/evaluate', {
            'expression': script['content']
        })
        
        return {
            'script_id': script_id,
            'script_name': script['name'],
            'result': response.get('result')
        }
    
    def _handle_wait(self, step: WorkflowStep, context: Dict) -> Dict:
        """Wait for a specified time"""
        params = step.params
        seconds = params.get('seconds', 5)
        time.sleep(seconds)
        return {'waited': seconds}
    
    def _handle_extract_data(self, step: WorkflowStep, context: Dict) -> Dict:
        """Extract data from page"""
        params = step.params
        session_name = params.get('session_name', context.get('session_name'))
        selector = params.get('selector')
        
        if not session_name or not selector:
            raise ValueError("Session name and selector required")
        
        js = f"""
        var elements = document.querySelectorAll('{selector}');
        var data = [];
        elements.forEach(function(el) {{
            data.push(el.textContent.trim());
        }});
        return data;
        """
        
        response = self._api_call('POST', f'/session/{session_name}/evaluate', {
            'expression': js
        })
        
        return {
            'selector': selector,
            'count': len(response.get('result', [])),
            'data': response.get('result', [])
        }
    
    def _handle_screenshot(self, step: WorkflowStep, context: Dict) -> Dict:
        """Take screenshot"""
        params = step.params
        session_name = params.get('session_name', context.get('session_name'))
        filename = params.get('filename', f"screenshot_{context['execution_id']}.png")
        
        if not session_name:
            raise ValueError("Session name required")
        
        response = self._api_call('GET', f'/session/{session_name}/screenshot')
        
        # Save screenshot
        if response.get('screenshot'):
            import base64
            file_path = Path(self.config.logs_dir) / filename
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'wb') as f:
                f.write(base64.b64decode(response['screenshot']))
            response['file_path'] = str(file_path)
        
        return response
    
    def _handle_webhook(self, step: WorkflowStep, context: Dict) -> Dict:
        """Send webhook"""
        params = step.params
        url = params.get('url')
        method = params.get('method', 'POST')
        data = params.get('data', {})
        
        if not url:
            raise ValueError("Webhook URL required")
        
        headers = params.get('headers', {'Content-Type': 'application/json'})
        
        response = requests.request(method, url, json=data, headers=headers, timeout=30)
        response.raise_for_status()
        
        return {
            'status_code': response.status_code,
            'response': response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text
        }
    
    def _handle_notify(self, step: WorkflowStep, context: Dict) -> Dict:
        """Send notification (console/email)"""
        params = step.params
        message = params.get('message', 'Workflow notification')
        level = params.get('level', 'info')
        
        # Simple console notification
        if level == 'info':
            console.print(f"[cyan]📢 {message}[/cyan]")
        elif level == 'success':
            console.print(f"[green]✅ {message}[/green]")
        elif level == 'warning':
            console.print(f"[yellow]⚠️ {message}[/yellow]")
        elif level == 'error':
            console.print(f"[red]❌ {message}[/red]")
        
        return {'message': message, 'level': level}
    
    def _api_call(self, method: str, endpoint: str, data: Dict = None) -> Dict:
        """Make API call to Chrome manager"""
        url = f"{self.api_base}{endpoint}"
        
        try:
            if method.upper() == 'GET':
                response = self.session.get(url, params=data)
            else:
                response = self.session.post(url, json=data)
            
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"API call failed: {e}")
    
    def _save_execution_log(self, execution_context: Dict):
        """Save execution log to file"""
        log_dir = Path(self.config.logs_dir) / "executions"
        log_dir.mkdir(parents=True, exist_ok=True)
        
        filename = f"{execution_context['execution_id']}.json"
        file_path = log_dir / filename
        
        with open(file_path, 'w') as f:
            json.dump(execution_context, f, indent=2)
    
    def get_execution_history(self, limit: int = 20) -> List[Dict]:
        """Get recent execution history"""
        return self.execution_history[-limit:]
    
    def get_workflow_status(self, workflow_id: str) -> Optional[Dict]:
        """Get status of a workflow"""
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            return None
        
        # Find recent executions
        recent_executions = [
            e for e in self.execution_history
            if e['workflow_id'] == workflow_id
        ][-5:]
        
        return {
            'workflow': workflow.to_dict(),
            'recent_executions': recent_executions,
            'total_executions': len([e for e in self.execution_history if e['workflow_id'] == workflow_id])
        }

# ============================================================================
# Interactive Workflow Builder
# ============================================================================

class WorkflowBuilder:
    """Interactive tool for building workflows"""
    
    def __init__(self, engine: WorkflowEngine):
        self.engine = engine
        self.current_workflow: Optional[Workflow] = None
    
    def build(self):
        """Start interactive build process"""
        console.print(Panel("[bold cyan]🧙 Workflow Builder Wizard[/bold cyan]", border_style="green"))
        
        # Step 1: Workflow info
        name = Prompt.ask("📝 Workflow name")
        if not name:
            console.print("[red]Name required[/red]")
            return
        
        description = Prompt.ask("📄 Description", default="")
        
        self.current_workflow = self.engine.create_workflow(name, description)
        console.print(f"[green]✅ Created workflow: {name}[/green]")
        
        # Step 1.a: Port configuration
        self._configure_port()
        
        # Step 2: Add steps
        self._build_steps()
        
        # Step 3: Schedule
        self._configure_schedule()
        
        # Step 4: Triggers
        self._configure_triggers()
        
        # Save and finalize
        self.engine._save_workflow(self.current_workflow)
        console.print(f"\n[bold green]✅ Workflow '{name}' complete![/bold green]")
        console.print(f"  ID: {self.current_workflow.id}")
        console.print(f"  Steps: {len(self.current_workflow.steps)}")
        console.print(f"  Schedule: {self.current_workflow.schedule or 'None'}")
        console.print(f"  Triggers: {len(self.current_workflow.triggers)} scripts can trigger this")
    
    def _configure_port(self):
        """Configure port for automation"""
        console.print("\n[bold cyan]🔌 Step 1.a: Port Configuration[/bold cyan]")
        
        # Get port as string first, then convert to int
        port_str = Prompt.ask("Port for automation", default="9222")
        try:
            port = int(port_str)
        except ValueError:
            console.print("[red]Invalid port number, using default 9222[/red]")
            port = 9222
        
        # Store port as int in params
        self.current_workflow.steps.append(WorkflowStep(
            id="config_port",
            type=StepType.WAIT,  # Just store config
            name="Port Configuration",
            params={"port": port}
        ))
        
        console.print(f"[green]Port {port} configured[/green]")
        
        # Print port details
        console.print(Panel(
            f"[bold]Port Details:[/bold]\n"
            f"  Port: {port}\n"
            f"  Debug URL: http://127.0.0.1:{port}\n"
            f"  Status: {'Available' if not self._check_port(port) else 'In use'}",
            title="📊 Port Information",
            border_style="blue"
        ))
    
    def _check_port(self, port: int) -> bool:
        """Check if port is in use"""
        import socket
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                return s.connect_ex(('127.0.0.1', port)) == 0
        except Exception:
            return False
    
    def _build_steps(self):
        """Build workflow steps interactively"""
        console.print("\n[bold cyan]Step 2: Add Steps to Workflow[/bold cyan]")
        
        while True:
            self._show_current_steps()
            
            console.print("\n[bold]Available Step Types:[/bold]")
            step_types = [
                ("1", "🚀 Start Session", "Start Chrome session"),
                ("2", "🛑 Stop Session", "Stop Chrome session"),
                ("3", "🧭 Navigate", "Navigate to URL"),
                ("4", "👆 Click", "Click an element"),
                ("5", "✏️ Fill", "Fill input field"),
                ("6", "📜 Execute Script", "Run JS script from library"),
                ("7", "⏳ Wait", "Wait for seconds"),
                ("8", "📊 Extract Data", "Extract data from page"),
                ("9", "📸 Screenshot", "Take screenshot"),
                ("10", "🔗 Webhook", "Send webhook"),
                ("11", "🔔 Notify", "Send notification"),
            ]
            
            for num, icon, desc in step_types:
                console.print(f"  {num}. {icon} {desc}")
            
            console.print("  0. Done adding steps")
            
            choice = Prompt.ask("Select step type", choices=["0","1","2","3","4","5","6","7","8","9","10","11"])
            
            if choice == "0":
                break
            
            self._add_step_interactive(int(choice))
    
    def _show_current_steps(self):
        """Show current steps in workflow"""
        if not self.current_workflow.steps:
            console.print("\n[dim]No steps added yet[/dim]")
            return
        
        table = Table(title=f"📋 Current Steps ({len(self.current_workflow.steps)})", box=box.ROUNDED)
        table.add_column("#", style="cyan", width=4)
        table.add_column("Type", style="green")
        table.add_column("Name", style="white")
        table.add_column("Params", style="dim")
        
        for i, step in enumerate(self.current_workflow.steps, 1):
            params_str = ", ".join([f"{k}={v}" for k, v in step.params.items()][:2])
            if len(step.params) > 2:
                params_str += "..."
            table.add_row(str(i), step.type.value, step.name, params_str)
        
        console.print(table)
    
    def _add_step_interactive(self, choice: int):
        """Add a step interactively based on choice"""
        step_type_map = {
            1: StepType.START_SESSION,
            2: StepType.STOP_SESSION,
            3: StepType.NAVIGATE,
            4: StepType.CLICK,
            5: StepType.FILL,
            6: StepType.EXECUTE_SCRIPT,
            7: StepType.WAIT,
            8: StepType.EXTRACT_DATA,
            9: StepType.SCREENSHOT,
            10: StepType.WEBHOOK,
            11: StepType.NOTIFY,
        }
        
        step_type = step_type_map.get(choice)
        if not step_type:
            return
        
        # Step name
        name = Prompt.ask("Step name", default=f"{step_type.value}_{len(self.current_workflow.steps) + 1}")
        
        # Collect params based on type
        params = {}
        
        if step_type == StepType.START_SESSION:
            params['session_name'] = Prompt.ask("Session name", default="workflow_session")
            params['url'] = Prompt.ask("Starting URL", default="https://www.google.com")
            params['port'] = int(Prompt.ask("Port", default="9222"))
        
        elif step_type == StepType.NAVIGATE:
            session_name = Prompt.ask("Session name", default="workflow_session")
            if session_name:
                params['session_name'] = session_name
            params['url'] = Prompt.ask("URL to navigate to")
        
        elif step_type in [StepType.CLICK, StepType.FILL]:
            session_name = Prompt.ask("Session name", default="workflow_session")
            if session_name:
                params['session_name'] = session_name
            params['selector'] = Prompt.ask("CSS Selector")
            if step_type == StepType.FILL:
                params['value'] = Prompt.ask("Value to fill")
        
        elif step_type == StepType.EXECUTE_SCRIPT:
            session_name = Prompt.ask("Session name", default="workflow_session")
            if session_name:
                params['session_name'] = session_name
            
            # Show available scripts
            console.print("\n[bold]Available Scripts:[/bold]")
            self.engine.script_library.display_scripts()
            
            script_id = Prompt.ask("Script ID or name to execute")
            # Try to find by ID or name
            script = self.engine.script_library.get_script(script_id)
            if not script:
                # Search by name
                for sid, s in self.engine.script_library.scripts.items():
                    if script_id.lower() in s['name'].lower():
                        script = s
                        script_id = sid
                        break
            
            if script:
                params['script_id'] = script_id
                console.print(f"[green]Selected: {script['name']}[/green]")
            else:
                console.print(f"[yellow]Script '{script_id}' not found. Will try to execute anyway.[/yellow]")
                params['script_id'] = script_id
        
        elif step_type == StepType.WAIT:
            params['seconds'] = int(Prompt.ask("Seconds to wait", default="5"))
        
        elif step_type == StepType.EXTRACT_DATA:
            session_name = Prompt.ask("Session name", default="workflow_session")
            if session_name:
                params['session_name'] = session_name
            params['selector'] = Prompt.ask("CSS Selector for data extraction")
        
        elif step_type == StepType.SCREENSHOT:
            session_name = Prompt.ask("Session name", default="workflow_session")
            if session_name:
                params['session_name'] = session_name
            params['filename'] = Prompt.ask("Filename", default="screenshot_{execution_id}.png")
        
        elif step_type == StepType.WEBHOOK:
            params['url'] = Prompt.ask("Webhook URL")
            params['method'] = Prompt.ask("Method", default="POST")
            params['data'] = {}
            if Confirm.ask("Add data payload?"):
                data_str = Prompt.ask("Data (JSON format)")
                try:
                    params['data'] = json.loads(data_str)
                except:
                    params['data'] = {"message": data_str}
        
        elif step_type == StepType.NOTIFY:
            params['message'] = Prompt.ask("Notification message")
            params['level'] = Prompt.ask("Level (info/success/warning/error)", default="info")
        
        # Add retry config
        retry_count = 0
        if Confirm.ask("Add retry configuration?"):
            retry_count = int(Prompt.ask("Retry count", default="1"))
        
        # Create and add step
        step = WorkflowStep(
            id=f"step_{len(self.current_workflow.steps) + 1}",
            type=step_type,
            name=name,
            params=params,
            retry_count=retry_count
        )
        
        self.current_workflow.steps.append(step)
        console.print(f"[green]✓ Step '{name}' added[/green]")
    
    def _configure_schedule(self):
        """Configure workflow schedule"""
        console.print("\n[bold cyan]Step 3: Schedule Configuration[/bold cyan]")
        
        if not Confirm.ask("Add schedule to this workflow?"):
            return
        
        console.print("\n[bold]Schedule Options:[/bold]")
        console.print("  1. Daily")
        console.print("  2. Weekly")
        console.print("  3. Monthly")
        console.print("  4. Custom Cron")
        
        choice = Prompt.ask("Select schedule type", choices=["1","2","3","4"])
        
        cron_expr = ""
        
        if choice == "1":  # Daily
            time_str = Prompt.ask("Time (HH:MM, e.g., 09:00)", default="09:00")
            hour, minute = time_str.split(':')
            cron_expr = f"{minute} {hour} * * *"
        
        elif choice == "2":  # Weekly
            days = ["0", "1", "2", "3", "4", "5", "6"]  # Sunday=0
            day_names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
            
            console.print("Day of week:")
            for i, name in enumerate(day_names):
                console.print(f"  {i}: {name}")
            
            day = Prompt.ask("Day number", default="0")
            time_str = Prompt.ask("Time (HH:MM)", default="09:00")
            hour, minute = time_str.split(':')
            cron_expr = f"{minute} {hour} * * {day}"
        
        elif choice == "3":  # Monthly
            day_of_month = Prompt.ask("Day of month (1-31)", default="1")
            time_str = Prompt.ask("Time (HH:MM)", default="09:00")
            hour, minute = time_str.split(':')
            cron_expr = f"{minute} {hour} {day_of_month} * *"
        
        else:  # Custom cron
            console.print("[dim]Cron format: minute hour day month day_of_week[/dim]")
            console.print("[dim]Example: '0 9 * * *' - daily at 9 AM[/dim]")
            cron_expr = Prompt.ask("Cron expression", default="0 9 * * *")
        
        self.current_workflow.schedule = cron_expr
        console.print(f"[green]Schedule set: {cron_expr}[/green]")
    
    def _configure_triggers(self):
        """Configure workflow triggers"""
        console.print("\n[bold cyan]Step 4: Trigger Configuration[/bold cyan]")
        
        console.print("[dim]Triggers are scripts that can start this workflow[/dim]")
        
        if not Confirm.ask("Add triggers (scripts that trigger this workflow)?"):
            return
        
        # Show available scripts
        console.print("\n[bold]Available Scripts:[/bold]")
        self.engine.script_library.display_scripts()
        
        while True:
            script_id = Prompt.ask("Script ID to add as trigger (or 'done' to finish)")
            if script_id.lower() == 'done':
                break
            
            # Find script
            script = self.engine.script_library.get_script(script_id)
            if not script:
                for sid, s in self.engine.script_library.scripts.items():
                    if script_id.lower() in s['name'].lower():
                        script = s
                        script_id = sid
                        break
            
            if script:
                self.current_workflow.triggers.append(script_id)
                console.print(f"[green]✓ Added trigger: {script['name']}[/green]")
            else:
                console.print(f"[yellow]Script '{script_id}' not found[/yellow]")
        
        # Scripts triggered by this workflow
        if Confirm.ask("Add scripts that this workflow should trigger?"):
            while True:
                script_id = Prompt.ask("Script ID to trigger (or 'done' to finish)")
                if script_id.lower() == 'done':
                    break
                
                script = self.engine.script_library.get_script(script_id)
                if not script:
                    for sid, s in self.engine.script_library.scripts.items():
                        if script_id.lower() in s['name'].lower():
                            script = s
                            script_id = sid
                            break
                
                if script:
                    self.current_workflow.triggered_scripts.append(script_id)
                    console.print(f"[green]✓ Added triggered script: {script['name']}[/green]")
                else:
                    console.print(f"[yellow]Script '{script_id}' not found[/yellow]")

# ============================================================================
# Workflow CLI - Main Interface
# ============================================================================

class WorkflowCLI:
    """Main CLI interface for workflow engine"""
    
    def __init__(self):
        self.config = WorkflowConfig()
        self.engine = WorkflowEngine(self.config)
        self.builder = WorkflowBuilder(self.engine)
    
    def run(self):
        """Main CLI loop"""
        while True:
            console.clear()
            console.print(Panel("[bold cyan]🚀 Workflow Template Engine[/bold cyan]", border_style="blue"))
            
            # Show workflows summary
            self._show_summary()
            
            menu = Table(show_header=False, box=box.MINIMAL_HEAVY_HEAD)
            menu.add_column("Option", style="cyan", width=8)
            menu.add_column("Action", style="white")
            menu.add_column("Description", style="dim")
            
            menu.add_row("1", "[green]Create Workflow[/green]", "Interactive workflow builder")
            menu.add_row("2", "[blue]Run Workflow[/blue]", "Execute a workflow")
            menu.add_row("3", "[cyan]Edit Workflow[/cyan]", "Edit existing workflow")
            menu.add_row("4", "[magenta]List Workflows[/magenta]", "Show all workflows")
            menu.add_row("5", "[yellow]Script Library[/yellow]", "Browse available scripts")
            menu.add_row("6", "[red]Delete Workflow[/red]", "Delete a workflow")
            menu.add_row("7", "[white]Execution History[/white]", "View workflow execution logs")
            menu.add_row("8", "[green]Schedule Status[/green]", "View scheduled workflows")
            menu.add_row("9", "[bold]Test Workflow[/bold]", "Test with debug mode")
            menu.add_row("0", "[red]Exit[/red]", "Exit")
            
            console.print(menu)
            console.print()
            
            choice = Prompt.ask("Select option", choices=["0","1","2","3","4","5","6","7","8","9"])
            
            if choice == "0":
                console.print("[green]Goodbye! 👋[/green]")
                break
            
            elif choice == "1":
                self.builder.build()
            
            elif choice == "2":
                self._run_workflow()
            
            elif choice == "3":
                self._edit_workflow()
            
            elif choice == "4":
                self._list_workflows()
            
            elif choice == "5":
                self._browse_scripts()
            
            elif choice == "6":
                self._delete_workflow()
            
            elif choice == "7":
                self._show_history()
            
            elif choice == "8":
                self._show_schedules()
            
            elif choice == "9":
                self._test_workflow()
            
            if choice != "0":
                console.print()
                Prompt.ask("Press Enter to continue...")
    
    def _show_summary(self):
        """Show summary of workflows"""
        if not self.engine.workflows:
            console.print("[dim]No workflows created yet. Use option 1 to create one.[/dim]")
            return
        
        table = Table(title=f"📋 Workflows ({len(self.engine.workflows)})", box=box.ROUNDED)
        table.add_column("Name", style="green")
        table.add_column("Description", style="dim")
        table.add_column("Steps", style="cyan", width=6)
        table.add_column("Schedule", style="yellow", width=12)
        table.add_column("Triggers", style="magenta", width=10)
        table.add_column("Status", style="white", width=8)
        
        for workflow in self.engine.workflows.values():
            status = "✅ Enabled" if workflow.enabled else "❌ Disabled"
            schedule = workflow.schedule or "None"
            if schedule != "None":
                schedule = schedule[:10] + "..." if len(schedule) > 10 else schedule
            
            trigger_count = len(workflow.triggers)
            
            table.add_row(
                workflow.name,
                workflow.description[:30] + "..." if len(workflow.description) > 30 else workflow.description,
                str(len(workflow.steps)),
                schedule,
                f"{trigger_count} triggers",
                status
            )
        
        console.print(table)
    
    def _run_workflow(self):
        """Run a workflow"""
        self._list_workflows(quiet=True)
        
        name = Prompt.ask("Enter workflow name or ID to run")
        if not name:
            return
        
        # Find workflow by name or ID
        workflow = None
        for w in self.engine.workflows.values():
            if w.name == name or w.id == name:
                workflow = w
                break
        
        if not workflow:
            console.print(f"[red]Workflow '{name}' not found[/red]")
            return
        
        # Optional: Add context
        context = {}
        if Confirm.ask("Add custom context data?"):
            context_str = Prompt.ask("Context (JSON format)")
            try:
                context = json.loads(context_str)
            except:
                console.print("[yellow]Invalid JSON, using empty context[/yellow]")
        
        # Execute
        result = self.engine.execute_workflow(workflow.id, context)
        
        # Show results
        console.print()
        console.print(Panel(
            f"[bold]Execution Results:[/bold]\n"
            f"  Status: {'✅ Success' if result['status'] == 'completed' else '❌ Failed'}\n"
            f"  Steps: {len(result['steps'])}\n"
            f"  Duration: {result.get('duration', 0):.2f}s\n"
            f"  ID: {result['execution_id']}\n"
            f"  Started: {result['started_at']}\n"
            f"  Completed: {result.get('completed_at', 'N/A')}",
            title="📊 Execution Results",
            border_style="green" if result['status'] == 'completed' else "red"
        ))
        
        # Show step details
        if result.get('steps'):
            step_table = Table(title="Step Results", box=box.SIMPLE)
            step_table.add_column("#", style="cyan", width=4)
            step_table.add_column("Step", style="white")
            step_table.add_column("Status", style="green")
            step_table.add_column("Result", style="dim")
            
            for i, step in enumerate(result['steps'], 1):
                status = "✅" if step['success'] else "❌"
                result_str = str(step.get('result', {}))[:50]
                step_table.add_row(str(i), step['step_name'], status, result_str)
            
            console.print(step_table)
    
    def _edit_workflow(self):
        """Edit an existing workflow"""
        self._list_workflows(quiet=True)
        
        name = Prompt.ask("Enter workflow name or ID to edit")
        if not name:
            return
        
        # Find workflow
        workflow = None
        for w in self.engine.workflows.values():
            if w.name == name or w.id == name:
                workflow = w
                break
        
        if not workflow:
            console.print(f"[red]Workflow '{name}' not found[/red]")
            return
        
        console.print(f"[cyan]Editing workflow: {workflow.name}[/cyan]")
        
        # Edit options
        console.print("\n[bold]What to edit?[/bold]")
        console.print("  1. Workflow properties (name, description)")
        console.print("  2. Steps")
        console.print("  3. Schedule")
        console.print("  4. Triggers")
        console.print("  5. Enable/Disable")
        
        choice = Prompt.ask("Select option", choices=["1","2","3","4","5"])
        
        if choice == "1":
            new_name = Prompt.ask("New name", default=workflow.name)
            new_desc = Prompt.ask("New description", default=workflow.description)
            workflow.name = new_name
            workflow.description = new_desc
            self.engine._save_workflow(workflow)
            console.print("[green]✅ Workflow properties updated[/green]")
        
        elif choice == "2":
            self._edit_steps(workflow)
        
        elif choice == "3":
            console.print(f"Current schedule: {workflow.schedule or 'None'}")
            if Confirm.ask("Remove schedule?"):
                workflow.schedule = None
            else:
                cron = Prompt.ask("New cron expression", default=workflow.schedule or "0 9 * * *")
                workflow.schedule = cron
            self.engine._save_workflow(workflow)
            console.print("[green]✅ Schedule updated[/green]")
        
        elif choice == "4":
            self._edit_triggers(workflow)
        
        elif choice == "5":
            workflow.enabled = not workflow.enabled
            self.engine._save_workflow(workflow)
            status = "enabled" if workflow.enabled else "disabled"
            console.print(f"[green]✅ Workflow {status}[/green]")
    
    def _edit_steps(self, workflow: Workflow):
        """Edit steps of a workflow"""
        while True:
            console.clear()
            console.print(Panel(f"[cyan]Editing Steps: {workflow.name}[/cyan]", border_style="blue"))
            
            # Show steps
            if workflow.steps:
                table = Table(title="Current Steps", box=box.ROUNDED)
                table.add_column("#", style="cyan", width=4)
                table.add_column("ID", style="dim", width=8)
                table.add_column("Type", style="green")
                table.add_column("Name", style="white")
                
                for i, step in enumerate(workflow.steps, 1):
                    table.add_row(str(i), step.id, step.type.value, step.name)
                console.print(table)
            
            console.print("\n[bold]Actions:[/bold]")
            console.print("  1. Add step")
            console.print("  2. Remove step")
            console.print("  3. Reorder steps")
            console.print("  4. Clear all steps")
            console.print("  0. Done")
            
            choice = Prompt.ask("Select action", choices=["0","1","2","3","4"])
            
            if choice == "0":
                break
            
            elif choice == "1":
                # Use builder to add step
                step_type = self._select_step_type()
                if step_type:
                    step_name = Prompt.ask("Step name", default=f"{step_type.value}_{len(workflow.steps) + 1}")
                    step_id = f"step_{len(workflow.steps) + 1}"
                    params = self._collect_step_params(step_type)
                    
                    step = WorkflowStep(
                        id=step_id,
                        type=step_type,
                        name=step_name,
                        params=params
                    )
                    workflow.steps.append(step)
                    self.engine._save_workflow(workflow)
                    console.print(f"[green]✓ Step '{step_name}' added[/green]")
            
            elif choice == "2":
                if not workflow.steps:
                    console.print("[yellow]No steps to remove[/yellow]")
                    continue
                idx = int(Prompt.ask("Step number to remove")) - 1
                if 0 <= idx < len(workflow.steps):
                    removed = workflow.steps.pop(idx)
                    self.engine._save_workflow(workflow)
                    console.print(f"[green]✓ Removed step: {removed.name}[/green]")
            
            elif choice == "3":
                if len(workflow.steps) < 2:
                    console.print("[yellow]Need at least 2 steps to reorder[/yellow]")
                    continue
                from_idx = int(Prompt.ask("From step number")) - 1
                to_idx = int(Prompt.ask("To step number")) - 1
                if 0 <= from_idx < len(workflow.steps) and 0 <= to_idx < len(workflow.steps):
                    step = workflow.steps.pop(from_idx)
                    workflow.steps.insert(to_idx, step)
                    self.engine._save_workflow(workflow)
                    console.print("[green]✓ Steps reordered[/green]")
            
            elif choice == "4":
                if Confirm.ask("Remove all steps?"):
                    workflow.steps = []
                    self.engine._save_workflow(workflow)
                    console.print("[green]✓ All steps cleared[/green]")
    
    def _select_step_type(self) -> Optional[StepType]:
        """Select a step type"""
        types = [
            ("1", StepType.START_SESSION, "Start Session"),
            ("2", StepType.STOP_SESSION, "Stop Session"),
            ("3", StepType.NAVIGATE, "Navigate"),
            ("4", StepType.CLICK, "Click"),
            ("5", StepType.FILL, "Fill"),
            ("6", StepType.EXECUTE_SCRIPT, "Execute Script"),
            ("7", StepType.WAIT, "Wait"),
            ("8", StepType.EXTRACT_DATA, "Extract Data"),
            ("9", StepType.SCREENSHOT, "Screenshot"),
            ("10", StepType.WEBHOOK, "Webhook"),
            ("11", StepType.NOTIFY, "Notify"),
        ]
        
        for num, _, name in types:
            console.print(f"  {num}. {name}")
        
        choice = Prompt.ask("Select type", choices=[t[0] for t in types])
        
        for num, step_type, _ in types:
            if num == choice:
                return step_type
        return None
    
    def _collect_step_params(self, step_type: StepType) -> Dict:
        """Collect parameters for a step type"""
        params = {}
        
        if step_type == StepType.START_SESSION:
            params['session_name'] = Prompt.ask("Session name", default="workflow_session")
            params['url'] = Prompt.ask("Starting URL", default="https://www.google.com")
            params['port'] = int(Prompt.ask("Port", default="9222"))
        
        elif step_type == StepType.NAVIGATE:
            params['url'] = Prompt.ask("URL to navigate to")
        
        elif step_type in [StepType.CLICK, StepType.FILL]:
            params['selector'] = Prompt.ask("CSS Selector")
            if step_type == StepType.FILL:
                params['value'] = Prompt.ask("Value to fill")
        
        elif step_type == StepType.EXECUTE_SCRIPT:
            params['script_id'] = Prompt.ask("Script ID")
        
        elif step_type == StepType.WAIT:
            params['seconds'] = int(Prompt.ask("Seconds to wait", default="5"))
        
        elif step_type == StepType.EXTRACT_DATA:
            params['selector'] = Prompt.ask("CSS Selector for data extraction")
        
        elif step_type == StepType.SCREENSHOT:
            params['filename'] = Prompt.ask("Filename", default="screenshot_{timestamp}.png")
        
        elif step_type == StepType.WEBHOOK:
            params['url'] = Prompt.ask("Webhook URL")
            params['method'] = Prompt.ask("Method", default="POST")
        
        elif step_type == StepType.NOTIFY:
            params['message'] = Prompt.ask("Notification message")
            params['level'] = Prompt.ask("Level (info/success/warning/error)", default="info")
        
        return params
    
    def _edit_triggers(self, workflow: Workflow):
        """Edit workflow triggers"""
        console.print(f"Current triggers: {workflow.triggers}")
        console.print(f"Triggered scripts: {workflow.triggered_scripts}")
        
        if Confirm.ask("Add trigger (script that starts this workflow)?"):
            self.engine.script_library.display_scripts()
            script_id = Prompt.ask("Script ID to add as trigger")
            if script_id:
                workflow.triggers.append(script_id)
                console.print(f"[green]✓ Trigger added: {script_id}[/green]")
        
        if Confirm.ask("Add triggered script (script this workflow starts)?"):
            self.engine.script_library.display_scripts()
            script_id = Prompt.ask("Script ID to trigger")
            if script_id:
                workflow.triggered_scripts.append(script_id)
                console.print(f"[green]✓ Triggered script added: {script_id}[/green]")
        
        self.engine._save_workflow(workflow)
    
    def _list_workflows(self, quiet: bool = False):
        """List all workflows"""
        if not quiet:
            console.print("\n[bold]📋 Workflows:[/bold]")
        
        if not self.engine.workflows:
            console.print("[dim]No workflows created[/dim]")
            return
        
        table = Table(title="Workflows", box=box.ROUNDED, show_header=True if not quiet else False)
        table.add_column("ID", style="dim", width=12)
        table.add_column("Name", style="green")
        table.add_column("Description", style="dim")
        table.add_column("Steps", style="cyan", width=6)
        table.add_column("Schedule", style="yellow", width=12)
        table.add_column("Status", style="white", width=8)
        
        for workflow in self.engine.workflows.values():
            status = "✅" if workflow.enabled else "❌"
            schedule = workflow.schedule or "None"
            if schedule != "None":
                schedule = schedule[:10] + "..." if len(schedule) > 10 else schedule
            
            table.add_row(
                workflow.id,
                workflow.name,
                workflow.description[:20] + "..." if len(workflow.description) > 20 else workflow.description,
                str(len(workflow.steps)),
                schedule,
                status
            )
        
        console.print(table)
    
    def _browse_scripts(self):
        """Browse script library"""
        console.print("\n[bold]📚 Script Library[/bold]")
        self.engine.script_library.display_scripts()
        
        if Confirm.ask("\nSearch scripts?"):
            query = Prompt.ask("Search term")
            results = self.engine.script_library.search_scripts(query)
            
            if results:
                table = Table(title=f"Search Results: '{query}'", box=box.ROUNDED)
                table.add_column("ID", style="dim")
                table.add_column("Name", style="green")
                table.add_column("Description", style="dim")
                table.add_column("Category", style="cyan")
                
                for script in results:
                    table.add_row(
                        script['id'],
                        script['name'],
                        script.get('description', '')[:30],
                        script.get('category', '')
                    )
                console.print(table)
            else:
                console.print("[yellow]No results found[/yellow]")
    
    def _delete_workflow(self):
        """Delete a workflow"""
        self._list_workflows(quiet=True)
        
        name = Prompt.ask("Enter workflow name or ID to delete")
        if not name:
            return
        
        # Find workflow
        workflow = None
        workflow_id = None
        for w in self.engine.workflows.values():
            if w.name == name or w.id == name:
                workflow = w
                workflow_id = w.id
                break
        
        if not workflow:
            console.print(f"[red]Workflow '{name}' not found[/red]")
            return
        
        if Confirm.ask(f"Delete workflow '{workflow.name}'?"):
            # Remove from engine
            del self.engine.workflows[workflow_id]
            
            # Remove file
            file_path = Path(self.config.workflows_dir) / f"{workflow_id}.yaml"
            if file_path.exists():
                file_path.unlink()
            
            console.print(f"[green]✅ Deleted workflow: {workflow.name}[/green]")
    
    def _show_history(self):
        """Show execution history"""
        history = self.engine.get_execution_history(limit=20)
        
        if not history:
            console.print("[dim]No execution history[/dim]")
            return
        
        table = Table(title="📊 Execution History", box=box.ROUNDED)
        table.add_column("ID", style="dim", width=8)
        table.add_column("Workflow", style="green")
        table.add_column("Status", style="white", width=10)
        table.add_column("Steps", style="cyan", width=6)
        table.add_column("Started", style="dim")
        
        for entry in history:
            status_color = "green" if entry['status'] == 'completed' else "red"
            table.add_row(
                entry['execution_id'][:8],
                entry['workflow_name'],
                f"[{status_color}]{entry['status']}[/{status_color}]",
                str(len(entry.get('steps', []))),
                entry['started_at'][:16]
            )
        
        console.print(table)
        
        # Option to view details
        if Confirm.ask("View execution details?"):
            exec_id = Prompt.ask("Execution ID")
            for entry in history:
                if entry['execution_id'] == exec_id:
                    console.print(Panel(
                        json.dumps(entry, indent=2),
                        title=f"Execution Details: {exec_id}",
                        border_style="blue"
                    ))
                    break
            else:
                console.print(f"[red]Execution '{exec_id}' not found[/red]")
    
    def _show_schedules(self):
        """Show scheduled workflows"""
        scheduled = [w for w in self.engine.workflows.values() if w.schedule and w.enabled]
        
        if not scheduled:
            console.print("[dim]No scheduled workflows[/dim]")
            return
        
        table = Table(title="⏰ Scheduled Workflows", box=box.ROUNDED)
        table.add_column("Workflow", style="green")
        table.add_column("Schedule (Cron)", style="yellow")
        table.add_column("Steps", style="cyan")
        table.add_column("Triggers", style="magenta")
        
        for workflow in scheduled:
            trigger_names = []
            for trigger_id in workflow.triggers:
                script = self.engine.script_library.get_script(trigger_id)
                if script:
                    trigger_names.append(script['name'])
                else:
                    trigger_names.append(trigger_id)
            
            table.add_row(
                workflow.name,
                workflow.schedule,
                str(len(workflow.steps)),
                ", ".join(trigger_names[:3]) + ("..." if len(trigger_names) > 3 else "")
            )
        
        console.print(table)
    
    def _test_workflow(self):
        """Test a workflow with debug mode"""
        self._list_workflows(quiet=True)
        
        name = Prompt.ask("Enter workflow name or ID to test")
        if not name:
            return
        
        # Find workflow
        workflow = None
        for w in self.engine.workflows.values():
            if w.name == name or w.id == name:
                workflow = w
                break
        
        if not workflow:
            console.print(f"[red]Workflow '{name}' not found[/red]")
            return
        
        console.print(f"\n[bold cyan]🧪 Testing Workflow: {workflow.name}[/bold cyan]")
        console.print("[dim]Debug mode - Step by step execution with details[/dim]\n")
        
        # Simulate execution without actually running
        for i, step in enumerate(workflow.steps, 1):
            console.print(f"\n[bold]Step {i}/{len(workflow.steps)}: {step.name}[/bold]")
            console.print(f"  Type: {step.type.value}")
            console.print(f"  Params: {json.dumps(step.params, indent=2)}")
            
            if step.condition:
                console.print(f"  Condition: {step.condition}")
            
            # Simulate result
            if Confirm.ask(f"  Simulate success for this step?", default=True):
                console.print("  [green]✓ Simulated success[/green]")
            else:
                console.print("  [red]✗ Simulated failure[/red]")
                if not Confirm.ask("  Continue to next step?", default=False):
                    break
        
        console.print("\n[bold]Test Summary:[/bold]")
        console.print(f"  Workflow: {workflow.name}")
        console.print(f"  Total steps: {len(workflow.steps)}")
        console.print(f"  Schedule: {workflow.schedule or 'None'}")
        console.print(f"  Triggers: {len(workflow.triggers)}")
        console.print(f"  Triggered scripts: {len(workflow.triggered_scripts)}")

# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Main entry point"""
    try:
        cli = WorkflowCLI()
        cli.run()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
