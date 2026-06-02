from pathlib import Path

from PIL import Image, ImageDraw

from lbh.evaluator import evaluate_observation_progress, image_diff_score


def _write_image(path: Path, color: str, draw_rect: bool = False) -> str:
    image = Image.new("RGB", (200, 120), color)
    if draw_rect:
        draw = ImageDraw.Draw(image)
        draw.rectangle((20, 20, 80, 80), fill="black")
    image.save(path)
    return str(path)


def test_image_diff_score_detects_change(tmp_path):
    before = _write_image(tmp_path / "before.png", "white")
    after = _write_image(tmp_path / "after.png", "white", draw_rect=True)
    assert image_diff_score(before, before) == 0.0
    assert image_diff_score(before, after) > 0.0


def test_progress_evaluation_increments_streak(tmp_path):
    before = _write_image(tmp_path / "before.png", "white")
    after = _write_image(tmp_path / "after.png", "white")
    evaluation = evaluate_observation_progress(
        {"screenshot_path": before, "active_window": {"title": "Chrome"}},
        {"screenshot_path": after, "active_window": {"title": "Chrome"}},
        no_progress_streak=1,
        threshold=2,
    )
    assert evaluation["changed"] is False
    assert evaluation["suspend_recommended"] is True
