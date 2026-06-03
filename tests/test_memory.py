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


def test_commit_normalizes_legacy_millisecond_timings(tmp_path):
    store = MemoryStore(memory_dir=tmp_path / "memories")

    created = store.commit_task_record(
        user_query="Open Chrome and go to ChatGPT.",
        task_description="Open Chrome, navigate to ChatGPT, and ask a question.",
        sequence=[
            {"action_name": "hotkey:ctrl+l", "status": "success", "duration": 455.0},
            {"action_name": "wait:3s", "status": "success", "duration": 3000.0},
        ],
        run_status="success",
        run_note="Legacy millisecond timing input.",
        elapsed_time=303000.0,
        change_summary="Initial raw sequence capture.",
        change_reason="First execution of the task.",
    )

    record = store.get_task_record(created["record"]["record_id"])
    assert record is not None
    assert record.versions[0].sequence[0].duration == 0.455
    assert record.versions[0].sequence[1].duration == 3.0
    assert record.versions[0].run_records[0].elapsed_time == 303.0


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


def test_commit_failed_changed_sequence_appends_run_instead_of_version(tmp_path):
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
            {"action_name": "press:end", "status": "success", "duration": 4},
            {"action_name": "press:pagedown", "status": "success", "duration": 4},
        ],
        run_status="failure",
        run_note="Response never appeared.",
        elapsed_time=500.0,
        change_summary="Failure branch should not become a new version.",
        change_reason="Failures are kept as run history only.",
    )

    record = store.get_task_record(updated["record"]["record_id"])
    assert len(record.versions) == 1
    assert len(record.versions[0].run_records) == 2
    assert updated["action"] == "append_run"
    assert record.latest_success_version_id == record.versions[0].version_id


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

    assert result["task_records"]
    assert result["task_records"][0]["record_id"] == second["record"]["record_id"]
    assert result["task_records"][1]["record_id"] == first["record"]["record_id"]


def test_task_record_summary_includes_success_versions_and_recent_failures(tmp_path):
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

    summary = result["task_records"][0]
    assert summary["success_versions"]
    assert summary["latest_success_version_id"] is not None
    assert summary["success_versions"][0]["sequence"][0]["action_name"] == "open_chrome"
    assert len(summary["recent_failures"]) == 3
    assert summary["recent_failures"][0]["note"] == "Failure 3"


def test_task_record_summary_lists_multiple_success_versions_newest_first(tmp_path):
    store = MemoryStore(memory_dir=tmp_path / "memories")
    created = store.commit_task_record(
        user_query="Open Chrome and go to ChatGPT.",
        task_description="Open Chrome, navigate to ChatGPT, and ask a question.",
        sequence=[
            {"action_name": "hotkey:ctrl+l", "status": "success", "duration": 0.4},
            {"action_name": "clipboard_set:url", "status": "success", "duration": 0.01},
            {"action_name": "hotkey:ctrl+v", "status": "success", "duration": 0.1},
            {"action_name": "press:enter", "status": "success", "duration": 0.1},
            {"action_name": "wait:3s", "status": "success", "duration": 3.0},
            {"action_name": "clipboard_set", "status": "success", "duration": 0.01},
            {"action_name": "hotkey:ctrl+v", "status": "success", "duration": 0.1},
            {"action_name": "press:enter", "status": "success", "duration": 0.1},
        ],
        run_status="success",
        run_note="Compact success.",
        elapsed_time=180.0,
        change_summary="Compact success path.",
        change_reason="Initial stable draft.",
    )

    store.commit_task_record(
        record_id=created["record"]["record_id"],
        user_query="Open Chrome and go to ChatGPT.",
        task_description="Open Chrome, navigate to ChatGPT, and ask a question.",
        sequence=[
            {"action_name": "window_activate:chrome", "status": "success", "duration": 0.2},
            {"action_name": "hotkey:ctrl+l", "status": "success", "duration": 0.4},
            {"action_name": "clipboard_set:url", "status": "success", "duration": 0.01},
            {"action_name": "hotkey:ctrl+v", "status": "success", "duration": 0.1},
            {"action_name": "press:enter", "status": "success", "duration": 0.1},
            {"action_name": "wait:3s", "status": "success", "duration": 3.0},
            {"action_name": "click:left:resized_image", "status": "success", "duration": 0.5},
            {"action_name": "hotkey:ctrl+l", "status": "success", "duration": 0.4},
            {"action_name": "clipboard_set:url", "status": "success", "duration": 0.01},
            {"action_name": "hotkey:ctrl+v", "status": "success", "duration": 0.1},
            {"action_name": "press:enter", "status": "success", "duration": 0.1},
            {"action_name": "wait:3s", "status": "success", "duration": 3.0},
            {"action_name": "hotkey:ctrl+a", "status": "success", "duration": 0.4},
            {"action_name": "hotkey:ctrl+c", "status": "success", "duration": 0.1},
        ],
        run_status="success",
        run_note="Latest but noisier success.",
        elapsed_time=150.0,
        change_summary="Noisier success path.",
        change_reason="Recorded a later but more repetitive path.",
    )

    result = store.search(goal="Open Chrome")

    summary = result["task_records"][0]
    assert summary["latest_success_version_id"] is not None
    assert len(summary["success_versions"]) == 2
    assert summary["success_versions"][0]["change_summary"] == "Noisier success path."
    assert summary["success_versions"][1]["change_summary"] == "Compact success path."


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


def test_task_record_summary_has_no_success_versions_when_no_success_exists(tmp_path):
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

    summary = result["task_records"][0]
    assert summary["latest_success_version_id"] is None
    assert summary["success_versions"] == []


def test_commit_uses_explicit_base_version_when_provided(tmp_path):
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
    record_id = created["record"]["record_id"]
    root_version_id = created["version_id"]
    updated = store.commit_task_record(
        record_id=record_id,
        base_version_id=root_version_id,
        user_query="Open Chrome and go to ChatGPT.",
        task_description="Open Chrome, navigate to ChatGPT, and ask a question.",
        sequence=[{"action_name": "navigate_chatgpt", "status": "success", "duration": 2}],
        run_status="success",
        run_note="Refined run.",
        elapsed_time=95.0,
        change_summary="Refined sequence.",
        change_reason="Use the chosen draft as the parent.",
    )

    assert updated["action"] == "append_version"
    assert updated["record"]["versions"][-1]["parent_version_id"] == root_version_id


def test_derive_sequence_from_events_uses_seconds(tmp_path):
    store = MemoryStore(memory_dir=tmp_path / "memories")

    sequence = store.derive_sequence_from_events(
        [
            {
                "type": "action",
                "action": {"fingerprint": "press:enter"},
                "primitive_status": "success",
                "duration_ms": 1250.0,
            }
        ]
    )

    assert sequence[0]["duration"] == 1.25
