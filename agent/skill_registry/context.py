"""Execution context carrying security credentials, db connection, and compensation stack."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set

from agent.database import Database

log = logging.getLogger(__name__)


@dataclass
class ExecutionContext:
    """Execution context passed through all skill invocations."""
    db: Database
    actor_type: str = "orchestrator"
    actor_id: str = "system"
    permissions: Set[str] = field(default_factory=lambda: {"*"})
    contact: Optional[Any] = None
    session_id: str = field(default_factory=lambda: f"sess_{uuid.uuid4().hex[:10]}")
    idempotency_key: Optional[str] = None
    tenant_id: str = "default_pharmacy"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Reliability: Compensation stack for transactional rollback
    _compensation_stack: List[Callable[[], None]] = field(default_factory=list, repr=False)
    
    # Provenance store
    facts: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def has_permission(self, perm: str) -> bool:
        return "*" in self.permissions or perm in self.permissions

    def push_compensation(self, callback: Callable[[], None]) -> None:
        """Register a rollback action to be executed if a subsequent step fails."""
        self._compensation_stack.append(callback)

    def rollback(self) -> List[str]:
        """Execute compensation actions in reverse order (LIFO)."""
        errors = []
        log.warning("Initiating rollback compensation for session %s...", self.session_id)
        while self._compensation_stack:
            compensate = self._compensation_stack.pop()
            try:
                compensate()
            except Exception as exc:
                log.error("Compensation step failed: %s", exc)
                errors.append(str(exc))
        return errors

    def record_fact(self, key: str, value: Any, source: str, confidence: float = 1.0) -> None:
        """Store verified fact with provenance tracking."""
        self.facts[key] = {
            "value": value,
            "source": source,
            "confidence": confidence,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_fact(self, key: str) -> Optional[Any]:
        fact = self.facts.get(key)
        return fact["value"] if fact else None
