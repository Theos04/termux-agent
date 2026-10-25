"""Shared runtime context for MCP tool handlers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from mmcp.config import MMCPConfig, load_config
from mmcp.graph.workflow import MultiModelWorkflow
from mmcp.har.capture import ProductionHARCapturer
from mmcp.models.router import ModelRouter, get_router


ToolExecutor = Callable[[str, Dict[str, Any]], Dict[str, Any]]


@dataclass
class MMCPContext:
    config: MMCPConfig = field(default_factory=load_config)
    router: Optional[ModelRouter] = None
    har: Optional[ProductionHARCapturer] = None
    workflow: Optional[MultiModelWorkflow] = None
    tool_executor: Optional[ToolExecutor] = None

    def ensure(self) -> "MMCPContext":
        if self.router is None:
            self.router = get_router(self.config)
        if self.har is None:
            self.har = ProductionHARCapturer(self.config)
        if self.workflow is None:
            self.workflow = MultiModelWorkflow(
                router=self.router,
                tool_executor=self.tool_executor,
                use_langgraph=self.config.use_langgraph,
            )
        return self


_CTX: Optional[MMCPContext] = None


def get_context(config: Optional[MMCPConfig] = None) -> MMCPContext:
    global _CTX
    if _CTX is None or config is not None:
        _CTX = MMCPContext(config=config or load_config()).ensure()
    return _CTX
