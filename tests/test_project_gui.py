from __future__ import annotations

import unittest

from project_gui.controller import (
    RuntimeSettings,
    health_url,
    normalize_url,
    parse_tool_arguments,
    tool_argument_template,
)


class ProjectGuiControllerTests(unittest.TestCase):
    def test_normalize_url_accepts_plain_and_markdown_links(self) -> None:
        plain = "https://plant-energy-mcp.onrender.com/mcp"
        markdown = f"[{plain}]({plain})"
        self.assertEqual(normalize_url(plain), plain)
        self.assertEqual(normalize_url(markdown), plain)

    def test_normalize_url_rejects_non_http_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "http"):
            normalize_url("plant-energy-mcp.onrender.com/mcp")

    def test_health_url_replaces_mcp_path(self) -> None:
        self.assertEqual(
            health_url("https://plant-energy-mcp.onrender.com/mcp"),
            "https://plant-energy-mcp.onrender.com/health",
        )

    def test_runtime_settings_builds_sanitized_environment(self) -> None:
        settings = RuntimeSettings(
            api_key=" key ",
            model="gemini-3.1-flash-lite",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            remote_url="[https://example.test/mcp](https://example.test/mcp)",
            remote_token=" token ",
        )
        env = settings.environment({"EXISTING": "value"})
        self.assertEqual(env["EXISTING"], "value")
        self.assertEqual(env["LLM_API_KEY"], "key")
        self.assertEqual(env["PLANT_MCP_REMOTE_URL"], "https://example.test/mcp")
        self.assertEqual(env["PLANT_MCP_AUTH_TOKEN"], "token")

    def test_tool_argument_template_and_parser(self) -> None:
        schema = {
            "type": "object",
            "properties": {"area": {"type": "string"}, "hours": {"type": "integer", "default": 4}},
            "required": ["area", "hours"],
        }
        self.assertEqual(tool_argument_template(schema), {"area": "", "hours": 4})
        self.assertEqual(parse_tool_arguments('{"area":"Utilities"}'), {"area": "Utilities"})
        with self.assertRaisesRegex(ValueError, "objeto JSON"):
            parse_tool_arguments("[]")


if __name__ == "__main__":
    unittest.main()
