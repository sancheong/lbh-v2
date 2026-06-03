import pytest
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


def test_runtime_memory_guards_are_noop_under_task_record_model(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.create_task("Open Chrome.", task_id="task-1")
    runtime.observe("task-1")

    result = runtime.execute_action(
        "task-1",
        {"type": "press", "key": "enter", "reason": "Continue."},
        observe_after=False,
    )

    assert result["status"] == "success"
    assert result["guard_matches"] == []


def test_batch_expectation_failure_is_semantic_failure(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.adapter.titles = ["Chrome", "Google Search - Chrome", "Google Search - Chrome"]
    runtime.adapter.images = [Image.new("RGB", (1920, 1080), "white"), Image.new("RGB", (1920, 1080), "black"), Image.new("RGB", (1920, 1080), "black")]
    runtime.create_task("Open ChatGPT.", task_id="task-1")
    runtime.observe("task-1")

    result = runtime.execute_batch(
        "task-1",
        {
            "observe_after": True,
            "expectation": {
                "title_contains_any": ["ChatGPT"],
                "title_not_contains_any": ["Search"],
                "require_changed": True,
            },
            "actions": [
                {"type": "press", "key": "enter", "reason": "Navigate"},
            ],
        },
    )

    assert result["primitive_results"][0]["status"] == "success"
    assert result["status"] == "semantic_failure"


def test_url_direct_typing_emits_warning(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.create_task("Open ChatGPT.", task_id="task-1")
    runtime.observe("task-1")

    result = runtime.execute_batch(
        "task-1",
        {
            "observe_after": False,
            "actions": [
                {"type": "type_text", "text": "https://chatgpt.com", "reason": "Type URL directly"},
                {"type": "press", "key": "enter", "reason": "Navigate"},
            ],
        },
    )

    assert any("clipboard_set:url" in warning for warning in result["warnings"])


def test_benchmark_report_summarizes_task(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.create_task("Open Chrome.", task_id="task-1")
    runtime.observe("task-1")
    runtime.execute_action(
        "task-1",
        {"type": "clipboard_get", "reason": "Read clipboard."},
        observe_after=False,
    )
    runtime.finish("task-1", "done")

    report = runtime.benchmark_report("task-1")

    assert report["status"] == "success"
    assert report["observation_count"] >= 1
    assert report["primitive_action_count"] >= 1


def test_runtime_memory_commit_derives_raw_sequence(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.create_task("Open ChatGPT.", task_id="task-1")
    runtime.observe("task-1")
    runtime.execute_batch(
        "task-1",
        {
            "observe_after": False,
            "actions": [
                {"type": "hotkey", "keys": ["ctrl", "l"], "reason": "Focus address bar"},
                {"type": "clipboard_set", "text": "https://chatgpt.com", "reason": "Prepare URL"},
            ],
        },
    )

    result = runtime.memory_commit(
        "task-1",
        {
            "task_description": "Open Chrome and navigate to ChatGPT.",
            "change_summary": "Initial raw capture.",
            "change_reason": "First run.",
            "run_note": "Recorded the first raw sequence.",
            "run_status": "success",
        },
    )

    record = result["memory_commit"]["record"]
    assert result["memory_commit"]["action"] == "create_record"
    assert record["versions"][0]["sequence"][0]["action_name"] == "hotkey:ctrl+l"


def test_runtime_memory_search_returns_task_records(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.memory_store.commit_task_record(
        user_query="Open Chrome and go to ChatGPT.",
        task_description="Open Chrome and navigate to ChatGPT.",
        sequence=[{"action_name": "open_chrome", "status": "success", "duration": 5}],
        run_status="success",
        run_note="Initial run.",
        elapsed_time=100.0,
    )

    runtime.create_task("Open Chrome and go to ChatGPT.", task_id="task-1")
    result = runtime.memory_search("task-1")

    assert result["memory"]["task_cards"]
    assert "ChatGPT" in result["memory"]["task_cards"][0]["task_description"]
    assert result["memory"]["task_cards"][0]["baseline_version"] is not None


def test_runtime_memory_search_exposes_baseline_version_without_success(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.memory_store.commit_task_record(
        user_query="Open Chrome and go to ChatGPT.",
        task_description="Open Chrome and navigate to ChatGPT.",
        sequence=[{"action_name": "open_chrome", "status": "success", "duration": 1}],
        run_status="failure",
        run_note="Initial failed run.",
        elapsed_time=100.0,
        change_summary="Initial failed sequence.",
        change_reason="Preserve the first trace even before any success exists.",
    )

    runtime.create_task("Open Chrome and go to ChatGPT.", task_id="task-1")
    result = runtime.memory_search("task-1")

    card = result["memory"]["task_cards"][0]
    assert card["latest_success_version"] is None
    assert card["baseline_version"] is not None


def test_runtime_memory_select_marks_selected_card_and_loads_full_record(tmp_path):
    runtime = _runtime(tmp_path)
    committed = runtime.memory_store.commit_task_record(
        user_query="Open Chrome and go to ChatGPT.",
        task_description="Open Chrome and navigate to ChatGPT.",
        sequence=[{"action_name": "open_chrome", "status": "success", "duration": 1}],
        run_status="success",
        run_note="Initial run.",
        elapsed_time=100.0,
        change_summary="Initial sequence.",
        change_reason="First run.",
    )
    record_id = committed["record"]["record_id"]
    runtime.create_task("Open Chrome and go to ChatGPT.", task_id="task-1")

    select_result = runtime.memory_select("task-1", record_id=record_id)
    record_result = runtime.memory_record("task-1")

    assert select_result["record_id"] == record_id
    assert select_result["memory"]["selected_record_id"] == record_id
    assert select_result["memory"]["task_cards"][0]["selected"] is True
    assert record_result["record"]["record_id"] == record_id
    assert record_result["record"]["versions"][0]["sequence"][0]["action_name"] == "open_chrome"


def test_runtime_memory_commit_uses_selected_record_by_default(tmp_path):
    runtime = _runtime(tmp_path)
    committed = runtime.memory_store.commit_task_record(
        user_query="Open Chrome and go to ChatGPT.",
        task_description="Open Chrome and navigate to ChatGPT.",
        sequence=[{"action_name": "open_chrome", "status": "success", "duration": 1}],
        run_status="success",
        run_note="Initial run.",
        elapsed_time=100.0,
        change_summary="Initial sequence.",
        change_reason="First run.",
    )
    record_id = committed["record"]["record_id"]
    runtime.create_task("Open Chrome and go to ChatGPT.", task_id="task-1")
    runtime.memory_select("task-1", record_id=record_id)

    result = runtime.memory_commit(
        "task-1",
        {
            "task_description": "Open Chrome and navigate to ChatGPT.",
            "sequence": [{"action_name": "open_chrome", "status": "success", "duration": 1}],
            "run_status": "failure",
            "run_note": "Retry failed.",
            "elapsed_time": 120.0,
        },
    )

    assert result["memory_commit"]["record"]["record_id"] == record_id
    assert result["memory_commit"]["action"] == "append_run"


def test_runtime_memory_commit_requires_core_fields(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.create_task("Open ChatGPT.", task_id="task-1")

    with pytest.raises(Exception):
        runtime.memory_commit("task-1", {"run_status": "success", "run_note": "ok"})
