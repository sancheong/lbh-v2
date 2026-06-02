from __future__ import annotations

from pathlib import Path
import time
import uuid
from typing import Any

from .capture import CaptureService
from .common import DEFAULT_JPEG_QUALITY, DEFAULT_MODEL_MAX_WIDTH
from .contracts import ActionBatch, ActionSpec, CoordinateSpace, CoordinateTransform, LocatorResult, TaskState
from .errors import TaskStateError
from .evaluator import StabilityWaiter, evaluate_observation_progress
from .locator import build_locator_prompt, parse_locator_response
from .memory import MemoryStore
from .platform import DesktopAdapter, PyAutoGUIDesktopAdapter
from .task_store import TaskStore


class LBHRuntime:
    def __init__(
        self,
        *,
        adapter: DesktopAdapter | None = None,
        task_store: TaskStore | None = None,
        memory_store: MemoryStore | None = None,
        memory_reference_enabled: bool = False,
    ):
        self.adapter = adapter or PyAutoGUIDesktopAdapter()
        self.task_store = task_store or TaskStore()
        self.memory_store = memory_store or MemoryStore()
        self.memory_reference_enabled = memory_reference_enabled
        self.capture_service = CaptureService(self.adapter)
        self.waiter = StabilityWaiter(self.capture_service)

    def create_task(
        self,
        goal: str,
        *,
        task_id: str | None = None,
        model_max_width: int = DEFAULT_MODEL_MAX_WIDTH,
        jpeg_quality: int = DEFAULT_JPEG_QUALITY,
        force: bool = False,
    ) -> dict[str, Any]:
        state = self.task_store.create_task(
            goal,
            task_id=task_id,
            model_max_width=model_max_width,
            jpeg_quality=jpeg_quality,
            force=force,
        )
        state.memory_context = self._automatic_memory_context(goal=goal, observation=None)
        self.task_store.save_state(state)
        self.task_store.append_event(
            state.task_dir,
            "task_started",
            "Started LBH V2 task.",
            status="success",
            goal=goal,
            model_max_width=model_max_width,
            jpeg_quality=jpeg_quality,
            relevant_memory=state.memory_context,
        )
        return {
            "status": "success",
            "task": state.to_dict(),
            "paths": self.paths_payload(state.task_dir),
            "relevant_memory": state.memory_context,
        }

    def observe(self, task: str | Path, *, save_full_resolution: bool = False) -> dict[str, Any]:
        state = self.task_store.load_state(task)
        return self._record_observation(
            state,
            expectation=None,
            label="observe",
            save_full_resolution=save_full_resolution,
        )

    def execute_action(
        self,
        task: str | Path,
        action_payload: ActionSpec | dict[str, Any],
        *,
        observe_after: bool = True,
        ignore_guards: bool = False,
    ) -> dict[str, Any]:
        state = self.task_store.load_state(task)
        self._ensure_mutable_task(state)
        action = action_payload if isinstance(action_payload, ActionSpec) else ActionSpec.from_dict(action_payload)
        pre_observation = state.latest_observation
        guard_matches = self._automatic_guard_matches(
            goal=state.goal,
            observation=pre_observation,
            action_fingerprints=[action.fingerprint()],
        )
        if not ignore_guards and any(match["decision"] == "block" for match in guard_matches):
            self.task_store.append_event(
                state.task_dir,
                "memory_guard",
                f"Blocked {action.type} by failure guard memory.",
                status="blocked",
                action=action.to_dict(),
                guard_matches=guard_matches,
            )
            return {"status": "blocked_by_failure_guard", "action": action.to_dict(), "guard_matches": guard_matches}

        transform = self._transform_for_action(state, action)
        started = time.perf_counter()
        status = "success"
        result = None
        error = None
        try:
            result = self._execute_primitive(action, transform)
        except Exception as exc:
            status = "error"
            error = {"error_type": exc.__class__.__name__, "message": str(exc)}
        duration_ms = round((time.perf_counter() - started) * 1000, 3)

        post_observation = None
        evaluation = None
        relevant_memory = state.memory_context
        if status == "success" and observe_after:
            observation_result = self._record_observation(state, expectation=action.expectation, label="post-action")
            post_observation = observation_result["observation"]
            evaluation = observation_result["evaluation"]
            relevant_memory = observation_result["relevant_memory"]
            state = self.task_store.load_state(task)

        event_action = {**action.to_dict(), "fingerprint": action.fingerprint()}
        self.task_store.append_event(
            state.task_dir,
            "action",
            f"Executed {action.type}.",
            status=status,
            duration_ms=duration_ms,
            action=event_action,
            result=result,
            error=error,
            guard_matches=guard_matches,
            pre_observation=pre_observation,
            post_observation=post_observation,
            evaluation=evaluation,
            coordinate_transform=transform.to_dict() if transform else None,
        )
        state.latest_action = {
            "status": status,
            "action": event_action,
            "result": result,
            "error": error,
            "duration_ms": duration_ms,
            "observed_after": observe_after,
        }
        state.latency_metrics["last_action_ms"] = duration_ms
        self.task_store.save_state(state)
        return {
            "status": status,
            "action": event_action,
            "result": result,
            "error": error,
            "duration_ms": duration_ms,
            "guard_matches": guard_matches,
            "post_observation": post_observation,
            "evaluation": evaluation,
            "relevant_memory": relevant_memory,
        }

    def execute_batch(
        self,
        task: str | Path,
        batch_payload: ActionBatch | dict[str, Any] | list[dict[str, Any]],
        *,
        ignore_guards: bool = False,
    ) -> dict[str, Any]:
        state = self.task_store.load_state(task)
        self._ensure_mutable_task(state)
        batch = batch_payload if isinstance(batch_payload, ActionBatch) else ActionBatch.from_payload(batch_payload)
        pre_observation = state.latest_observation
        guard_matches = self._automatic_guard_matches(
            goal=state.goal,
            observation=pre_observation,
            action_fingerprints=[action.fingerprint() for action in batch.actions],
        )
        if not ignore_guards and any(match["decision"] == "block" for match in guard_matches):
            self.task_store.append_event(
                state.task_dir,
                "memory_guard",
                "Blocked action batch by failure guard memory.",
                status="blocked",
                batch=batch.to_dict(),
                guard_matches=guard_matches,
            )
            return {"status": "blocked_by_failure_guard", "batch": batch.to_dict(), "guard_matches": guard_matches}

        transform = self._transform_for_batch(state, batch)
        batch_id = uuid.uuid4().hex
        started = time.perf_counter()
        primitive_results: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        completed = True
        for index, action in enumerate(batch.actions):
            elapsed = time.perf_counter() - started
            if batch.max_duration_seconds and elapsed > batch.max_duration_seconds:
                errors.append({"error_type": "TimeoutError", "message": f"Batch exceeded max_duration_seconds={batch.max_duration_seconds}."})
                completed = False
                break
            action_started = time.perf_counter()
            status = "success"
            result = None
            error = None
            try:
                result = self._execute_primitive(action, transform)
            except Exception as exc:
                status = "error"
                error = {"error_type": exc.__class__.__name__, "message": str(exc)}
                errors.append(error)
            duration_ms = round((time.perf_counter() - action_started) * 1000, 3)
            primitive_payload = {
                "status": status,
                "action": {**action.to_dict(), "fingerprint": action.fingerprint()},
                "result": result,
                "error": error,
                "duration_ms": duration_ms,
                "index": index,
            }
            primitive_results.append(primitive_payload)
            self.task_store.append_event(
                state.task_dir,
                "action",
                f"Executed {action.type} in batch.",
                status=status,
                duration_ms=duration_ms,
                batch_id=batch_id,
                action=primitive_payload["action"],
                result=result,
                error=error,
                pre_observation=pre_observation if index == 0 else None,
                coordinate_transform=transform.to_dict() if transform else None,
            )
            if status == "error" and batch.stop_on_error:
                completed = False
                break

        total_duration_ms = round((time.perf_counter() - started) * 1000, 3)
        post_observation = None
        evaluation = None
        relevant_memory = state.memory_context
        if batch.observe_after:
            observation_result = self._record_observation(state, expectation=None, label="post-batch")
            post_observation = observation_result["observation"]
            evaluation = observation_result["evaluation"]
            relevant_memory = observation_result["relevant_memory"]
            state = self.task_store.load_state(task)

        summary_status = "success" if completed and not errors else "partial"
        self.task_store.append_event(
            state.task_dir,
            "batch",
            f"Executed batch with {len(batch.actions)} primitive actions.",
            status=summary_status,
            duration_ms=total_duration_ms,
            batch_id=batch_id,
            batch=batch.to_dict(),
            primitive_results=primitive_results,
            errors=errors,
            completed=completed,
            guard_matches=guard_matches,
            post_observation=post_observation,
            evaluation=evaluation,
        )
        state.latest_batch = {
            "status": summary_status,
            "batch": batch.to_dict(),
            "duration_ms": total_duration_ms,
            "completed": completed,
            "errors": errors,
            "observe_after": batch.observe_after,
        }
        state.latency_metrics["last_batch_ms"] = total_duration_ms
        self.task_store.save_state(state)
        return {
            "status": summary_status,
            "batch_id": batch_id,
            "batch": batch.to_dict(),
            "primitive_results": primitive_results,
            "duration_ms": total_duration_ms,
            "completed": completed,
            "errors": errors,
            "guard_matches": guard_matches,
            "final_observation_path": post_observation.get("screenshot_path") if post_observation else None,
            "post_observation": post_observation,
            "evaluation": evaluation,
            "relevant_memory": relevant_memory,
        }

    def finish(self, task: str | Path, answer: str) -> dict[str, Any]:
        state = self.task_store.load_state(task)
        result_path = self.task_store.write_result(task, answer)
        state.status = "completed"
        state.result_answer = answer
        self.task_store.save_state(state)
        events = self.task_store.read_events(task)
        memory_updates = self.memory_store.consolidate_task(state=state, events=events, final_answer=answer)
        for update_type, payload in memory_updates.items():
            if isinstance(payload, list):
                for item in payload:
                    self.task_store.append_memory_update(task, {"timestamp": time.time(), "type": update_type, "record": item})
            elif payload:
                self.task_store.append_memory_update(task, {"timestamp": time.time(), "type": update_type, "record": payload})
        self.task_store.append_event(state.task_dir, "finish", "Finished task.", status="success", answer=answer, result_path=result_path)
        return {"status": "success", "task": state.to_dict(), "result_path": result_path, "memory_updates": memory_updates}

    def suspend(
        self,
        task: str | Path,
        *,
        reason_code: str,
        user_action: str,
        done_when: str | None = None,
        resume_action: str | None = None,
    ) -> dict[str, Any]:
        state = self.task_store.load_state(task)
        state.status = "suspended"
        state.suspension = {
            "reason_code": reason_code,
            "user_action": user_action,
            "done_when": done_when,
            "resume_action": resume_action,
            "created_at": time.time(),
        }
        self.task_store.save_state(state)
        self.task_store.append_event(state.task_dir, "suspend", "Suspended task for manual intervention.", status="suspended", suspension=state.suspension)
        return {"status": "success", "task": state.to_dict(), "suspension": state.suspension}

    def resume(self, task: str | Path, *, note: str, observe_after: bool = True) -> dict[str, Any]:
        state = self.task_store.load_state(task)
        if state.status != "suspended":
            raise TaskStateError("Only suspended tasks can be resumed.")
        previous_suspension = state.suspension
        state.status = "active"
        state.suspension = None
        self.task_store.save_state(state)
        self.task_store.append_event(state.task_dir, "resume", "Resumed task after manual intervention.", status="success", note=note, previous_suspension=previous_suspension)
        observation_result = self._record_observation(state, label="resume") if observe_after else None
        state = self.task_store.load_state(task)
        return {
            "status": "success",
            "task": state.to_dict(),
            "resume_note": note,
            "previous_suspension": previous_suspension,
            "post_resume_observation": observation_result["observation"] if observation_result else None,
        }

    def status(self, task: str | Path, *, event_limit: int = 5) -> dict[str, Any]:
        state = self.task_store.load_state(task)
        return {"status": "success", "task": state.to_dict(), "paths": self.paths_payload(state.task_dir), "recent_events": self.task_store.read_events(task, limit=event_limit)}

    def memory_search(self, task: str | Path, *, query: str | None = None, limit: int = 5) -> dict[str, Any]:
        state = self.task_store.load_state(task)
        memory = self.memory_store.search(goal=state.goal, observation=state.latest_observation, query=query, limit=limit)
        state.memory_context = memory
        self.task_store.save_state(state)
        self.task_store.append_event(state.task_dir, "memory_search", "Searched actionable memory.", status="success", query=query, results=memory)
        return {"status": "success", "memory": memory}

    def wait_stable(
        self,
        task: str | Path,
        *,
        stable_seconds: float,
        timeout_seconds: float,
        interval_seconds: float = 1.0,
        diff_threshold: float = 0.01,
    ) -> dict[str, Any]:
        state = self.task_store.load_state(task)
        self._ensure_mutable_task(state)
        previous = state.latest_observation
        started = time.perf_counter()
        wait_result = self.waiter.wait_for_stable_screen(
            state.task_dir,
            model_max_width=state.model_max_width,
            jpeg_quality=state.jpeg_quality,
            stable_seconds=stable_seconds,
            timeout_seconds=timeout_seconds,
            interval_seconds=interval_seconds,
            diff_threshold=diff_threshold,
        )
        final_observation = wait_result["final_observation"]
        evaluation = evaluate_observation_progress(
            previous,
            final_observation,
            no_progress_streak=state.no_progress_streak,
            threshold=state.no_progress_threshold,
            diff_threshold=diff_threshold,
        )
        state.latest_observation = final_observation
        state.latest_evaluation = evaluation
        state.no_progress_streak = evaluation["no_progress_streak"]
        state.memory_context = self._automatic_memory_context(goal=state.goal, observation=final_observation)
        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        state.latency_metrics["last_wait_stable_ms"] = duration_ms
        self.task_store.save_state(state)
        self.task_store.append_event(state.task_dir, "wait_stable", "Waited for the screen to stabilize.", status=wait_result["status"], duration_ms=duration_ms, wait_result=wait_result, evaluation=evaluation)
        return {"status": wait_result["status"], "wait_result": wait_result, "evaluation": evaluation, "relevant_memory": state.memory_context}

    def benchmark(
        self,
        task: str | Path,
        *,
        action_payload: dict[str, Any] | None = None,
        batch_payload: dict[str, Any] | list[dict[str, Any]] | None = None,
        stable_seconds: float | None = None,
        timeout_seconds: float = 60.0,
        interval_seconds: float = 1.0,
        sample_count: int = 5000,
        ignore_guards: bool = False,
    ) -> dict[str, Any]:
        state = self.task_store.load_state(task)
        if state.latest_observation:
            observation = state.latest_observation
        else:
            observation = self.observe(task)["observation"]
            state = self.task_store.load_state(task)
        metrics: dict[str, Any] = {
            "latest_screenshot": {
                "image_width": observation["image_width"],
                "image_height": observation["image_height"],
                "image_byte_count": observation["image_byte_count"],
                "coordinate_space_name": observation["coordinate_space_name"],
            }
        }
        transform = CoordinateTransform.from_observation(observation)
        benchmark_point = ActionSpec.from_dict(
            {
                "type": "click",
                "point": {"x": observation["image_width"] / 2, "y": observation["image_height"] / 2, "space": "resized_image"},
                "reason": "benchmark transform",
            }
        ).point
        transform_start = time.perf_counter_ns()
        for _ in range(sample_count):
            transform.point_to_desktop(benchmark_point)
        transform_elapsed_ns = time.perf_counter_ns() - transform_start
        metrics["coordinate_transform"] = {
            "sample_count": sample_count,
            "total_ns": transform_elapsed_ns,
            "average_ns": round(transform_elapsed_ns / sample_count, 3),
        }
        if action_payload:
            metrics["action"] = self.execute_action(task, action_payload, observe_after=False, ignore_guards=ignore_guards)
        if batch_payload:
            metrics["batch"] = self.execute_batch(task, batch_payload, ignore_guards=ignore_guards)
        if stable_seconds is not None:
            metrics["wait_stable"] = self.wait_stable(task, stable_seconds=stable_seconds, timeout_seconds=timeout_seconds, interval_seconds=interval_seconds)
        self.task_store.append_event(state.task_dir, "benchmark", "Collected LBH V2 benchmark metrics.", status="success", benchmark=metrics)
        return {"status": "success", "benchmark": metrics}

    def locator_contract(self, task: str | Path, target: str) -> dict[str, Any]:
        state = self.task_store.load_state(task)
        observation = state.latest_observation or self.observe(task)["observation"]
        return {
            "status": "success",
            "target": target,
            "image_path": observation["screenshot_path"],
            "observation": observation,
            "prompt": build_locator_prompt(target, observation),
        }

    def locate_parse(self, task: str | Path, response_text: str) -> dict[str, Any]:
        state = self.task_store.load_state(task)
        if not state.latest_observation:
            raise TaskStateError("No observation is available. Observe before parsing locator output.")
        locator = parse_locator_response(response_text)
        transform = CoordinateTransform.from_observation(state.latest_observation)
        desktop_center = transform.point_to_desktop(locator.center).to_dict() if locator.center else None
        desktop_bbox = transform.box_to_desktop(locator.bbox).to_dict() if locator.bbox else None
        payload = {
            "target": locator.target,
            "confidence": locator.confidence,
            "source": locator.source,
            "reason": locator.reason,
            "center": locator.center.to_dict() if locator.center else None,
            "bbox": locator.bbox.to_dict() if locator.bbox else None,
            "desktop_center": desktop_center,
            "desktop_bbox": desktop_bbox,
            "task_id": state.task_id,
            "observation_id": state.latest_observation.get("observation_id"),
            "active_window_title": (state.latest_observation.get("active_window") or {}).get("title"),
            "timestamp": time.time(),
        }
        self.memory_store.store_locator(payload)
        self.task_store.append_event(state.task_dir, "locator", f"Parsed locator result for {locator.target}.", status="success", locator=payload)
        return {"status": "success", "locator": payload}

    def skills(self, task: str | Path | None = None, *, consolidate: bool = False) -> dict[str, Any]:
        if consolidate:
            task_path = task if task is not None else None
            if task_path is None:
                return {"status": "success", "message": "Skill candidates are consolidated automatically on finish."}
            state = self.task_store.load_state(task_path)
            events = self.task_store.read_events(task_path)
            created = self.memory_store.consolidate_task(state=state, events=events, final_answer=state.result_answer or "In-progress consolidation")["skills"]
            return {"status": "success", "skills": created}
        if task is None:
            return {"status": "success", "skills": self.memory_store._read_jsonl(self.memory_store.skills_path)}
        state = self.task_store.load_state(task)
        skills = self.memory_store.search(goal=state.goal, observation=state.latest_observation)["skills"]
        return {"status": "success", "skills": skills}

    def paths_payload(self, task: str | Path) -> dict[str, str]:
        return {key: str(path.resolve()) for key, path in self.task_store.paths_for(task).items()}

    def _automatic_memory_context(
        self,
        *,
        goal: str,
        observation: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not self.memory_reference_enabled:
            return {}
        return self.memory_store.search(goal=goal, observation=observation)

    def _automatic_guard_matches(
        self,
        *,
        goal: str,
        observation: dict[str, Any] | None,
        action_fingerprints: list[str],
    ) -> list[dict[str, Any]]:
        if not self.memory_reference_enabled:
            return []
        return self.memory_store.evaluate_failure_guards(
            goal=goal,
            observation=observation,
            action_fingerprints=action_fingerprints,
        )

    def _ensure_mutable_task(self, state: TaskState) -> None:
        if state.status == "completed":
            raise TaskStateError("This task is already completed.")
        if state.status == "suspended":
            raise TaskStateError("This task is suspended. Resume it before sending more actions.")

    def _transform_for_action(self, state: TaskState, action: ActionSpec) -> CoordinateTransform | None:
        if not action.point:
            return None
        if action.point.space == CoordinateSpace.DESKTOP:
            return CoordinateTransform.from_observation(state.latest_observation) if state.latest_observation else None
        if not state.latest_observation:
            raise TaskStateError("Observe the task before using resized_image, active_window, or crop coordinates.")
        return CoordinateTransform.from_observation(state.latest_observation)

    def _transform_for_batch(self, state: TaskState, batch: ActionBatch) -> CoordinateTransform | None:
        point_actions = [action for action in batch.actions if action.point]
        if not point_actions:
            return None
        if not state.latest_observation:
            if any(action.point and action.point.space != CoordinateSpace.DESKTOP for action in point_actions):
                raise TaskStateError("Observe the task before using resized_image, active_window, or crop coordinates.")
            return None
        return CoordinateTransform.from_observation(state.latest_observation)

    def _execute_primitive(self, action: ActionSpec, transform: CoordinateTransform | None) -> dict[str, Any]:
        if action.type in {"click", "double_click"}:
            if not action.point:
                raise TaskStateError(f"{action.type} requires a point.")
            desktop_point = transform.point_to_desktop(action.point) if transform and action.point.space != CoordinateSpace.DESKTOP else action.point
            clicks = 2 if action.type == "double_click" else 1
            result = self.adapter.click(
                int(round(desktop_point.x)),
                int(round(desktop_point.y)),
                clicks=clicks,
                button=action.button,
                interval=action.interval if action.interval is not None else (0.2 if clicks > 1 else 0.0),
            )
            result["input_point"] = action.point.to_dict()
            result["desktop_point"] = desktop_point.to_dict()
            return self._attach_active_window(result)
        if action.type == "type_text":
            return self._attach_active_window(self.adapter.type_text(action.text or "", interval=action.interval or 0.0))
        if action.type == "press":
            return self._attach_active_window(self.adapter.press(action.key or ""))
        if action.type == "hotkey":
            return self._attach_active_window(self.adapter.hotkey(action.keys or []))
        if action.type == "wait":
            return self.adapter.wait(action.seconds or 0.0)
        if action.type == "clipboard_set":
            return self.adapter.set_clipboard(action.text or "")
        if action.type == "clipboard_get":
            return self.adapter.get_clipboard()
        window_actions = {
            "window_activate": "activate",
            "window_minimize": "minimize",
            "window_maximize": "maximize",
            "window_restore": "restore",
            "close_window": "close",
        }
        if action.type in window_actions:
            return self.adapter.window_action(window_actions[action.type], title_contains=action.title_contains)
        raise TaskStateError(f"Unsupported action type: {action.type}")

    def _attach_active_window(self, result: dict[str, Any]) -> dict[str, Any]:
        try:
            active_window = self.adapter.active_window()
        except Exception:
            active_window = None
        if active_window:
            result["active_window_after_action"] = active_window.to_dict()
        return result

    def _record_observation(
        self,
        state: TaskState,
        *,
        expectation,
        label: str,
        save_full_resolution: bool = False,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        previous = state.latest_observation
        observation = self.capture_service.capture(
            state.task_dir,
            model_max_width=state.model_max_width,
            jpeg_quality=state.jpeg_quality,
            label=label,
            save_full_resolution=save_full_resolution,
        )
        evaluation = evaluate_observation_progress(
            previous,
            observation.to_dict(),
            expectation=expectation,
            no_progress_streak=state.no_progress_streak,
            threshold=state.no_progress_threshold,
        )
        state.latest_observation = observation.to_dict()
        state.latest_evaluation = evaluation
        state.no_progress_streak = evaluation["no_progress_streak"]
        state.memory_context = self._automatic_memory_context(goal=state.goal, observation=state.latest_observation)
        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        state.latency_metrics["last_observe_ms"] = duration_ms
        self.task_store.save_state(state)
        self.task_store.append_event(
            state.task_dir,
            "observation",
            "Captured resized observation.",
            status="success",
            duration_ms=duration_ms,
            observation=state.latest_observation,
            evaluation=evaluation,
            relevant_memory=state.memory_context,
        )
        return {
            "status": "success",
            "observation": state.latest_observation,
            "evaluation": evaluation,
            "relevant_memory": state.memory_context,
            "duration_ms": duration_ms,
        }
