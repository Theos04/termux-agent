"""
Multi-Model Context Protocol (mmcp).

Production stack for:
  - multi-model routing (llama.cpp / OpenAI-compat / MMDeploy)
  - LangGraph orchestration (with pure-Python fallback)
  - MCP tools over stdio or HTTP
  - hardened HAR capture / serialize / analyze
"""

from __future__ import annotations

from mmcp.config import MMCPConfig, load_config
from mmcp.models.router import ModelRouter, get_router
from mmcp.graph.workflow import MultiModelWorkflow, langgraph_available

__version__ = "1.0.0"

__all__ = [
    "MMCPConfig",
    "load_config",
    "ModelRouter",
    "get_router",
    "MultiModelWorkflow",
    "langgraph_available",
    "__version__",
]
