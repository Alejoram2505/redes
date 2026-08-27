"""Manual JSON-RPC 2.0 and MCP request dispatcher."""

from __future__ import annotations

import json
from typing import Any

from . import __version__
from .service import ToolInputError
from .tools import ToolRegistry

PROTOCOL_VERSION = "2025-11-25"


class JsonRpcError(Exception):
    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


def error_response(request_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


class McpDispatcher:
    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self.registry = registry or ToolRegistry()
        self.initialized = False
        self.client_initialized = False

    def parse_line(self, line: str) -> dict[str, Any]:
        try:
            message = json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise JsonRpcError(-32700, "Parse error") from exc
        if not isinstance(message, dict):
            raise JsonRpcError(-32600, "Invalid Request")
        if message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
            raise JsonRpcError(-32600, "Invalid Request")
        if "id" in message and isinstance(message["id"], (dict, list, bool)):
            raise JsonRpcError(-32600, "Invalid Request")
        return message

    def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        request_id = message.get("id")
        is_notification = "id" not in message
        method = message["method"]
        params = message.get("params", {})
        try:
            result = self._dispatch(method, params, is_notification)
            if is_notification:
                return None
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except JsonRpcError as exc:
            if is_notification:
                return None
            return error_response(request_id, exc.code, exc.message, exc.data)
        except ToolInputError as exc:
            if is_notification:
                return None
            return error_response(request_id, -32602, "Invalid params", str(exc))
        except Exception:
            if is_notification:
                return None
            return error_response(request_id, -32603, "Internal error")

    def _dispatch(self, method: str, params: Any, is_notification: bool) -> dict[str, Any]:
        if not isinstance(params, dict):
            raise JsonRpcError(-32602, "Invalid params", "params must be an object")
        if method == "initialize":
            if is_notification:
                raise JsonRpcError(-32600, "Invalid Request")
            requested = params.get("protocolVersion")
            if not isinstance(requested, str):
                raise JsonRpcError(-32602, "Invalid params", "protocolVersion is required")
            if requested != PROTOCOL_VERSION:
                raise JsonRpcError(-32602, "Unsupported protocol version", {"supported": [PROTOCOL_VERSION]})
            self.initialized = True
            return {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "plant-energy-mcp", "version": __version__},
                "instructions": "Use the tools to inspect deterministic plant energy demo data.",
            }
        if method == "notifications/initialized":
            if not is_notification or not self.initialized:
                raise JsonRpcError(-32600, "Invalid Request")
            self.client_initialized = True
            return {}
        if not (self.initialized and self.client_initialized):
            raise JsonRpcError(-32002, "Server not initialized")
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": self.registry.list_tools()}
        if method == "tools/call":
            name = params.get("name")
            if not isinstance(name, str):
                raise JsonRpcError(-32602, "Invalid params", "name must be a string")
            arguments = params.get("arguments", {})
            payload = self.registry.call(name, arguments)
            return {
                "content": [{"type": "text", "text": json.dumps(payload, separators=(",", ":"), sort_keys=True)}],
                "structuredContent": payload,
                "isError": False,
            }
        raise JsonRpcError(-32601, "Method not found")
