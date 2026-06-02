import json

from PIL import Image

from lbh.memory import MemoryStore
from lbh.runtime import LBHRuntime
from lbh.task_store import TaskStore


class FakeAdapter:
    def __init__(self):
        self.images = [
            Image.new("RGB", (1920, 1080), "white"),
            Image.new("RGB", (1920, 1080), "lightgray"),
            Image.new("RGB", (1920, 1080), "gray"),
        ]
        self.titles = ["Desktop", "Chrome", "ChatGPT"]
        self.screenshot_index = 0
        self.last_index = 0
        self.actions = []
        self.clipboard = ""

    def screenshot(self):
        index = min(self.screenshot_index, len(self.images) - 1)
        self.last_index = index
        if self.screenshot_index < len(self.images) - 1:
            self.screenshot_index += 1
        return self.images[index].copy()

    def screen_size(self):
        return (1920, 1080)

    def active_window(self):
        from lbh.contracts import WindowMetadata

        title = self.titles[self.last_index]
        return WindowMetadata(title=title, left=0, top=0, width=1920, height=1080, right=1920, bottom=1080, is_active=True, is_minimized=False, is_maximized=True)

    def click(self, x, y, *, clicks, button, interval):
        self.actions.append(("click", x, y, clicks, button))
        return {"status": "success", "desktop_x": x, "desktop_y": y, "clicks": clicks}

    def type_text(self, text, *, interval):
        self.actions.append(("type_text", text))
        return {"status": "success", "text": text}

    def press(self, key):
        self.actions.append(("press", key))
        return {"status": "success", "key": key}

    def hotkey(self, keys):
        self.actions.append(("hotkey", tuple(keys)))
        return {"status": "success", "keys": keys}

    def wait(self, seconds):
        self.actions.append(("wait", seconds))
        return {"status": "success", "seconds": seconds}

    def set_clipboard(self, text):
        self.clipboard = text
        self.actions.append(("clipboard_set", text))
        return {"status": "success"}

    def get_clipboard(self):
        self.actions.append(("clipboard_get",))
        return {"status": "success", "text": self.clipboard}

    def window_action(self, action, *, title_contains=None):
        self.actions.append(("window_action", action, title_contains))
        return {"status": "success", "action": action}


def _runtime(tmp_path):
    return LBHRuntime(
        adapter=FakeAdapter(),
        task_store=TaskStore(tasks_dir=tmp_path / "tasks"),
        memory_store=MemoryStore(memory_dir=tmp_path / "memories"),
    )


def test_runtime_click_converts_resized_coordinates(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.create_task("Open Chrome.", task_id="task-1")
    runtime.observe("task-1")
    result = runtime.execute_action(
        "task-1",
        {"type": "click", "point": {"x": 640, "y": 360, "space": "resized_image"}, "reason": "Click center."},
        observe_after=False,
    )
    assert result["result"]["desktop_point"]["x"] == 960
    assert result["result"]["desktop_point"]["y"] == 540


def test_runtime_batch_executes_and_observes_once(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.create_task("Navigate in Chrome.", task_id="task-1")
    runtime.observe("task-1")
    result = runtime.execute_batch(
        "task-1",
        {
            "observe_after": True,
            "actions": [
                {"type": "hotkey", "keys": ["ctrl", "l"], "reason": "Focus address bar"},
                {"type": "clipboard_set", "text": "https://chatgpt.com", "reason": "Prepare URL"},
                {"type": "hotkey", "keys": ["ctrl", "v"], "reason": "Paste URL"},
                {"type": "press", "key": "enter", "reason": "Navigate"},
            ],
        },
    )
    assert result["completed"] is True
    status = runtime.status("task-1", event_limit=20)
    observation_events = [event for event in status["recent_events"] if event["type"] == "observation"]
    assert len(observation_events) == 2


def test_runtime_does_not_attach_memory_context_automatically(tmp_path):
    runtime = _runtime(tmp_path)

    created = runtime.create_task("Open Chrome.", task_id="task-1")
    observed = runtime.observe("task-1")

    assert created["relevant_memory"] == {}
    assert observed["relevant_memory"] == {}


def test_runtime_ignores_failure_guards_when_memory_reference_is_disabled(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.create_task("Open Chrome.", task_id="task-1")
    runtime.observe("task-1")
    guard = {
        "id": "guard-1",
        "situation_signature": "Open Chrome. | Desktop",
        "situation_tokens": ["open", "chrome", "desktop"],
        "action_fingerprint": "press:enter",
        "bad_action_pattern": "press:enter",
        "reason": "Block enter.",
        "replacement_suggestion": "Do something else.",
        "support_count": 5,
        "failure_count": 5,
        "failure_rate": 1.0,
        "confidence": 0.95,
    }
    runtime.memory_store.failure_guards_path.write_text(json.dumps(guard) + "\n", encoding="utf-8")

    result = runtime.execute_action(
        "task-1",
        {"type": "press", "key": "enter", "reason": "Continue."},
        observe_after=False,
    )

    assert result["status"] == "success"
    assert result["guard_matches"] == []
