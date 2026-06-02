from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ScreenshotConfig:
    model_max_width: int = 1280
    jpeg_quality: int = 75
    save_original: bool = False
    save_resized: bool = True
    max_screenshots_per_task: int = 80


@dataclass(frozen=True)
class CoordinatePolicy:
    model_output_space: str = "resized_image"
    action_input_space: str = "desktop"
    require_explicit_space: bool = True
    reject_unknown_space: bool = True


@dataclass(frozen=True)
class LocatorConfig:
    min_confidence_for_click: float = 0.80
    refine_if_confidence_below: float = 0.80
    refine_if_bbox_width_below_px: int = 40
    precision_crop_padding_px_desktop: int = 120


@dataclass(frozen=True)
class MemoryConfig:
    memory_dir: Path = Path("memories")
    min_skill_support: int = 3
    min_skill_success_rate: float = 0.80
    failure_guard_threshold: int = 2


@dataclass(frozen=True)
class LBHConfig:
    tasks_dir: Path = Path("tasks")
    screenshot: ScreenshotConfig = ScreenshotConfig()
    coordinate_policy: CoordinatePolicy = CoordinatePolicy()
    locator: LocatorConfig = LocatorConfig()
    memory: MemoryConfig = MemoryConfig()


DEFAULT_CONFIG = LBHConfig()
