from __future__ import annotations

from io import BytesIO
from pathlib import Path
import time
from typing import Any

from PIL import Image, ImageChops, ImageStat

from .contracts import Expectation


def _load_image(source: str | Path | bytes) -> Image.Image:
    if isinstance(source, bytes):
        return Image.open(BytesIO(source))
    return Image.open(source)


def image_diff_score(
    before: str | Path | bytes,
    after: str | Path | bytes,
    *,
    sample_size: tuple[int, int] = (320, 200),
) -> float:
    left = _load_image(before).convert("L").resize(sample_size)
    right = _load_image(after).convert("L").resize(sample_size)
    diff = ImageChops.difference(left, right)
    stat = ImageStat.Stat(diff)
    return round((stat.mean[0] if stat.mean else 0.0) / 255.0, 6)


def active_window_title(observation: dict[str, Any] | None) -> str:
    if not observation:
        return ""
    active_window = observation.get("active_window") or {}
    return str(active_window.get("title") or "").strip()


def evaluate_expectation(
    expectation: Expectation | dict[str, Any] | None,
    pre_observation: dict[str, Any] | None,
    post_observation: dict[str, Any] | None,
    primitive_results: list[dict[str, Any]] | None,
    clipboard_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    expectation_obj = (
        expectation
        if isinstance(expectation, Expectation) or expectation is None
        else Expectation.from_payload(expectation)
    )
    if expectation_obj is None:
        return {"matched": True, "status": "success", "reason": "No explicit expectation.", "checks": []}

    checks: list[dict[str, Any]] = []
    before_title = active_window_title(pre_observation)
    after_title = active_window_title(post_observation)
    diff_threshold = expectation_obj.image_diff_threshold or 0.015
    diff_score = None
    if pre_observation and post_observation:
        diff_score = image_diff_score(pre_observation["screenshot_path"], post_observation["screenshot_path"])
    changed = bool(before_title.lower() != after_title.lower()) or bool(diff_score is not None and diff_score >= diff_threshold)
    clipboard_text = ""
    if clipboard_result:
        clipboard_text = str(clipboard_result.get("text") or "")
    observed_text = "\n".join(
        item
        for item in [
            before_title,
            after_title,
            clipboard_text,
            _primitive_results_text(primitive_results or []),
        ]
        if item
    )

    def _check(name: str, passed: bool, observed: Any, expected: Any = None) -> None:
        checks.append({"name": name, "passed": bool(passed), "observed": observed, "expected": expected})

    if expectation_obj.active_window_title_contains:
        passed = expectation_obj.active_window_title_contains.lower() in after_title.lower()
        _check("active_window_title_contains", passed, after_title, expectation_obj.active_window_title_contains)
    if expectation_obj.title_contains_any:
        passed = any(item.lower() in after_title.lower() for item in expectation_obj.title_contains_any)
        _check("title_contains_any", passed, after_title, expectation_obj.title_contains_any)
    if expectation_obj.title_contains_all:
        passed = all(item.lower() in after_title.lower() for item in expectation_obj.title_contains_all)
        _check("title_contains_all", passed, after_title, expectation_obj.title_contains_all)
    if expectation_obj.title_not_contains_any:
        passed = all(item.lower() not in after_title.lower() for item in expectation_obj.title_not_contains_any)
        _check("title_not_contains_any", passed, after_title, expectation_obj.title_not_contains_any)
    if expectation_obj.forbidden_title_contains_any:
        passed = all(item.lower() not in after_title.lower() for item in expectation_obj.forbidden_title_contains_any)
        _check("forbidden_title_contains_any", passed, after_title, expectation_obj.forbidden_title_contains_any)
    if expectation_obj.require_changed is True:
        _check("require_changed", changed, {"changed": changed, "diff_score": diff_score}, True)
    if expectation_obj.allow_no_visual_change is False or expectation_obj.visual_change_expected is True:
        _check("visual_change_expected", changed, {"changed": changed, "diff_score": diff_score}, True)
    if expectation_obj.expected_clipboard_contains is not None:
        passed = expectation_obj.expected_clipboard_contains in clipboard_text
        _check("expected_clipboard_contains", passed, clipboard_text, expectation_obj.expected_clipboard_contains)
    if expectation_obj.expected_clipboard_equals is not None:
        passed = clipboard_text == expectation_obj.expected_clipboard_equals
        _check("expected_clipboard_equals", passed, clipboard_text, expectation_obj.expected_clipboard_equals)
    if expectation_obj.success_hints_any:
        passed = any(item.lower() in observed_text.lower() for item in expectation_obj.success_hints_any)
        _check("success_hints_any", passed, observed_text, expectation_obj.success_hints_any)
    if expectation_obj.failure_hints_any:
        passed = all(item.lower() not in observed_text.lower() for item in expectation_obj.failure_hints_any)
        _check("failure_hints_any", passed, observed_text, expectation_obj.failure_hints_any)

    failed_checks = [item for item in checks if not item["passed"]]
    if failed_checks:
        failed_names = ", ".join(item["name"] for item in failed_checks)
        return {
            "matched": False,
            "status": "semantic_failure",
            "reason": f"Expectation checks failed: {failed_names}.",
            "checks": checks,
            "title_before": before_title,
            "title_after": after_title,
            "changed": changed,
            "image_diff_score": diff_score,
        }
    return {
        "matched": True,
        "status": "success",
        "reason": "Expectation checks passed.",
        "checks": checks,
        "title_before": before_title,
        "title_after": after_title,
        "changed": changed,
        "image_diff_score": diff_score,
    }


def evaluate_observation_progress(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
    *,
    expectation: Expectation | dict[str, Any] | None = None,
    no_progress_streak: int = 0,
    threshold: int = 3,
    diff_threshold: float = 0.015,
) -> dict[str, Any]:
    expectation_obj = (
        expectation
        if isinstance(expectation, Expectation) or expectation is None
        else Expectation.from_payload(expectation)
    )
    if not previous:
        title = active_window_title(current)
        return {
            "reason": "initial_observation",
            "changed": True,
            "image_diff_score": None,
            "title_before": None,
            "title_after": title,
            "title_changed": bool(title),
            "expectation_match": None,
            "no_progress_streak": 0,
            "suspend_recommended": False,
            "diff_threshold": diff_threshold,
        }

    diff_score = image_diff_score(previous["screenshot_path"], current["screenshot_path"])
    before_title = active_window_title(previous)
    after_title = active_window_title(current)
    title_changed = before_title.lower() != after_title.lower()
    visual_changed = diff_score >= diff_threshold
    expectation_match = None
    if expectation_obj:
        expectation_result = evaluate_expectation(expectation_obj, previous, current, primitive_results=[])
        expectation_match = expectation_result["matched"] if expectation_result["checks"] else None
    changed = visual_changed or title_changed or bool(expectation_match)
    new_streak = 0 if changed else no_progress_streak + 1
    return {
        "reason": "observation_comparison",
        "changed": changed,
        "image_diff_score": diff_score,
        "title_before": before_title,
        "title_after": after_title,
        "title_changed": title_changed,
        "expectation_match": expectation_match,
        "no_progress_streak": new_streak,
        "suspend_recommended": new_streak >= threshold,
        "diff_threshold": diff_threshold,
    }


class StabilityWaiter:
    def __init__(self, capture_service):
        self.capture_service = capture_service

    def wait_for_stable_screen(
        self,
        task_dir: str | Path,
        *,
        model_max_width: int,
        jpeg_quality: int,
        stable_seconds: float,
        timeout_seconds: float,
        interval_seconds: float = 1.0,
        diff_threshold: float = 0.01,
        label: str = "wait-stable",
    ) -> dict[str, Any]:
        start = time.perf_counter()
        previous = self.capture_service.capture(
            task_dir,
            model_max_width=model_max_width,
            jpeg_quality=jpeg_quality,
            label=f"{label}-start",
        )
        stable_duration = 0.0
        stable_frames = 0
        samples: list[dict[str, Any]] = []
        current = previous
        while True:
            elapsed = time.perf_counter() - start
            if elapsed >= timeout_seconds:
                return {
                    "status": "timeout",
                    "stable": False,
                    "stable_frames": stable_frames,
                    "stable_duration": round(stable_duration, 3),
                    "elapsed_seconds": round(elapsed, 3),
                    "diff_threshold": diff_threshold,
                    "samples": samples,
                    "final_observation": current.to_dict(),
                }
            time.sleep(interval_seconds)
            current = self.capture_service.capture(
                task_dir,
                model_max_width=model_max_width,
                jpeg_quality=jpeg_quality,
                label=f"{label}-sample",
            )
            diff_score = image_diff_score(previous.screenshot_path, current.screenshot_path)
            if diff_score <= diff_threshold:
                stable_frames += 1
                stable_duration += interval_seconds
            else:
                stable_frames = 0
                stable_duration = 0.0
            samples.append(
                {
                    "timestamp": current.timestamp,
                    "image_diff_score": diff_score,
                    "stable_frames": stable_frames,
                    "stable_duration": round(stable_duration, 3),
                    "screenshot_path": current.screenshot_path,
                }
            )
            if stable_duration >= stable_seconds:
                elapsed = time.perf_counter() - start
                return {
                    "status": "success",
                    "stable": True,
                    "stable_frames": stable_frames,
                    "stable_duration": round(stable_duration, 3),
                    "elapsed_seconds": round(elapsed, 3),
                    "diff_threshold": diff_threshold,
                    "samples": samples,
            "final_observation": current.to_dict(),
        }
            previous = current


def _primitive_results_text(primitive_results: list[dict[str, Any]]) -> str:
    fragments: list[str] = []
    for item in primitive_results:
        action = item.get("action") or {}
        result = item.get("result") or {}
        error = item.get("error") or {}
        for value in [
            action.get("reason"),
            action.get("type"),
            action.get("key"),
            " ".join(action.get("keys", [])) if action.get("keys") else None,
            action.get("text"),
            result.get("text"),
            error.get("message"),
            ((result.get("active_window_after_action") or {}).get("title") if isinstance(result.get("active_window_after_action"), dict) else None),
        ]:
            if value:
                fragments.append(str(value))
    return "\n".join(fragments)
