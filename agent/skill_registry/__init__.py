"""Skill Registry System — 15 capability families, formal contracts, and composable workflows."""

from .contract import (
    BaseSkill,
    RetryPolicy,
    SideEffect,
    SkillContract,
    SkillFamily,
    SkillResult,
)
from .context import ExecutionContext
from .registry import SkillRegistry, registry
from .workflow import WorkflowPipeline, WorkflowResult, WorkflowStep

# Auto-register built-in domain skills
from . import library

# Import predefined workflows
from .workflows import (
    build_action_rfq_workflow,
    build_address_change_workflow,
    build_quote_recording_workflow,
    build_read_stock_workflow,
)

__all__ = [
    "SkillFamily",
    "SideEffect",
    "RetryPolicy",
    "SkillContract",
    "SkillResult",
    "BaseSkill",
    "ExecutionContext",
    "SkillRegistry",
    "registry",
    "WorkflowStep",
    "WorkflowPipeline",
    "WorkflowResult",
    "build_read_stock_workflow",
    "build_address_change_workflow",
    "build_quote_recording_workflow",
    "build_action_rfq_workflow",
]
