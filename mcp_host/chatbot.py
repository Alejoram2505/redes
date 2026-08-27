"""Terminal chatbot that connects an LLM to manually implemented MCP clients."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from .llm import LlmProvider
from .logging import McpAuditLogger


class ToolClient(Protocol):
    name: str

    def list_tools(self) -> list[dict[str, Any]]: ...
    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...
    def close(self) -> None: ...


SENSITIVE_WORDS = ("write", "create", "delete", "move", "commit", "add", "record", "set", "remove")


@dataclass
class RoutedTool:
    exposed_name: str
    original_name: str
    client: ToolClient
    definition: dict[str, Any]

    @property
    def sensitive(self) -> bool:
        lowered = self.original_name.lower()
        return any(word in lowered for word in SENSITIVE_WORDS)


class ChatSession:
    def __init__(
        self,
        provider: LlmProvider,
        clients: list[ToolClient],
        *,
        confirm: Callable[[str], bool] | None = None,
        logger: McpAuditLogger | None = None,
    ) -> None:
        self.provider, self.clients = provider, clients
        self.confirm = confirm or (
            lambda prompt: input(f"{prompt} [s/N]: ").strip().lower() in {"s", "si", "sí", "y", "yes"}
        )
        self.logger = logger or McpAuditLogger()
        self.messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": "You are a helpful assistant. Use MCP tools only when useful. Never invent tool results.",
            }
        ]
        self.tools: dict[str, RoutedTool] = {}
        self.failures: dict[str, str] = {}
        self.refresh_tools()

    def refresh_tools(self) -> None:
        self.tools.clear()
        for client in self.clients:
            try:
                for definition in client.list_tools():
                    original = definition["name"]
                    exposed = f"{client.name}__{original}".replace("-", "_")
                    routed_def = {
                        **definition,
                        "name": exposed,
                        "description": f"[{client.name}] {definition.get('description', '')}",
                    }
                    self.tools[exposed] = RoutedTool(exposed, original, client, routed_def)
                self.failures.pop(client.name, None)
            except Exception as exc:
                self.failures[client.name] = str(exc)

    def ask(self, text: str, *, max_tool_rounds: int = 6) -> str:
        self.messages.append({"role": "user", "content": text})
        for _ in range(max_tool_rounds):
            reply = self.provider.complete(self.messages, [item.definition for item in self.tools.values()])
            assistant: dict[str, Any] = {"role": "assistant", "content": reply.text or ""}
            if reply.tool_calls:
                assistant["tool_calls"] = [
                    {
                        "id": call["id"],
                        "type": "function",
                        "function": {"name": call["name"], "arguments": json.dumps(call.get("arguments", {}))},
                    }
                    for call in reply.tool_calls
                ]
            self.messages.append(assistant)
            if not reply.tool_calls:
                return reply.text
            for call in reply.tool_calls:
                result = self._execute(call["name"], call.get("arguments", {}))
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "name": call["name"],
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
        raise RuntimeError("LLM exceeded the tool-call round limit")

    def _execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        routed = self.tools.get(name)
        if routed is None:
            return {"isError": True, "error": f"Unknown tool: {name}"}
        if routed.sensitive and not self.confirm(f"La herramienta {name} tendrá efectos laterales. ¿Autorizar?"):
            return {"isError": True, "error": "Tool execution declined by the user"}
        try:
            return routed.client.call_tool(routed.original_name, arguments)
        except Exception as exc:
            self.failures[routed.client.name] = str(exc)
            return {"isError": True, "error": f"MCP server {routed.client.name} failed: {exc}"}

    def close(self) -> None:
        for client in self.clients:
            try:
                client.close()
            except Exception:
                pass
