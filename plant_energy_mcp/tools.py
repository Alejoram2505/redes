"""MCP tool definitions, input validation, and business dispatch."""

from __future__ import annotations

from typing import Any, Callable

from .service import EnergyService, ToolInputError


AREA_SCHEMA = {"type": "string", "enum": ["Forming", "Utilities"]}
PERIOD_PROPERTIES = {
    "equipment_id": {"type": "string", "minLength": 1},
    "start_timestamp": {"type": "string", "format": "date-time"},
    "end_timestamp": {"type": "string", "format": "date-time"},
}

TOOL_DEFINITIONS = [
    {
        "name": "list_equipment",
        "description": "List registered plant equipment, optionally filtered by area.",
        "inputSchema": {
            "type": "object",
            "properties": {"area": AREA_SCHEMA},
            "additionalProperties": False,
        },
    },
    {
        "name": "record_energy_reading",
        "description": "Record a cumulative energy meter reading for equipment in the current demo session.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "equipment_id": {"type": "string", "minLength": 1},
                "timestamp": {"type": "string", "format": "date-time"},
                "energy_kwh": {"type": "number", "minimum": 0, "maximum": 1000000000},
            },
            "required": ["equipment_id", "timestamp", "energy_kwh"],
            "additionalProperties": False,
        },
    },
    {
        "name": "calculate_consumption",
        "description": "Calculate consumption between two recorded cumulative meter readings.",
        "inputSchema": {
            "type": "object",
            "properties": PERIOD_PROPERTIES,
            "required": ["equipment_id", "start_timestamp", "end_timestamp"],
            "additionalProperties": False,
        },
    },
    {
        "name": "detect_usage_alerts",
        "description": "Compare average energy use for a recorded period with the equipment threshold.",
        "inputSchema": {
            "type": "object",
            "properties": PERIOD_PROPERTIES,
            "required": ["equipment_id", "start_timestamp", "end_timestamp"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_energy_report",
        "description": "Summarize consumption and threshold status from the first to latest reading.",
        "inputSchema": {
            "type": "object",
            "properties": {"area": AREA_SCHEMA},
            "additionalProperties": False,
        },
    },
]


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "object":
        return isinstance(value, dict)
    return False


def validate_arguments(arguments: Any, schema: dict[str, Any]) -> dict[str, Any]:
    """Validate the supported JSON Schema subset without an external dependency."""
    if not isinstance(arguments, dict):
        raise ToolInputError("arguments must be an object")
    properties = schema.get("properties", {})
    missing = [name for name in schema.get("required", []) if name not in arguments]
    if missing:
        raise ToolInputError(f"missing required parameter(s): {', '.join(missing)}")
    unexpected = sorted(set(arguments) - set(properties))
    if schema.get("additionalProperties") is False and unexpected:
        raise ToolInputError(f"unexpected parameter(s): {', '.join(unexpected)}")
    for name, value in arguments.items():
        rule = properties[name]
        if not _matches_type(value, rule["type"]):
            raise ToolInputError(f"{name} must be of type {rule['type']}")
        if "minLength" in rule and len(value) < rule["minLength"]:
            raise ToolInputError(f"{name} must not be empty")
        if "minimum" in rule and value < rule["minimum"]:
            raise ToolInputError(f"{name} must be at least {rule['minimum']}")
        if "maximum" in rule and value > rule["maximum"]:
            raise ToolInputError(f"{name} must be at most {rule['maximum']}")
        if "enum" in rule and value not in rule["enum"]:
            raise ToolInputError(f"{name} must be one of: {', '.join(rule['enum'])}")
    return arguments


class ToolRegistry:
    def __init__(self, service: EnergyService | None = None) -> None:
        self.service = service or EnergyService()
        self._handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "list_equipment": self.service.list_equipment,
            "record_energy_reading": self.service.record_energy_reading,
            "calculate_consumption": self.service.calculate_consumption,
            "detect_usage_alerts": self.service.detect_usage_alerts,
            "get_energy_report": self.service.get_energy_report,
        }
        self._schemas = {tool["name"]: tool["inputSchema"] for tool in TOOL_DEFINITIONS}

    def list_tools(self) -> list[dict[str, Any]]:
        return TOOL_DEFINITIONS

    def call(self, name: str, arguments: Any) -> dict[str, Any]:
        if name not in self._handlers:
            raise ToolInputError(f"unknown tool: {name}")
        validated = validate_arguments(arguments, self._schemas[name])
        return self._handlers[name](validated)

