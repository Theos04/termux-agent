"""Task scheduler - determines when tasks run"""
import time
import threading
from typing import Dict, Optional, List
from datetime import datetime
from .task import Task, TaskStatus
from .executor import Executor
from .events import get_event_bus, Event

class Scheduler:
    """Schedules tasks for execution"""
    
    def __init__(self, planner):
        self.planner = planner
        self.executor = Executor(planner)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._interval = 5  # seconds
    
    def start(self) -> None:
        """Start the scheduler loop"""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._schedule_loop, daemon=True)
        self._thread.start()
        
        get_event_bus().publish(Event(
            type="scheduler.started",
            source="scheduler",
            payload={"interval": self._interval}
        ))
    
    def stop(self) -> None:
        """Stop the scheduler"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        get_event_bus().publish(Event(
            type="scheduler.stopped",
            source="scheduler",
            payload={}
        ))
    
    def _schedule_loop(self) -> None:
        """Main scheduling loop"""
        while self._running:
            try:
                self._schedule_once()
                time.sleep(self._interval)
            except Exception as e:
                print(f"Scheduler error: {e}")
    
    def _schedule_once(self) -> None:
        """Single scheduling iteration"""
        with self._lock:
            # Find all pending plans
            for plan_id, plan in self.planner.plans.items():
                if plan.status.value not in ["pending", "running"]:
                    continue
                
                # Find tasks that are ready to run
                ready_tasks = self._get_ready_tasks(plan_id)
                if ready_tasks:
                    # Submit ready tasks
                    for task in ready_tasks:
                        self.executor.submit(task)
    
    def _get_ready_tasks(self, plan_id: str) -> List[Task]:
        """Get tasks that are ready to run"""
        ready = []
        
        for task_id in self.planner.plans[plan_id].tasks:
            task = self.planner.tasks.get(task_id)
            if not task:
                continue
            
            if task.status != TaskStatus.PENDING:
                continue
            
            # Check dependencies
            deps_complete = True
            for dep_id in task.dependencies:
                dep = self.planner.tasks.get(dep_id)
                if not dep or dep.status != TaskStatus.COMPLETED:
                    deps_complete = False
                    break
            
            if deps_complete:
                ready.append(task)
        
        return ready
    
    def get_status(self) -> dict:
        """Get scheduler status"""
        with self._lock:
            return {
                "running": self._running,
                "interval": self._interval,
                "queued": len(self.executor._queue),
                "processing": len(self.executor._processing)
            }
