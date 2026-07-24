"""Executor - dispatches tasks to agents"""
import threading
import time
from typing import Dict, List, Optional
from queue import Queue
from .task import Task, TaskStatus
from .registry import get_registry
from .events import get_event_bus, Event

class Executor:
    """Executes tasks using appropriate agents"""
    
    def __init__(self, planner):
        self.planner = planner
        self.registry = get_registry()
        self.event_bus = get_event_bus()
        self._queue: Queue = Queue()
        self._processing: Dict[str, threading.Thread] = {}
        self._lock = threading.Lock()
        self._running = True
        self._workers = 4
        
        # Start workers
        for i in range(self._workers):
            thread = threading.Thread(target=self._worker_loop, args=(i,), daemon=True)
            thread.start()
    
    def submit(self, task: Task) -> None:
        """Submit a task to the queue"""
        self._queue.put(task)
        self.event_bus.publish(Event(
            type="task.submitted",
            source="executor",
            payload={"task_id": task.id, "action": task.action}
        ))
    
    def _worker_loop(self, worker_id: int) -> None:
        """Worker thread loop"""
        while self._running:
            try:
                task = self._queue.get(timeout=1)
                self._execute_task(task)
                self._queue.task_done()
            except:
                continue
    
    def _execute_task(self, task: Task) -> None:
        """Execute a single task"""
        # Update status to running
        self.planner.update_task_status(task.id, TaskStatus.RUNNING)
        
        self.event_bus.publish(Event(
            type="task.started",
            source="executor",
            payload={"task_id": task.id, "action": task.action}
        ))
        
        try:
            # Find agent
            agent = self.registry.get_agent(task.action)
            if not agent:
                raise ValueError(f"No agent found for action: {task.action}")
            
            # Execute
            context = self.planner.get_context(task.action.split('.')[0])
            result = agent.execute(task, context)
            
            # Update status
            self.planner.update_task_status(task.id, TaskStatus.COMPLETED, result)
            
            self.event_bus.publish(Event(
                type="task.completed",
                source="executor",
                payload={"task_id": task.id, "result": str(result)[:200]}
            ))
            
        except Exception as e:
            # Handle failure
            error = str(e)
            task.retries += 1
            
            if task.retries >= task.max_retries:
                self.planner.update_task_status(task.id, TaskStatus.FAILED, error=error)
                self.event_bus.publish(Event(
                    type="task.failed",
                    source="executor",
                    payload={"task_id": task.id, "error": error}
                ))
            else:
                # Re-queue with backoff
                self.planner.update_task_status(task.id, TaskStatus.PENDING)
                # Simple backoff: retry after 2^retries seconds
                backoff = 2 ** task.retries
                time.sleep(backoff)
                self.submit(task)
    
    def get_status(self) -> dict:
        """Get executor status"""
        with self._lock:
            return {
                "queue_size": self._queue.qsize(),
                "processing": len(self._processing),
                "workers": self._workers
            }
