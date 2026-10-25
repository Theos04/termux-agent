"""Shared state for multi-model agent graphs."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class AgentGraphState(TypedDict, total=False):
    goal: str
    role: str
    plan: str
    observations: List[str]
    tool_calls: List[Dict[str, Any]]
    vision_result: Optional[Dict[str, Any]]
    har_summary: str
    answer: str
    error: Optional[str]
    model_used: str
    step: int
    max_steps: int
    done: bool
