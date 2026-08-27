"""Safe, explicit MCP server configuration for the terminal host and demos."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any

from .client import RemoteHttpMcpClient, StdioMcpClient
from .logging import McpAuditLogger


def create_clients(
    names: list[str], project_root: Path | None = None, demo_repo_path: Path | None = None
) -> tuple[list[Any], list[str]]:
    root = (project_root or Path.cwd()).resolve()
    demo_root = (root / "demo_workspace").resolve()
    demo_repo = (demo_repo_path or demo_root / "git_repo").resolve()
    if demo_root != demo_repo and demo_root not in demo_repo.parents:
        raise ValueError("demo Git repository must be inside demo_workspace")
    demo_root.mkdir(parents=True, exist_ok=True)
    demo_repo.mkdir(parents=True, exist_ok=True)
    logger = McpAuditLogger(project_root=root)
    clients: list[Any] = []
    notes: list[str] = []
    for name in names:
        if name == "plant-local":
            clients.append(StdioMcpClient(name, [sys.executable, "-m", "plant_energy_mcp"], cwd=root, logger=logger))
        elif name == "filesystem":
            command = (
                ["cmd", "/c", "npx", "-y", "@modelcontextprotocol/server-filesystem", str(demo_root)]
                if os.name == "nt"
                else ["npx", "-y", "@modelcontextprotocol/server-filesystem", str(demo_root)]
            )
            clients.append(StdioMcpClient(name, command, cwd=root, logger=logger, timeout=30))
        elif name == "git":
            if shutil.which("uvx"):
                command = ["uvx", "mcp-server-git", "--repository", str(demo_repo)]
            elif shutil.which("mcp-server-git"):
                command = ["mcp-server-git", "--repository", str(demo_repo)]
            else:
                command = [
                    sys.executable,
                    "-c",
                    "from mcp_server_git import main; main()",
                    "--repository",
                    str(demo_repo),
                ]
                notes.append(
                    "Git MCP uses the current Python interpreter because uvx/console script was not found; "
                    "install mcp-server-git in this environment."
                )
            clients.append(StdioMcpClient(name, command, cwd=root, logger=logger, timeout=30))
        elif name == "plant-remote":
            clients.append(
                RemoteHttpMcpClient(
                    name,
                    os.environ.get("PLANT_MCP_REMOTE_URL", "http://127.0.0.1:8080/mcp"),
                    token=os.environ.get("PLANT_MCP_AUTH_TOKEN", ""),
                    logger=logger,
                )
            )
        else:
            notes.append(f"Unknown MCP server name ignored: {name}")
    return clients, notes
