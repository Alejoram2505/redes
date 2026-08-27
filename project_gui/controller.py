"""Testable helpers used by the desktop interface."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit

MARKDOWN_URL = re.compile(r"^\[(https?://[^\]]+)]\((https?://[^)]+)\)$")


def tool_argument_template(schema: dict[str, Any]) -> dict[str, Any]:
    """Build an editable JSON template containing only required tool arguments."""
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    if not isinstance(properties, dict) or not isinstance(required, list):
        return {}

    def placeholder(definition: Any) -> Any:
        if not isinstance(definition, dict):
            return ""
        if "default" in definition:
            return definition["default"]
        kind = definition.get("type")
        if not isinstance(kind, str):
            return ""
        return {"boolean": False, "integer": 0, "number": 0, "array": [], "object": {}}.get(kind, "")

    return {name: placeholder(properties.get(name)) for name in required if isinstance(name, str)}


def parse_tool_arguments(text: str) -> dict[str, Any]:
    value = json.loads(text or "{}")
    if not isinstance(value, dict):
        raise ValueError("Los parámetros deben ser un objeto JSON, por ejemplo: {}")
    return value


def normalize_url(value: str) -> str:
    """Return a plain HTTP URL, accepting accidental Markdown link syntax."""
    cleaned = value.strip().strip("`").strip()
    match = MARKDOWN_URL.fullmatch(cleaned)
    if match:
        cleaned = match.group(1)
    parsed = urlsplit(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("La URL debe comenzar con http:// o https://")
    return cleaned.rstrip("/")


def health_url(mcp_url: str) -> str:
    """Build the health endpoint URL belonging to an MCP endpoint."""
    parsed = urlsplit(normalize_url(mcp_url))
    return urlunsplit((parsed.scheme, parsed.netloc, "/health", "", ""))


@dataclass(frozen=True)
class RuntimeSettings:
    api_key: str
    model: str
    base_url: str
    remote_url: str
    remote_token: str

    def validate(self, *, require_llm: bool = True, require_remote: bool = True) -> None:
        if require_llm and not self.api_key.strip():
            raise ValueError("Pega la API key de Gemini para conectar el chatbot.")
        if require_llm and not self.model.strip():
            raise ValueError("El modelo de Gemini no puede estar vacío.")
        normalize_url(self.base_url)
        if require_remote:
            normalize_url(self.remote_url)
            if not self.remote_token.strip():
                raise ValueError("Pega el token MCP de Render para usar el servidor remoto.")

    def environment(self, base: Mapping[str, str] | None = None) -> dict[str, str]:
        env = dict(base or os.environ)
        env.update(
            {
                "LLM_PROVIDER": "openai",
                "LLM_API_KEY": self.api_key.strip(),
                "LLM_MODEL": self.model.strip(),
                "LLM_BASE_URL": normalize_url(self.base_url),
                "PLANT_MCP_REMOTE_URL": normalize_url(self.remote_url),
                "PLANT_MCP_AUTH_TOKEN": self.remote_token.strip(),
            }
        )
        return env


def run_module(module: str, settings: RuntimeSettings, root: Path, *, timeout: int = 180) -> str:
    """Run one documented demo with the interface configuration."""
    completed = subprocess.run(
        [sys.executable, "-m", module],
        cwd=root,
        env=settings.environment(),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    output = "\n".join(part.strip() for part in (completed.stdout, completed.stderr) if part.strip())
    if completed.returncode:
        raise RuntimeError(output or f"El comando terminó con código {completed.returncode}")
    return output or "Comando completado correctamente."
