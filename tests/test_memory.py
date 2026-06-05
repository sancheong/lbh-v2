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


def test_commit_stores_codex_draft_sequence_separately_from_raw_sequence(tmp_path):
    store = MemoryStore(memory_dir=tmp_path / "memories")

    created = store.commit_task_record(
        user_query="Open Chrome and go to ChatGPT.",
        task_description="Open Chrome, navigate to ChatGPT, and ask a question.",
        sequence=[
            {"action_name": "hotkey:ctrl+l", "status": "success", "duration": 0.4},
            {"action_name": "clipboard_set:url", "status": "success", "duration": 0.01},
            {"action_name": "hotkey:ctrl+v", "status": "success", "duration": 0.1},
            {"action_name": "press:enter", "status": "success", "duration": 0.1},
        ],
        draft_sequence=[
            {
                "type": "batch",
                "status": "success",
                "payload": {
                    "observe_after": True,
                    "actions": [
                        {"type": "hotkey", "keys": ["ctrl", "l"], "reason": "Focus address bar."},
                        {"type": "clipboard_set", "text": "https://chatgpt.com", "reason": "Prepare URL."},
                        {"type": "hotkey", "keys": ["ctrl", "v"], "reason": "Paste URL."},
                        {"type": "press", "key": "enter", "reason": "Navigate."},
                    ],
                },
            }
        ],
        run_status="success",
        run_note="Initial run.",
        elapsed_time=100.0,
    )

    summary = store.search(goal="Open Chrome")["task_records"][0]["success_versions"][0]

    assert created["record"]["versions"][0]["sequence"][0]["action_name"] == "hotkey:ctrl+l"
    assert summary["draft_sequence"][0]["payload"]["actions"][1]["text"] == "https://chatgpt.com"
    assert summary["planning_summary"]["draft_batch_count"] == 1
    assert summary["planning_summary"]["draft_action_count"] == 4


def test_commit_preserves_task_type_metadata(tmp_path):
    store = MemoryStore(memory_dir=tmp_path / "memories")

    created = store.commit_task_record(
        user_query="Create a private GitHub repository named demo.",
        task_description="Parameterized private GitHub repository creation.",
        task_type="github_private_repo_create",
        parameter_schema={"repo_name": {"type": "string", "required": True}},
        start_state_requirements=["Desktop is visible.", "GitHub profile is signed in."],
        optimization_summary={"removed_observation_checkpoints": 7},
        sequence=[{"action_name": "hotkey:win+r", "status": "success", "duration": 0.3}],
        draft_sequence=[{"type": "batch", "payload": {"actions": [{"type": "hotkey", "keys": ["win", "r"], "reason": "Open Run."}]}}],
        run_status="success",
        run_note="Initial optimized memory.",
        elapsed_time=20.0,
    )

    record_id = created["record"]["record_id"]
    summary = store.search(goal="Create GitHub repository demo")["task_records"][0]
    view = store.get_task_record_view(record_id)

    assert summary["task_type"] == "github_private_repo_create"
    assert summary["parameter_schema"]["repo_name"]["required"] is True
    assert view["start_state_requirements"][0] == "Desktop is visible."
    assert view["optimization_summary"]["removed_observation_checkpoints"] == 7


def test_commit_changed_draft_sequence_appends_new_success_version(tmp_path):
    store = MemoryStore(memory_dir=tmp_path / "memories")
    created = store.commit_task_record(
        user_query="Open Chrome and go to ChatGPT.",
        task_description="Open Chrome, navigate to ChatGPT, and ask a question.",
        sequence=[{"action_name": "open_chrome", "status": "success", "duration": 1}],
        draft_sequence=[{"type": "action", "payload": {"type": "window_activate", "reason": "Focus Chrome."}}],
        run_status="success",
        run_note="Initial run.",
        elapsed_time=100.0,
    )

    updated = store.commit_task_record(
        record_id=created["record"]["record_id"],
        user_query="Open Chrome and go to ChatGPT.",
        task_description="Open Chrome, navigate to ChatGPT, and ask a question.",
        sequence=[{"action_name": "open_chrome", "status": "success", "duration": 1}],
        draft_sequence=[{"type": "action", "payload": {"type": "window_activate", "reason": "Focus existing Chrome window."}}],
        run_status="success",
        run_note="Refined draft only.",
        elapsed_time=95.0,
        change_summary="Refined executable draft.",
        change_reason="The raw fingerprint sequence stayed the same, but Codex should see the improved draft.",
    )

    assert updated["action"] == "append_version"
    assert len(updated["record"]["versions"]) == 2


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


def test_derive_draft_sequence_from_events_preserves_batch_payload(tmp_path):
    store = MemoryStore(memory_dir=tmp_path / "memories")

    draft = store.derive_draft_sequence_from_events(
        [
            {
                "type": "action",
                "batch_id": "batch-1",
                "action": {"type": "hotkey", "keys": ["ctrl", "l"], "fingerprint": "hotkey:ctrl+l"},
                "primitive_status": "success",
                "duration_ms": 100.0,
            },
            {
                "type": "batch",
                "batch_id": "batch-1",
                "status": "success",
                "duration_ms": 500.0,
                "batch": {
                    "observe_after": True,
                    "expectation": {"title_contains_any": ["ChatGPT"]},
                    "actions": [
                        {"type": "hotkey", "keys": ["ctrl", "l"], "reason": "Focus address bar."},
                        {"type": "clipboard_set", "text": "https://chatgpt.com", "reason": "Prepare URL."},
                    ],
                },
            },
            {
                "type": "action",
                "status": "success",
                "primitive_status": "success",
                "duration_ms": 50.0,
                "action": {"type": "clipboard_get", "reason": "Verify response.", "fingerprint": "clipboard_get"},
            },
        ]
    )

    assert len(draft) == 2
    assert draft[0]["type"] == "batch"
    assert draft[0]["payload"]["actions"][1]["text"] == "https://chatgpt.com"
    assert draft[1]["type"] == "action"
    assert "fingerprint" not in draft[1]["payload"]
