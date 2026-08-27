"""Sanitized JSONL audit log for MCP interactions."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SENSITIVE = re.compile(r"(authorization|api[-_]?key|token|secret|password)", re.IGNORECASE)


def redact(value: Any, project_root: Path | None = None) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if SENSITIVE.search(str(key)) else redact(item, project_root)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item, project_root) for item in value]
    if isinstance(value, str):
        text = SENSITIVE.sub("[REDACTED]", value)
        if project_root:
            text = text.replace(str(project_root), "[PROJECT_ROOT]")
        return text[:500] + ("…" if len(text) > 500 else "")
    return value


class McpAuditLogger:
    def __init__(self, path: Path | str = ".runtime/mcp_interactions.jsonl", project_root: Path | None = None) -> None:
        self.path = Path(path)
        self.project_root = (project_root or Path.cwd()).resolve()

    def write(
        self,
        *,
        server: str,
        transport: str,
        direction: str,
        method: str | None,
        request_id: Any = None,
        duration_ms: float | None = None,
        summary: Any = None,
        error_code: Any = None,
    ) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "server": server,
            "transport": transport,
            "direction": direction,
            "method": method,
            "id": request_id,
            "duration_ms": None if duration_ms is None else round(duration_ms, 2),
            "summary": redact(summary, self.project_root),
            "error_code": error_code,
        }
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")

    def tail(self, count: int = 20) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()[-count:]
        return [json.loads(line) for line in lines]
