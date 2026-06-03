from __future__ import annotations

from pathlib import Path
from datetime import datetime
import time
import uuid
from typing import Any

from .capture import CaptureService
from .common import DEFAULT_JPEG_QUALITY, DEFAULT_MODEL_MAX_WIDTH
from .contracts import ActionBatch, ActionSpec, CoordinateSpace, CoordinateTransform, Expectation, LocatorResult, TaskState, looks_like_url
from .errors import TaskStateError
from .evaluator import StabilityWaiter, active_window_title, evaluate_expectation, evaluate_observation_progress
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
        memory_mode: str = "off",
    ):
        self.adapter = adapter or PyAutoGUIDesktopAdapter()
        self.task_store = task_store or TaskStore()
        self.memory_store = memory_store or MemoryStore()
        self.memory_mode = memory_mode
        self.memory_reference_enabled = memory_reference_enabled or memory_mode != "off"
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
        state.memory_context = self._automatic_memory_context(
            goal=goal,
            observation=None,
            selected_record_id=state.selected_memory_record_id,
        )
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
        warnings = self._collect_action_warnings(action)
        guard_matches = self._automatic_guard_matches(
            goal=state.goal,
            observation=pre_observation,
            action_fingerprints=[action.fingerprint()],
        )
        if self._should_block_on_guards(guard_matches, ignore_guards=ignore_guards):
            self.task_store.append_event(
                state.task_dir,
                "memory_guard",
                f"Blocked {action.type} by failure guard memory.",
                status="blocked",
                action=action.to_dict(),
                guard_matches=guard_matches,
                warnings=warnings,
            )
            return {
                "status": "blocked",
                "primitive_status": "not_run",
                "action": action.to_dict(),
                "guard_matches": guard_matches,
                "warnings": warnings,
            }

        transform = self._transform_for_action(state, action)
        started = time.perf_counter()
        primitive_status = "success"
        result = None
        error = None
        try:
            result = self._execute_primitive(action, transform)
        except Exception as exc:
            primitive_status = "error"
            error = {"error_type": exc.__class__.__name__, "message": str(exc)}
        duration_ms = round((time.perf_counter() - started) * 1000, 3)

        post_observation = None
        evaluation = None
        relevant_memory = state.memory_context
        if primitive_status == "success" and observe_after:
            observation_result = self._record_observation(state, expectation=action.expectation, label="post-action")
            post_observation = observation_result["observation"]
            evaluation = observation_result["evaluation"]
            relevant_memory = observation_result["relevant_memory"]
            state = self.task_store.load_state(task)

        primitive_payload = {
            "status": primitive_status,
            "action": {**action.to_dict(), "fingerprint": action.fingerprint()},
            "result": result,
            "error": error,
            "duration_ms": duration_ms,
        }
        semantic_evaluation = self._evaluate_action_semantics(
            action=action,
            pre_observation=pre_observation,
            post_observation=post_observation,
            primitive_payload=primitive_payload,
            observation_evaluation=evaluation,
        )
        status = "primitive_error" if primitive_status != "success" else semantic_evaluation["status"]

        event_action = primitive_payload["action"]
        self.task_store.append_event(
            state.task_dir,
            "action",
            f"Executed {action.type}.",
            status=status,
            primitive_status=primitive_status,
            duration_ms=duration_ms,
            action=event_action,
            result=result,
            error=error,
            guard_matches=guard_matches,
            warnings=warnings,
            pre_observation=pre_observation,
            post_observation=post_observation,
            evaluation=evaluation,
            semantic_evaluation=semantic_evaluation,
            coordinate_transform=transform.to_dict() if transform else None,
        )
        state.latest_action = {
            "status": status,
            "primitive_status": primitive_status,
            "action": event_action,
            "result": result,
            "error": error,
            "duration_ms": duration_ms,
            "observed_after": observe_after,
            "warnings": warnings,
            "semantic_evaluation": semantic_evaluation,
        }
        state.latency_metrics["last_action_ms"] = duration_ms
        self.task_store.save_state(state)
        return {
            "status": status,
            "primitive_status": primitive_status,
            "action": event_action,
            "result": result,
            "error": error,
            "duration_ms": duration_ms,
            "guard_matches": guard_matches,
            "warnings": warnings,
            "post_observation": post_observation,
            "evaluation": evaluation,
            "semantic_evaluation": semantic_evaluation,
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
        sequence_fingerprint = self._batch_sequence_fingerprint(batch)
        warnings = self._collect_batch_warnings(batch)
        guard_matches = self._automatic_guard_matches(
            goal=state.goal,
            observation=pre_observation,
            action_fingerprints=[action.fingerprint() for action in batch.actions] + [sequence_fingerprint],
        )
        if self._should_block_on_guards(guard_matches, ignore_guards=ignore_guards):
            self.task_store.append_event(
                state.task_dir,
                "memory_guard",
                "Blocked action batch by failure guard memory.",
                status="blocked",
                batch=batch.to_dict(),
                guard_matches=guard_matches,
                warnings=warnings,
            )
            return {
                "status": "blocked",
                "batch": batch.to_dict(),
                "guard_matches": guard_matches,
                "warnings": warnings,
            }

        transform = self._transform_for_batch(state, batch)
        batch_id = uuid.uuid4().hex
        started = time.perf_counter()
        primitive_results: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        completed = True
        timed_out = False
        for index, action in enumerate(batch.actions):
            elapsed = time.perf_counter() - started
            if batch.max_duration_seconds and elapsed > batch.max_duration_seconds:
                errors.append({"error_type": "TimeoutError", "message": f"Batch exceeded max_duration_seconds={batch.max_duration_seconds}."})
                completed = False
                timed_out = True
                break
            action_started = time.perf_counter()
            primitive_status = "success"
            result = None
            error = None
            try:
                result = self._execute_primitive(action, transform)
            except Exception as exc:
                primitive_status = "error"
                error = {"error_type": exc.__class__.__name__, "message": str(exc)}
                errors.append(error)
            duration_ms = round((time.perf_counter() - action_started) * 1000, 3)
            primitive_payload = {
                "status": primitive_status,
                "action": {**action.to_dict(), "fingerprint": action.fingerprint()},
                "result": result,
                "error": error,
                "duration_ms": duration_ms,
                "index": index,
                "warnings": self._collect_action_warnings(action),
            }
            primitive_results.append(primitive_payload)
            self.task_store.append_event(
                state.task_dir,
                "action",
                f"Executed {action.type} in batch.",
                status="primitive_error" if primitive_status != "success" else "success",
                primitive_status=primitive_status,
                duration_ms=duration_ms,
                batch_id=batch_id,
                action=primitive_payload["action"],
                result=result,
                error=error,
                warnings=primitive_payload["warnings"],
                pre_observation=pre_observation if index == 0 else None,
                coordinate_transform=transform.to_dict() if transform else None,
            )
            if primitive_status == "error" and batch.stop_on_error:
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

        semantic_evaluation = self._evaluate_batch_semantics(
            batch=batch,
            pre_observation=pre_observation,
            post_observation=post_observation,
            primitive_results=primitive_results,
            observation_evaluation=evaluation,
            timed_out=timed_out,
            errors=errors,
        )
        summary_status = semantic_evaluation["status"]
        self.task_store.append_event(
            state.task_dir,
            "batch",
            f"Executed batch with {len(batch.actions)} primitive actions.",
            status=summary_status,
            primitive_status=semantic_evaluation["primitive_status"],
            duration_ms=total_duration_ms,
            batch_id=batch_id,
            batch=batch.to_dict(),
            primitive_results=primitive_results,
            errors=errors,
            completed=completed,
            warnings=warnings,
            guard_matches=guard_matches,
            post_observation=post_observation,
            evaluation=evaluation,
            semantic_evaluation=semantic_evaluation,
        )
        state.latest_batch = {
            "status": summary_status,
            "primitive_status": semantic_evaluation["primitive_status"],
            "batch": batch.to_dict(),
            "duration_ms": total_duration_ms,
            "completed": completed,
            "errors": errors,
            "observe_after": batch.observe_after,
            "warnings": warnings,
            "semantic_evaluation": semantic_evaluation,
        }
        state.latency_metrics["last_batch_ms"] = total_duration_ms
        self.task_store.save_state(state)
        return {
            "status": summary_status,
            "primitive_status": semantic_evaluation["primitive_status"],
            "batch_id": batch_id,
            "batch": batch.to_dict(),
            "primitive_results": primitive_results,
            "duration_ms": total_duration_ms,
            "completed": completed,
            "errors": errors,
            "warnings": warnings,
            "guard_matches": guard_matches,
            "final_observation_path": post_observation.get("screenshot_path") if post_observation else None,
            "post_observation": post_observation,
            "evaluation": evaluation,
            "semantic_evaluation": semantic_evaluation,
            "relevant_memory": relevant_memory,
        }

    def finish(self, task: str | Path, answer: str) -> dict[str, Any]:
        state = self.task_store.load_state(task)
        result_path = self.task_store.write_result(task, answer)
        state.status = "completed"
        state.result_answer = answer
        self.task_store.save_state(state)
        self.task_store.append_event(
            state.task_dir,
            "finish",
            "Finished task.",
            status="success",
            answer=answer,
            result_path=result_path,
            duration_ms=0.0,
        )
        return {
            "status": "success",
            "task": state.to_dict(),
            "result_path": result_path,
            "memory_updates": {},
            "memory_consolidation_ms": 0.0,
        }

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
        events = self.task_store.read_events(task)
        return {
            "status": "success",
            "task": state.to_dict(),
            "paths": self.paths_payload(state.task_dir),
            "recent_events": events[-event_limit:] if event_limit is not None else events,
            "sequence_improvement_signals": self._sequence_improvement_signals(events),
            "lifecycle_warnings": self._lifecycle_warnings(state, events),
        }

    def memory_search(self, task: str | Path, *, query: str | None = None, limit: int = 5) -> dict[str, Any]:
        state = self.task_store.load_state(task)
        memory = self._decorate_memory_context(
            self.memory_store.search(goal=state.goal, observation=state.latest_observation, query=query, limit=limit),
            selected_record_id=state.selected_memory_record_id,
        )
        state.memory_context = memory
        self.task_store.save_state(state)
        self.task_store.append_event(state.task_dir, "memory_search", "Searched actionable memory.", status="success", query=query, results=memory)
        return {"status": "success", "memory": memory}

    def memory_record(self, task: str | Path, *, record_id: str | None = None) -> dict[str, Any]:
        state = self.task_store.load_state(task)
        resolved_record_id = record_id or state.selected_memory_record_id
        if not resolved_record_id:
            raise TaskStateError("memory-record requires 'record_id' or a previously selected memory record.")
        record = self.memory_store.get_task_record_view(resolved_record_id)
        if record is None:
            raise TaskStateError(f"Memory record not found: {resolved_record_id}")
        self.task_store.append_event(
            state.task_dir,
            "memory_record",
            "Loaded full passive task-record memory.",
            status="success",
            record_id=resolved_record_id,
        )
        return {
            "status": "success",
            "record": record,
            "selected_record_id": state.selected_memory_record_id,
        }

    def memory_select(self, task: str | Path, *, record_id: str) -> dict[str, Any]:
        state = self.task_store.load_state(task)
        record = self.memory_store.get_task_record(record_id)
        if record is None:
            raise TaskStateError(f"Memory record not found: {record_id}")
        state.selected_memory_record_id = record_id
        state.memory_context = self._decorate_memory_context(
            self.memory_store.search(goal=state.goal, observation=state.latest_observation, limit=5),
            selected_record_id=record_id,
        )
        self.task_store.save_state(state)
        self.task_store.append_event(
            state.task_dir,
            "memory_select",
            "Selected passive task-record memory as the current draft baseline.",
            status="success",
            record_id=record_id,
        )
        return {
            "status": "success",
            "record_id": record_id,
            "task_description": record.task_description,
            "memory": state.memory_context,
        }

    def memory_commit(self, task: str | Path, payload: dict[str, Any]) -> dict[str, Any]:
        state = self.task_store.load_state(task)
        events = self.task_store.read_events(task)
        if not str(payload.get("task_description") or "").strip():
            raise TaskStateError("memory-commit requires 'task_description'.")
        if not str(payload.get("run_status") or "").strip():
            raise TaskStateError("memory-commit requires 'run_status'.")
        if payload.get("run_status") not in {"success", "failure"}:
            raise TaskStateError("memory-commit 'run_status' must be 'success' or 'failure'.")
        if "run_note" not in payload:
            raise TaskStateError("memory-commit requires 'run_note'.")
        sequence = payload.get("sequence") or self.memory_store.derive_sequence_from_events(events)
        commit_result = self.memory_store.commit_task_record(
            user_query=str(payload.get("user_query") or state.goal),
            task_description=str(payload.get("task_description") or state.goal),
            sequence=sequence,
            run_status=str(payload.get("run_status") or "success"),
            run_note=str(payload.get("run_note") or ""),
            elapsed_time=float(payload.get("elapsed_time") or self._events_wall_clock_ms(events)),
            change_summary=str(payload.get("change_summary") or ""),
            change_reason=str(payload.get("change_reason") or ""),
            record_id=payload.get("record_id") or state.selected_memory_record_id,
        )
        post_commit_events = [*events, {"type": "memory_commit"}]
        sequence_improvement_signals = self._sequence_improvement_signals(events)
        lifecycle_warnings = self._lifecycle_warnings(state, post_commit_events)
        state.selected_memory_record_id = commit_result["record"]["record_id"]
        self.task_store.append_memory_update(
            task,
            {
                "timestamp": time.time(),
                "type": "task_record",
                "record": commit_result["record"],
                "action": commit_result["action"],
                "version_id": commit_result.get("version_id"),
                "run_record": commit_result.get("run_record"),
            },
        )
        self.task_store.append_event(
            state.task_dir,
            "memory_commit",
            "Committed passive task-record memory.",
            status="success",
            memory_commit=commit_result,
            sequence_improvement_signals=sequence_improvement_signals,
            lifecycle_warnings=lifecycle_warnings,
        )
        state.memory_context = self._decorate_memory_context(
            self.memory_store.search(goal=state.goal, observation=state.latest_observation, limit=5),
            selected_record_id=state.selected_memory_record_id,
        )
        self.task_store.save_state(state)
        return {
            "status": "success",
            "memory_commit": commit_result,
            "sequence_improvement_signals": sequence_improvement_signals,
            "lifecycle_warnings": lifecycle_warnings,
        }

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
        state.memory_context = self._automatic_memory_context(
            goal=state.goal,
            observation=final_observation,
            selected_record_id=state.selected_memory_record_id,
        )
        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        state.latency_metrics["last_wait_stable_ms"] = duration_ms
        self.task_store.save_state(state)
        self.task_store.append_event(state.task_dir, "wait_stable", "Waited for the screen to stabilize.", status=wait_result["status"], duration_ms=duration_ms, wait_result=wait_result, evaluation=evaluation)
        return {"status": wait_result["status"], "wait_result": wait_result, "evaluation": evaluation, "relevant_memory": state.memory_context}

    def benchmark_report(self, task: str | Path, *, top_n: int = 5) -> dict[str, Any]:
        state = self.task_store.load_state(task)
        events = self.task_store.read_events(task)
        observation_events = [event for event in events if event.get("type") == "observation"]
        action_events = [event for event in events if event.get("type") == "action"]
        batch_events = [event for event in events if event.get("type") == "batch"]
        failed_events = [
            event for event in events if event.get("status") in {"semantic_failure", "primitive_error", "partial_failure", "timeout", "blocked", "error"}
        ]
        total_wall_clock_ms = self._events_wall_clock_ms(events)
        report = {
            "status": "success",
            "task_id": state.task_id,
            "task_status": state.status,
            "total_task_wall_clock_ms": total_wall_clock_ms,
            "observation_count": len(observation_events),
            "total_observation_time_ms": round(sum(float(event.get("duration_ms", 0.0)) for event in observation_events), 3),
            "primitive_action_count": len(action_events),
            "total_action_time_ms": round(sum(float(event.get("duration_ms", 0.0)) for event in action_events), 3),
            "batch_count": len(batch_events),
            "total_batch_time_ms": round(sum(float(event.get("duration_ms", 0.0)) for event in batch_events), 3),
            "decision_points_approx": len(observation_events),
            "failed_event_count": len(failed_events),
            "failed_events": [
                {
                    "type": event.get("type"),
                    "status": event.get("status"),
                    "summary": event.get("summary"),
                }
                for event in failed_events
            ],
            "recovery_count": self._count_recoveries(events),
            "memory_consolidation_ms": float(state.latency_metrics.get("memory_consolidation_ms", 0.0)),
            "sequence_improvement_signals": self._sequence_improvement_signals(events),
            "lifecycle_warnings": self._lifecycle_warnings(state, events),
            "screenshot_sizes": [
                {
                    "path": event.get("observation", {}).get("screenshot_path"),
                    "bytes": event.get("observation", {}).get("image_byte_count"),
                }
                for event in observation_events
            ],
            "most_expensive_events": sorted(
                [
                    {
                        "type": event.get("type"),
                        "status": event.get("status"),
                        "summary": event.get("summary"),
                        "duration_ms": float(event.get("duration_ms", 0.0)),
                    }
                    for event in events
                    if isinstance(event.get("duration_ms"), (int, float))
                ],
                key=lambda item: item["duration_ms"],
                reverse=True,
            )[:top_n],
        }
        return report

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
        return {"status": "success", "skills": [], "message": "Skill memories were retired in favor of passive task records."}

    def paths_payload(self, task: str | Path) -> dict[str, str]:
        return {key: str(path.resolve()) for key, path in self.task_store.paths_for(task).items()}

    def _collect_action_warnings(self, action: ActionSpec) -> list[str]:
        warnings: list[str] = []
        if action.type == "type_text" and looks_like_url(action.text):
            warnings.append("Direct URL typing is fragile. Prefer clipboard_set + ctrl+v for URLs.")
        if action.type == "type_text" and action.text and len(action.text) >= 40:
            warnings.append("Long text entry should usually use clipboard_set + ctrl+v instead of type_text.")
        return warnings

    def _collect_batch_warnings(self, batch: ActionBatch) -> list[str]:
        warnings: list[str] = []
        action_fingerprints = [action.fingerprint() for action in batch.actions]
        if any(fingerprint == "type_text:url" for fingerprint in action_fingerprints) and any(fingerprint == "press:enter" for fingerprint in action_fingerprints):
            warnings.append("This batch types a URL directly and submits it. Prefer clipboard_set:url + hotkey:ctrl+v.")
        for action in batch.actions:
            warnings.extend(self._collect_action_warnings(action))
        return sorted(set(warnings))

    def _batch_sequence_fingerprint(self, batch: ActionBatch) -> str:
        return "sequence:" + " -> ".join(action.fingerprint() for action in batch.actions)

    def _should_block_on_guards(self, guard_matches: list[dict[str, Any]], *, ignore_guards: bool) -> bool:
        if ignore_guards or self.memory_mode != "block":
            return False
        return any(match["decision"] == "block" for match in guard_matches)

    def _effective_expectation(
        self,
        *,
        expectation: Expectation | None,
        require_changed: bool | None = None,
        allow_no_visual_change: bool | None = None,
        visual_change_expected: bool | None = None,
    ) -> Expectation | None:
        payload = dict(expectation.to_dict()) if expectation else {}
        if require_changed is not None and "require_changed" not in payload:
            payload["require_changed"] = require_changed
        if allow_no_visual_change is not None and "allow_no_visual_change" not in payload:
            payload["allow_no_visual_change"] = allow_no_visual_change
        if visual_change_expected is not None and "visual_change_expected" not in payload:
            payload["visual_change_expected"] = visual_change_expected
        return Expectation.from_payload(payload)

    def _evaluate_action_semantics(
        self,
        *,
        action: ActionSpec,
        pre_observation: dict[str, Any] | None,
        post_observation: dict[str, Any] | None,
        primitive_payload: dict[str, Any],
        observation_evaluation: dict[str, Any] | None,
    ) -> dict[str, Any]:
        expectation = action.expectation
        if expectation is None:
            return {
                "status": "success",
                "matched": True,
                "reason": "No explicit semantic expectation for action.",
                "checks": [],
                "action_category": action.action_category,
                "visual_change_expected": action.visual_change_expected_default,
                "allow_no_visual_change": action.is_non_visual_action or bool(action.allow_no_visual_change),
                "changed": (observation_evaluation or {}).get("changed"),
            }
        expectation = self._effective_expectation(
            expectation=expectation,
            allow_no_visual_change=action.is_non_visual_action or action.allow_no_visual_change,
            visual_change_expected=action.visual_change_expected_default,
        )
        clipboard_result = primitive_payload["result"] if action.type == "clipboard_get" else None
        evaluation = evaluate_expectation(expectation, pre_observation, post_observation, [primitive_payload], clipboard_result)
        evaluation["action_category"] = action.action_category
        evaluation["visual_change_expected"] = action.visual_change_expected_default
        evaluation["allow_no_visual_change"] = action.is_non_visual_action or bool(action.allow_no_visual_change)
        return evaluation

    def _evaluate_batch_semantics(
        self,
        *,
        batch: ActionBatch,
        pre_observation: dict[str, Any] | None,
        post_observation: dict[str, Any] | None,
        primitive_results: list[dict[str, Any]],
        observation_evaluation: dict[str, Any] | None,
        timed_out: bool,
        errors: list[dict[str, Any]],
    ) -> dict[str, Any]:
        primitive_error_count = sum(1 for item in primitive_results if item["status"] != "success")
        primitive_status = "success" if primitive_error_count == 0 and not timed_out else "error"
        clipboard_result = next(
            (item.get("result") for item in reversed(primitive_results) if (item.get("action") or {}).get("type") == "clipboard_get"),
            None,
        )
        explicit_expectation = batch.postcondition or batch.expectation
        visual_actions = [action for action in batch.actions if not action.is_non_visual_action]
        allow_no_visual_change = (
            batch.allow_no_visual_change
            if batch.allow_no_visual_change is not None
            else (explicit_expectation.allow_no_visual_change if explicit_expectation else None)
        )
        visual_change_expected = (
            batch.visual_change_expected
            if batch.visual_change_expected is not None
            else (explicit_expectation.visual_change_expected if explicit_expectation else None)
        )
        if visual_change_expected is None:
            visual_change_expected = bool(visual_actions)
        if allow_no_visual_change is None:
            allow_no_visual_change = not visual_actions
        expectation = self._effective_expectation(
            expectation=explicit_expectation,
            require_changed=True if visual_change_expected and not allow_no_visual_change else None,
            allow_no_visual_change=allow_no_visual_change,
            visual_change_expected=visual_change_expected,
        )
        expectation_result = evaluate_expectation(expectation, pre_observation, post_observation, primitive_results, clipboard_result)
        changed = (observation_evaluation or {}).get("changed")
        semantic_failure_reasons: list[str] = []
        if expectation_result["status"] == "semantic_failure":
            semantic_failure_reasons.append(expectation_result["reason"])
        if not explicit_expectation and visual_change_expected and not allow_no_visual_change and post_observation and changed is False:
            semantic_failure_reasons.append("Batch expected visible progress but the final observation did not change.")
        post_title = active_window_title(post_observation)
        if any(action.fingerprint() == "type_text:url" for action in batch.actions) and "search" in post_title.lower():
            semantic_failure_reasons.append("Direct URL typing appears to have produced a search page instead of target navigation.")

        if timed_out:
            status = "timeout"
        elif primitive_error_count and primitive_results and len(primitive_results) > primitive_error_count:
            status = "partial_failure"
        elif primitive_error_count:
            status = "primitive_error"
        elif semantic_failure_reasons:
            status = "semantic_failure"
        else:
            status = "success"
        return {
            "status": status,
            "primitive_status": primitive_status,
            "matched": status == "success",
            "reason": " | ".join(semantic_failure_reasons) if semantic_failure_reasons else expectation_result["reason"],
            "checks": expectation_result.get("checks", []),
            "expectation_result": expectation_result,
            "changed": changed,
            "visual_change_expected": visual_change_expected,
            "allow_no_visual_change": allow_no_visual_change,
            "post_title": post_title,
            "sequence_fingerprint": self._batch_sequence_fingerprint(batch),
            "primitive_error_count": primitive_error_count,
            "errors": errors,
        }

    def _events_wall_clock_ms(self, events: list[dict[str, Any]]) -> float:
        timestamps = [event.get("timestamp") for event in events if event.get("timestamp")]
        if len(timestamps) < 2:
            return 0.0
        started = datetime.fromisoformat(str(timestamps[0]))
        ended = datetime.fromisoformat(str(timestamps[-1]))
        return round((ended - started).total_seconds() * 1000.0, 3)

    def _count_recoveries(self, events: list[dict[str, Any]]) -> int:
        seen_failure = False
        recoveries = 0
        for event in events:
            status = event.get("status")
            if status in {"semantic_failure", "primitive_error", "partial_failure", "timeout", "blocked", "error"}:
                seen_failure = True
            elif seen_failure and status == "success":
                recoveries += 1
                seen_failure = False
        return recoveries

    def _sequence_improvement_signals(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []
        for event in events:
            if event.get("status") != "semantic_failure":
                continue
            semantic = event.get("semantic_evaluation") or {}
            entry = {
                "event_type": event.get("type"),
                "summary": event.get("summary"),
                "reason": semantic.get("reason") or event.get("summary"),
                "sequence_fingerprint": semantic.get("sequence_fingerprint"),
                "action_fingerprint": ((event.get("action") or {}).get("fingerprint") if event.get("type") == "action" else None),
            }
            signals.append({key: value for key, value in entry.items() if value})
        return signals

    def _lifecycle_warnings(self, state: TaskState, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        warnings: list[dict[str, Any]] = []
        memory_committed = any(event.get("type") == "memory_commit" for event in events)
        finished = any(event.get("type") == "finish" for event in events)
        if memory_committed and not finished and state.status != "completed":
            warnings.append(
                {
                    "code": "memory_committed_task_not_finished",
                    "message": "Memory was committed before the task was explicitly finished. Close the task lifecycle with finish when the final result is captured.",
                }
            )
        return warnings

    def _decorate_memory_context(
        self,
        memory: dict[str, Any],
        *,
        selected_record_id: str | None,
    ) -> dict[str, Any]:
        task_cards = []
        for card in memory.get("task_cards", []):
            decorated = dict(card)
            decorated["selected"] = bool(selected_record_id and card.get("record_id") == selected_record_id)
            task_cards.append(decorated)
        return {
            **memory,
            "selected_record_id": selected_record_id,
            "task_cards": task_cards,
        }

    def _automatic_memory_context(
        self,
        *,
        goal: str,
        observation: dict[str, Any] | None,
        selected_record_id: str | None = None,
    ) -> dict[str, Any]:
        if not self.memory_reference_enabled:
            return {}
        return self._decorate_memory_context(
            self.memory_store.search(goal=goal, observation=observation),
            selected_record_id=selected_record_id,
        )

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
        state.memory_context = self._automatic_memory_context(
            goal=state.goal,
            observation=state.latest_observation,
            selected_record_id=state.selected_memory_record_id,
        )
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
