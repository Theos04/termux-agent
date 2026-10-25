"""
Multi-Model Context Protocol server.

Transports:
  - stdio JSON-RPC (MCP-compatible: initialize / tools/list / tools/call / ping)
  - optional FastMCP when `mcp` package is installed
  - optional HTTP JSON endpoint (MMCP_TRANSPORT=http)
"""

from __future__ import annotations

import json
import logging
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from mmcp import __version__
from mmcp.config import MMCPConfig, load_config
from mmcp.protocol.context import MMCPContext, get_context
from mmcp.protocol.tools import call_tool, tool_result_text, tool_specs

logger = logging.getLogger(__name__)


PROTOCOL_VERSION = "2024-11-05"


class MMCPServer:
    def __init__(self, config: Optional[MMCPConfig] = None, ctx: Optional[MMCPContext] = None):
        self.config = config or load_config()
        self.ctx = (ctx or get_context(self.config)).ensure()

    def handle_rpc(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle one JSON-RPC 2.0 request; return response or None for notifications."""
        if not isinstance(message, dict):
            return self._error(None, -32600, "Invalid Request")

        msg_id = message.get("id", None)
        method = message.get("method")
        params = message.get("params") or {}

        # Notifications have no id
        is_notification = "id" not in message

        try:
            result = self._dispatch(method, params)
        except Exception as e:
            logger.exception("RPC error on %s", method)
            if is_notification:
                return None
            return self._error(msg_id, -32000, str(e))

        if is_notification:
            return None
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    def _dispatch(self, method: Optional[str], params: Dict[str, Any]) -> Any:
        if method == "initialize":
            return {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {
                    "tools": {"listChanged": False},
                },
                "serverInfo": {
                    "name": self.config.server_name,
                    "version": self.config.server_version or __version__,
                },
            }
        if method in ("notifications/initialized", "initialized"):
            return {}
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": tool_specs()}
        if method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if not name:
                raise ValueError("tools/call requires name")
            raw = call_tool(str(name), arguments, ctx=self.ctx)
            is_err = bool(raw.get("error")) and not raw.get("ok", True)
            return {
                "content": [{"type": "text", "text": tool_result_text(raw)}],
                "isError": is_err,
                "structuredContent": raw,
            }
        if method == "resources/list":
            return {"resources": []}
        if method == "prompts/list":
            return {"prompts": []}
        raise ValueError(f"Method not found: {method}")

    @staticmethod
    def _error(msg_id: Any, code: int, message: str) -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": code, "message": message},
        }

    # ----- transports -----

    def serve_stdio(self) -> None:
        logger.info(
            "mmcp stdio server %s v%s",
            self.config.server_name,
            self.config.server_version,
        )
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                resp = self._error(None, -32700, "Parse error")
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
                continue

            # Support Content-Length framed batches later; line-delimited first
            if isinstance(message, list):
                out = []
                for m in message:
                    r = self.handle_rpc(m)
                    if r is not None:
                        out.append(r)
                if out:
                    sys.stdout.write(json.dumps(out) + "\n")
                    sys.stdout.flush()
                continue

            resp = self.handle_rpc(message)
            if resp is not None:
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()

    def serve_http(self, host: Optional[str] = None, port: Optional[int] = None) -> None:
        host = host or self.config.http_host
        port = port or self.config.http_port
        server_self = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: Any) -> None:
                logger.debug("http: " + fmt, *args)

            def _send(self, code: int, body: Dict[str, Any]) -> None:
                data = json.dumps(body).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:  # noqa: N802
                path = urlparse(self.path).path
                if path in ("/", "/health", "/status"):
                    raw = call_tool("mmcp_status", {}, ctx=server_self.ctx)
                    self._send(200, raw)
                    return
                if path == "/tools":
                    self._send(200, {"tools": tool_specs()})
                    return
                self._send(404, {"error": "not found"})

            def do_POST(self) -> None:  # noqa: N802
                path = urlparse(self.path).path
                length = int(self.headers.get("Content-Length") or 0)
                raw_body = self.rfile.read(length) if length else b"{}"
                try:
                    body = json.loads(raw_body.decode("utf-8") or "{}")
                except json.JSONDecodeError:
                    self._send(400, {"error": "invalid json"})
                    return

                if path in ("/rpc", "/mcp"):
                    resp = server_self.handle_rpc(body)
                    self._send(200, resp or {"ok": True})
                    return
                if path.startswith("/tools/"):
                    name = path.split("/tools/", 1)[1].strip("/")
                    result = call_tool(name, body if isinstance(body, dict) else {}, ctx=server_self.ctx)
                    self._send(200, result)
                    return
                self._send(404, {"error": "not found"})

        httpd = ThreadingHTTPServer((host, port), Handler)
        logger.info("mmcp HTTP listening on http://%s:%s", host, port)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            httpd.shutdown()

    def serve_fastmcp(self) -> bool:
        """Bind tools to official FastMCP if installed. Returns False if unavailable."""
        try:
            from mcp.server.fastmcp import FastMCP  # type: ignore
        except Exception:
            return False

        mcp = FastMCP(self.config.server_name)
        ctx = self.ctx

        @mcp.tool()
        def models_list() -> str:
            return tool_result_text(call_tool("models_list", {}, ctx=ctx))

        @mcp.tool()
        def model_complete(
            prompt: str,
            role: str = "chat",
            system: str = "",
            image_path: str = "",
            model_name: str = "",
            max_tokens: int = 0,
            temperature: float = -1.0,
        ) -> str:
            args: Dict[str, Any] = {"prompt": prompt, "role": role}
            if system:
                args["system"] = system
            if image_path:
                args["image_path"] = image_path
            if model_name:
                args["model_name"] = model_name
            if max_tokens:
                args["max_tokens"] = max_tokens
            if temperature >= 0:
                args["temperature"] = temperature
            return tool_result_text(call_tool("model_complete", args, ctx=ctx))

        @mcp.tool()
        def agent_run(goal: str, max_steps: int = 6, har_summary: str = "") -> str:
            return tool_result_text(
                call_tool(
                    "agent_run",
                    {"goal": goal, "max_steps": max_steps, "har_summary": har_summary},
                    ctx=ctx,
                )
            )

        @mcp.tool()
        def har_start(port: int = 0, multi_tab: bool = True) -> str:
            args: Dict[str, Any] = {"multi_tab": multi_tab}
            if port:
                args["port"] = port
            return tool_result_text(call_tool("har_start", args, ctx=ctx))

        @mcp.tool()
        def har_stop() -> str:
            return tool_result_text(call_tool("har_stop", {}, ctx=ctx))

        @mcp.tool()
        def har_save(filepath: str = "", redact: bool = True) -> str:
            args: Dict[str, Any] = {"redact": redact}
            if filepath:
                args["filepath"] = filepath
            return tool_result_text(call_tool("har_save", args, ctx=ctx))

        @mcp.tool()
        def har_summary(limit: int = 12, url_substr: str = "") -> str:
            return tool_result_text(
                call_tool(
                    "har_summary",
                    {"limit": limit, "url_substr": url_substr},
                    ctx=ctx,
                )
            )

        @mcp.tool()
        def har_analyze(filepath: str, deep: bool = True) -> str:
            return tool_result_text(
                call_tool("har_analyze", {"filepath": filepath, "deep": deep}, ctx=ctx)
            )

        @mcp.tool()
        def vision_detect(image_path: str, prompt: str = "Detect objects") -> str:
            return tool_result_text(
                call_tool(
                    "vision_detect",
                    {"image_path": image_path, "prompt": prompt},
                    ctx=ctx,
                )
            )

        @mcp.tool()
        def mmcp_status() -> str:
            return tool_result_text(call_tool("mmcp_status", {}, ctx=ctx))

        mcp.run(transport="stdio")
        return True

    def run(self, transport: Optional[str] = None) -> None:
        transport = (transport or self.config.transport or "stdio").lower()
        if transport == "http":
            self.serve_http()
            return
        if transport in ("fastmcp", "mcp"):
            if self.serve_fastmcp():
                return
            logger.warning("FastMCP not installed; falling back to stdio JSON-RPC")
        # Prefer FastMCP automatically when available on plain stdio
        if transport == "stdio":
            try:
                from mcp.server.fastmcp import FastMCP  # noqa: F401

                if self.serve_fastmcp():
                    return
            except Exception:
                pass
        self.serve_stdio()


def main(argv: Optional[list] = None) -> int:
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    p = argparse.ArgumentParser(prog="mmcp", description="Multi-Model Context Protocol server")
    p.add_argument(
        "--transport",
        choices=["stdio", "http", "fastmcp"],
        default=None,
        help="Override MMCP_TRANSPORT",
    )
    p.add_argument("--host", default=None)
    p.add_argument("--port", type=int, default=None)
    args = p.parse_args(argv)

    cfg = load_config()
    if args.host:
        cfg.http_host = args.host
    if args.port:
        cfg.http_port = args.port
    if args.transport:
        cfg.transport = args.transport

    MMCPServer(cfg).run(cfg.transport)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
