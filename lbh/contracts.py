from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any, Mapping

from .common import DEFAULT_JPEG_QUALITY, DEFAULT_MODEL_MAX_WIDTH, DEFAULT_NO_PROGRESS_THRESHOLD
from .coordinates import Box, CoordinateSpace, CoordinateTransform, Point, Size
from .errors import ValidationError


VALID_BUTTONS = {"left", "middle", "right"}
POINT_ACTIONS = {"click", "double_click"}
ACTION_TYPES = {
    "click",
    "double_click",
    "type_text",
    "press",
    "hotkey",
    "wait",
    "clipboard_set",
    "clipboard_get",
    "window_activate",
    "window_minimize",
    "window_maximize",
    "window_restore",
    "close_window",
}


@dataclass(frozen=True)
class WindowMetadata:
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

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | None) -> "WindowMetadata | None":
        if not payload:
            return None
        return cls(
            title=payload.get("title"),
            left=payload.get("left"),
            top=payload.get("top"),
            width=payload.get("width"),
            height=payload.get("height"),
            right=payload.get("right"),
            bottom=payload.get("bottom"),
            is_active=payload.get("is_active"),
            is_minimized=payload.get("is_minimized"),
            is_maximized=payload.get("is_maximized"),
        )

    def desktop_box(self) -> Box | None:
        if None in (self.left, self.top, self.right, self.bottom):
            return None
        return Box(
            left=float(self.left),
            top=float(self.top),
            right=float(self.right),
            bottom=float(self.bottom),
            space=CoordinateSpace.DESKTOP,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "left": self.left,
            "top": self.top,
            "width": self.width,
            "height": self.height,
            "right": self.right,
            "bottom": self.bottom,
            "is_active": self.is_active,
            "is_minimized": self.is_minimized,
            "is_maximized": self.is_maximized,
        }


@dataclass
class ObservationRecord:
    observation_id: str
    timestamp: str
    screenshot_path: str
    coordinate_space_name: str
    image_width: int
    image_height: int
    original_width: int
    original_height: int
    scale_x_to_desktop: float
    scale_y_to_desktop: float
    model_max_width: int = DEFAULT_MODEL_MAX_WIDTH
    jpeg_quality: int = DEFAULT_JPEG_QUALITY
    image_byte_count: int = 0
    image_sha256: str | None = None
    active_window: WindowMetadata | None = None
    full_resolution_path: str | None = None
    crop_box: dict[str, Any] | None = None
    crop_image_size: dict[str, Any] | None = None
    image_bytes: bytes = field(default=b"", repr=False)

    def transform(self) -> CoordinateTransform:
        return CoordinateTransform(
            desktop_size=Size(self.original_width, self.original_height),
            resized_size=Size(self.image_width, self.image_height),
            active_window_box=self.active_window.desktop_box() if self.active_window else None,
            crop_box=Box.from_dict(self.crop_box) if self.crop_box else None,
            crop_image_size=(
                Size(
                    int(self.crop_image_size["width"]),
                    int(self.crop_image_size["height"]),
                )
                if self.crop_image_size
                else None
            ),
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ObservationRecord":
        return cls(
            observation_id=str(payload["observation_id"]),
            timestamp=str(payload["timestamp"]),
            screenshot_path=str(payload["screenshot_path"]),
            coordinate_space_name=str(payload["coordinate_space_name"]),
            image_width=int(payload["image_width"]),
            image_height=int(payload["image_height"]),
            original_width=int(payload["original_width"]),
            original_height=int(payload["original_height"]),
            scale_x_to_desktop=float(payload["scale_x_to_desktop"]),
            scale_y_to_desktop=float(payload["scale_y_to_desktop"]),
            model_max_width=int(payload.get("model_max_width", DEFAULT_MODEL_MAX_WIDTH)),
            jpeg_quality=int(payload.get("jpeg_quality", DEFAULT_JPEG_QUALITY)),
            image_byte_count=int(payload.get("image_byte_count", 0)),
            image_sha256=payload.get("image_sha256"),
            active_window=WindowMetadata.from_dict(payload.get("active_window")),
            full_resolution_path=payload.get("full_resolution_path"),
            crop_box=payload.get("crop_box"),
            crop_image_size=payload.get("crop_image_size"),
        )

    def to_dict(self, include_image_bytes: bool = False) -> dict[str, Any]:
        payload = {
            "observation_id": self.observation_id,
            "timestamp": self.timestamp,
            "screenshot_path": self.screenshot_path,
            "coordinate_space_name": self.coordinate_space_name,
            "image_width": self.image_width,
            "image_height": self.image_height,
            "original_width": self.original_width,
            "original_height": self.original_height,
            "scale_x_to_desktop": self.scale_x_to_desktop,
            "scale_y_to_desktop": self.scale_y_to_desktop,
            "model_max_width": self.model_max_width,
            "jpeg_quality": self.jpeg_quality,
            "image_byte_count": self.image_byte_count,
            "image_sha256": self.image_sha256,
            "active_window": self.active_window.to_dict() if self.active_window else None,
            "full_resolution_path": self.full_resolution_path,
            "crop_box": self.crop_box,
            "crop_image_size": self.crop_image_size,
            "transform": self.transform().to_dict(),
        }
        if include_image_bytes and self.image_bytes:
            payload["image_bytes_base64"] = base64.b64encode(self.image_bytes).decode("ascii")
        return payload


@dataclass(frozen=True)
class Expectation:
    active_window_title_contains: str | None = None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "Expectation | None":
        if not payload:
            return None
        return cls(active_window_title_contains=payload.get("active_window_title_contains"))

    def to_dict(self) -> dict[str, Any]:
        return {"active_window_title_contains": self.active_window_title_contains}


@dataclass(frozen=True)
class ActionSpec:
    type: str
    reason: str
    point: Point | None = None
    text: str | None = None
    key: str | None = None
    keys: list[str] | None = None
    seconds: float | None = None
    button: str = "left"
    interval: float | None = None
    expectation: Expectation | None = None
    timeout: float | None = None
    risk: str | None = None
    title_contains: str | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ActionSpec":
        action_type = str(payload.get("type") or "").strip()
        if action_type == "window_action":
            action_name = str(payload.get("window_action") or payload.get("action") or "").strip().lower()
            action_type = {
                "activate": "window_activate",
                "minimize": "window_minimize",
                "maximize": "window_maximize",
                "restore": "window_restore",
                "close": "close_window",
            }.get(action_name, "")
        if action_type not in ACTION_TYPES:
            raise ValidationError(f"Unsupported action type: {action_type}")
        point = _extract_point(payload)
        spec = cls(
            type=action_type,
            reason=str(payload.get("reason") or "").strip(),
            point=point,
            text=payload.get("text"),
            key=payload.get("key"),
            keys=[str(item) for item in payload.get("keys", [])] if payload.get("keys") else None,
            seconds=float(payload["seconds"]) if payload.get("seconds") is not None else None,
            button=str(payload.get("button", "left")).lower(),
            interval=float(payload["interval"]) if payload.get("interval") is not None else None,
            expectation=Expectation.from_payload(payload.get("expectation")),
            timeout=float(payload["timeout"]) if payload.get("timeout") is not None else None,
            risk=payload.get("risk") or payload.get("safety"),
            title_contains=payload.get("title_contains"),
        )
        spec.validate()
        return spec

    def validate(self) -> None:
        if self.type in POINT_ACTIONS and not self.point:
            raise ValidationError(f"{self.type} requires a point.")
        if self.type in POINT_ACTIONS and self.button not in VALID_BUTTONS:
            raise ValidationError(f"Unsupported mouse button: {self.button}")
        if self.type == "type_text" and self.text is None:
            raise ValidationError("type_text requires 'text'.")
        if self.type == "press" and not self.key:
            raise ValidationError("press requires 'key'.")
        if self.type == "hotkey" and not self.keys:
            raise ValidationError("hotkey requires non-empty 'keys'.")
        if self.type == "wait" and (self.seconds is None or self.seconds < 0):
            raise ValidationError("wait requires non-negative 'seconds'.")
        if self.type == "clipboard_set" and self.text is None:
            raise ValidationError("clipboard_set requires 'text'.")

    @property
    def coordinate_space(self) -> str | None:
        return self.point.space.value if self.point else None

    def fingerprint(self) -> str:
        if self.type in POINT_ACTIONS and self.point:
            return f"{self.type}:{self.button}:{self.point.space.value}"
        if self.type == "type_text":
            return "type_text"
        if self.type == "press":
            return f"press:{self.key}"
        if self.type == "hotkey":
            return "hotkey:" + "+".join(self.keys or [])
        if self.type == "wait":
            return f"wait:{int(self.seconds or 0)}s"
        if self.type.startswith("window_"):
            target = f":{self.title_contains.lower()}" if self.title_contains else ""
            return f"{self.type}{target}"
        return self.type

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": self.type,
            "reason": self.reason,
            "button": self.button if self.type in POINT_ACTIONS else None,
            "interval": self.interval,
            "timeout": self.timeout,
            "risk": self.risk,
            "text": self.text,
            "key": self.key,
            "keys": self.keys,
            "seconds": self.seconds,
            "title_contains": self.title_contains,
            "expectation": self.expectation.to_dict() if self.expectation else None,
        }
        if self.point:
            payload["point"] = self.point.to_dict()
            payload["coordinate_space"] = self.point.space.value
        return {key: value for key, value in payload.items() if value is not None and value != ""}


@dataclass(frozen=True)
class ActionBatch:
    actions: list[ActionSpec]
    observe_after: bool = True
    stop_on_error: bool = True
    max_duration_seconds: float | None = None
    reason: str = ""

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | list[Mapping[str, Any]]) -> "ActionBatch":
        if isinstance(payload, list):
            return cls(actions=[ActionSpec.from_dict(item) for item in payload])
        actions_raw = payload.get("actions")
        if not isinstance(actions_raw, list) or not actions_raw:
            raise ValidationError("Batch JSON must include a non-empty 'actions' array.")
        max_duration_seconds = (
            float(payload["max_duration_seconds"])
            if payload.get("max_duration_seconds") is not None
            else None
        )
        if max_duration_seconds is not None and max_duration_seconds <= 0:
            raise ValidationError("max_duration_seconds must be positive.")
        return cls(
            actions=[ActionSpec.from_dict(item) for item in actions_raw],
            observe_after=bool(payload.get("observe_after", True)),
            stop_on_error=bool(payload.get("stop_on_error", True)),
            max_duration_seconds=max_duration_seconds,
            reason=str(payload.get("reason") or "").strip(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "actions": [action.to_dict() for action in self.actions],
            "observe_after": self.observe_after,
            "stop_on_error": self.stop_on_error,
            "max_duration_seconds": self.max_duration_seconds,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class LocatorResult:
    target: str
    center: Point | None = None
    bbox: Box | None = None
    confidence: float = 0.0
    source: str = "model"
    reason: str | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LocatorResult":
        center = Point.from_dict(payload["center"]) if payload.get("center") else None
        bbox = Box.from_dict(payload["bbox"]) if payload.get("bbox") else None
        if not center and not bbox:
            raise ValidationError("Locator results must include either 'center' or 'bbox'.")
        return cls(
            target=str(payload["target"]),
            center=center,
            bbox=bbox,
            confidence=float(payload.get("confidence", 0.0)),
            source=str(payload.get("source", "model")),
            reason=payload.get("reason"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "center": self.center.to_dict() if self.center else None,
            "bbox": self.bbox.to_dict() if self.bbox else None,
            "confidence": self.confidence,
            "source": self.source,
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
    model_max_width: int = DEFAULT_MODEL_MAX_WIDTH
    jpeg_quality: int = DEFAULT_JPEG_QUALITY
    no_progress_threshold: int = DEFAULT_NO_PROGRESS_THRESHOLD
    no_progress_streak: int = 0
    latest_observation: dict[str, Any] | None = None
    latest_action: dict[str, Any] | None = None
    latest_batch: dict[str, Any] | None = None
    latest_evaluation: dict[str, Any] | None = None
    suspension: dict[str, Any] | None = None
    result_answer: str | None = None
    memory_context: dict[str, Any] = field(default_factory=dict)
    latency_metrics: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TaskState":
        return cls(
            task_id=str(payload["task_id"]),
            goal=str(payload["goal"]),
            task_dir=str(payload["task_dir"]),
            status=str(payload.get("status", "active")),
            created_at=payload.get("created_at"),
            updated_at=payload.get("updated_at"),
            model_max_width=int(payload.get("model_max_width", DEFAULT_MODEL_MAX_WIDTH)),
            jpeg_quality=int(payload.get("jpeg_quality", DEFAULT_JPEG_QUALITY)),
            no_progress_threshold=int(payload.get("no_progress_threshold", DEFAULT_NO_PROGRESS_THRESHOLD)),
            no_progress_streak=int(payload.get("no_progress_streak", 0)),
            latest_observation=payload.get("latest_observation"),
            latest_action=payload.get("latest_action"),
            latest_batch=payload.get("latest_batch"),
            latest_evaluation=payload.get("latest_evaluation"),
            suspension=payload.get("suspension"),
            result_answer=payload.get("result_answer"),
            memory_context=dict(payload.get("memory_context") or {}),
            latency_metrics=dict(payload.get("latency_metrics") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "task_dir": self.task_dir,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "model_max_width": self.model_max_width,
            "jpeg_quality": self.jpeg_quality,
            "no_progress_threshold": self.no_progress_threshold,
            "no_progress_streak": self.no_progress_streak,
            "latest_observation": self.latest_observation,
            "latest_action": self.latest_action,
            "latest_batch": self.latest_batch,
            "latest_evaluation": self.latest_evaluation,
            "suspension": self.suspension,
            "result_answer": self.result_answer,
            "memory_context": self.memory_context,
            "latency_metrics": self.latency_metrics,
        }


def _extract_point(payload: Mapping[str, Any]) -> Point | None:
    if payload.get("point"):
        return Point.from_dict(payload["point"])
    if payload.get("x") is not None and payload.get("y") is not None:
        coordinate_space = payload.get("coordinate_space") or payload.get("space")
        if not coordinate_space:
            raise ValidationError("Point actions require 'coordinate_space' or 'space' when x/y are provided.")
        return Point(
            x=float(payload["x"]),
            y=float(payload["y"]),
            space=CoordinateSpace(str(coordinate_space)),
        )
    return None
