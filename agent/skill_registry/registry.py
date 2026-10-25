"""Central Skill Registry holding registered skills and dispatching invocations."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .contract import BaseSkill, SkillContract, SkillFamily, SkillResult
from .context import ExecutionContext

log = logging.getLogger(__name__)


class SkillRegistry:
    """Registry managing approved business and platform skills."""

    def __init__(self):
        self._skills: Dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill) -> None:
        """Register a skill implementation."""
        name = skill.contract.name
        if name in self._skills:
            log.debug("Overwriting existing skill '%s'", name)
        self._skills[name] = skill
        log.debug("Registered skill: %s (family: %s, version: %s)", name, skill.contract.family.value, skill.contract.version)

    def get(self, name: str) -> Optional[BaseSkill]:
        """Look up skill by name."""
        return self._skills.get(name)

    def list_skills(self, family: Optional[SkillFamily] = None) -> List[SkillContract]:
        """List all registered skill contracts, optionally filtered by family."""
        skills = list(self._skills.values())
        if family:
            skills = [s for s in skills if s.contract.family == family]
        return [s.contract for s in skills]

    def invoke(self, name: str, context: ExecutionContext, inputs: Dict[str, Any]) -> SkillResult:
        """Invoke a skill through its formal contract."""
        skill = self.get(name)
        if not skill:
            return SkillResult(
                ok=False,
                error=f"Skill '{name}' not found in registry",
            )
        return skill.execute(context, inputs)

    def export_catalog(self) -> List[Dict[str, Any]]:
        """Export full JSON catalog of registered skills for inspection or UI."""
        return [
            {
                "name": s.contract.name,
                "version": s.contract.version,
                "family": s.contract.family.value,
                "description": s.contract.description,
                "permissions": s.contract.permissions,
                "side_effects": s.contract.side_effects.value,
                "timeout_seconds": s.contract.timeout_seconds,
                "audit_required": s.contract.audit_required,
                "input_schema": s.contract.input_schema,
                "output_schema": s.contract.output_schema,
            }
            for s in self._skills.values()
        ]


# Singleton default registry
registry = SkillRegistry()
