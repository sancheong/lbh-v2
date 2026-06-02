from __future__ import annotations

from datetime import datetime
from pathlib import Path
import uuid

from PIL import Image

from .config import LBHConfig, DEFAULT_CONFIG
from .coordinates import ResizeTransform, resized_dimensions
from .models import ActiveWindow, Observation
from .storage import TaskStore


def average_hash(image: Image.Image, size: int = 8) -> str:
    """Small perceptual hash for screen-change caching.

    This is intentionally simple and dependency-free. It is not cryptographic.
    """

    gray = image.convert("L").resize((size, size))
    pixels = list(gray.getdata())
    avg = sum(pixels) / len(pixels)
    bits = ["1" if px >= avg else "0" for px in pixels]
    return f"{int(''.join(bits), 2):0{size * size // 4}x}"


def _active_window_payload() -> ActiveWindow | None:
    try:
        import pygetwindow as gw  # type: ignore

        window = gw.getActiveWindow()
        if not window:
            return None
        return ActiveWindow(
            title=window.title,
            left=window.left,
            top=window.top,
            width=window.width,
            height=window.height,
            right=window.right,
            bottom=window.bottom,
            is_active=window.isActive,
            is_minimized=window.isMinimized,
            is_maximized=window.isMaximized,
        )
    except Exception:
        return None


class PyAutoGuiCapture:
    def __init__(self, config: LBHConfig = DEFAULT_CONFIG, store: TaskStore | None = None):
        self.config = config
        self.store = store or TaskStore(config)

    def capture(self, task: str | Path) -> Observation:
        try:
            import pyautogui  # type: ignore
        except ImportError as exc:
            raise RuntimeError("pyautogui is required for desktop capture") from exc

        state = self.store.read_state(task)
        screenshots_dir = self.store.screenshots_dir(task)

        raw = pyautogui.screenshot()
        original_width, original_height = raw.size
        max_width = self.config.screenshot.model_max_width
        image_width, image_height = resized_dimensions(original_width, original_height, max_width)
        resized = raw.resize((image_width, image_height)) if (image_width, image_height) != raw.size else raw

        image_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
        original_path = None
        if self.config.screenshot.save_original:
            original_path = screenshots_dir / f"{image_id}-original.png"
            raw.save(original_path)

        image_path = screenshots_dir / f"{image_id}-resized.jpg"
        quality = max(5, min(int(self.config.screenshot.jpeg_quality), 95))
        resized.save(image_path, format="JPEG", quality=quality, optimize=True)
        self.store.cleanup_screenshots(task)

        obs = Observation(
            task_id=state.task_id,
            image_path=str(image_path.resolve()),
            coordinate_system="resized_image",
            image_width=image_width,
            image_height=image_height,
            desktop_width=original_width,
            desktop_height=original_height,
            scale_x_to_desktop=original_width / image_width,
            scale_y_to_desktop=original_height / image_height,
            jpeg_quality=quality,
            image_bytes=image_path.stat().st_size,
            screenshot_hash=average_hash(resized),
            active_window=_active_window_payload(),
            original_path=str(original_path.resolve()) if original_path else None,
        )
        state.latest_observation = obs.to_dict()
        self.store.write_state(state)
        self.store.append_log(task, "observation", "Captured resized desktop screenshot", obs.to_dict())
        return obs

    @staticmethod
    def transform_from_observation(obs: Observation) -> ResizeTransform:
        return ResizeTransform(
            desktop_width=obs.desktop_width,
            desktop_height=obs.desktop_height,
            image_width=obs.image_width,
            image_height=obs.image_height,
        )
