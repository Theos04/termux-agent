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
