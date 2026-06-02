from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Literal


class CoordSpace(str, Enum):
    DESKTOP = "desktop"
    RESIZED_IMAGE = "resized_image"
    CROP_IMAGE = "crop_image"
    WINDOW = "window"


@dataclass(frozen=True)
class Point:
    x: int
    y: int
    space: CoordSpace

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Point":
        return cls(x=int(data["x"]), y=int(data["y"]), space=CoordSpace(data["space"]))

    def to_dict(self) -> dict[str, Any]:
        return {"x": self.x, "y": self.y, "space": self.space.value}


@dataclass(frozen=True)
class BBox:
    x1: int
    y1: int
    x2: int
    y2: int
    space: CoordSpace

    @property
    def width(self) -> int:
        return max(0, self.x2 - self.x1)

    @property
    def height(self) -> int:
        return max(0, self.y2 - self.y1)

    @property
    def center(self) -> Point:
        return Point((self.x1 + self.x2) // 2, (self.y1 + self.y2) // 2, self.space)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BBox":
        return cls(
            x1=int(data["x1"]),
            y1=int(data["y1"]),
            x2=int(data["x2"]),
            y2=int(data["y2"]),
            space=CoordSpace(data["space"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "x1": self.x1,
            "y1": self.y1,
            "x2": self.x2,
            "y2": self.y2,
            "space": self.space.value,
            "width": self.width,
            "height": self.height,
        }


@dataclass
class ActiveWindow:
    title: str | None = None
    left: int | None = None
    top: int | None = None
    width: int | None = None
    height: int | None = None
    right: int | None = None
    bottom: int | None = None
    is_active: bool | None = None
    is_minimized: bool | None = None
    is_maximized: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Observation:
    task_id: str
    image_path: str
    coordinate_system: Literal["resized_image"]
    image_width: int
    image_height: int
    desktop_width: int
    desktop_height: int
    scale_x_to_desktop: float
    scale_y_to_desktop: float
    jpeg_quality: int
    image_bytes: int
    screenshot_hash: str
    active_window: ActiveWindow | None = None
    original_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if self.active_window:
            payload["active_window"] = self.active_window.to_dict()
        return payload


AtomicActionType = Literal[
    "click",
    "double_click",
    "type_text",
    "press",
    "hotkey",
    "wait",
    "clipboard_set",
    "window_activate",
    "noop",
]


@dataclass
class AtomicAction:
    type: AtomicActionType
    point: Point | None = None
    text: str | None = None
    key: str | None = None
    keys: list[str] | None = None
    seconds: float | None = None
    title_contains: str | None = None
    button: Literal["left", "middle", "right"] = "left"
    clicks: int = 1
    reason: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AtomicAction":
        point = None
        if data.get("point"):
            point = Point.from_dict(data["point"])
        # Convenience: allow {"x":..., "y":..., "space":...}
        elif all(k in data for k in ("x", "y", "space")):
            point = Point(x=int(data["x"]), y=int(data["y"]), space=CoordSpace(data["space"]))
        return cls(
            type=data["type"],
            point=point,
            text=data.get("text"),
            key=data.get("key"),
            keys=list(data.get("keys") or []) or None,
            seconds=float(data["seconds"]) if data.get("seconds") is not None else None,
            title_contains=data.get("title_contains"),
            button=data.get("button", "left"),
            clicks=int(data.get("clicks", 1)),
            reason=data.get("reason"),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if self.point:
            payload["point"] = self.point.to_dict()
        payload = {k: v for k, v in payload.items() if v is not None}
        return payload


@dataclass
class ActionBatch:
    actions: list[AtomicAction]
    observe_after: bool = True
    max_duration_ms: int | None = None
    stop_conditions: list[str] = field(default_factory=list)
    expected_observation: dict[str, Any] | None = None
    reason: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | list[dict[str, Any]]) -> "ActionBatch":
        if isinstance(data, list):
            return cls(actions=[AtomicAction.from_dict(item) for item in data])
        return cls(
            actions=[AtomicAction.from_dict(item) for item in data.get("actions", [])],
            observe_after=bool(data.get("observe_after", True)),
            max_duration_ms=data.get("max_duration_ms"),
            stop_conditions=list(data.get("stop_conditions") or []),
            expected_observation=data.get("expected_observation"),
            reason=data.get("reason"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "actions": [a.to_dict() for a in self.actions],
            "observe_after": self.observe_after,
            "max_duration_ms": self.max_duration_ms,
            "stop_conditions": self.stop_conditions,
            "expected_observation": self.expected_observation,
            "reason": self.reason,
        }


@dataclass
class LocatorResult:
    target: str
    center: Point | None
    bbox: BBox | None
    confidence: float
    source: str
    evidence_path: str | None = None
    reason: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LocatorResult":
        center = Point.from_dict(data["center"]) if data.get("center") else None
        bbox = BBox.from_dict(data["bbox"]) if data.get("bbox") else None
        return cls(
            target=data["target"],
            center=center,
            bbox=bbox,
            confidence=float(data.get("confidence", 0.0)),
            source=data.get("source", "unknown"),
            evidence_path=data.get("evidence_path"),
            reason=data.get("reason"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "center": self.center.to_dict() if self.center else None,
            "bbox": self.bbox.to_dict() if self.bbox else None,
            "confidence": self.confidence,
            "source": self.source,
            "evidence_path": self.evidence_path,
            "reason": self.reason,
        }


@dataclass
class TaskState:
    task_id: str
    goal: str
    task_dir: str
    status: str = "active"
    created_at: str | None = None
    updated_at: str | None = None
    latest_observation: dict[str, Any] | None = None
    latest_action_result: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
