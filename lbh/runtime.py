from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .actions import PyAutoGuiExecutor
from .capture import PyAutoGuiCapture
from .config import LBHConfig, DEFAULT_CONFIG
from .coordinates import ResizeTransform
from .locator import LocatorCache, LocatorContract
from .memory import (
    EpisodeRecord,
    FailureGuard,
    MemoryStore,
    SituationSignature,
    batch_signature,
    now_iso,
)
from .models import ActionBatch, AtomicAction, CoordSpace, LocatorResult, Observation, Point
from .storage import TaskStore


class LBHRuntime:
    def __init__(self, config: LBHConfig = DEFAULT_CONFIG):
        self.config = config
        self.store = TaskStore(config)
        self.capture_provider = PyAutoGuiCapture(config, self.store)
        self.executor = PyAutoGuiExecutor()
        self.memory = MemoryStore(config)

    def create_task(self, goal: str, task_id: str | None = None, force: bool = False):
        return self.store.create_task(goal, task_id=task_id, force=force)

    def observe(self, task: str | Path) -> Observation:
        return self.capture_provider.capture(task)

    def _latest_transform(self, task: str | Path) -> ResizeTransform:
        state = self.store.read_state(task)
        obs = state.latest_observation
        if not obs:
            obs_obj = self.observe(task)
            obs = obs_obj.to_dict()
        return ResizeTransform(
            desktop_width=int(obs["desktop_width"]),
            desktop_height=int(obs["desktop_height"]),
            image_width=int(obs["image_width"]),
            image_height=int(obs["image_height"]),
        )

    def execute_action(self, task: str | Path, action: AtomicAction, observe_after: bool = True) -> dict[str, Any]:
        transform = self._latest_transform(task)
        started = time.perf_counter()
        result = self.executor.execute(action, transform=transform)
        elapsed = round((time.perf_counter() - started) * 1000)
        payload = {"status": "success", "action_result": result, "elapsed_ms": elapsed}
        self.store.append_log(task, "action", f"Executed {action.type}", payload)
        state = self.store.read_state(task)
        state.latest_action_result = payload
        self.store.write_state(state)
        if observe_after:
            payload["post_observation"] = self.observe(task).to_dict()
        return payload

    def execute_batch(self, task: str | Path, batch: ActionBatch) -> dict[str, Any]:
        state = self.store.read_state(task)
        situation = SituationSignature.from_observation(state.goal, state.latest_observation)
        guards = self.memory.find_relevant_failure_guards(situation, batch)
        if guards:
            payload = {
                "status": "blocked_by_memory_guard",
                "guards": guards,
                "proposed_batch": batch.to_dict(),
            }
            self.store.append_log(task, "memory_guard", "Blocked proposed action batch by failure memory", payload)
            return payload

        transform = self._latest_transform(task)
        before = self.store.read_state(task).latest_observation
        started = time.perf_counter()
        result = self.executor.execute_many(batch.actions, transform=transform)
        elapsed = round((time.perf_counter() - started) * 1000)
        after = self.observe(task).to_dict() if batch.observe_after else None
        payload = {
            "status": "success",
            "batch_result": result,
            "elapsed_ms": elapsed,
            "post_observation": after,
        }
        self.store.append_log(task, "action_batch", f"Executed {len(batch.actions)} actions", {**payload, "batch": batch.to_dict()})

        # Store episode record. Outcome is provisional success at the runtime layer;
        # higher-level controller can later record task-level failure/rollback.
        self.memory.remember_episode(
            EpisodeRecord(
                id=f"episode-{state.task_id}-{int(time.time() * 1000)}",
                created_at=now_iso(),
                task_id=state.task_id,
                goal=state.goal,
                situation=situation.__dict__,
                action_batch=batch.to_dict(),
                outcome="success" if payload["status"] == "success" else "unknown",
                latency_ms=elapsed,
                observation_before=before,
                observation_after=after,
            )
        )
        state = self.store.read_state(task)
        state.latest_action_result = payload
        self.store.write_state(state)
        return payload

    def locator_contract(self, task: str | Path, target: str) -> dict[str, Any]:
        state = self.store.read_state(task)
        if not state.latest_observation:
            obs = self.observe(task).to_dict()
        else:
            obs = state.latest_observation
        prompt = LocatorContract.build_prompt(target, obs)
        return {
            "status": "success",
            "target": target,
            "image_path": obs["image_path"],
            "prompt": prompt,
            "observation": obs,
        }

    def cache_locator_result(self, task: str | Path, result: LocatorResult) -> dict[str, Any]:
        state = self.store.read_state(task)
        obs = state.latest_observation
        if not obs:
            raise ValueError("No observation available to cache locator result")
        active = obs.get("active_window") or {}
        cache = LocatorCache(Path(state.task_dir) / "locator_cache.json")
        cache.put(result.target, obs["screenshot_hash"], active.get("title"), result)
        self.store.append_log(task, "locator_cache", f"Cached locator result for {result.target}", result.to_dict())
        return {"status": "success", "cached": result.to_dict()}

    def locate_from_json(self, task: str | Path, response_text: str) -> dict[str, Any]:
        result = LocatorContract.parse_response(response_text)
        state = self.store.read_state(task)
        transform = self._latest_transform(task)
        desktop_center = None
        if result.center:
            desktop_center = transform.point_to_desktop(result.center).to_dict()
        payload = {"status": "success", "locator_result": result.to_dict(), "desktop_center": desktop_center}
        self.cache_locator_result(task, result)
        self.store.append_log(task, "locator_result", f"Parsed locator result for {result.target}", payload)
        return payload

    def propose_skills(self, task: str | Path) -> dict[str, Any]:
        state = self.store.read_state(task)
        situation = SituationSignature.from_observation(state.goal, state.latest_observation)
        return {"status": "success", "skills": self.memory.propose_skills(situation)}

    def consolidate_skills(self) -> dict[str, Any]:
        skills = self.memory.consolidate_simple_skills()
        return {"status": "success", "created": [s.__dict__ for s in skills]}
