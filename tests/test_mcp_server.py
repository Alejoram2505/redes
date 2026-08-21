from __future__ import annotations

import json
import subprocess
import sys
import unittest
from typing import Any

from plant_energy_mcp.protocol import McpDispatcher


class ServerProcess:
    def __enter__(self) -> "ServerProcess":
        self.process = subprocess.Popen(
            [sys.executable, "-m", "plant_energy_mcp"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return self

    def send(self, message: dict[str, Any] | str) -> None:
        assert self.process.stdin is not None
        line = message if isinstance(message, str) else json.dumps(message, separators=(",", ":"))
        self.process.stdin.write(line + "\n")
        self.process.stdin.flush()

    def receive(self) -> dict[str, Any]:
        assert self.process.stdout is not None
        line = self.process.stdout.readline()
        self.last_raw_line = line
        return json.loads(line)

    def initialize(self) -> None:
        self.send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}})
        response = self.receive()
        if response.get("result", {}).get("protocolVersion") != "2025-11-25":
            raise AssertionError(response)
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    def call_tool(self, request_id: int, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.send({"jsonrpc": "2.0", "id": request_id, "method": "tools/call", "params": {"name": name, "arguments": arguments}})
        return self.receive()

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self.process.stdin:
            self.process.stdin.close()
        self.return_code = self.process.wait(timeout=5)
        self.stderr = self.process.stderr.read() if self.process.stderr else ""
        if self.process.stdout:
            self.process.stdout.close()
        if self.process.stderr:
            self.process.stderr.close()


class McpServerIntegrationTests(unittest.TestCase):
    def test_handshake_list_ping_and_clean_shutdown(self) -> None:
        with ServerProcess() as server:
            server.initialize()
            server.send({"jsonrpc": "2.0", "id": 2, "method": "ping", "params": {}})
            self.assertEqual(server.receive()["result"], {})
            server.send({"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}})
            tools = server.receive()["result"]["tools"]
            self.assertEqual(len(tools), 5)
            self.assertTrue(all({"name", "description", "inputSchema"} <= set(tool) for tool in tools))
        self.assertEqual(server.return_code, 0)
        self.assertIn("shutting down cleanly", server.stderr)

    def test_each_tool_success(self) -> None:
        period = {"equipment_id": "press-01", "start_timestamp": "2026-08-20T08:00:00Z", "end_timestamp": "2026-08-20T12:00:00Z"}
        cases = [
            ("list_equipment", {}),
            ("record_energy_reading", {"equipment_id": "press-01", "timestamp": "2026-08-20T13:00:00Z", "energy_kwh": 12770}),
            ("calculate_consumption", period),
            ("detect_usage_alerts", period),
            ("get_energy_report", {}),
        ]
        with ServerProcess() as server:
            server.initialize()
            for request_id, (name, arguments) in enumerate(cases, start=10):
                response = server.call_tool(request_id, name, arguments)
                self.assertFalse(response["result"]["isError"], name)
                self.assertIn("structuredContent", response["result"])

    def test_parse_method_params_and_internal_errors(self) -> None:
        with ServerProcess() as server:
            server.send("{bad json")
            self.assertEqual(server.receive()["error"]["code"], -32700)
            server.initialize()
            server.send({"jsonrpc": "2.0", "id": 20, "method": "unknown", "params": {}})
            unknown = server.receive()
            self.assertEqual(unknown["id"], 20)
            self.assertEqual(unknown["error"]["code"], -32601)
            invalid = server.call_tool(21, "record_energy_reading", {"equipment_id": "press-01"})
            self.assertEqual(invalid["id"], 21)
            self.assertEqual(invalid["error"]["code"], -32602)

        class BrokenRegistry:
            def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
                raise RuntimeError("private implementation detail")

        dispatcher = McpDispatcher(registry=BrokenRegistry())  # type: ignore[arg-type]
        dispatcher.initialized = True
        dispatcher.client_initialized = True
        response = dispatcher.handle(
            {"jsonrpc": "2.0", "id": 22, "method": "tools/call", "params": {"name": "broken", "arguments": {}}}
        )
        self.assertEqual(response, {"jsonrpc": "2.0", "id": 22, "error": {"code": -32603, "message": "Internal error"}})

    def test_not_initialized_and_invalid_business_input(self) -> None:
        with ServerProcess() as server:
            server.send({"jsonrpc": "2.0", "id": 30, "method": "tools/list", "params": {}})
            self.assertEqual(server.receive()["error"]["code"], -32002)
            server.initialize()
            response = server.call_tool(
                31,
                "calculate_consumption",
                {"equipment_id": "missing", "start_timestamp": "2026-08-20T08:00:00Z", "end_timestamp": "2026-08-20T12:00:00Z"},
            )
            self.assertEqual(response["error"]["code"], -32602)
            self.assertNotIn("Traceback", json.dumps(response))

    def test_stdout_contains_only_json_lines(self) -> None:
        with ServerProcess() as server:
            server.initialize()
            server.send({"jsonrpc": "2.0", "id": 40, "method": "tools/list", "params": {}})
            server.receive()
            json.loads(server.last_raw_line)


if __name__ == "__main__":
    unittest.main()
