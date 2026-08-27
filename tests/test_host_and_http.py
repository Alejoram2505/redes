from __future__ import annotations

import sys
import threading
import unittest
from pathlib import Path
from typing import Any

from mcp_host.chatbot import ChatSession
from mcp_host.client import McpError, RemoteHttpMcpClient, StdioMcpClient
from mcp_host.llm import LlmReply
from mcp_host.logging import McpAuditLogger, redact
from plant_energy_mcp.http_server import PlantMcpHttpServer
from plant_energy_mcp.protocol import McpDispatcher

RUNTIME_DIR = Path.cwd() / ".runtime" / "tests"
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


class FakeLlm:
    def __init__(self) -> None:
        self.calls = 0
        self.seen_messages: list[list[dict[str, Any]]] = []

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LlmReply:
        self.seen_messages.append(list(messages))
        self.calls += 1
        if self.calls == 1:
            return LlmReply(tool_calls=[{"id": "call-1", "name": "plant__list_equipment", "arguments": {}}])
        return LlmReply(text="Hay tres equipos registrados.")


class FakeClient:
    name = "plant"

    def list_tools(self) -> list[dict[str, Any]]:
        return [{"name": "list_equipment", "description": "List", "inputSchema": {"type": "object"}}]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return {"structuredContent": {"count": 3}}

    def close(self) -> None:
        pass


class HostTests(unittest.TestCase):
    def test_context_and_tool_loop_with_fake_llm(self) -> None:
        provider = FakeLlm()
        session = ChatSession(provider, [FakeClient()], confirm=lambda _: True)
        self.assertEqual(session.ask("¿Cuántos equipos hay?"), "Hay tres equipos registrados.")
        self.assertEqual(provider.calls, 2)
        final_messages = provider.seen_messages[-1]
        self.assertTrue(any(item["role"] == "tool" for item in final_messages))
        self.assertEqual(final_messages[1]["content"], "¿Cuántos equipos hay?")
        self.assertEqual(session.ask("¿Y en qué área trabajan?"), "Hay tres equipos registrados.")
        continuation = provider.seen_messages[-1]
        self.assertEqual(continuation[-1]["content"], "¿Y en qué área trabajan?")
        self.assertTrue(any(item.get("content") == "¿Cuántos equipos hay?" for item in continuation))

    def test_logger_redacts_secrets_and_private_paths(self) -> None:
        path = RUNTIME_DIR / "logger_test.jsonl"
        path.unlink(missing_ok=True)
        self.addCleanup(path.unlink, missing_ok=True)
        logger = McpAuditLogger(path, project_root=RUNTIME_DIR)
        logger.write(
            server="x",
            transport="stdio",
            direction="request",
            method="tools/call",
            summary={"api_key": "abc", "path": str(RUNTIME_DIR / "secret.txt"), "Authorization": "Bearer xyz"},
        )
        content = path.read_text(encoding="utf-8")
        self.assertNotIn("abc", content)
        self.assertNotIn("xyz", content)
        self.assertNotIn(str(RUNTIME_DIR), content)
        self.assertIn("[REDACTED]", content)

    def test_redact_limits_long_content(self) -> None:
        self.assertLess(len(redact("x" * 2000)), 510)


class ProtocolTests(unittest.TestCase):
    def test_incorrect_handshake_version(self) -> None:
        dispatcher = McpDispatcher()
        response = dispatcher.handle(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "1900-01-01"}}
        )
        assert response is not None
        self.assertEqual(response["error"]["code"], -32602)
        self.assertFalse(dispatcher.initialized)

    def test_stdio_client_local_integration(self) -> None:
        path = RUNTIME_DIR / "stdio_test.jsonl"
        path.unlink(missing_ok=True)
        self.addCleanup(path.unlink, missing_ok=True)
        logger = McpAuditLogger(path)
        with StdioMcpClient("plant", [sys.executable, "-m", "plant_energy_mcp"], timeout=3, logger=logger) as client:
            self.assertEqual(len(client.list_tools()), 5)
            result = client.call_tool("list_equipment", {})
            self.assertEqual(result["structuredContent"]["count"], 3)

    def test_stdio_timeout_and_clean_close(self) -> None:
        command = [sys.executable, "-c", "import sys,time; sys.stdin.readline(); time.sleep(2)"]
        client = StdioMcpClient("slow", command, timeout=0.05)
        with self.assertRaises(McpError):
            client.start()
        client.close()


class HttpTransportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = PlantMcpHttpServer(("127.0.0.1", 0), token="test-token")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/mcp"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_remote_handshake_tools_call_and_parity(self) -> None:
        with RemoteHttpMcpClient("remote", self.url, token="test-token") as remote:
            names = [item["name"] for item in remote.list_tools()]
            self.assertEqual(names, [item["name"] for item in McpDispatcher().registry.list_tools()])
            result = remote.call_tool("get_energy_report", {})
            self.assertEqual(result["structuredContent"]["equipment_count"], 3)

    def test_authentication_and_session_errors_are_safe(self) -> None:
        client = RemoteHttpMcpClient("remote", self.url, token="wrong")
        with self.assertRaisesRegex(McpError, "HTTP 401"):
            client.start()


if __name__ == "__main__":
    unittest.main()
