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
