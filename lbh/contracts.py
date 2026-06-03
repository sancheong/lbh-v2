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
    title_contains_any: list[str] | None = None
    title_contains_all: list[str] | None = None
    title_not_contains_any: list[str] | None = None
    forbidden_title_contains_any: list[str] | None = None
    require_changed: bool | None = None
    allow_no_visual_change: bool | None = None
    visual_change_expected: bool | None = None
    non_visual_action: bool | None = None
    success_hints_any: list[str] | None = None
    failure_hints_any: list[str] | None = None
    expected_clipboard_contains: str | None = None
    expected_clipboard_equals: str | None = None
    image_diff_threshold: float | None = None
    allow_visual_only: bool | None = None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "Expectation | None":
        if not payload:
            return None
        title_contains_any = _coerce_string_list(payload.get("title_contains_any"))
        if not title_contains_any and payload.get("active_window_title_contains"):
            title_contains_any = [str(payload.get("active_window_title_contains"))]
        return cls(
            active_window_title_contains=payload.get("active_window_title_contains"),
            title_contains_any=title_contains_any,
            title_contains_all=_coerce_string_list(payload.get("title_contains_all")),
            title_not_contains_any=_coerce_string_list(payload.get("title_not_contains_any")),
            forbidden_title_contains_any=_coerce_string_list(payload.get("forbidden_title_contains_any")),
            require_changed=payload.get("require_changed"),
            allow_no_visual_change=payload.get("allow_no_visual_change"),
            visual_change_expected=payload.get("visual_change_expected"),
            non_visual_action=payload.get("non_visual_action"),
            success_hints_any=_coerce_string_list(payload.get("success_hints_any")),
            failure_hints_any=_coerce_string_list(payload.get("failure_hints_any")),
            expected_clipboard_contains=payload.get("expected_clipboard_contains"),
            expected_clipboard_equals=payload.get("expected_clipboard_equals"),
            image_diff_threshold=float(payload["image_diff_threshold"]) if payload.get("image_diff_threshold") is not None else None,
            allow_visual_only=payload.get("allow_visual_only"),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "active_window_title_contains": self.active_window_title_contains,
            "title_contains_any": self.title_contains_any,
            "title_contains_all": self.title_contains_all,
            "title_not_contains_any": self.title_not_contains_any,
            "forbidden_title_contains_any": self.forbidden_title_contains_any,
            "require_changed": self.require_changed,
            "allow_no_visual_change": self.allow_no_visual_change,
            "visual_change_expected": self.visual_change_expected,
            "non_visual_action": self.non_visual_action,
            "success_hints_any": self.success_hints_any,
            "failure_hints_any": self.failure_hints_any,
            "expected_clipboard_contains": self.expected_clipboard_contains,
            "expected_clipboard_equals": self.expected_clipboard_equals,
            "image_diff_threshold": self.image_diff_threshold,
            "allow_visual_only": self.allow_visual_only,
        }
        return {key: value for key, value in payload.items() if value is not None and value != []}


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
    allow_no_visual_change: bool | None = None
    visual_change_expected: bool | None = None
    non_visual_action: bool | None = None
    semantic_status: str | None = None

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
            allow_no_visual_change=payload.get("allow_no_visual_change"),
            visual_change_expected=payload.get("visual_change_expected"),
            non_visual_action=payload.get("non_visual_action"),
            semantic_status=payload.get("semantic_status"),
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

    @property
    def action_category(self) -> str:
        if self.type in {"clipboard_set", "clipboard_get"}:
            return "clipboard_action"
        if self.type == "type_text":
            return "text_entry_action"
        if self.type in {"window_activate", "window_minimize", "window_maximize", "window_restore", "close_window"}:
            return "window_action"
        if self.type == "wait":
            return "non_visual_action"
        if self.type in {"press", "hotkey"}:
            if self.key == "enter":
                return "navigation_action"
            keys = [item.lower() for item in (self.keys or [])]
            if any(key in {"ctrl", "alt", "shift"} for key in keys):
                return "navigation_action"
        return "visual_action"

    @property
    def is_non_visual_action(self) -> bool:
        if self.non_visual_action is not None:
            return bool(self.non_visual_action)
        if self.allow_no_visual_change:
            return True
        if self.type in {"clipboard_set", "clipboard_get", "wait"}:
            return True
        reason = (self.reason or "").lower()
        if "copy" in reason or "clipboard" in reason:
            return True
        return False

    @property
    def visual_change_expected_default(self) -> bool:
        if self.visual_change_expected is not None:
            return bool(self.visual_change_expected)
        return not self.is_non_visual_action

    def fingerprint(self) -> str:
        if self.type in POINT_ACTIONS and self.point:
            return f"{self.type}:{self.button}:{self.point.space.value}"
        if self.type == "type_text":
            if looks_like_url(self.text):
                return "type_text:url"
            if self.text and len(self.text) >= 40:
                return "type_text:long_text"
            return "type_text"
        if self.type == "clipboard_set":
            if looks_like_url(self.text):
                return "clipboard_set:url"
            if self.text and len(self.text) >= 40:
                return "clipboard_set:long_text"
            return "clipboard_set"
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
            "allow_no_visual_change": self.allow_no_visual_change,
            "visual_change_expected": self.visual_change_expected,
            "non_visual_action": self.non_visual_action,
            "semantic_status": self.semantic_status,
            "action_category": self.action_category,
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
    max_duration_ms: float | None = None
    reason: str = ""
    expectation: Expectation | None = None
    postcondition: Expectation | None = None
    semantic_status: str | None = None
    allow_no_visual_change: bool | None = None
    visual_change_expected: bool | None = None
    non_visual_action: bool | None = None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | list[Mapping[str, Any]]) -> "ActionBatch":
        if isinstance(payload, list):
            return cls(actions=[ActionSpec.from_dict(item) for item in payload])
        actions_raw = payload.get("actions")
        if not isinstance(actions_raw, list) or not actions_raw:
            raise ValidationError("Batch JSON must include a non-empty 'actions' array.")
        max_duration_seconds = float(payload["max_duration_seconds"]) if payload.get("max_duration_seconds") is not None else None
        max_duration_ms = float(payload["max_duration_ms"]) if payload.get("max_duration_ms") is not None else None
        if max_duration_seconds is None and max_duration_ms is not None:
            max_duration_seconds = max_duration_ms / 1000.0
        if max_duration_seconds is not None and max_duration_seconds <= 0:
            raise ValidationError("max_duration_seconds must be positive.")
        expectation_payload = _merge_expectation_payload(payload.get("expectation"), payload)
        postcondition_payload = _merge_expectation_payload(payload.get("postcondition"), payload)
        return cls(
            actions=[ActionSpec.from_dict(item) for item in actions_raw],
            observe_after=bool(payload.get("observe_after", True)),
            stop_on_error=bool(payload.get("stop_on_error", True)),
            max_duration_seconds=max_duration_seconds,
            max_duration_ms=max_duration_ms,
            reason=str(payload.get("reason") or "").strip(),
            expectation=Expectation.from_payload(expectation_payload),
            postcondition=Expectation.from_payload(postcondition_payload),
            semantic_status=payload.get("semantic_status"),
            allow_no_visual_change=payload.get("allow_no_visual_change"),
            visual_change_expected=payload.get("visual_change_expected"),
            non_visual_action=payload.get("non_visual_action"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "actions": [action.to_dict() for action in self.actions],
            "observe_after": self.observe_after,
            "stop_on_error": self.stop_on_error,
            "max_duration_seconds": self.max_duration_seconds,
            "max_duration_ms": self.max_duration_ms,
            "reason": self.reason,
            "expectation": self.expectation.to_dict() if self.expectation else None,
            "postcondition": self.postcondition.to_dict() if self.postcondition else None,
            "semantic_status": self.semantic_status,
            "allow_no_visual_change": self.allow_no_visual_change,
            "visual_change_expected": self.visual_change_expected,
            "non_visual_action": self.non_visual_action,
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


@dataclass(frozen=True)
class SequenceStepRecord:
    action_name: str
    status: str
    duration: float

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SequenceStepRecord":
        return cls(
            action_name=str(payload.get("action_name") or ""),
            status=str(payload.get("status") or ""),
            duration=float(payload.get("duration", 0.0)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_name": self.action_name,
            "status": self.status,
            "duration": self.duration,
        }


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    status: str
    elapsed_time: float
    note: str
    created_at: str | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RunRecord":
        return cls(
            run_id=str(payload.get("run_id") or ""),
            status=str(payload.get("status") or ""),
            elapsed_time=float(payload.get("elapsed_time", 0.0)),
            note=str(payload.get("note") or ""),
            created_at=payload.get("created_at"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "elapsed_time": self.elapsed_time,
            "note": self.note,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class SequenceVersionRecord:
    version_id: str
    parent_version_id: str | None
    change_summary: str
    change_reason: str
    sequence: list[SequenceStepRecord]
    run_records: list[RunRecord]
    created_at: str | None = None
    updated_at: str | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SequenceVersionRecord":
        return cls(
            version_id=str(payload.get("version_id") or ""),
            parent_version_id=payload.get("parent_version_id"),
            change_summary=str(payload.get("change_summary") or ""),
            change_reason=str(payload.get("change_reason") or ""),
            sequence=[SequenceStepRecord.from_dict(item) for item in payload.get("sequence", [])],
            run_records=[RunRecord.from_dict(item) for item in payload.get("run_records", [])],
            created_at=payload.get("created_at"),
            updated_at=payload.get("updated_at"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version_id": self.version_id,
            "parent_version_id": self.parent_version_id,
            "change_summary": self.change_summary,
            "change_reason": self.change_reason,
            "sequence": [item.to_dict() for item in self.sequence],
            "run_records": [item.to_dict() for item in self.run_records],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class TaskMemoryRecord:
    record_id: str
    user_query: str
    task_description: str
    versions: list[SequenceVersionRecord]
    root_version_id: str | None = None
    latest_version_id: str | None = None
    latest_success_version_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TaskMemoryRecord":
        return cls(
            record_id=str(payload.get("record_id") or ""),
            user_query=str(payload.get("user_query") or ""),
            task_description=str(payload.get("task_description") or ""),
            versions=[SequenceVersionRecord.from_dict(item) for item in payload.get("versions", [])],
            root_version_id=payload.get("root_version_id"),
            latest_version_id=payload.get("latest_version_id"),
            latest_success_version_id=payload.get("latest_success_version_id"),
            created_at=payload.get("created_at"),
            updated_at=payload.get("updated_at"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "user_query": self.user_query,
            "task_description": self.task_description,
            "versions": [item.to_dict() for item in self.versions],
            "root_version_id": self.root_version_id,
            "latest_version_id": self.latest_version_id,
            "latest_success_version_id": self.latest_success_version_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
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
    selected_memory_record_id: str | None = None
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
            selected_memory_record_id=payload.get("selected_memory_record_id"),
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
            "selected_memory_record_id": self.selected_memory_record_id,
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


def looks_like_url(text: str | None) -> bool:
    if not text:
        return False
    candidate = text.strip().lower()
    return candidate.startswith(("http://", "https://")) or "://" in candidate


def _coerce_string_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else None
    if isinstance(value, (list, tuple, set)):
        items = [str(item).strip() for item in value if str(item).strip()]
        return items or None
    return [str(value).strip()]


def _merge_expectation_payload(
    expectation_payload: Mapping[str, Any] | None,
    root_payload: Mapping[str, Any],
) -> dict[str, Any] | None:
    merged: dict[str, Any] = dict(expectation_payload or {})
    for key in [
        "active_window_title_contains",
        "title_contains_any",
        "title_contains_all",
        "title_not_contains_any",
        "forbidden_title_contains_any",
        "require_changed",
        "allow_no_visual_change",
        "visual_change_expected",
        "non_visual_action",
        "success_hints_any",
        "failure_hints_any",
        "expected_clipboard_contains",
        "expected_clipboard_equals",
        "image_diff_threshold",
        "allow_visual_only",
    ]:
        if root_payload.get(key) is not None and key not in merged:
            merged[key] = root_payload.get(key)
    return merged or None
