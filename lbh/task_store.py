from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil
from typing import Any

from .common import (
    DEFAULT_JPEG_QUALITY,
    DEFAULT_MODEL_MAX_WIDTH,
    DEFAULT_NO_PROGRESS_THRESHOLD,
    TASKS_DIR,
    append_jsonl,
    ensure_dir,
    iter_jsonl,
    now_iso,
    read_json,
    read_text,
    safe_slug,
    write_json,
    write_text,
)
from .contracts import TaskState
from .errors import TaskStateError


class TaskStore:
    def __init__(self, tasks_dir: Path = TASKS_DIR):
        self.tasks_dir = tasks_dir

    def resolve_task(self, task: str | Path) -> Path:
        path = Path(task)
        if not path.is_absolute():
            path = self.tasks_dir / path
        resolved = path.resolve()
        tasks_root = self.tasks_dir.resolve()
        if resolved != tasks_root and tasks_root not in resolved.parents:
            raise TaskStateError(f"Task path must stay under {tasks_root}: {resolved}")
        return resolved

    def paths_for(self, task: str | Path) -> dict[str, Path]:
        task_dir = self.resolve_task(task)
        return {
            "task_dir": task_dir,
            "goal": task_dir / "goal.md",
            "state": task_dir / "state.json",
            "events": task_dir / "events.jsonl",
            "result": task_dir / "result.md",
            "screenshots": task_dir / "screenshots",
            "artifacts": task_dir / "artifacts",
            "memory_updates": task_dir / "memory_updates.jsonl",
        }

    def create_task(
        self,
        goal: str,
        *,
        task_id: str | None = None,
        model_max_width: int = DEFAULT_MODEL_MAX_WIDTH,
        jpeg_quality: int = DEFAULT_JPEG_QUALITY,
        no_progress_threshold: int = DEFAULT_NO_PROGRESS_THRESHOLD,
        force: bool = False,
    ) -> TaskState:
        timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        slug = safe_slug(goal, fallback="lbh-task")[:48]
        resolved_id = safe_slug(task_id, fallback=f"{timestamp}-{slug}") if task_id else f"{timestamp}-{slug}"
        task_dir = self.resolve_task(resolved_id)
        if task_dir.exists():
            if not force:
                raise TaskStateError(f"Task already exists: {task_dir}")
            shutil.rmtree(task_dir)

        ensure_dir(task_dir)
        ensure_dir(task_dir / "screenshots")
        ensure_dir(task_dir / "artifacts")
        write_text(
            task_dir / "goal.md",
            "\n".join(
                [
                    "# Goal",
                    "",
                    goal.strip(),
                    "",
                    "## LBH V2 Runtime",
                    "",
                    f"- Model max width: {model_max_width}",
                    "- Coordinate contract: resized_image -> desktop conversion is mandatory for GUI actions.",
                    "- Use suspend for login, 2FA, CAPTCHA, UAC, payments, or irreversible actions.",
                    "",
                ]
            ),
        )
        write_text(task_dir / "result.md", "# Result\n\nPending.\n")
        write_text(task_dir / "events.jsonl", "")
        write_text(task_dir / "memory_updates.jsonl", "")

        state = TaskState(
            task_id=resolved_id,
            goal=goal.strip(),
            task_dir=str(task_dir.resolve()),
            status="active",
            created_at=now_iso(),
            updated_at=now_iso(),
            model_max_width=model_max_width,
            jpeg_quality=jpeg_quality,
            no_progress_threshold=no_progress_threshold,
        )
        write_json(task_dir / "state.json", state.to_dict())
        return state

    def load_state(self, task: str | Path) -> TaskState:
        state_path = self.paths_for(task)["state"]
        payload = read_json(state_path)
        if not payload:
            raise TaskStateError(f"Task state does not exist: {state_path}")
        return TaskState.from_dict(payload)

    def save_state(self, state: TaskState) -> TaskState:
        state.updated_at = now_iso()
        write_json(self.paths_for(state.task_dir)["state"], state.to_dict())
        return state

    def append_event(self, task: str | Path, event_type: str, summary: str, **payload: Any) -> dict[str, Any]:
        event = {"timestamp": now_iso(), "type": event_type, "summary": summary}
        event.update({key: value for key, value in payload.items() if value is not None})
        append_jsonl(self.paths_for(task)["events"], event)
        return event

    def read_events(self, task: str | Path, limit: int | None = None) -> list[dict[str, Any]]:
        events = list(iter_jsonl(self.paths_for(task)["events"]))
        return events[-limit:] if limit is not None else events

    def read_goal(self, task: str | Path) -> str:
        lines = read_text(self.paths_for(task)["goal"]).splitlines()
        cleaned = []
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("-"):
                continue
            cleaned.append(stripped)
        return " ".join(cleaned[:6]).strip()

    def write_result(self, task: str | Path, answer: str) -> str:
        result_path = self.paths_for(task)["result"]
        write_text(result_path, "\n".join(["# Result", "", answer.strip(), ""]))
        return str(result_path.resolve())

    def append_memory_update(self, task: str | Path, payload: dict[str, Any]) -> dict[str, Any]:
        append_jsonl(self.paths_for(task)["memory_updates"], payload)
        return payload
