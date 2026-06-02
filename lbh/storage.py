from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
import re
import shutil
from typing import Any

from .config import LBHConfig, DEFAULT_CONFIG
from .models import TaskState


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value).strip()).strip("-._")
    return slug.lower() or "lbh-task"


class TaskStore:
    def __init__(self, config: LBHConfig = DEFAULT_CONFIG):
        self.config = config
        self.tasks_dir = Path(config.tasks_dir)
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

    def create_task(self, goal: str, task_id: str | None = None, force: bool = False) -> TaskState:
        if not task_id:
            task_id = f"{datetime.now().strftime('%Y-%m-%d-%H%M%S')}-{safe_slug(goal)[:48]}"
        task_id = safe_slug(task_id)
        task_dir = self.tasks_dir / task_id
        if task_dir.exists() and not force:
            raise FileExistsError(f"Task already exists: {task_dir}")
        if task_dir.exists():
            shutil.rmtree(task_dir)
        (task_dir / "screenshots").mkdir(parents=True, exist_ok=True)
        (task_dir / "artifacts").mkdir(parents=True, exist_ok=True)
        state = TaskState(
            task_id=task_id,
            goal=goal,
            task_dir=str(task_dir.resolve()),
            created_at=now_iso(),
            updated_at=now_iso(),
        )
        (task_dir / "goal.md").write_text(f"# Goal\n\n{goal}\n", encoding="utf-8")
        self.write_state(state)
        self.append_log(task_id, "task_created", "Task created", {"goal": goal})
        return state

    def task_dir(self, task: str | Path) -> Path:
        path = Path(task)
        if not path.is_absolute():
            path = self.tasks_dir / path
        if not path.exists():
            raise FileNotFoundError(f"Task directory not found: {path}")
        return path

    def read_state(self, task: str | Path) -> TaskState:
        task_dir = self.task_dir(task)
        data = json.loads((task_dir / "state.json").read_text(encoding="utf-8"))
        return TaskState(**data)

    def write_state(self, state: TaskState) -> TaskState:
        state.updated_at = now_iso()
        path = Path(state.task_dir) / "state.json"
        path.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return state

    def append_log(self, task: str | Path, event_type: str, summary: str, payload: dict[str, Any] | None = None) -> Path:
        task_dir = self.task_dir(task)
        entry = {
            "timestamp": now_iso(),
            "type": event_type,
            "summary": summary,
            "payload": payload or {},
        }
        log_path = task_dir / "events.jsonl"
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return log_path

    def screenshots_dir(self, task: str | Path) -> Path:
        path = self.task_dir(task) / "screenshots"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def cleanup_screenshots(self, task: str | Path) -> None:
        screenshots = self.screenshots_dir(task)
        limit = self.config.screenshot.max_screenshots_per_task
        if limit <= 0:
            return
        files = sorted(screenshots.glob("*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in files[limit:]:
            try:
                path.unlink()
            except OSError:
                pass
