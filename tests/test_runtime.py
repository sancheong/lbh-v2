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
    assert "sequence_improvement_signals" in report
    assert "lifecycle_warnings" in report


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


def test_runtime_memory_commit_prefers_raw_sequence_for_root_version(tmp_path):
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
                {"type": "hotkey", "keys": ["ctrl", "v"], "reason": "Paste URL"},
            ],
        },
    )

    result = runtime.memory_commit(
        "task-1",
        {
            "task_description": "Open Chrome and navigate to ChatGPT.",
            "sequence": [
                {"action_name": "navigate_chatgpt", "status": "success", "duration": 1},
            ],
            "change_summary": "Refined root attempt.",
            "change_reason": "Would prefer a compact abstraction.",
            "run_note": "Capture the first run.",
            "run_status": "success",
        },
    )

    sequence = result["memory_commit"]["record"]["versions"][0]["sequence"]
    assert sequence[0]["action_name"] == "hotkey:ctrl+l"
    assert result["quality_notes"]


def test_runtime_memory_commit_keeps_refined_sequence_for_later_versions(tmp_path):
    runtime = _runtime(tmp_path)
    committed = runtime.memory_store.commit_task_record(
        user_query="Open Chrome and go to ChatGPT.",
        task_description="Open Chrome and navigate to ChatGPT.",
        sequence=[
            {"action_name": "hotkey:ctrl+l", "status": "success", "duration": 1},
            {"action_name": "clipboard_set:url", "status": "success", "duration": 1},
        ],
        run_status="success",
        run_note="Initial raw run.",
        elapsed_time=100.0,
        change_summary="Initial root sequence.",
        change_reason="Preserve raw root.",
    )
    record_id = committed["record"]["record_id"]
    runtime.create_task("Open Chrome and go to ChatGPT.", task_id="task-1")
    runtime.memory_select("task-1", record_id=record_id)

    result = runtime.memory_commit(
        "task-1",
        {
            "task_description": "Open Chrome and navigate to ChatGPT.",
            "sequence": [
                {"action_name": "navigate_chatgpt", "status": "success", "duration": 1},
            ],
            "change_summary": "Merged URL navigation.",
            "change_reason": "Use a compact stable draft for later reuse.",
            "run_note": "Create refined follow-up version.",
            "run_status": "success",
            "elapsed_time": 90.0,
        },
    )

    latest_version = result["memory_commit"]["record"]["versions"][-1]
    assert latest_version["sequence"][0]["action_name"] == "navigate_chatgpt"
    assert result["quality_notes"] == []


def test_runtime_memory_commit_warns_when_successful_prompt_used_type_text(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.create_task("Open ChatGPT.", task_id="task-1")
    runtime.observe("task-1")
    runtime.execute_batch(
        "task-1",
        {
            "observe_after": False,
            "actions": [
                {"type": "click", "point": {"x": 10, "y": 10, "space": "resized_image"}, "reason": "Focus the prompt box."},
                {"type": "type_text", "text": "Reply with exactly OK.", "reason": "Send the exact prompt."},
                {"type": "press", "key": "enter", "reason": "Submit the message."},
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

    assert any("type_text" in note for note in result["quality_notes"])


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

    assert result["memory"]["task_records"]
    assert "ChatGPT" in result["memory"]["task_records"][0]["task_description"]
    assert result["memory"]["task_records"][0]["success_versions"]


def test_runtime_memory_search_exposes_empty_success_candidates_without_success(tmp_path):
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

    record = result["memory"]["task_records"][0]
    assert record["latest_success_version_id"] is None
    assert record["success_versions"] == []


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
    assert select_result["memory"]["task_records"][0]["selected"] is True
    assert record_result["record"]["record_id"] == record_id
    assert record_result["record"]["versions"][0]["sequence"][0]["action_name"] == "open_chrome"


def test_runtime_memory_commit_passes_explicit_base_version(tmp_path):
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
    root_version_id = committed["version_id"]
    runtime.create_task("Open Chrome and go to ChatGPT.", task_id="task-1")
    runtime.memory_select("task-1", record_id=record_id)

    result = runtime.memory_commit(
        "task-1",
        {
            "task_description": "Open Chrome and navigate to ChatGPT.",
            "sequence": [{"action_name": "navigate_chatgpt", "status": "success", "duration": 1}],
            "run_status": "success",
            "run_note": "Refined run.",
            "elapsed_time": 90.0,
            "change_summary": "Refined sequence.",
            "change_reason": "Use explicit chosen draft.",
            "base_version_id": root_version_id,
        },
    )

    assert result["memory_commit"]["record"]["versions"][-1]["parent_version_id"] == root_version_id


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


def test_runtime_memory_commit_failed_changed_sequence_appends_run(tmp_path):
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
            "sequence": [{"action_name": "press:end", "status": "success", "duration": 1}],
            "run_status": "failure",
            "run_note": "Response did not appear.",
            "elapsed_time": 120.0,
            "change_summary": "Failure branch.",
            "change_reason": "Should stay as run history only.",
        },
    )

    assert result["memory_commit"]["record"]["record_id"] == record_id
    assert result["memory_commit"]["action"] == "append_run"
    assert len(result["memory_commit"]["record"]["versions"]) == 1


def test_runtime_memory_commit_returns_sequence_improvement_signals_and_lifecycle_warning(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.create_task("Open ChatGPT.", task_id="task-1")
    runtime.execute_batch(
        "task-1",
        {
            "observe_after": False,
            "expectation": {"title_contains_any": ["ChatGPT"], "require_changed": True},
            "actions": [
                {"type": "press", "key": "enter", "reason": "Navigate"},
            ],
        },
    )

    result = runtime.memory_commit(
        "task-1",
        {
            "task_description": "Open ChatGPT.",
            "sequence": [{"action_name": "press:enter", "status": "success", "duration": 1}],
            "run_status": "failure",
            "run_note": "Still unstable.",
            "elapsed_time": 10.0,
        },
    )

    assert result["sequence_improvement_signals"]
    assert result["sequence_improvement_signals"][0]["event_type"] == "batch"
    assert result["lifecycle_warnings"]


def test_runtime_memory_commit_defaults_elapsed_time_in_seconds(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path)
    runtime.create_task("Open ChatGPT.", task_id="task-1")
    monkeypatch.setattr(runtime, "_events_wall_clock_seconds", lambda events: 42.5)

    result = runtime.memory_commit(
        "task-1",
        {
            "task_description": "Open ChatGPT.",
            "sequence": [{"action_name": "press:enter", "status": "success", "duration": 1.25}],
            "run_status": "success",
            "run_note": "Used default elapsed time.",
        },
    )

    assert result["memory_commit"]["run_record"]["elapsed_time"] == 42.5


def test_runtime_status_returns_sequence_improvement_signals_and_lifecycle_warnings(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.create_task("Open ChatGPT.", task_id="task-1")
    runtime.execute_batch(
        "task-1",
        {
            "observe_after": False,
            "expectation": {"title_contains_any": ["ChatGPT"], "require_changed": True},
            "actions": [
                {"type": "press", "key": "enter", "reason": "Navigate"},
            ],
        },
    )
    runtime.memory_commit(
        "task-1",
        {
            "task_description": "Open ChatGPT.",
            "sequence": [{"action_name": "press:enter", "status": "success", "duration": 1}],
            "run_status": "failure",
            "run_note": "Still unstable.",
            "elapsed_time": 10.0,
        },
    )

    status = runtime.status("task-1", event_limit=10)

    assert status["sequence_improvement_signals"]
    assert status["lifecycle_warnings"]


def test_runtime_memory_commit_requires_core_fields(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.create_task("Open ChatGPT.", task_id="task-1")

    with pytest.raises(Exception):
        runtime.memory_commit("task-1", {"run_status": "success", "run_note": "ok"})
