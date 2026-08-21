"""Minimal subprocess harness demonstrating the complete MCP lifecycle."""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any


def send(process: subprocess.Popen[str], message: dict[str, Any]) -> None:
    assert process.stdin is not None
    process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
    process.stdin.flush()


def receive(process: subprocess.Popen[str]) -> dict[str, Any]:
    assert process.stdout is not None
    line = process.stdout.readline()
    if not line:
        raise RuntimeError("server closed stdout before returning a response")
    return json.loads(line)


def show(label: str, value: dict[str, Any]) -> None:
    print(f"{label}: {json.dumps(value, indent=2, sort_keys=True)}")


def main() -> int:
    process = subprocess.Popen(
        [sys.executable, "-m", "plant_energy_mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        send(
            process,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "plant-energy-demo", "version": "0.1.0"},
                },
            },
        )
        show("initialize", receive(process))
        send(process, {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        send(process, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        show("tools/list", receive(process))
        period = {
            "equipment_id": "press-01",
            "start_timestamp": "2026-08-20T08:00:00Z",
            "end_timestamp": "2026-08-20T12:00:00Z",
        }
        send(
            process,
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "calculate_consumption", "arguments": period}},
        )
        show("tools/call calculate_consumption", receive(process))
        send(
            process,
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "detect_usage_alerts", "arguments": period}},
        )
        show("tools/call detect_usage_alerts", receive(process))
    finally:
        if process.stdin:
            process.stdin.close()
        return_code = process.wait(timeout=5)
        stderr = process.stderr.read() if process.stderr else ""
        print(f"server exit code: {return_code}")
        print(f"server stderr: {stderr.strip()}")
        if process.stdout:
            process.stdout.close()
        if process.stderr:
            process.stderr.close()
    return 0 if return_code == 0 else return_code


if __name__ == "__main__":
    raise SystemExit(main())
