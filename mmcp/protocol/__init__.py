"""MCP server + tool surface for multi-model context protocol."""

from mmcp.protocol.server import MMCPServer, main
from mmcp.protocol.tools import call_tool, tool_specs
from mmcp.protocol.context import MMCPContext, get_context

__all__ = [
    "MMCPServer",
    "main",
    "call_tool",
    "tool_specs",
    "MMCPContext",
    "get_context",
]
