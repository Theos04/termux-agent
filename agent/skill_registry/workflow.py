"""Composable Workflow Engine — combines modular skills into pipelines with automatic rollback."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .context import ExecutionContext
from .contract import SkillResult
from .registry import registry

log = logging.getLogger(__name__)


@dataclass
class WorkflowStep:
    """A discrete, modular step in a workflow pipeline."""
    name: str
    skill_name: str
    inputs_mapper: Optional[Callable[[Dict[str, Any], ExecutionContext], Dict[str, Any]]] = None
    condition: Optional[Callable[[Dict[str, Any], ExecutionContext], bool]] = None
    validator: Optional[Callable[[SkillResult, Dict[str, Any]], bool]] = None
    on_failure: str = "rollback_and_abort"  # "rollback_and_abort" | "abort" | "continue"


@dataclass
class WorkflowResult:
    """Consolidated result of a multi-step workflow execution."""
    ok: bool
    pipeline_name: str
    final_output: Dict[str, Any] = field(default_factory=dict)
    step_results: Dict[str, SkillResult] = field(default_factory=dict)
    trace: List[str] = field(default_factory=list)
    error: Optional[str] = None
    rolled_back: bool = False
    duration_ms: float = 0.0


class WorkflowPipeline:
    """Modular pipeline composing a sequence of approved skills."""

    def __init__(self, name: str, steps: Optional[List[WorkflowStep]] = None):
        self.name = name
        self.steps: List[WorkflowStep] = steps or []

    def add_step(
        self,
        name: str,
        skill_name: str,
        inputs_mapper: Optional[Callable[[Dict[str, Any], ExecutionContext], Dict[str, Any]]] = None,
        condition: Optional[Callable[[Dict[str, Any], ExecutionContext], bool]] = None,
        validator: Optional[Callable[[SkillResult, Dict[str, Any]], bool]] = None,
        on_failure: str = "rollback_and_abort",
    ) -> WorkflowPipeline:
        """Fluent builder: append a step to the pipeline."""
        self.steps.append(WorkflowStep(
            name=name,
            skill_name=skill_name,
            inputs_mapper=inputs_mapper,
            condition=condition,
            validator=validator,
            on_failure=on_failure,
        ))
        return self

    def execute(self, context: ExecutionContext, initial_inputs: Dict[str, Any]) -> WorkflowResult:
        """Execute pipeline steps sequentially with context and compensation."""
        t0 = time.perf_counter()
        state = dict(initial_inputs)
        step_results: Dict[str, SkillResult] = {}
        trace: List[str] = []

        log.info("Starting workflow '%s' with %d steps...", self.name, len(self.steps))
        trace.append(f"PIPELINE_START: {self.name} (session={context.session_id})")

        for step in self.steps:
            # 1. Condition check
            if step.condition and not step.condition(state, context):
                trace.append(f"STEP_SKIPPED: {step.name} (condition not met)")
                continue

            # 2. Map inputs
            step_inputs = step.inputs_mapper(state, context) if step.inputs_mapper else state

            # 3. Invoke skill from registry
            trace.append(f"STEP_INVOKE: {step.name} -> {step.skill_name}")
            result = registry.invoke(step.skill_name, context, step_inputs)
            step_results[step.name] = result

            is_valid = result.ok
            if is_valid and step.validator:
                try:
                    is_valid = bool(step.validator(result, state))
                except Exception as val_err:
                    is_valid = False
                    result.error = f"Step validation error: {val_err}"

            if not is_valid:
                err_msg = result.error or "Step validation criteria failed"
                trace.append(f"STEP_FAILED: {step.name} (error={err_msg})")
                log.warning("Workflow '%s' step '%s' failed: %s", self.name, step.name, err_msg)

                if step.on_failure == "rollback_and_abort":
                    log.warning("Triggering automatic compensation rollback for '%s'...", self.name)
                    rollback_errors = context.rollback()
                    trace.append(f"ROLLBACK_EXECUTED: {len(rollback_errors)} errors")
                    return WorkflowResult(
                        ok=False,
                        pipeline_name=self.name,
                        final_output=state,
                        step_results=step_results,
                        trace=trace,
                        error=f"Step '{step.name}' failed: {err_msg}",
                        rolled_back=True,
                        duration_ms=(time.perf_counter() - t0) * 1000,
                    )
                elif step.on_failure == "abort":
                    return WorkflowResult(
                        ok=False,
                        pipeline_name=self.name,
                        final_output=state,
                        step_results=step_results,
                        trace=trace,
                        error=f"Step '{step.name}' aborted workflow",
                        rolled_back=False,
                        duration_ms=(time.perf_counter() - t0) * 1000,
                    )
                # else "continue": proceed to next step

            # Merge successful step output into state
            trace.append(f"STEP_SUCCESS: {step.name} ({result.execution_ms:.1f}ms)")
            state.update(result.data)

        trace.append(f"PIPELINE_COMPLETE: {self.name}")
        return WorkflowResult(
            ok=True,
            pipeline_name=self.name,
            final_output=state,
            step_results=step_results,
            trace=trace,
            rolled_back=False,
            duration_ms=(time.perf_counter() - t0) * 1000,
        )
