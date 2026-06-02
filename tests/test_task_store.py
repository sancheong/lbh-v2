from lbh.task_store import TaskStore


def test_task_store_create_and_events(tmp_path):
    store = TaskStore(tasks_dir=tmp_path / "tasks")
    state = store.create_task("Open Chrome.", task_id="task-1")
    assert state.task_id == "task-1"
    store.append_event("task-1", "observation", "Captured resized observation.", status="success")
    events = store.read_events("task-1")
    assert len(events) == 1
    assert events[0]["type"] == "observation"
