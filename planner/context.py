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
