"""Formal Skill Contract and Base Definition for the 15 Capability Families."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

import jsonschema

log = logging.getLogger(__name__)


class SkillFamily(str, Enum):
    """The 15 capability families of the skill universe."""
    PERCEPTION_RETRIEVAL = "01_perception_retrieval"
    REASONING_INTELLIGENCE = "02_reasoning_intelligence"
    CREATION_TRANSFORMATION = "03_creation_transformation"
    EXECUTION_CONTROL = "04_execution_control"
    COMMUNICATION_COORDINATION = "05_communication_coordination"
    PLANNING_OPTIMIZATION = "06_planning_optimization"
    MEMORY_KNOWLEDGE = "07_memory_knowledge"
    GOVERNANCE_ASSURANCE = "08_governance_assurance"
    MONITORING_DIAGNOSIS = "09_monitoring_diagnosis"
    LEARNING_ADAPTATION = "10_learning_adaptation"
    CUSTOMER_INTELLIGENCE = "11_customer_intelligence"
    TRADING_PROCUREMENT = "12_trading_procurement"
    WORKFLOW_ORCHESTRATION = "13_workflow_orchestration"
    ENGINEERING_DATA_OPS = "14_engineering_data_ops"
    INVESTIGATION_INTELLIGENCE = "15_investigation_intelligence"


class SideEffect(str, Enum):
    NONE = "none"                        # Pure read-only, safe for speculative execution
    IDEMPOTENT_WRITE = "idempotent_write"# Modifies state safely; repeated executions yield same state
    IRREVERSIBLE = "irreversible"        # Financial transactions, dispatches, physical notifications


@dataclass
class RetryPolicy:
    max_retries: int = 2
    base_delay_seconds: float = 0.5
    backoff_multiplier: float = 2.0
    retryable_exceptions: tuple = (TimeoutError, ConnectionError)


@dataclass
class SkillContract:
    """Formal interface contract for a reusable agent skill."""
    name: str
    version: str
    family: SkillFamily
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    permissions: List[str] = field(default_factory=list)
    side_effects: SideEffect = SideEffect.NONE
    timeout_seconds: float = 10.0
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    audit_required: bool = True
    owner: str = "core_team"


@dataclass
class SkillResult:
    """Standardized output returned by every skill execution."""
    ok: bool
    data: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    error: Optional[str] = None
    execution_ms: float = 0.0
    audit_id: Optional[int] = None
    provenance: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "data": self.data,
            "warnings": self.warnings,
            "error": self.error,
            "execution_ms": self.execution_ms,
            "audit_id": self.audit_id,
            "provenance": self.provenance,
        }


class BaseSkill(ABC):
    """Abstract base class for all executable skills."""

    contract: SkillContract

    def validate_inputs(self, inputs: Dict[str, Any]) -> None:
        """Validate input payload against JSON Schema."""
        if self.contract.input_schema:
            try:
                jsonschema.validate(instance=inputs, schema=self.contract.input_schema)
            except jsonschema.ValidationError as err:
                raise ValueError(f"Input validation error for skill '{self.contract.name}': {err.message}")

    def validate_outputs(self, outputs: Dict[str, Any]) -> None:
        """Validate output payload against JSON Schema."""
        if self.contract.output_schema:
            try:
                jsonschema.validate(instance=outputs, schema=self.contract.output_schema)
            except jsonschema.ValidationError as err:
                log.warning("Output validation warning for skill '%s': %s", self.contract.name, err.message)

    @abstractmethod
    def run(self, context: Any, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Core skill execution logic to be implemented by each skill."""
        pass

    def execute(self, context: Any, inputs: Dict[str, Any]) -> SkillResult:
        """Standard wrapper: permissions, schema checks, metrics, and audit."""
        t0 = time.perf_counter()

        # 1. Permission check
        required_perms = set(self.contract.permissions)
        if required_perms:
            context_perms = getattr(context, "permissions", set())
            # Wildcard or exact check
            if "*" not in context_perms and not required_perms.issubset(context_perms):
                missing = required_perms - context_perms
                return SkillResult(
                    ok=False,
                    error=f"Permission denied: Missing required permissions {missing} for skill '{self.contract.name}'",
                    execution_ms=(time.perf_counter() - t0) * 1000,
                )

        # 2. Input validation
        try:
            self.validate_inputs(inputs)
        except ValueError as exc:
            return SkillResult(
                ok=False,
                error=str(exc),
                execution_ms=(time.perf_counter() - t0) * 1000,
            )

        # 3. Execution with retry policy
        attempts = 0
        max_attempts = 1 + (self.contract.retry_policy.max_retries if self.contract.side_effects == SideEffect.NONE else 0)
        delay = self.contract.retry_policy.base_delay_seconds
        last_error = None
        data = {}
        warnings: List[str] = []

        while attempts < max_attempts:
            attempts += 1
            try:
                data = self.run(context, inputs)
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                log.warning("Skill '%s' attempt %d failed: %s", self.contract.name, attempts, exc)
                if attempts < max_attempts and isinstance(exc, self.contract.retry_policy.retryable_exceptions):
                    time.sleep(delay)
                    delay *= self.contract.retry_policy.backoff_multiplier
                else:
                    break

        elapsed_ms = (time.perf_counter() - t0) * 1000

        if last_error is not None:
            return SkillResult(
                ok=False,
                error=f"Skill '{self.contract.name}' failed: {last_error}",
                execution_ms=elapsed_ms,
            )

        # 4. Output validation
        self.validate_outputs(data)

        # 5. Provenance tracking
        provenance = {
            "skill": self.contract.name,
            "version": self.contract.version,
            "family": self.contract.family.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "actor": getattr(context, "actor_id", "system"),
        }

        # 6. Audit logging if required
        audit_id = None
        if self.contract.audit_required and hasattr(context, "db") and context.db:
            try:
                audit_id = context.db.record_audit_event(
                    actor_type=getattr(context, "actor_type", "system"),
                    actor_id=getattr(context, "actor_id", "system"),
                    action=f"skill_execute:{self.contract.name}",
                    resource_type=self.contract.family.value,
                    resource_id=inputs.get("id") or inputs.get("order_id") or inputs.get("product_id") or "skill",
                    outcome="success",
                    metadata={"inputs": {k: str(v)[:80] for k, v in inputs.items()}, "execution_ms": elapsed_ms},
                )
            except Exception as audit_exc:
                log.warning("Audit event recording failed: %s", audit_exc)

        return SkillResult(
            ok=True,
            data=data,
            warnings=warnings,
            execution_ms=elapsed_ms,
            audit_id=audit_id,
            provenance=provenance,
        )
