"""Main planner - orchestrates tasks"""
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from .task import Task, TaskStatus, TaskPriority
from .plan import Plan, PlanStatus
from .registry import get_registry
from .context import Context
from .events import EventBus, Event, get_event_bus
from .scheduler import Scheduler

class Planner:
    """Orchestrates task execution"""
    
    def __init__(self):
        self.registry = get_registry()
        self.event_bus = get_event_bus()
        self.scheduler = Scheduler(self)
        self.plans: Dict[str, Plan] = {}
        self.tasks: Dict[str, Task] = {}
        self.contexts: Dict[str, Context] = {}
        self._running = False
    
    def create_plan(self, goal: str, description: str = "") -> Plan:
        """Create a new plan"""
        plan = Plan(goal=goal, description=description)
        self.plans[plan.id] = plan
        self.contexts[plan.id] = Context(goal=goal)
        
        # Publish event
        self.event_bus.publish(Event(
            type="plan.created",
            source="planner",
            payload={"plan_id": plan.id, "goal": goal}
        ))
        
        return plan
    
    def add_task(self, plan_id: str, task: Task) -> None:
        """Add a task to a plan"""
        if plan_id not in self.plans:
            raise ValueError(f"Plan {plan_id} not found")
        
        plan = self.plans[plan_id]
        self.tasks[task.id] = task
        plan.tasks.append(task.id)
        
        # Publish event
        self.event_bus.publish(Event(
            type="task.created",
            source="planner",
            payload={"plan_id": plan_id, "task_id": task.id, "action": task.action}
        ))
    
    def build_dag(self, plan_id: str) -> None:
        """Build dependency graph for a plan"""
        if plan_id not in self.plans:
            return
        
        plan = self.plans[plan_id]
        dependencies = {}
        
        for task_id in plan.tasks:
            task = self.tasks[task_id]
            deps = []
            for dep_id in task.dependencies:
                if dep_id in self.tasks:
                    deps.append(dep_id)
            dependencies[task_id] = deps
        
        plan.dependencies = dependencies
        
        # Publish event
        self.event_bus.publish(Event(
            type="plan.ready",
            source="planner",
            payload={"plan_id": plan_id, "task_count": len(plan.tasks)}
        ))
    
    def start(self) -> None:
        """Start the planner"""
        self._running = True
        self.event_bus.publish(Event(
            type="planner.started",
            source="planner",
            payload={}
        ))
        self.scheduler.start()
    
    def stop(self) -> None:
        """Stop the planner"""
        self._running = False
        self.scheduler.stop()
        self.event_bus.publish(Event(
            type="planner.stopped",
            source="planner",
            payload={}
        ))
    
    def get_status(self) -> dict:
        """Get planner status"""
        try:
            scheduler_status = self.scheduler.get_status()
        except Exception as e:
            scheduler_status = {"error": str(e), "running": False}
        
        return {
            "running": self._running,
            "plans": len(self.plans),
            "tasks": len(self.tasks),
            "scheduler": scheduler_status,
            "agents": self.registry.list_agents()
        }
    
    def get_plan(self, plan_id: str) -> Optional[dict]:
        """Get plan details"""
        plan = self.plans.get(plan_id)
        if not plan:
            return None
        
        tasks = []
        for task_id in plan.tasks:
            task = self.tasks.get(task_id)
            if task:
                tasks.append(task.to_dict())
        
        result = plan.to_dict()
        result["tasks"] = tasks
        return result
    
    def get_task(self, task_id: str) -> Optional[dict]:
        """Get task details"""
        task = self.tasks.get(task_id)
        if task:
            return task.to_dict()
        return None
    
    def get_context(self, plan_id: str) -> Optional[Context]:
        """Get context for a plan"""
        return self.contexts.get(plan_id)
    
    def update_task_status(self, task_id: str, status: TaskStatus, result: Any = None, error: str = None):
        """Update task status"""
        task = self.tasks.get(task_id)
        if not task:
            return
        
        old_status = task.status
        task.status = status
        
        if status == TaskStatus.RUNNING:
            task.started_at = datetime.now()
        elif status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
            task.completed_at = datetime.now()
            if result is not None:
                task.result = result
            if error:
                task.error = error
        
        # Update plan progress
        for plan_id, plan in self.plans.items():
            if task_id in plan.tasks:
                completed = sum(1 for t in plan.tasks 
                              if self.tasks.get(t) and self.tasks[t].status == TaskStatus.COMPLETED)
                plan.progress = completed / len(plan.tasks) if plan.tasks else 0.0
                
                if plan.progress >= 1.0:
                    plan.status = PlanStatus.COMPLETED
                    plan.completed_at = datetime.now()
                elif any(self.tasks.get(t) and self.tasks[t].status == TaskStatus.FAILED 
                        for t in plan.tasks):
                    plan.status = PlanStatus.FAILED
        
        # Publish event
        self.event_bus.publish(Event(
            type=f"task.{status.value}",
            source="planner",
            payload={
                "task_id": task_id,
                "action": task.action,
                "result": str(result)[:200] if result else None,
                "error": error
            }
        ))
