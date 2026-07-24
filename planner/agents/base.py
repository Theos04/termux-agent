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
