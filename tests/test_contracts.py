import pytest

from lbh.contracts import ActionBatch, ActionSpec
from lbh.errors import ValidationError


def test_action_spec_parses_click():
    action = ActionSpec.from_dict(
        {
            "type": "click",
            "point": {"x": 640, "y": 520, "space": "resized_image"},
            "reason": "Click composer.",
        }
    )
    assert action.coordinate_space == "resized_image"
    assert action.fingerprint() == "click:left:resized_image"


def test_action_spec_rejects_xy_without_coordinate_space():
    with pytest.raises(ValidationError):
        ActionSpec.from_dict({"type": "click", "x": 1, "y": 2, "reason": "bad"})


def test_action_batch_parses():
    batch = ActionBatch.from_payload(
        {
            "observe_after": True,
            "actions": [
                {"type": "hotkey", "keys": ["ctrl", "l"], "reason": "Focus address bar"},
                {"type": "press", "key": "enter", "reason": "Navigate"},
            ],
        }
    )
    assert [item.type for item in batch.actions] == ["hotkey", "press"]
