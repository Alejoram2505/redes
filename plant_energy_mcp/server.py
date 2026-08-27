"""Line-delimited stdio transport for the manual MCP implementation."""

from __future__ import annotations

import json
import sys
from typing import TextIO

from .protocol import JsonRpcError, McpDispatcher, error_response


def serve(stdin: TextIO, stdout: TextIO, stderr: TextIO) -> int:
    dispatcher = McpDispatcher()
    for raw_line in stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            message = dispatcher.parse_line(line)
            response = dispatcher.handle(message)
        except JsonRpcError as exc:
            response = error_response(None, exc.code, exc.message, exc.data)
        if response is not None:
            stdout.write(json.dumps(response, separators=(",", ":"), ensure_ascii=True) + "\n")
            stdout.flush()
    stderr.write("plant-energy-mcp: stdin closed; shutting down cleanly\n")
    stderr.flush()
    return 0


def main() -> int:
    return serve(sys.stdin, sys.stdout, sys.stderr)
