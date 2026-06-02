from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import BBox, CoordSpace, LocatorResult, Point


LOCATOR_JSON_SCHEMA = {
    "target": "string",
    "center": {"x": "int", "y": "int", "space": "resized_image"},
    "bbox": {"x1": "int", "y1": "int", "x2": "int", "y2": "int", "space": "resized_image"},
    "confidence": "float 0..1",
    "source": "llm|cache|cv|human",
    "reason": "short string",
}


class LocatorContract:
    """Prompt/JSON contract for an external brain.

    LBH V2 does not hardcode a model provider. Codex, LangGraph, or another
    controller should call `build_prompt`, inspect the resized screenshot, and
    return JSON matching the schema.
    """

    @staticmethod
    def build_prompt(target: str, observation: dict[str, Any]) -> str:
        return f"""You are locating a GUI element in a resized desktop screenshot.
Return JSON only.

Target: {target}

Coordinate contract:
- The screenshot coordinate space is `resized_image`.
- Do not return desktop coordinates.
- If uncertain, return center=null and bbox=null with confidence below 0.5.

Observation:
{json.dumps(observation, ensure_ascii=False, indent=2)}

Required JSON shape:
{{
  "target": {json.dumps(target, ensure_ascii=False)},
  "center": {{"x": 0, "y": 0, "space": "resized_image"}} | null,
  "bbox": {{"x1": 0, "y1": 0, "x2": 0, "y2": 0, "space": "resized_image"}} | null,
  "confidence": 0.0,
  "source": "llm",
  "reason": "short reason"
}}
"""

    @staticmethod
    def parse_response(text: str) -> LocatorResult:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            # naive fenced JSON extraction
            cleaned = cleaned.strip("`")
            if "\n" in cleaned:
                cleaned = cleaned.split("\n", 1)[1]
        data = json.loads(cleaned)
        if data.get("center"):
            data["center"]["space"] = data["center"].get("space", "resized_image")
        if data.get("bbox"):
            data["bbox"]["space"] = data["bbox"].get("space", "resized_image")
        return LocatorResult.from_dict(data)


class LocatorCache:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []

    def _save(self, entries: list[dict[str, Any]]) -> None:
        self.path.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def get(self, target: str, screenshot_hash: str, active_window_title: str | None) -> LocatorResult | None:
        for entry in reversed(self._load()):
            if entry.get("target") == target and entry.get("screenshot_hash") == screenshot_hash and entry.get("active_window_title") == active_window_title:
                result = LocatorResult.from_dict(entry["result"])
                result.source = "cache"
                return result
        return None

    def put(self, target: str, screenshot_hash: str, active_window_title: str | None, result: LocatorResult) -> None:
        entries = self._load()
        entries.append(
            {
                "target": target,
                "screenshot_hash": screenshot_hash,
                "active_window_title": active_window_title,
                "result": result.to_dict(),
            }
        )
        self._save(entries[-300:])
