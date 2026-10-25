"""Tool implementations exposed over the multi-model context protocol."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from mmcp.har.analyze import analyze_har
from mmcp.protocol.context import MMCPContext, get_context


def tool_specs() -> List[Dict[str, Any]]:
    """MCP tools/list style descriptors."""
    return [
        {
            "name": "models_list",
            "description": "List configured multi-model endpoints, health, and circuit state.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "model_complete",
            "description": "Route a completion through the multi-model router (role-aware).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "role": {
                        "type": "string",
                        "enum": ["chat", "plan", "extract", "vision", "detect"],
                        "default": "chat",
                    },
                    "system": {"type": "string"},
                    "image_path": {"type": "string"},
                    "model_name": {"type": "string"},
                    "max_tokens": {"type": "integer"},
                    "temperature": {"type": "number"},
                },
                "required": ["prompt"],
            },
        },
        {
            "name": "agent_run",
            "description": "Run the LangGraph (or fallback) multi-model agent workflow for a goal.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "goal": {"type": "string"},
                    "max_steps": {"type": "integer", "default": 6},
                    "har_summary": {"type": "string"},
                },
                "required": ["goal"],
            },
        },
        {
            "name": "har_start",
            "description": "Start multi-tab CDP HAR capture on Chrome debug port.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "port": {"type": "integer"},
                    "multi_tab": {"type": "boolean"},
                },
            },
        },
        {
            "name": "har_stop",
            "description": "Stop HAR capture and return summary stats.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "har_save",
            "description": "Serialize captured traffic to a HAR 1.2 file (secrets redacted by default).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string"},
                    "redact": {"type": "boolean", "default": True},
                },
            },
        },
        {
            "name": "har_summary",
            "description": "Live HAR capture summary + recent API-like requests.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 12},
                    "url_substr": {"type": "string"},
                },
            },
        },
        {
            "name": "har_analyze",
            "description": "Analyze a HAR file (advanced analyzer when available).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string"},
                    "deep": {"type": "boolean", "default": True},
                },
                "required": ["filepath"],
            },
        },
        {
            "name": "vision_detect",
            "description": "Run MMDeploy (or vision-capable fallback) on an image.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "image_path": {"type": "string"},
                    "prompt": {"type": "string"},
                },
                "required": ["image_path"],
            },
        },
        {
            "name": "mmcp_status",
            "description": "Server / router / HAR / LangGraph status snapshot.",
            "inputSchema": {"type": "object", "properties": {}},
        },
    ]


def call_tool(name: str, arguments: Optional[Dict[str, Any]] = None, ctx: Optional[MMCPContext] = None) -> Dict[str, Any]:
    args = arguments or {}
    c = (ctx or get_context()).ensure()
    assert c.router is not None and c.har is not None and c.workflow is not None

    if name == "models_list":
        return {"endpoints": c.router.list_endpoints(), "stats": {
            "calls": c.router.stats.calls,
            "successes": c.router.stats.successes,
            "failures": c.router.stats.failures,
            "by_model": dict(c.router.stats.by_model),
        }}

    if name == "model_complete":
        resp = c.router.complete(
            str(args.get("prompt") or ""),
            role=str(args.get("role") or "chat"),
            system=args.get("system"),
            image_path=args.get("image_path"),
            model_name=args.get("model_name"),
            max_tokens=args.get("max_tokens"),
            temperature=args.get("temperature"),
        )
        return {
            "ok": resp.ok,
            "text": resp.text,
            "model": resp.model,
            "provider": resp.provider,
            "latency_ms": resp.latency_ms,
            "structured": resp.structured,
            "error": resp.error,
            "usage": resp.usage,
        }

    if name == "agent_run":
        state = c.workflow.run(
            str(args.get("goal") or ""),
            har_summary=str(args.get("har_summary") or c.har.summary_for_prompt()),
            max_steps=int(args.get("max_steps") or 6),
        )
        return {
            "backend": c.workflow.backend,
            "answer": state.get("answer"),
            "role": state.get("role"),
            "plan": state.get("plan"),
            "model_used": state.get("model_used"),
            "observations": state.get("observations"),
            "tool_calls": state.get("tool_calls"),
            "done": state.get("done"),
        }

    if name == "har_start":
        ok = c.har.start(
            port=args.get("port"),
            multi_tab=args.get("multi_tab"),
        )
        return {"ok": ok, "summary": c.har.summary()}

    if name == "har_stop":
        return {"ok": True, "summary": c.har.stop()}

    if name == "har_save":
        path, n = c.har.save(
            args.get("filepath"),
            redact=args.get("redact"),
        )
        return {"ok": True, "filepath": path, "entries": n}

    if name == "har_summary":
        return {
            "summary": c.har.summary(),
            "apis": c.har.recent_apis(
                limit=int(args.get("limit") or 12),
                url_substr=str(args.get("url_substr") or ""),
            ),
            "prompt_block": c.har.summary_for_prompt(limit=int(args.get("limit") or 8)),
        }

    if name == "har_analyze":
        return analyze_har(str(args["filepath"]), deep=bool(args.get("deep", True)))

    if name == "vision_detect":
        resp = c.router.complete(
            str(args.get("prompt") or "Detect objects"),
            role="vision",
            image_path=str(args["image_path"]),
        )
        return {
            "ok": resp.ok,
            "text": resp.text,
            "structured": resp.structured,
            "model": resp.model,
            "provider": resp.provider,
            "error": resp.error,
        }

    if name == "mmcp_status":
        from mmcp import __version__
        from mmcp.graph.workflow import langgraph_available
        from mmcp.models.providers.mmdeploy_vision import MMDeployVisionProvider

        return {
            "version": __version__,
            "server": c.config.server_name,
            "transport": c.config.transport,
            "langgraph": langgraph_available(),
            "workflow_backend": c.workflow.backend,
            "mmdeploy": MMDeployVisionProvider().available,
            "har": c.har.summary(),
            "models": c.router.list_endpoints(),
        }

    return {"error": f"Unknown tool: {name}"}


def tool_result_text(result: Dict[str, Any]) -> str:
    return json.dumps(result, indent=2, default=str)
