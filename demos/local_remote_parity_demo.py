"""Compare the local and configured remote Plant Energy MCP tool behavior."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from mcp_host.client import RemoteHttpMcpClient, StdioMcpClient


def main() -> int:
    root = Path.cwd().resolve()
    import os

    url = os.environ.get("PLANT_MCP_REMOTE_URL", "http://127.0.0.1:8080/mcp")
    token = os.environ.get("PLANT_MCP_AUTH_TOKEN", "")
    with (
        StdioMcpClient("plant-local", [sys.executable, "-m", "plant_energy_mcp"], cwd=root) as local,
        RemoteHttpMcpClient("plant-remote", url, token=token) as remote,
    ):
        local_result = local.call_tool("get_energy_report", {})["structuredContent"]
        remote_result = remote.call_tool("get_energy_report", {})["structuredContent"]
        print(
            json.dumps(
                {"equal": local_result == remote_result, "local": local_result, "remote": remote_result},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0 if local_result == remote_result else 1


if __name__ == "__main__":
    raise SystemExit(main())
