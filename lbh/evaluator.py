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
    if expectation_obj and expectation_obj.active_window_title_contains:
        expectation_match = expectation_obj.active_window_title_contains.lower() in after_title.lower()
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
