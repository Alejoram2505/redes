"""Small replaceable LLM adapters using only HTTP from the Python standard library."""

from __future__ import annotations

import json
import os
import random
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class LlmReply:
    text: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


class LlmProvider(Protocol):
    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LlmReply: ...


TRANSIENT_HTTP_CODES = {408, 429, 500, 502, 503, 504}


def _http_error_detail(exc: urllib.error.HTTPError) -> str:
    """Return only the provider's structured status/message, never the request."""
    try:
        data = json.loads(exc.read(16_384))
    except (AttributeError, json.JSONDecodeError, OSError, TypeError, UnicodeDecodeError):
        return ""
    error = data.get("error") if isinstance(data, dict) else None
    if not isinstance(error, dict):
        return ""
    status = str(error.get("status") or "").strip()
    message = " ".join(str(error.get("message") or "").split())[:500]
    parts = [part for part in (status, message) if part]
    return f": {' — '.join(parts)}" if parts else ""


def _post_json(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: float = 60,
    max_attempts: int = 4,
) -> dict[str, Any]:
    for attempt in range(max_attempts):
        request = urllib.request.Request(
            url, json.dumps(payload).encode(), headers={"Content-Type": "application/json", **headers}, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            code = exc.code
            detail = _http_error_detail(exc)
            exc.close()
            if code not in TRANSIENT_HTTP_CODES:
                # Do not expose response bodies, which could repeat sensitive input.
                raise RuntimeError(f"LLM API returned HTTP {code}{detail}") from exc
            if attempt == max_attempts - 1:
                raise RuntimeError(
                    f"LLM API temporarily unavailable after {max_attempts} attempts (HTTP {code}). Try again shortly."
                ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == max_attempts - 1:
                raise RuntimeError(f"LLM API network error after {max_attempts} attempts") from exc
        delay = (2**attempt) + random.uniform(0, 0.25 * (2**attempt))
        time.sleep(delay)
    raise RuntimeError("LLM API request failed")


class OpenAiProvider:
    def __init__(self, api_key: str, model: str, base_url: str = "https://api.openai.com/v1") -> None:
        self.api_key, self.model = api_key, model
        self.url = base_url.rstrip("/") + "/chat/completions"

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LlmReply:
        schema = [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("inputSchema", {"type": "object"}),
                },
            }
            for tool in tools
        ]
        payload: dict[str, Any] = {"model": self.model, "messages": messages}
        if schema:
            payload["tools"] = schema
        data = _post_json(self.url, {"Authorization": f"Bearer {self.api_key}"}, payload)
        message = data["choices"][0]["message"]
        calls = []
        for call in message.get("tool_calls", []):
            parsed_call = {
                "id": call["id"],
                "name": call["function"]["name"],
                "arguments": json.loads(call["function"].get("arguments") or "{}"),
            }
            # Gemini 3 returns its required thought signature here. It must be
            # replayed unchanged with the assistant tool call on the next turn.
            if "extra_content" in call:
                parsed_call["extra_content"] = call["extra_content"]
            calls.append(parsed_call)
        return LlmReply(message.get("content") or "", calls)


class AnthropicProvider:
    def __init__(self, api_key: str, model: str, base_url: str = "https://api.anthropic.com/v1") -> None:
        self.api_key, self.model = api_key, model
        self.url = base_url.rstrip("/") + "/messages"

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LlmReply:
        system = "You are a helpful industrial plant assistant."
        converted: list[dict[str, Any]] = []
        for message in messages:
            if message["role"] == "system":
                system = message["content"]
            elif message["role"] in {"user", "assistant"} and "tool_calls" not in message:
                converted.append(message)
            elif message["role"] == "assistant":
                blocks: list[dict[str, Any]] = []
                if message.get("content"):
                    blocks.append({"type": "text", "text": message["content"]})
                blocks.extend(
                    {
                        "type": "tool_use",
                        "id": call["id"],
                        "name": call["function"]["name"],
                        "input": json.loads(call["function"].get("arguments") or "{}"),
                    }
                    for call in message.get("tool_calls", [])
                )
                converted.append({"role": "assistant", "content": blocks})
            elif message["role"] == "tool":
                block = {"type": "tool_result", "tool_use_id": message["tool_call_id"], "content": message["content"]}
                if converted and converted[-1]["role"] == "user" and isinstance(converted[-1]["content"], list):
                    converted[-1]["content"].append(block)
                else:
                    converted.append({"role": "user", "content": [block]})
        schema = [
            {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "input_schema": tool.get("inputSchema", {"type": "object"}),
            }
            for tool in tools
        ]
        payload = {"model": self.model, "max_tokens": 1024, "system": system, "messages": converted}
        if schema:
            payload["tools"] = schema
        data = _post_json(self.url, {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}, payload)
        texts, calls = [], []
        for block in data.get("content", []):
            if block.get("type") == "text":
                texts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                calls.append({"id": block["id"], "name": block["name"], "arguments": block.get("input", {})})
        return LlmReply("\n".join(texts), calls)


def provider_from_env() -> LlmProvider:
    api_key = os.environ.get("LLM_API_KEY", "")
    model = os.environ.get("LLM_MODEL", "")
    provider = os.environ.get("LLM_PROVIDER", "openai").lower()
    if not api_key:
        raise RuntimeError("LLM_API_KEY is missing. Set it in the environment; the key will not be printed.")
    if not model:
        raise RuntimeError("LLM_MODEL is missing. Set the model identifier supplied by your provider.")
    base_url = os.environ.get("LLM_BASE_URL", "")
    if provider == "openai":
        return OpenAiProvider(api_key, model, base_url or "https://api.openai.com/v1")
    if provider == "anthropic":
        return AnthropicProvider(api_key, model, base_url or "https://api.anthropic.com/v1")
    raise RuntimeError("LLM_PROVIDER must be 'openai' or 'anthropic'")
