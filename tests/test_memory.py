from lbh.memory import MemoryStore


def test_commit_creates_new_task_record(tmp_path):
    store = MemoryStore(memory_dir=tmp_path / "memories")

    result = store.commit_task_record(
        user_query="Open Chrome and go to ChatGPT.",
        task_description="Open Chrome, navigate to ChatGPT, and ask a question.",
        sequence=[
            {"action_name": "hotkey:ctrl+l", "status": "success", "duration": 10},
            {"action_name": "clipboard_set:url", "status": "success", "duration": 5},
        ],
        run_status="success",
        run_note="Initial raw sequence.",
        elapsed_time=420.0,
        change_summary="Initial raw sequence capture.",
        change_reason="First execution of the task.",
    )

    record = store.get_task_record(result["record"]["record_id"])
    assert record is not None
    assert len(record.versions) == 1
    assert record.latest_success_version_id == record.versions[0].version_id
    assert record.versions[0].run_records[0].status == "success"


def test_commit_same_sequence_appends_run_record(tmp_path):
    store = MemoryStore(memory_dir=tmp_path / "memories")
    created = store.commit_task_record(
        user_query="Open Chrome and go to ChatGPT.",
        task_description="Open Chrome, navigate to ChatGPT, and ask a question.",
        sequence=[
            {"action_name": "hotkey:ctrl+l", "status": "success", "duration": 10},
            {"action_name": "clipboard_set:url", "status": "success", "duration": 5},
        ],
        run_status="success",
        run_note="Initial run.",
        elapsed_time=420.0,
        change_summary="Initial raw sequence capture.",
        change_reason="First execution of the task.",
    )

    updated = store.commit_task_record(
        record_id=created["record"]["record_id"],
        user_query="Open Chrome and go to ChatGPT.",
        task_description="Open Chrome, navigate to ChatGPT, and ask a question.",
        sequence=[
            {"action_name": "hotkey:ctrl+l", "status": "success", "duration": 11},
            {"action_name": "clipboard_set:url", "status": "success", "duration": 6},
        ],
        run_status="failure",
        run_note="Navigation failed due to IME.",
        elapsed_time=520.0,
    )

    record = store.get_task_record(updated["record"]["record_id"])
    assert len(record.versions) == 1
    assert len(record.versions[0].run_records) == 2
    assert updated["action"] == "append_run"


def test_commit_changed_sequence_appends_new_version(tmp_path):
    store = MemoryStore(memory_dir=tmp_path / "memories")
    created = store.commit_task_record(
        user_query="Open Chrome and go to ChatGPT.",
        task_description="Open Chrome, navigate to ChatGPT, and ask a question.",
        sequence=[
            {"action_name": "hotkey:ctrl+l", "status": "success", "duration": 10},
            {"action_name": "clipboard_set:url", "status": "success", "duration": 5},
        ],
        run_status="success",
        run_note="Initial run.",
        elapsed_time=420.0,
        change_summary="Initial raw sequence capture.",
        change_reason="First execution of the task.",
    )

    updated = store.commit_task_record(
        record_id=created["record"]["record_id"],
        user_query="Open Chrome and go to ChatGPT.",
        task_description="Open Chrome, navigate to ChatGPT, and ask a question.",
        sequence=[
            {"action_name": "navigate_chatgpt", "status": "success", "duration": 18},
            {"action_name": "wait:3s", "status": "success", "duration": 3000},
        ],
        run_status="success",
        run_note="Merged navigation sequence.",
        elapsed_time=390.0,
        change_summary="Merged URL paste and enter into one step.",
        change_reason="Reduced observation overhead.",
    )

    record = store.get_task_record(updated["record"]["record_id"])
    assert len(record.versions) == 2
    assert updated["action"] == "append_version"
    assert record.latest_success_version_id == record.versions[-1].version_id
    assert record.versions[-1].parent_version_id == record.versions[0].version_id


def test_search_returns_matching_task_records(tmp_path):
    store = MemoryStore(memory_dir=tmp_path / "memories")
    store.commit_task_record(
        user_query="Open Chrome and go to ChatGPT.",
        task_description="Open Chrome, navigate to ChatGPT, and ask a question.",
        sequence=[{"action_name": "open_chrome", "status": "success", "duration": 1}],
        run_status="success",
        run_note="Initial run.",
        elapsed_time=100.0,
    )
    store.commit_task_record(
        user_query="Open Notepad and type a sentence.",
        task_description="Open Notepad and enter text.",
        sequence=[{"action_name": "open_notepad", "status": "success", "duration": 1}],
        run_status="success",
        run_note="Initial run.",
        elapsed_time=80.0,
    )

    result = store.search(goal="Open Chrome, navigate to ChatGPT, and ask a question.")

    assert result["task_records"]
    assert "ChatGPT" in result["task_records"][0]["task_description"]
