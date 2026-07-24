# workflow_light.py - Lightweight Chrome Automation Workflow Engine
#!/usr/bin/env python3
"""
Chrome Automation Workflow Engine using NetworkX
Lightweight version - no matplotlib
Features:
- DAG-based workflow execution
- Parallel task execution
- Conditional branching
- Text-based visualization
- YAML persistence
"""

import asyncio
import json
import logging
import time
import re
from datetime import datetime
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import networkx as nx
import yaml
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich import box
from rich.tree import Tree
from rich.markdown import Markdown

from client import ChromeClient
from cdpv119 import ChromeSessionManager

console = Console()
logger = logging.getLogger(__name__)

# ============================================================================
# Task Definitions
# ============================================================================

class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRY = "retry"

class TaskType(Enum):
    # Chrome operations
    START_SESSION = "start_session"
    STOP_SESSION = "stop_session"
    NAVIGATE = "navigate"
    CLICK = "click"
    FILL_FORM = "fill_form"
    EXTRACT_HTML = "extract_html"
    EXTRACT_TEXT = "extract_text"
    SCREENSHOT = "screenshot"
    EVALUATE = "evaluate"
    WAIT = "wait"
    WAIT_FOR_ELEMENT = "wait_for_element"
    
    # Flow control
    CONDITION = "condition"
    PARALLEL = "parallel"
    LOOP = "loop"
    
    # Data operations
    EXTRACT_JSON = "extract_json"
    SAVE_DATA = "save_data"
    SEND_NOTIFICATION = "send_notification"

@dataclass
class TaskResult:
    task_id: str
    status: TaskStatus
    data: Any = None
    error: str = None
    start_time: float = None
    end_time: float = None
    duration: float = None

# ============================================================================
# Workflow Classes (same as before, but with text visualization)
# ============================================================================

class WorkflowNode:
    def __init__(self, 
                 task_id: str,
                 task_type: TaskType,
                 params: Dict[str, Any] = None,
                 label: str = None,
                 retry_count: int = 3,
                 timeout: int = 60,
                 condition: str = None):
        self.task_id = task_id
        self.task_type = task_type
        self.params = params or {}
        self.label = label or task_id
        self.retry_count = retry_count
        self.timeout = timeout
        self.condition = condition
        self.status = TaskStatus.PENDING
        self.result = None
        self.dependencies = []
        self.children = []

class Workflow:
    def __init__(self, 
                 name: str,
                 description: str = "",
                 version: str = "1.0"):
        self.name = name
        self.description = description
        self.version = version
        self.graph = nx.DiGraph()
        self.nodes: Dict[str, WorkflowNode] = {}
        self.entry_points = []
        self.exit_points = []
        self.context = {}
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self.execution_id = None
        
    def add_node(self, node: WorkflowNode):
        self.graph.add_node(node.task_id, node=node)
        self.nodes[node.task_id] = node
        
    def add_edge(self, from_id: str, to_id: str, condition: str = None):
        if from_id not in self.nodes or to_id not in self.nodes:
            raise ValueError(f"Node not found: {from_id} or {to_id}")
        self.graph.add_edge(from_id, to_id, condition=condition)
        self.nodes[to_id].dependencies.append(from_id)
        
    def validate(self) -> bool:
        try:
            cycles = list(nx.simple_cycles(self.graph))
            if cycles:
                console.print(f"[red]❌ Workflow has cycles: {cycles}[/red]")
                return False
        except nx.NetworkXNoCycle:
            pass
            
        isolated = list(nx.isolates(self.graph))
        if isolated:
            console.print(f"[yellow]⚠️ Isolated nodes: {isolated}[/yellow]")
            
        return True
        
    def get_topological_order(self) -> List[str]:
        if not self.entry_points:
            self.entry_points = [n for n in self.nodes if not self.graph.in_degree(n)]
        return list(nx.topological_sort(self.graph))
    
    def get_parallel_groups(self) -> List[List[str]]:
        topo = self.get_topological_order()
        groups = []
        processed = set()
        
        for node in topo:
            if node in processed:
                continue
            deps = set(nx.ancestors(self.graph, node))
            group = [node]
            for other in topo:
                if other == node or other in processed:
                    continue
                other_deps = set(nx.ancestors(self.graph, other))
                if other_deps == deps:
                    group.append(other)
            processed.update(group)
            groups.append(group)
            
        return groups

    def visualize_text(self) -> str:
        """Generate text-based visualization of the workflow"""
        lines = []
        lines.append(f"📊 [bold cyan]{self.name}[/bold cyan]")
        lines.append(f"   {self.description}")
        lines.append("")
        
        # Show node status
        lines.append("[bold]Nodes:[/bold]")
        for node_id, node in self.nodes.items():
            status_icon = {
                TaskStatus.COMPLETED: "✅",
                TaskStatus.FAILED: "❌",
                TaskStatus.RUNNING: "🔄",
                TaskStatus.PENDING: "⏳",
                TaskStatus.SKIPPED: "⏭️",
                TaskStatus.RETRY: "🔁"
            }.get(node.status, "❓")
            
            deps = ", ".join(node.dependencies) if node.dependencies else "none"
            lines.append(f"  {status_icon} [cyan]{node_id}[/cyan] ({node.task_type.value})")
            lines.append(f"     → depends on: {deps}")
            if node.result and node.result.data:
                lines.append(f"     → data: {str(node.result.data)[:50]}")
            if node.result and node.result.error:
                lines.append(f"     → [red]error: {node.result.error[:50]}[/red]")
        
        return "\n".join(lines)

# ============================================================================
# Task Executor (same as before, simplified)
# ============================================================================

class TaskExecutor:
    def __init__(self, client: ChromeClient = None):
        self.client = client or ChromeClient()
        self.session_manager = ChromeSessionManager()
        
    async def execute(self, node: WorkflowNode, context: Dict) -> TaskResult:
        task_type = node.task_type
        params = node.params
        
        if node.condition:
            if not self._evaluate_condition(node.condition, context):
                return TaskResult(
                    task_id=node.task_id,
                    status=TaskStatus.SKIPPED,
                    error="Condition not met"
                )
        
        handlers = {
            TaskType.START_SESSION: self._start_session,
            TaskType.STOP_SESSION: self._stop_session,
            TaskType.NAVIGATE: self._navigate,
            TaskType.CLICK: self._click,
            TaskType.FILL_FORM: self._fill_form,
            TaskType.EXTRACT_HTML: self._extract_html,
            TaskType.EXTRACT_TEXT: self._extract_text,
            TaskType.SCREENSHOT: self._screenshot,
            TaskType.EVALUATE: self._evaluate,
            TaskType.WAIT: self._wait,
            TaskType.WAIT_FOR_ELEMENT: self._wait_for_element,
            TaskType.CONDITION: self._condition,
            TaskType.EXTRACT_JSON: self._extract_json,
            TaskType.SAVE_DATA: self._save_data,
            TaskType.SEND_NOTIFICATION: self._send_notification,
        }
        
        handler = handlers.get(task_type)
        if not handler:
            return TaskResult(
                task_id=node.task_id,
                status=TaskStatus.FAILED,
                error=f"Unknown task type: {task_type}"
            )
            
        start_time = time.time()
        
        for attempt in range(node.retry_count + 1):
            try:
                result = await handler(params, context)
                if result.get('success', False) or 'error' not in result:
                    return TaskResult(
                        task_id=node.task_id,
                        status=TaskStatus.COMPLETED,
                        data=result.get('data'),
                        start_time=start_time,
                        end_time=time.time(),
                        duration=time.time() - start_time
                    )
                else:
                    error_msg = result.get('error', 'Unknown error')
                    if attempt < node.retry_count:
                        await asyncio.sleep(2 ** attempt)
                    else:
                        return TaskResult(
                            task_id=node.task_id,
                            status=TaskStatus.FAILED,
                            error=error_msg,
                            start_time=start_time,
                            end_time=time.time(),
                            duration=time.time() - start_time
                        )
            except Exception as e:
                if attempt < node.retry_count:
                    await asyncio.sleep(2 ** attempt)
                else:
                    return TaskResult(
                        task_id=node.task_id,
                        status=TaskStatus.FAILED,
                        error=str(e),
                        start_time=start_time,
                        end_time=time.time(),
                        duration=time.time() - start_time
                    )
                    
        return TaskResult(
            task_id=node.task_id,
            status=TaskStatus.FAILED,
            error="Max retries exceeded",
            start_time=start_time,
            end_time=time.time(),
            duration=time.time() - start_time
        )
    
    # Task handlers (same as before)
    async def _start_session(self, params: Dict, context: Dict) -> Dict:
        session_name = params.get('session_name', 'unstop')
        url = params.get('url', 'https://unstop.com/')
        result = await self.client.start_session(session_name, url)
        context['session'] = session_name
        return result
    
    async def _stop_session(self, params: Dict, context: Dict) -> Dict:
        session_name = params.get('session_name', context.get('session', 'unstop'))
        return await self.client.stop_session(session_name)
    
    async def _navigate(self, params: Dict, context: Dict) -> Dict:
        url = params.get('url')
        session_name = params.get('session_name', context.get('session', 'unstop'))
        if not url:
            return {'error': 'URL required'}
        return await self.client.navigate(url, session_name)
    
    async def _click(self, params: Dict, context: Dict) -> Dict:
        selector = params.get('selector')
        session_name = params.get('session_name', context.get('session', 'unstop'))
        if not selector:
            return {'error': 'Selector required'}
        return await self.client.click(selector, session_name)
    
    async def _fill_form(self, params: Dict, context: Dict) -> Dict:
        fields = params.get('fields', {})
        session_name = params.get('session_name', context.get('session', 'unstop'))
        results = []
        for selector, value in fields.items():
            await self.client.click(selector, session_name)
            js = f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (el) {{
                    el.value = '';
                    el.value = '{value}';
                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    return true;
                }}
                return false;
            }})()
            """
            result = await self.client.evaluate(js, session_name)
            results.append(result)
        return {'success': True, 'results': results}
    
    async def _extract_html(self, params: Dict, context: Dict) -> Dict:
        session_name = params.get('session_name', context.get('session', 'unstop'))
        return await self.client.get_html(session_name)
    
    async def _extract_text(self, params: Dict, context: Dict) -> Dict:
        selector = params.get('selector')
        session_name = params.get('session_name', context.get('session', 'unstop'))
        if selector:
            js = f"""
            (function() {{
                const el = document.querySelector('{selector}');
                return el ? el.textContent.trim() : null;
            }})()
            """
            result = await self.client.evaluate(js, session_name)
            if 'result' in result and 'result' in result['result']:
                return {'data': result['result']['result']['value']}
            return {'error': 'Failed to extract text'}
        return await self.client.evaluate("document.body.innerText", session_name)
    
    async def _screenshot(self, params: Dict, context: Dict) -> Dict:
        session_name = params.get('session_name', context.get('session', 'unstop'))
        return await self.client.screenshot(session_name)
    
    async def _evaluate(self, params: Dict, context: Dict) -> Dict:
        expression = params.get('expression')
        session_name = params.get('session_name', context.get('session', 'unstop'))
        if not expression:
            return {'error': 'Expression required'}
        return await self.client.evaluate(expression, session_name)
    
    async def _wait(self, params: Dict, context: Dict) -> Dict:
        seconds = params.get('seconds', 5)
        await asyncio.sleep(seconds)
        return {'success': True, 'waited': seconds}
    
    async def _wait_for_element(self, params: Dict, context: Dict) -> Dict:
        selector = params.get('selector')
        timeout = params.get('timeout', 10)
        session_name = params.get('session_name', context.get('session', 'unstop'))
        if not selector:
            return {'error': 'Selector required'}
        result = await self.client.wait_for_element(selector, timeout)
        return {'found': result, 'selector': selector}
    
    async def _condition(self, params: Dict, context: Dict) -> Dict:
        expression = params.get('expression')
        if not expression:
            return {'error': 'Condition expression required'}
        try:
            result = eval(expression, {}, context)
            return {'result': result}
        except Exception as e:
            return {'error': f'Condition evaluation failed: {e}'}
    
    async def _extract_json(self, params: Dict, context: Dict) -> Dict:
        session_name = params.get('session_name', context.get('session', 'unstop'))
        expression = params.get('expression', 'document.body.textContent')
        result = await self.client.evaluate(f"JSON.parse({expression})", session_name)
        if 'result' in result and 'result' in result['result']:
            return {'data': result['result']['result']['value']}
        return {'error': 'Failed to extract JSON'}
    
    async def _save_data(self, params: Dict, context: Dict) -> Dict:
        data = params.get('data')
        filepath = params.get('filepath')
        if not filepath:
            return {'error': 'Filepath required'}
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(filepath, 'w') as f:
                json.dump(data or context, f, indent=2, default=str)
            return {'success': True, 'filepath': filepath}
        except Exception as e:
            return {'error': f'Failed to save: {e}'}
    
    async def _send_notification(self, params: Dict, context: Dict) -> Dict:
        message = params.get('message', 'Workflow completed')
        level = params.get('level', 'info')
        if level == 'error':
            console.print(f"[red]🔴 {message}[/red]")
        elif level == 'warning':
            console.print(f"[yellow]🟡 {message}[/yellow]")
        elif level == 'success':
            console.print(f"[green]✅ {message}[/green]")
        else:
            console.print(f"[blue]🔔 {message}[/blue]")
        return {'success': True, 'message': message, 'level': level}
    
    def _evaluate_condition(self, condition: str, context: Dict) -> bool:
        try:
            return eval(condition, {}, context)
        except Exception:
            return False

# ============================================================================
# Workflow Engine
# ============================================================================

class WorkflowEngine:
    def __init__(self, session_name: str = "unstop"):
        self.client = ChromeClient(session_name=session_name)
        self.executor = TaskExecutor(self.client)
        self.results: Dict[str, TaskResult] = {}
        self._workflow_dir = Path.home() / "workflows"
        self._workflow_dir.mkdir(exist_ok=True)
        
    async def execute(self, workflow: Workflow) -> Dict[str, TaskResult]:
        console.print(f"[bold cyan]🚀 Starting workflow: {workflow.name}[/bold cyan]")
        console.print(f"[dim]Description: {workflow.description}[/dim]")
        console.print(f"[dim]Nodes: {len(workflow.nodes)}[/dim]")
        
        if not workflow.validate():
            console.print("[red]❌ Workflow validation failed[/red]")
            return {}
        
        order = workflow.get_topological_order()
        parallel_groups = workflow.get_parallel_groups()
        
        results = {}
        workflow.execution_id = f"exec_{int(time.time())}"
        workflow.context['execution_id'] = workflow.execution_id
        
        for group in parallel_groups:
            console.print(f"[cyan]▶️ Executing group: {group}[/cyan]")
            tasks = []
            for node_id in group:
                node = workflow.nodes[node_id]
                if node.dependencies:
                    dep_done = all(results.get(dep, {}).status == TaskStatus.COMPLETED 
                                  for dep in node.dependencies)
                    if not dep_done:
                        console.print(f"[yellow]⚠️ Dependencies not done for {node_id}, skipping[/yellow]")
                        continue
                task = asyncio.create_task(
                    self.executor.execute(node, workflow.context)
                )
                tasks.append((node_id, task))
            
            for node_id, task in tasks:
                result = await task
                results[node_id] = result
                workflow.nodes[node_id].result = result
                workflow.nodes[node_id].status = result.status
                if result.status == TaskStatus.COMPLETED:
                    console.print(f"[green]✅ {node_id}: {result.status.value}[/green]")
                    if result.data:
                        workflow.context[node_id] = result.data
                else:
                    console.print(f"[red]❌ {node_id}: {result.status.value} - {result.error}[/red]")
                    if workflow.nodes[node_id].params.get('critical', False):
                        console.print("[red]Critical task failed, stopping workflow[/red]")
                        self.results = results
                        return results
        
        self.results = results
        
        # Show summary
        completed = sum(1 for r in results.values() if r.status == TaskStatus.COMPLETED)
        failed = sum(1 for r in results.values() if r.status == TaskStatus.FAILED)
        skipped = sum(1 for r in results.values() if r.status == TaskStatus.SKIPPED)
        
        console.print()
        console.print(Panel(
            f"[bold]Workflow Complete: {workflow.name}[/bold]\n"
            f"  ✅ Completed: {completed}\n"
            f"  ❌ Failed: {failed}\n"
            f"  ⏭️ Skipped: {skipped}\n"
            f"  📊 Total: {len(results)}",
            border_style="green" if failed == 0 else "red"
        ))
        
        # Show text visualization
        console.print()
        console.print(workflow.visualize_text())
        
        return results
    
    def save_workflow(self, workflow: Workflow, path: str = None):
        if not path:
            path = self._workflow_dir / f"{workflow.name}.yaml"
        
        data = {
            'name': workflow.name,
            'description': workflow.description,
            'version': workflow.version,
            'nodes': {nid: node.to_dict() for nid, node in workflow.nodes.items()},
            'edges': [{'from': u, 'to': v, 'condition': d.get('condition')} 
                     for u, v, d in workflow.graph.edges(data=True)],
            'entry_points': workflow.entry_points
        }
        
        with open(path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False)
        
        console.print(f"[green]✅ Workflow saved to {path}[/green]")
        
    def load_workflow(self, path: str) -> Workflow:
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
        
        workflow = Workflow(
            name=data['name'],
            description=data.get('description', ''),
            version=data.get('version', '1.0')
        )
        
        for node_id, node_data in data['nodes'].items():
            node = WorkflowNode(
                task_id=node_id,
                task_type=TaskType(node_data['type']),
                params=node_data.get('params', {}),
                label=node_data.get('label', node_id),
                retry_count=node_data.get('retry_count', 3),
                timeout=node_data.get('timeout', 60),
                condition=node_data.get('condition')
            )
            workflow.add_node(node)
        
        for edge in data.get('edges', []):
            workflow.add_edge(edge['from'], edge['to'], edge.get('condition'))
        
        workflow.entry_points = data.get('entry_points', [])
        return workflow

# ============================================================================
# Pre-built Templates
# ============================================================================

class WorkflowTemplates:
    @staticmethod
    def unstop_job_search() -> Workflow:
        workflow = Workflow("unstop_job_search", "Search and extract job listings from Unstop")
        
        nodes = [
            WorkflowNode("start_session", TaskType.START_SESSION, 
                        {'session_name': 'unstop', 'url': 'https://unstop.com/'},
                        "Start Chrome", retry_count=2),
            WorkflowNode("navigate_jobs", TaskType.NAVIGATE,
                        {'url': 'https://unstop.com/job/'},
                        "Navigate to Jobs", retry_count=2),
            WorkflowNode("wait_jobs_load", TaskType.WAIT_FOR_ELEMENT,
                        {'selector': '[class*="job"]', 'timeout': 15},
                        "Wait for Jobs", retry_count=2),
            WorkflowNode("extract_jobs", TaskType.EXTRACT_HTML,
                        {'selector': 'body'},
                        "Extract Job Data", retry_count=2),
            WorkflowNode("save_jobs", TaskType.SAVE_DATA,
                        {'filepath': 'data/jobs_{timestamp}.json'},
                        "Save Job Data", retry_count=1),
            WorkflowNode("send_notification", TaskType.SEND_NOTIFICATION,
                        {'message': '✅ Job extraction completed!', 'level': 'success'},
                        "Notify", retry_count=1),
            WorkflowNode("take_screenshot", TaskType.SCREENSHOT,
                        {},
                        "Screenshot", retry_count=1),
        ]
        
        for node in nodes:
            workflow.add_node(node)
        
        workflow.add_edge("start_session", "navigate_jobs")
        workflow.add_edge("navigate_jobs", "wait_jobs_load")
        workflow.add_edge("wait_jobs_load", "extract_jobs")
        workflow.add_edge("extract_jobs", "save_jobs")
        workflow.add_edge("extract_jobs", "take_screenshot")
        workflow.add_edge("save_jobs", "send_notification")
        workflow.add_edge("take_screenshot", "send_notification")
        
        return workflow
    
    @staticmethod
    def whatsapp_message() -> Workflow:
        workflow = Workflow("whatsapp_message", "Send a WhatsApp message via web")
        
        nodes = [
            WorkflowNode("start_session", TaskType.START_SESSION,
                        {'session_name': 'whatsapp', 'url': 'https://web.whatsapp.com/'},
                        "Start WhatsApp", retry_count=2),
            WorkflowNode("wait_qr", TaskType.WAIT_FOR_ELEMENT,
                        {'selector': 'canvas[aria-label*="QR code"]', 'timeout': 30},
                        "Wait for QR Code", retry_count=2),
            WorkflowNode("send_notification", TaskType.SEND_NOTIFICATION,
                        {'message': '📱 Please scan QR code to login', 'level': 'info'},
                        "Notify QR", retry_count=1),
            WorkflowNode("wait_chat", TaskType.WAIT_FOR_ELEMENT,
                        {'selector': '[data-testid="conversation-panel"]', 'timeout': 60},
                        "Wait for Chat", retry_count=2),
            WorkflowNode("send_message", TaskType.EVALUATE,
                        {'expression': """
                            (function() {
                                const input = document.querySelector('[data-testid="compose-box"]');
                                if (input) {
                                    const message = 'Hello from Chrome Automation!';
                                    input.value = message;
                                    input.dispatchEvent(new Event('input', {bubbles: true}));
                                    const sendBtn = document.querySelector('[data-testid="compose-btn-send"]');
                                    if (sendBtn) sendBtn.click();
                                    return 'Message sent: ' + message;
                                }
                                return 'Failed to send message';
                            })()
                        """},
                        "Send Message", retry_count=2),
            WorkflowNode("take_screenshot", TaskType.SCREENSHOT,
                        {},
                        "Screenshot", retry_count=1),
        ]
        
        for node in nodes:
            workflow.add_node(node)
        
        workflow.add_edge("start_session", "wait_qr")
        workflow.add_edge("wait_qr", "send_notification")
        workflow.add_edge("send_notification", "wait_chat")
        workflow.add_edge("wait_chat", "send_message")
        workflow.add_edge("send_message", "take_screenshot")
        
        return workflow
    
    @staticmethod
    def data_extraction_pipeline() -> Workflow:
        workflow = Workflow("data_extraction_pipeline", "Extract multiple data types in parallel")
        
        nodes = [
            WorkflowNode("start_session", TaskType.START_SESSION,
                        {'session_name': 'unstop', 'url': 'https://unstop.com/'},
                        "Start Chrome", retry_count=2),
            WorkflowNode("navigate_target", TaskType.NAVIGATE,
                        {'url': 'https://unstop.com/job/'},
                        "Navigate to Target", retry_count=2),
            WorkflowNode("extract_title", TaskType.EVALUATE,
                        {'expression': 'document.title'},
                        "Extract Title", retry_count=2),
            WorkflowNode("extract_job_count", TaskType.EVALUATE,
                        {'expression': 'document.querySelectorAll("[class*=\'job\']").length'},
                        "Extract Job Count", retry_count=2),
            WorkflowNode("extract_all_text", TaskType.EXTRACT_TEXT,
                        {},
                        "Extract All Text", retry_count=2),
            WorkflowNode("take_screenshot", TaskType.SCREENSHOT,
                        {},
                        "Take Screenshot", retry_count=2),
            WorkflowNode("save_results", TaskType.SAVE_DATA,
                        {'filepath': 'data/extraction_{timestamp}.json'},
                        "Save Results", retry_count=2),
            WorkflowNode("send_notification", TaskType.SEND_NOTIFICATION,
                        {'message': '✅ Data extraction completed!', 'level': 'success'},
                        "Notify", retry_count=1),
        ]
        
        for node in nodes:
            workflow.add_node(node)
        
        workflow.add_edge("start_session", "navigate_target")
        workflow.add_edge("navigate_target", "extract_title")
        workflow.add_edge("navigate_target", "extract_job_count")
        workflow.add_edge("navigate_target", "extract_all_text")
        workflow.add_edge("navigate_target", "take_screenshot")
        workflow.add_edge("extract_title", "save_results")
        workflow.add_edge("extract_job_count", "save_results")
        workflow.add_edge("extract_all_text", "save_results")
        workflow.add_edge("take_screenshot", "save_results")
        workflow.add_edge("save_results", "send_notification")
        
        return workflow

# ============================================================================
# Interactive CLI
# ============================================================================

class WorkflowCLI:
    def __init__(self):
        self.engine = WorkflowEngine()
        self.templates = WorkflowTemplates()
        
    def main_menu(self):
        while True:
            console.clear()
            console.print(Panel(
                "[bold cyan]🔄 Chrome Automation Workflow Engine[/bold cyan]\n"
                "[dim]NetworkX DAG - Text Visualization - No matplotlib[/dim]",
                border_style="blue"
            ))
            
            menu = Table(title="Workflow Actions", box=box.ROUNDED)
            menu.add_column("Option", style="cyan", width=8)
            menu.add_column("Action", style="green")
            menu.add_column("Description", style="dim")
            
            menu.add_row("1", "Run Template", "Run a pre-built workflow template")
            menu.add_row("2", "Create Workflow", "Create a custom workflow")
            menu.add_row("3", "Load Workflow", "Load workflow from file")
            menu.add_row("4", "Visualize Text", "Show text-based workflow graph")
            menu.add_row("5", "List Workflows", "Show saved workflows")
            menu.add_row("6", "Results", "Show last execution results")
            menu.add_row("0", "Exit", "Exit the workflow manager")
            
            console.print(menu)
            console.print()
            
            choice = Prompt.ask("Select option", choices=["0","1","2","3","4","5","6"])
            
            if choice == "0":
                console.print("[green]Goodbye! 👋[/green]")
                break
            elif choice == "1":
                self.run_template_menu()
            elif choice == "2":
                self.create_workflow_menu()
            elif choice == "3":
                self.load_workflow_menu()
            elif choice == "4":
                self.visualize_text_menu()
            elif choice == "5":
                self.list_workflows()
            elif choice == "6":
                self.show_results()
                
            if choice != "0":
                console.print()
                Prompt.ask("Press Enter to continue...")
    
    def run_template_menu(self):
        console.clear()
        console.print(Panel("[bold green]📋 Workflow Templates[/bold green]", border_style="green"))
        
        templates = [
            ("1", "unstop_job_search", "Extract job listings from Unstop"),
            ("2", "whatsapp_message", "Send WhatsApp message"),
            ("3", "data_extraction_pipeline", "Parallel data extraction"),
        ]
        
        for key, name, desc in templates:
            console.print(f"[cyan]{key}[/cyan]) [bold]{name}[/bold] - {desc}")
        
        choice = Prompt.ask("Select template", choices=["1","2","3"])
        
        if choice == "1":
            workflow = self.templates.unstop_job_search()
        elif choice == "2":
            workflow = self.templates.whatsapp_message()
        else:
            workflow = self.templates.data_extraction_pipeline()
        
        console.print(f"\n[bold]Workflow: {workflow.name}[/bold]")
        console.print(f"[dim]{workflow.description}[/dim]")
        console.print(f"Nodes: {len(workflow.nodes)}")
        
        # Show text visualization
        console.print("\n[bold cyan]Workflow Structure:[/bold cyan]")
        console.print(workflow.visualize_text())
        
        if Confirm.ask("\nRun this workflow?"):
            asyncio.run(self.engine.execute(workflow))
            
        if Confirm.ask("Save this workflow?"):
            self.engine.save_workflow(workflow)
    
    def create_workflow_menu(self):
        console.clear()
        console.print(Panel("[bold green]🛠️ Create Custom Workflow[/bold green]", border_style="green"))
        
        name = Prompt.ask("Workflow name")
        description = Prompt.ask("Description", default="")
        
        workflow = Workflow(name, description)
        
        while True:
            console.print("\n[bold]Add Node:[/bold]")
            task_id = Prompt.ask("Node ID")
            
            console.print("\n[bold]Task Types:[/bold]")
            types = list(TaskType)
            for i, t in enumerate(types, 1):
                console.print(f"  {i:2}. {t.value}")
            
            type_choice = int(Prompt.ask("Select task type (number)", default="1"))
            task_type = types[type_choice - 1] if 1 <= type_choice <= len(types) else TaskType.WAIT
            
            params = {}
            console.print("[dim]Enter parameters (key=value, empty to finish)[/dim]")
            while True:
                param = Prompt.ask("Parameter", default="")
                if not param:
                    break
                if '=' in param:
                    key, value = param.split('=', 1)
                    params[key.strip()] = value.strip()
            
            node = WorkflowNode(
                task_id=task_id,
                task_type=task_type,
                params=params,
                label=Prompt.ask("Label", default=task_id)
            )
            workflow.add_node(node)
            
            if len(workflow.nodes) > 1:
                deps = Prompt.ask("Dependencies (comma-separated IDs)", default="")
                if deps:
                    for dep in deps.split(','):
                        dep = dep.strip()
                        if dep in workflow.nodes:
                            workflow.add_edge(dep, task_id)
            
            if not Confirm.ask("Add another node?"):
                break
        
        console.print("\n[bold cyan]Workflow Structure:[/bold cyan]")
        console.print(workflow.visualize_text())
        
        if Confirm.ask("Save this workflow?"):
            self.engine.save_workflow(workflow)
        
        if Confirm.ask("Run this workflow?"):
            asyncio.run(self.engine.execute(workflow))
    
    def load_workflow_menu(self):
        workflows = list(self.engine._workflow_dir.glob("*.yaml"))
        if not workflows:
            console.print("[yellow]No workflows found[/yellow]")
            return
        
        console.print("\n[bold]Saved Workflows:[/bold]")
        for i, wf in enumerate(workflows, 1):
            console.print(f"  {i:2}. {wf.stem}")
        
        choice = int(Prompt.ask("Select workflow (number)")) - 1
        if 0 <= choice < len(workflows):
            workflow = self.engine.load_workflow(workflows[choice])
            console.print(f"[green]✅ Loaded: {workflow.name}[/green]")
            console.print(workflow.visualize_text())
            if Confirm.ask("Run this workflow?"):
                asyncio.run(self.engine.execute(workflow))
    
    def visualize_text_menu(self):
        workflows = list(self.engine._workflow_dir.glob("*.yaml"))
        if not workflows:
            console.print("[yellow]No workflows found[/yellow]")
            return
        
        console.print("\n[bold]Saved Workflows:[/bold]")
        for i, wf in enumerate(workflows, 1):
            console.print(f"  {i:2}. {wf.stem}")
        
        choice = int(Prompt.ask("Select workflow (number)")) - 1
        if 0 <= choice < len(workflows):
            workflow = self.engine.load_workflow(workflows[choice])
            console.print("\n[bold cyan]Workflow Visualization:[/bold cyan]")
            console.print(workflow.visualize_text())
    
    def list_workflows(self):
        workflows = list(self.engine._workflow_dir.glob("*.yaml"))
        if not workflows:
            console.print("[yellow]No saved workflows[/yellow]")
            return
        
        table = Table(title="Saved Workflows", box=box.ROUNDED)
        table.add_column("#", style="cyan", width=4)
        table.add_column("Name", style="green")
        table.add_column("Size", style="yellow", width=10)
        table.add_column("Modified", style="dim")
        
        for i, wf in enumerate(workflows, 1):
            size = wf.stat().st_size / 1024
            modified = datetime.fromtimestamp(wf.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            table.add_row(str(i), wf.stem, f"{size:.1f} KB", modified)
        
        console.print(table)
    
    def show_results(self):
        if not self.engine.results:
            console.print("[yellow]No results from previous execution[/yellow]")
            return
        
        table = Table(title="Execution Results", box=box.ROUNDED)
        table.add_column("Task", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Duration", style="yellow", width=12)
        table.add_column("Data/Error", style="dim")
        
        for task_id, result in self.engine.results.items():
            status_color = "green" if result.status == TaskStatus.COMPLETED else "red"
            duration = f"{result.duration:.2f}s" if result.duration else "N/A"
            data = str(result.data)[:50] if result.data else ""
            if result.error:
                data = f"[red]{result.error[:50]}[/red]"
            
            table.add_row(
                task_id,
                f"[{status_color}]{result.status.value}[/{status_color}]",
                duration,
                data
            )
        
        console.print(table)

# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    try:
        cli = WorkflowCLI()
        cli.main_menu()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
