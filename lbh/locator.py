from __future__ import annotations

import json

from .contracts import LocatorResult


def build_locator_prompt(target: str, observation: dict) -> str:
    return "\n".join(
        [
            "You are locating a GUI target in a resized screenshot for LBH V2.",
            f"Target: {target}",
            "Return JSON only.",
            "Coordinates must be in resized_image space.",
            "Use either center or bbox.",
            "",
            "Valid JSON shape:",
            json.dumps(
                {
                    "target": target,
                    "center": {"x": 640, "y": 360, "space": "resized_image"},
                    "confidence": 0.92,
                    "source": "model",
                    "reason": "The target is clearly visible in the screenshot.",
                },
                ensure_ascii=False,
                indent=2,
            ),
            "",
            f"Screenshot path: {observation.get('screenshot_path')}",
            f"Image size: {observation.get('image_width')}x{observation.get('image_height')}",
            f"Coordinate space: {observation.get('coordinate_space_name')}",
        ]
    )


def parse_locator_response(text: str) -> LocatorResult:
    return LocatorResult.from_dict(json.loads(text))
