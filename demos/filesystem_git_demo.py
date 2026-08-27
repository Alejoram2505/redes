"""Opt-in demo using official Filesystem and Git MCP servers in an isolated repo."""

from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path

from mcp_host.config import create_clients


def main() -> int:
    root = Path.cwd().resolve()
    workspace = (root / "demo_workspace").resolve()
    if workspace.parent != root:
        raise RuntimeError("demo workspace resolved outside the project root")
    repo = workspace / f"git_repo_{uuid.uuid4().hex[:8]}"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "MCP Demo"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "mcp-demo@example.invalid"], check=True)
    clients, notes = create_clients(["filesystem", "git"], root, demo_repo_path=repo)
    for note in notes:
        print(note)
    started = []
    try:
        for client in clients:
            started.append(client.start())
        filesystem, git = started
        write = filesystem.call_tool(
            "write_file", {"path": str(repo / "README.md"), "content": "# MCP isolated demo\n"}
        )
        add = git.call_tool("git_add", {"repo_path": str(repo), "files": ["README.md"]})
        commit = git.call_tool("git_commit", {"repo_path": str(repo), "message": "docs: create isolated MCP demo"})
        print(
            json.dumps(
                {"repository": str(repo), "write": write, "add": add, "commit": commit}, ensure_ascii=False, indent=2
            )
        )
    finally:
        for client in started:
            client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
