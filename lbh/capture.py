from __future__ import annotations

from io import BytesIO
from pathlib import Path
import uuid

from PIL import Image

from .common import DEFAULT_JPEG_QUALITY, DEFAULT_MODEL_MAX_WIDTH, ensure_dir, now_iso, safe_slug, sha256_bytes
from .contracts import ObservationRecord
from .platform import DesktopAdapter, PyAutoGUIDesktopAdapter


class CaptureService:
    def __init__(self, adapter: DesktopAdapter | None = None):
        self.adapter = adapter or PyAutoGUIDesktopAdapter()

    def capture(
        self,
        task_dir: str | Path,
        *,
        model_max_width: int = DEFAULT_MODEL_MAX_WIDTH,
        jpeg_quality: int = DEFAULT_JPEG_QUALITY,
        label: str = "observe",
        save_full_resolution: bool = False,
    ) -> ObservationRecord:
        task_path = Path(task_dir)
        screenshots_dir = ensure_dir(task_path / "screenshots")
        artifacts_dir = ensure_dir(task_path / "artifacts")

        screenshot = self.adapter.screenshot()
        original_width, original_height = screenshot.size
        resized = screenshot
        if model_max_width and original_width > model_max_width:
            resized_height = round(original_height * model_max_width / original_width)
            resized = screenshot.resize((model_max_width, resized_height), Image.Resampling.LANCZOS)

        image_width, image_height = resized.size
        bounded_quality = max(30, min(int(jpeg_quality), 95))
        image_buffer = BytesIO()
        resized.save(image_buffer, format="JPEG", quality=bounded_quality, optimize=True)
        image_bytes = image_buffer.getvalue()
        image_sha256 = sha256_bytes(image_bytes)

        slug_label = safe_slug(label, fallback="observe")
        filename = f"{now_iso().replace(':', '').replace('-', '')}-{slug_label}-{uuid.uuid4().hex[:8]}.jpg"
        screenshot_path = screenshots_dir / filename
        screenshot_path.write_bytes(image_bytes)

        full_resolution_path = None
        if save_full_resolution:
            full_resolution_path = artifacts_dir / f"{screenshot_path.stem}-full.png"
            screenshot.save(full_resolution_path, format="PNG")

        active_window = self.adapter.active_window()
        return ObservationRecord(
            observation_id=uuid.uuid4().hex,
            timestamp=now_iso(),
            screenshot_path=str(screenshot_path.resolve()),
            coordinate_space_name="resized_image",
            image_width=image_width,
            image_height=image_height,
            original_width=original_width,
            original_height=original_height,
            scale_x_to_desktop=original_width / image_width,
            scale_y_to_desktop=original_height / image_height,
            model_max_width=model_max_width,
            jpeg_quality=bounded_quality,
            image_byte_count=len(image_bytes),
            image_sha256=image_sha256,
            active_window=active_window,
            full_resolution_path=str(full_resolution_path.resolve()) if full_resolution_path else None,
            image_bytes=image_bytes,
        )
