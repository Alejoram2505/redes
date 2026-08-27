"""Manual, dependency-free Streamable HTTP adapter for Plant Energy MCP."""

from __future__ import annotations

import hmac
import json
import os
import secrets
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

from .protocol import PROTOCOL_VERSION, JsonRpcError, McpDispatcher, error_response


class SessionStore:
    def __init__(self) -> None:
        self._items: dict[str, McpDispatcher] = {}
        self._lock = threading.Lock()

    def create(self) -> tuple[str, McpDispatcher]:
        session_id, dispatcher = secrets.token_urlsafe(24), McpDispatcher()
        with self._lock:
            self._items[session_id] = dispatcher
        return session_id, dispatcher

    def get(self, session_id: str) -> McpDispatcher | None:
        with self._lock:
            return self._items.get(session_id)

    def delete(self, session_id: str) -> bool:
        with self._lock:
            return self._items.pop(session_id, None) is not None


class PlantMcpHttpServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        token: str = "",
        allowed_origins: set[str] | None = None,
        max_body: int = 1_048_576,
    ) -> None:
        super().__init__(address, PlantMcpHandler)
        self.token = token
        self.allowed_origins = allowed_origins or {"http://127.0.0.1", "http://localhost"}
        self.max_body = max_body
        self.sessions = SessionStore()


class PlantMcpHandler(BaseHTTPRequestHandler):
    server: PlantMcpHttpServer

    def log_message(self, fmt: str, *args: Any) -> None:
        # BaseHTTPRequestHandler logs to stderr, never to the MCP response stream.
        super().log_message(fmt, *args)

    def _json(self, status: int, body: dict[str, Any] | None = None, *, session_id: str | None = None) -> None:
        data = b"" if body is None else json.dumps(body, separators=(",", ":")).encode()
        self.send_response(status)
        if body is not None:
            self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if session_id:
            self.send_header("MCP-Session-Id", session_id)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if data:
            self.wfile.write(data)

    def _authorized(self) -> bool:
        if not self.server.token:
            return True
        supplied = self.headers.get("Authorization", "")
        return hmac.compare_digest(supplied, f"Bearer {self.server.token}")

    def _origin_allowed(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        parsed = urlsplit(origin)
        normalized = f"{parsed.scheme}://{parsed.netloc}"
        return normalized in self.server.allowed_origins

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json(HTTPStatus.OK, {"status": "ok"})
            return
        if self.path == "/mcp":
            self._json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "SSE listening stream is not offered"})
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_DELETE(self) -> None:
        if self.path != "/mcp":
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        if not self._origin_allowed() or not self._authorized():
            self._json(HTTPStatus.UNAUTHORIZED, {"error": "authentication required"})
            return
        if self.headers.get("MCP-Protocol-Version") != PROTOCOL_VERSION:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "unsupported MCP protocol version"})
            return
        session_id = self.headers.get("MCP-Session-Id", "")
        self._json(HTTPStatus.NO_CONTENT if self.server.sessions.delete(session_id) else HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if self.path != "/mcp":
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        if not self._origin_allowed():
            self._json(HTTPStatus.FORBIDDEN, {"error": "origin not allowed"})
            return
        if not self._authorized():
            self._json(HTTPStatus.UNAUTHORIZED, {"error": "authentication required"})
            return
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        accept = self.headers.get("Accept", "")
        if content_type != "application/json" or "application/json" not in accept or "text/event-stream" not in accept:
            self._json(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                {"error": "Content-Type application/json and both MCP Accept types are required"},
            )
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if length < 0 or length > self.server.max_body:
            self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "request body too large"})
            return
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError
        except (json.JSONDecodeError, ValueError):
            self._json(HTTPStatus.BAD_REQUEST, error_response(None, -32700, "Parse error"))
            return
        method = payload.get("method")
        session_id = self.headers.get("MCP-Session-Id")
        dispatcher: McpDispatcher | None
        if method == "initialize":
            session_id, dispatcher = self.server.sessions.create()
        else:
            if self.headers.get("MCP-Protocol-Version") != PROTOCOL_VERSION:
                self._json(
                    HTTPStatus.BAD_REQUEST,
                    error_response(payload.get("id"), -32600, "Unsupported MCP protocol version"),
                )
                return
            dispatcher = self.server.sessions.get(session_id or "")
            if dispatcher is None:
                self._json(
                    HTTPStatus.NOT_FOUND, error_response(payload.get("id"), -32001, "Unknown or expired MCP session")
                )
                return
        if dispatcher is None:
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, error_response(payload.get("id"), -32603, "Internal error"))
            return
        try:
            parsed = dispatcher.parse_line(json.dumps(payload))
            response = dispatcher.handle(parsed)
        except JsonRpcError as exc:
            response = error_response(None, exc.code, exc.message, exc.data)
        if method == "initialize" and response is not None and "error" in response:
            self.server.sessions.delete(session_id or "")
            session_id = None
        if response is None:
            self._json(HTTPStatus.ACCEPTED, session_id=session_id)
        else:
            self._json(HTTPStatus.OK, response, session_id=session_id)


def build_server() -> PlantMcpHttpServer:
    host = os.environ.get("PLANT_MCP_HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8080"))
    token = os.environ.get("PLANT_MCP_AUTH_TOKEN", "")
    if host not in {"127.0.0.1", "localhost", "::1"} and not token:
        raise RuntimeError("PLANT_MCP_AUTH_TOKEN is required when binding beyond loopback")
    origins = {
        item.strip()
        for item in os.environ.get("PLANT_MCP_ALLOWED_ORIGINS", "http://127.0.0.1,http://localhost").split(",")
        if item.strip()
    }
    max_body = int(os.environ.get("PLANT_MCP_MAX_BODY_BYTES", "1048576"))
    return PlantMcpHttpServer((host, port), token=token, allowed_origins=origins, max_body=max_body)


def main() -> int:
    server = build_server()
    print(f"plant-energy-mcp HTTP listening on http://{server.server_name}:{server.server_port}/mcp", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
