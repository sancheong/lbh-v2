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
    first = store.commit_task_record(
        user_query="Open Chrome and go to ChatGPT.",
        task_description="Open Chrome, navigate to ChatGPT, and ask a question.",
        sequence=[{"action_name": "open_chrome", "status": "success", "duration": 1}],
        run_status="success",
        run_note="Initial run.",
        elapsed_time=100.0,
    )
    second = store.commit_task_record(
        user_query="Open Notepad and type a sentence.",
        task_description="Open another app and enter text.",
        sequence=[{"action_name": "open_notepad", "status": "success", "duration": 1}],
        run_status="success",
        run_note="Initial run.",
        elapsed_time=80.0,
    )

    result = store.search(goal="Open app")

    assert result["task_cards"]
    assert result["task_cards"][0]["record_id"] == second["record"]["record_id"]
    assert result["task_cards"][1]["record_id"] == first["record"]["record_id"]


def test_task_card_includes_latest_success_version_and_recent_failures(tmp_path):
    store = MemoryStore(memory_dir=tmp_path / "memories")
    created = store.commit_task_record(
        user_query="Open Chrome and go to ChatGPT.",
        task_description="Open Chrome, navigate to ChatGPT, and ask a question.",
        sequence=[{"action_name": "open_chrome", "status": "success", "duration": 1}],
        run_status="success",
        run_note="Initial run.",
        elapsed_time=100.0,
        change_summary="Initial sequence.",
        change_reason="First run.",
    )

    for index in range(4):
        store.commit_task_record(
            record_id=created["record"]["record_id"],
            user_query="Open Chrome and go to ChatGPT.",
            task_description="Open Chrome, navigate to ChatGPT, and ask a question.",
            sequence=[{"action_name": "open_chrome", "status": "success", "duration": 1}],
            run_status="failure",
            run_note=f"Failure {index}",
            elapsed_time=100.0 + index,
        )

    result = store.search(goal="Open Chrome")

    card = result["task_cards"][0]
    assert card["latest_success_version"] is not None
    assert card["baseline_version"] is not None
    assert card["latest_success_version"]["sequence"][0]["action_name"] == "open_chrome"
    assert card["baseline_version"]["sequence"][0]["action_name"] == "open_chrome"
    assert len(card["recent_failures"]) == 3
    assert card["recent_failures"][0]["note"] == "Failure 3"


def test_get_task_record_view_returns_full_version_history(tmp_path):
    store = MemoryStore(memory_dir=tmp_path / "memories")
    created = store.commit_task_record(
        user_query="Open Chrome and go to ChatGPT.",
        task_description="Open Chrome, navigate to ChatGPT, and ask a question.",
        sequence=[{"action_name": "open_chrome", "status": "success", "duration": 1}],
        run_status="success",
        run_note="Initial run.",
        elapsed_time=100.0,
        change_summary="Initial sequence.",
        change_reason="First run.",
    )

    record = store.get_task_record_view(created["record"]["record_id"])

    assert record is not None
    assert record["versions"][0]["change_summary"] == "Initial sequence."
    assert record["versions"][0]["run_records"][0]["note"] == "Initial run."


def test_task_card_exposes_baseline_version_when_no_success_exists(tmp_path):
    store = MemoryStore(memory_dir=tmp_path / "memories")
    store.commit_task_record(
        user_query="Open Chrome and go to ChatGPT.",
        task_description="Open Chrome, navigate to ChatGPT, and ask a question.",
        sequence=[{"action_name": "open_chrome", "status": "success", "duration": 1}],
        run_status="failure",
        run_note="Initial attempt failed.",
        elapsed_time=100.0,
        change_summary="Initial failed sequence.",
        change_reason="First run still needs to be preserved.",
    )

    result = store.search(goal="Open Chrome")

    card = result["task_cards"][0]
    assert card["latest_success_version"] is None
    assert card["baseline_version"] is not None
    assert card["baseline_version"]["sequence"][0]["action_name"] == "open_chrome"
