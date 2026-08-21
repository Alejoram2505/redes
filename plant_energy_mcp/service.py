"""Business logic and deterministic in-memory demonstration data."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


EQUIPMENT = {
    "press-01": {
        "name": "Hydraulic press 01",
        "area": "Forming",
        "rated_kw": 75.0,
        "alert_kwh_per_hour": 62.0,
    },
    "chiller-01": {
        "name": "Process chiller 01",
        "area": "Utilities",
        "rated_kw": 45.0,
        "alert_kwh_per_hour": 38.0,
    },
    "compressor-01": {
        "name": "Air compressor 01",
        "area": "Utilities",
        "rated_kw": 55.0,
        "alert_kwh_per_hour": 46.0,
    },
}

INITIAL_READINGS = {
    "press-01": [
        {"timestamp": "2026-08-20T08:00:00Z", "energy_kwh": 12500.0},
        {"timestamp": "2026-08-20T12:00:00Z", "energy_kwh": 12720.0},
    ],
    "chiller-01": [
        {"timestamp": "2026-08-20T08:00:00Z", "energy_kwh": 8300.0},
        {"timestamp": "2026-08-20T12:00:00Z", "energy_kwh": 8428.0},
    ],
    "compressor-01": [
        {"timestamp": "2026-08-20T08:00:00Z", "energy_kwh": 10100.0},
        {"timestamp": "2026-08-20T12:00:00Z", "energy_kwh": 10300.0},
    ],
}


class ToolInputError(ValueError):
    """Safe error caused by invalid tool input."""


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ToolInputError("timestamp must be an ISO 8601 value with a timezone") from exc
    if parsed.tzinfo is None:
        raise ToolInputError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


class EnergyService:
    """Owns demo state and energy calculations independently of JSON-RPC."""

    def __init__(self) -> None:
        self._readings = deepcopy(INITIAL_READINGS)

    def _equipment(self, equipment_id: str) -> dict[str, Any]:
        if equipment_id not in EQUIPMENT:
            raise ToolInputError(f"unknown equipment_id: {equipment_id}")
        return EQUIPMENT[equipment_id]

    def list_equipment(self, arguments: dict[str, Any]) -> dict[str, Any]:
        area = arguments.get("area")
        equipment = [
            {"equipment_id": key, **value}
            for key, value in sorted(EQUIPMENT.items())
            if area is None or value["area"] == area
        ]
        return {"count": len(equipment), "equipment": equipment}

    def record_energy_reading(self, arguments: dict[str, Any]) -> dict[str, Any]:
        equipment_id = arguments["equipment_id"]
        self._equipment(equipment_id)
        parsed = _parse_timestamp(arguments["timestamp"])
        energy_kwh = float(arguments["energy_kwh"])
        readings = self._readings[equipment_id]
        if any(item["timestamp"] == arguments["timestamp"] for item in readings):
            raise ToolInputError("a reading already exists at this timestamp")
        if readings:
            latest = max(readings, key=lambda item: _parse_timestamp(item["timestamp"]))
            if parsed <= _parse_timestamp(latest["timestamp"]):
                raise ToolInputError("timestamp must be later than the latest reading")
            if energy_kwh < latest["energy_kwh"]:
                raise ToolInputError("cumulative energy_kwh cannot decrease")
        reading = {"timestamp": arguments["timestamp"], "energy_kwh": energy_kwh}
        readings.append(reading)
        return {"equipment_id": equipment_id, "recorded": reading}

    def calculate_consumption(self, arguments: dict[str, Any]) -> dict[str, Any]:
        equipment_id = arguments["equipment_id"]
        self._equipment(equipment_id)
        start = _parse_timestamp(arguments["start_timestamp"])
        end = _parse_timestamp(arguments["end_timestamp"])
        if end <= start:
            raise ToolInputError("end_timestamp must be later than start_timestamp")
        indexed = {_parse_timestamp(item["timestamp"]): item for item in self._readings[equipment_id]}
        if start not in indexed or end not in indexed:
            raise ToolInputError("both timestamps must match recorded meter readings")
        consumption = indexed[end]["energy_kwh"] - indexed[start]["energy_kwh"]
        hours = (end - start).total_seconds() / 3600
        return {
            "equipment_id": equipment_id,
            "start_timestamp": arguments["start_timestamp"],
            "end_timestamp": arguments["end_timestamp"],
            "consumption_kwh": round(consumption, 3),
            "average_kwh_per_hour": round(consumption / hours, 3),
        }

    def detect_usage_alerts(self, arguments: dict[str, Any]) -> dict[str, Any]:
        result = self.calculate_consumption(arguments)
        equipment = self._equipment(arguments["equipment_id"])
        observed = result["average_kwh_per_hour"]
        threshold = equipment["alert_kwh_per_hour"]
        return {
            **result,
            "threshold_kwh_per_hour": threshold,
            "alert": observed > threshold,
            "status": "above_threshold" if observed > threshold else "normal",
        }

    def get_energy_report(self, arguments: dict[str, Any]) -> dict[str, Any]:
        area = arguments.get("area")
        rows = []
        for equipment_id, equipment in sorted(EQUIPMENT.items()):
            if area is not None and equipment["area"] != area:
                continue
            readings = sorted(self._readings[equipment_id], key=lambda item: _parse_timestamp(item["timestamp"]))
            first, last = readings[0], readings[-1]
            usage = self.calculate_consumption(
                {
                    "equipment_id": equipment_id,
                    "start_timestamp": first["timestamp"],
                    "end_timestamp": last["timestamp"],
                }
            )
            rows.append(
                {
                    "equipment_id": equipment_id,
                    "area": equipment["area"],
                    "consumption_kwh": usage["consumption_kwh"],
                    "average_kwh_per_hour": usage["average_kwh_per_hour"],
                    "status": (
                        "above_threshold"
                        if usage["average_kwh_per_hour"] > equipment["alert_kwh_per_hour"]
                        else "normal"
                    ),
                }
            )
        return {
            "generated_from": "deterministic in-memory demo data",
            "area": area or "all",
            "equipment_count": len(rows),
            "total_consumption_kwh": round(sum(row["consumption_kwh"] for row in rows), 3),
            "items": rows,
        }

