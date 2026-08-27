"""Manual MCP clients for newline-delimited stdio and Streamable HTTP."""

from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from plant_energy_mcp.protocol import PROTOCOL_VERSION

from .logging import McpAuditLogger


class McpError(RuntimeError):
    pass


class JsonRpcRemoteError(McpError):
    def __init__(self, error: dict[str, Any]) -> None:
        self.code = error.get("code")
        super().__init__(f"JSON-RPC {self.code}: {error.get('message', 'unknown error')}")


class StdioMcpClient:
    def __init__(
        self,
        name: str,
        command: list[str],
        *,
        cwd: Path | None = None,
        timeout: float = 10,
        logger: McpAuditLogger | None = None,
    ) -> None:
        self.name, self.command, self.cwd, self.timeout = name, command, cwd, timeout
        self.logger = logger or McpAuditLogger()
        self._next_id = 1
        self._pending: dict[Any, queue.Queue[Any]] = {}
        self._lock = threading.Lock()
        self._closed = False
        self.process: subprocess.Popen[str] | None = None

    def start(self) -> "StdioMcpClient":
        self.process = subprocess.Popen(
            self.command,
            cwd=self.cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()
        result = self.request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "plant-energy-chatbot", "version": "1.0.0"},
            },
        )
        negotiated = result.get("protocolVersion")
        if not isinstance(negotiated, str):
            self.close()
            raise McpError(f"{self.name} returned no MCP protocol version")
        self.notify("notifications/initialized", {})
        return self

    def _read_stdout(self) -> None:
        assert self.process and self.process.stdout
        for raw in self.process.stdout:
            try:
                message = json.loads(raw)
                if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
                    raise ValueError("not a JSON-RPC object")
            except (json.JSONDecodeError, ValueError) as exc:
                self.logger.write(
                    server=self.name,
                    transport="stdio",
                    direction="error",
                    method=None,
                    summary=str(exc),
                    error_code="invalid_json",
                )
                self._fail_pending(McpError(f"{self.name} emitted invalid JSON-RPC on stdout"))
                continue
            request_id = message.get("id")
            self.logger.write(
                server=self.name,
                transport="stdio",
                direction="response" if request_id is not None else "notification",
                method=message.get("method"),
                request_id=request_id,
                summary=message.get("error") or message.get("result"),
                error_code=(message.get("error") or {}).get("code"),
            )
            with self._lock:
                waiter = self._pending.get(request_id)
            if waiter:
                waiter.put(message)
        self._fail_pending(McpError(f"{self.name} process ended"))

    def _read_stderr(self) -> None:
        assert self.process and self.process.stderr
        for raw in self.process.stderr:
            self.logger.write(
                server=self.name, transport="stdio", direction="notification", method="stderr", summary=raw.strip()
            )

    def _fail_pending(self, error: Exception) -> None:
        with self._lock:
            waiters = list(self._pending.values())
        for waiter in waiters:
            waiter.put(error)

    def _send(self, payload: dict[str, Any]) -> None:
        if not self.process or self.process.poll() is not None or not self.process.stdin:
            raise McpError(f"{self.name} process is not running")
        self.process.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
        self.process.stdin.flush()

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            request_id = self._next_id
            self._next_id += 1
            waiter: queue.Queue[Any] = queue.Queue(maxsize=1)
            self._pending[request_id] = waiter
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}
        started = time.monotonic()
        self.logger.write(
            server=self.name,
            transport="stdio",
            direction="request",
            method=method,
            request_id=request_id,
            summary=params,
        )
        try:
            self._send(payload)
            try:
                response = waiter.get(timeout=self.timeout)
            except queue.Empty as exc:
                raise McpError(f"{self.name} timed out during {method}") from exc
            if isinstance(response, Exception):
                raise response
            duration = (time.monotonic() - started) * 1000
            if "error" in response:
                self.logger.write(
                    server=self.name,
                    transport="stdio",
                    direction="error",
                    method=method,
                    request_id=request_id,
                    duration_ms=duration,
                    summary=response["error"],
                    error_code=response["error"].get("code"),
                )
                raise JsonRpcRemoteError(response["error"])
            return response.get("result", {})
        finally:
            with self._lock:
                self._pending.pop(request_id, None)

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        self.logger.write(server=self.name, transport="stdio", direction="notification", method=method, summary=params)
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def list_tools(self) -> list[dict[str, Any]]:
        return self.request("tools/list").get("tools", [])

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self.request("tools/call", {"name": name, "arguments": arguments})

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self.process:
            if self.process.stdin:
                self.process.stdin.close()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                self.process.wait(timeout=3)
            if self.process.stdout:
                self.process.stdout.close()
            if self.process.stderr:
                self.process.stderr.close()

    def __enter__(self) -> "StdioMcpClient":
        return self.start()

    def __exit__(self, *_: Any) -> None:
        self.close()


class RemoteHttpMcpClient:
    def __init__(
        self, name: str, url: str, *, token: str = "", timeout: float = 10, logger: McpAuditLogger | None = None
    ) -> None:
        self.name, self.url, self.token, self.timeout = name, url, token, timeout
        self.logger = logger or McpAuditLogger()
        self.session_id: str | None = None
        self._next_id = 1

    def _post(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        method, request_id = payload.get("method"), payload.get("id")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": PROTOCOL_VERSION,
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.session_id:
            headers["MCP-Session-Id"] = self.session_id
        started = time.monotonic()
        direction = "request" if request_id is not None else "notification"
        self.logger.write(
            server=self.name,
            transport="streamable-http",
            direction=direction,
            method=method,
            request_id=request_id,
            summary=payload.get("params"),
        )
        request = urllib.request.Request(self.url, json.dumps(payload).encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                self.session_id = response.headers.get("MCP-Session-Id") or self.session_id
                body = response.read()
        except urllib.error.HTTPError as exc:
            body = exc.read()
            try:
                detail = json.loads(body)
            except json.JSONDecodeError:
                detail = {"error": {"code": exc.code, "message": "HTTP transport error"}}
            self.logger.write(
                server=self.name,
                transport="streamable-http",
                direction="error",
                method=method,
                request_id=request_id,
                duration_ms=(time.monotonic() - started) * 1000,
                summary=detail,
                error_code=exc.code,
            )
            raise McpError(f"{self.name} HTTP {exc.code}") from exc
        if not body:
            return None
        result = json.loads(body)
        self.logger.write(
            server=self.name,
            transport="streamable-http",
            direction="response",
            method=method,
            request_id=request_id,
            duration_ms=(time.monotonic() - started) * 1000,
            summary=result.get("error") or result.get("result"),
            error_code=(result.get("error") or {}).get("code"),
        )
        return result

    def start(self) -> "RemoteHttpMcpClient":
        result = self.request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "plant-energy-chatbot", "version": "1.0.0"},
            },
        )
        if not result.get("protocolVersion"):
            raise McpError("remote server returned no protocol version")
        self.notify("notifications/initialized", {})
        return self

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        response = self._post({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})
        if not response:
            raise McpError(f"empty response for {method}")
        if response.get("id") != request_id:
            raise McpError("mismatched JSON-RPC response id")
        if "error" in response:
            raise JsonRpcRemoteError(response["error"])
        return response.get("result", {})

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        self._post({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def list_tools(self) -> list[dict[str, Any]]:
        return self.request("tools/list").get("tools", [])

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self.request("tools/call", {"name": name, "arguments": arguments})

    def close(self) -> None:
        if not self.session_id:
            return
        headers = {"MCP-Session-Id": self.session_id, "MCP-Protocol-Version": PROTOCOL_VERSION}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(self.url, headers=headers, method="DELETE")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout):
                pass
        except (urllib.error.URLError, TimeoutError):
            pass
        finally:
            self.session_id = None

    def __enter__(self) -> "RemoteHttpMcpClient":
        return self.start()

    def __exit__(self, *_: Any) -> None:
        self.close()
