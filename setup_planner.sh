#!/bin/bash
# Complete planner setup script

echo "🚀 Setting up Automation Planner..."

# Create directory structure
mkdir -p planner/{agents,storage,templates}
mkdir -p scraped_data

# Create __init__.py files
touch planner/__init__.py
touch planner/agents/__init__.py
touch planner/storage/__init__.py

# Create all the planner files in one go
cat > planner/config.py << 'INNEREOF'
"""Configuration for the planner system"""
import os
from dataclasses import dataclass
from typing import Optional

@dataclass
class Config:
    # Core settings
    planner_name: str = "Chrome Automation Planner"
    debug: bool = False
    max_workers: int = 4
    default_timeout: int = 300
    
    # Storage
    storage_dir: str = "planner/storage"
    plans_db: str = "planner/storage/plans.db"
    memory_db: str = "planner/storage/memory.db"
    logs_db: str = "planner/storage/logs.db"
    
    # Chrome
    chrome_port: int = 9226
    default_url: str = "https://unstop.com/"
    
    # LLM (for future)
    llm_model: Optional[str] = None
    llm_api_key: Optional[str] = None
    
    # Scheduler
    scheduler_interval: int = 5  # seconds
    
    @classmethod
    def from_env(cls):
        return cls(
            debug=os.getenv("DEBUG", "false").lower() == "true",
            max_workers=int(os.getenv("MAX_WORKERS", "4")),
            chrome_port=int(os.getenv("CHROME_PORT", "9226")),
            llm_model=os.getenv("LLM_MODEL"),
            llm_api_key=os.getenv("OPENAI_API_KEY")
        )
INNEREOF

cat > planner/task.py << 'INNEREOF'
"""Task model"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum
import uuid

class TaskStatus(Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"

class TaskPriority(Enum):
    HIGH = 1
    MEDIUM = 2
    LOW = 3

@dataclass
class Task:
    """A unit of work for the planner"""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    action: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    priority: TaskPriority = TaskPriority.MEDIUM
    status: TaskStatus = TaskStatus.PENDING
    dependencies: List[str] = field(default_factory=list)
    assigned_agent: Optional[str] = None
    retries: int = 0
    max_retries: int = 3
    timeout: int = 300
    result: Optional[Any] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "action": self.action,
            "parameters": self.parameters,
            "priority": self.priority.value,
            "status": self.status.value,
            "dependencies": self.dependencies,
            "assigned_agent": self.assigned_agent,
            "retries": self.retries,
            "max_retries": self.max_retries,
            "timeout": self.timeout,
            "result": str(self.result)[:500] if self.result else None,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "metadata": self.metadata
        }
INNEREOF

cat > planner/plan.py << 'INNEREOF'
"""Plan model - collection of tasks"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
import uuid
from enum import Enum

class PlanStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class Plan:
    """A plan consisting of multiple tasks"""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    goal: str = ""
    description: str = ""
    status: PlanStatus = PlanStatus.PENDING
    tasks: List[str] = field(default_factory=list)
    dependencies: Dict[str, List[str]] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    progress: float = 0.0
    priority: int = 1
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "goal": self.goal,
            "description": self.description,
            "status": self.status.value,
            "tasks": self.tasks,
            "dependencies": self.dependencies,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "metadata": self.metadata,
            "progress": self.progress,
            "priority": self.priority
        }
INNEREOF

cat > planner/context.py << 'INNEREOF'
"""Shared execution context"""
from typing import Dict, Any, Optional
from dataclasses import dataclass, field

@dataclass
class Context:
    """Shared context passed to all tasks"""
    goal: str = ""
    conversation: list = field(default_factory=list)
    variables: Dict[str, Any] = field(default_factory=dict)
    memory: Dict[str, Any] = field(default_factory=dict)
    working_directory: str = "."
    browser_session: Optional[str] = None
    environment: Dict[str, str] = field(default_factory=dict)
    temp_files: list = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def get(self, key: str, default=None):
        if key in self.variables:
            return self.variables[key]
        if key in self.memory:
            return self.memory[key]
        if key in self.metadata:
            return self.metadata[key]
        return default
    
    def set(self, key: str, value: Any) -> None:
        self.variables[key] = value
    
    def remember(self, key: str, value: Any) -> None:
        self.memory[key] = value
    
    def to_dict(self) -> dict:
        return {
            "goal": self.goal,
            "variables": self.variables,
            "memory": self.memory,
            "working_directory": self.working_directory,
            "browser_session": self.browser_session
        }
INNEREOF

cat > planner/events.py << 'INNEREOF'
"""Event bus for inter-component communication"""
from typing import Dict, List, Any, Callable, Optional
from datetime import datetime
from dataclasses import dataclass, field
import uuid

@dataclass
class Event:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    type: str = ""
    source: str = ""
    payload: Any = None
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "source": self.source,
            "payload": str(self.payload)[:200] if self.payload else None,
            "timestamp": self.timestamp.isoformat()
        }

class EventBus:
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._events: List[Event] = []
        self._max_events = 1000
    
    def subscribe(self, event_type: str, callback: Callable) -> None:
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)
    
    def publish(self, event: Event) -> None:
        self._events.append(event)
        if len(self._events) > self._max_events:
            self._events = self._events[-self._max_events:]
        
        if event.type in self._subscribers:
            for callback in self._subscribers[event.type]:
                try:
                    callback(event)
                except Exception as e:
                    print(f"Error in subscriber: {e}")
    
    def get_events(self, event_type: Optional[str] = None, limit: int = 100) -> List[Event]:
        if event_type:
            return [e for e in self._events[-limit:] if e.type == event_type]
        return self._events[-limit:]

_event_bus = EventBus()
def get_event_bus() -> EventBus:
    return _event_bus
INNEREOF

cat > planner/agents/base.py << 'INNEREOF'
"""Base agent interface"""
from abc import ABC, abstractmethod
from typing import List, Any
from ..task import Task
from ..context import Context

class Agent(ABC):
    @abstractmethod
    def capabilities(self) -> List[str]:
        pass
    
    @abstractmethod
    def execute(self, task: Task, context: Context) -> Any:
        pass
    
    @abstractmethod
    def can_execute(self, action: str) -> bool:
        pass
    
    def name(self) -> str:
        return self.__class__.__name__.replace("Agent", "").lower()
    
    def health_check(self) -> bool:
        return True
INNEREOF

cat > planner/registry.py << 'INNEREOF'
"""Agent registry"""
from typing import Dict, List, Optional
from .agents.base import Agent

class AgentRegistry:
    def __init__(self):
        self._agents: List[Agent] = []
        self._capability_map: Dict[str, List[Agent]] = {}
    
    def register(self, agent: Agent) -> None:
        self._agents.append(agent)
        for capability in agent.capabilities():
            if capability not in self._capability_map:
                self._capability_map[capability] = []
            self._capability_map[capability].append(agent)
    
    def get_agent(self, capability: str) -> Optional[Agent]:
        agents = self._capability_map.get(capability, [])
        return agents[0] if agents else None
    
    def list_capabilities(self) -> Dict[str, List[str]]:
        return {
            capability: [agent.name() for agent in agents]
            for capability, agents in self._capability_map.items()
        }
    
    def list_agents(self) -> List[dict]:
        return [
            {
                "name": agent.name(),
                "capabilities": agent.capabilities(),
                "healthy": agent.health_check()
            }
            for agent in self._agents
        ]

_registry = AgentRegistry()
def get_registry() -> AgentRegistry:
    return _registry
INNEREOF

cat > planner/agents/browser.py << 'INNEREOF'
"""Browser agent for Chrome automation"""
import asyncio
import time
import base64
from typing import List, Any, Optional
from .base import Agent
from ..task import Task
from ..context import Context

class BrowserAgent(Agent):
    def __init__(self, daemon=None):
        self.daemon = daemon
        self._session = None
    
    def capabilities(self) -> List[str]:
        return [
            "browser.navigate",
            "browser.extract",
            "browser.click",
            "browser.fill",
            "browser.screenshot",
            "browser.execute_js",
            "browser.get_html",
            "browser.get_text",
            "browser.wait_for"
        ]
    
    def can_execute(self, action: str) -> bool:
        return action in self.capabilities()
    
    def execute(self, task: Task, context: Context) -> Any:
        action = task.action
        params = task.parameters
        
        session_name = params.get("session", "unstop")
        self._ensure_session(session_name, context)
        
        if action == "browser.navigate":
            return self._navigate(params.get("url"), params.get("wait", 5))
        elif action == "browser.extract":
            return self._extract(params.get("selector"), params.get("multiple", False))
        elif action == "browser.click":
            return self._click(params.get("selector"))
        elif action == "browser.fill":
            return self._fill(params.get("selector"), params.get("value"))
        elif action == "browser.screenshot":
            return self._screenshot(params.get("path"))
        elif action == "browser.execute_js":
            return self._execute_js(params.get("script"), params.get("await_promise", False))
        elif action == "browser.get_html":
            return self._get_html()
        elif action == "browser.get_text":
            return self._get_text()
        elif action == "browser.wait_for":
            return self._wait_for(params.get("selector"), params.get("timeout", 30))
        else:
            raise ValueError(f"Unknown action: {action}")
    
    def _ensure_session(self, name: str, context: Context):
        if self.daemon:
            session = self.daemon.get_session(name)
            if not session:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                url = context.get("browser_url", "https://unstop.com/")
                result = loop.run_until_complete(
                    self.daemon.start_session(name, url)
                )
                if not result.get("success"):
                    raise RuntimeError(f"Failed to start session: {result}")
            self._session = name
    
    def _navigate(self, url: str, wait: int = 5):
        if not self.daemon:
            return {"success": False, "error": "No daemon available"}
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(
            self.daemon.navigate(self._session, url)
        )
        time.sleep(wait)
        return result
    
    def _extract(self, selector: str, multiple: bool = False):
        if multiple:
            script = f"""
            const els = document.querySelectorAll('{selector}');
            return Array.from(els).map(el => el.innerText || el.textContent || '');
            """
        else:
            script = f"""
            const el = document.querySelector('{selector}');
            if (!el) return null;
            return el.innerText || el.textContent || '';
            """
        return self._execute_js(script)
    
    def _click(self, selector: str):
        script = f"""
        const el = document.querySelector('{selector}');
        if (!el) {{ return {{success: false, error: 'Element not found'}}; }}
        el.click();
        return {{success: true}};
        """
        return self._execute_js(script)
    
    def _fill(self, selector: str, value: str):
        script = f"""
        const el = document.querySelector('{selector}');
        if (!el) {{ return {{success: false, error: 'Element not found'}}; }}
        el.value = '{value}';
        el.dispatchEvent(new Event('input', {{bubbles: true}}));
        return {{success: true}};
        """
        return self._execute_js(script)
    
    def _screenshot(self, path: Optional[str] = None):
        if not self.daemon:
            return {"success": False, "error": "No daemon available"}
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(
            self.daemon.screenshot(self._session)
        )
        if path and result.get("screenshot"):
            with open(path, "wb") as f:
                f.write(base64.b64decode(result["screenshot"]))
            result["file"] = path
        return result
    
    def _execute_js(self, script: str, await_promise: bool = False):
        if not self.daemon:
            return {"success": False, "error": "No daemon available"}
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(
            self.daemon.evaluate(self._session, script)
        )
    
    def _get_html(self):
        return self._execute_js("document.documentElement.outerHTML")
    
    def _get_text(self):
        return self._execute_js("document.body.innerText")
    
    def _wait_for(self, selector: str, timeout: int = 30):
        start = time.time()
        while time.time() - start < timeout:
            result = self._execute_js(f"document.querySelector('{selector}')")
            if result and not result.get("error"):
                return {"success": True, "found": True}
            time.sleep(1)
        return {"success": False, "found": False, "timeout": True}
INNEREOF

echo "✅ All planner files created!"
echo ""
echo "Now run: python -m planner.app"
