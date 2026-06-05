from __future__ import annotations

from copy import deepcopy
from hashlib import sha1
import json
from typing import Any, Iterable, Mapping
import uuid

from .common import MEMORY_DIR, append_jsonl, ensure_dir, now_iso, tokenise
from .contracts import RunRecord, SequenceStepRecord, SequenceVersionRecord, TaskMemoryRecord

RECENT_FAILURE_LIMIT = 3
LEGACY_STEP_DURATION_MS_THRESHOLD = 100.0
LEGACY_RUN_ELAPSED_MS_THRESHOLD = 1000.0


def jaccard_similarity(left: Iterable[str], right: Iterable[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)


class MemoryStore:
    def __init__(self, memory_dir=MEMORY_DIR):
        self.memory_dir = ensure_dir(memory_dir)
        self.task_records_path = self.memory_dir / "task_records.jsonl"
        self.locators_path = self.memory_dir / "locator_memory.jsonl"

    def _read_jsonl(self, path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        records: list[dict[str, Any]] = []
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                records.append(__import__("json").loads(raw_line))
            except __import__("json").JSONDecodeError:
                continue
        return records

    def _rewrite_jsonl(self, path, records: Iterable[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        for record in records:
            append_jsonl(path, record)

    def build_situation_signature(self, goal: str, observation: dict[str, Any] | None = None) -> dict[str, Any]:
        active_title = ""
        if observation:
            active_window = observation.get("active_window") or {}
            active_title = str(active_window.get("title") or "")
        signature = " | ".join(part for part in (goal.strip(), active_title.strip()) if part)
        return {
            "signature": signature or goal.strip(),
            "tokens": tokenise(signature or goal),
            "active_window_title": active_title,
        }

    def search(
        self,
        *,
        goal: str,
        observation: dict[str, Any] | None = None,
        query: str | None = None,
        limit: int = 5,
    ) -> dict[str, Any]:
        signature = self.build_situation_signature(goal, observation)
        query_tokens = tokenise(query or signature["signature"])
        ranked = self._rank_task_records(query_tokens, limit)
        return {
            "query_signature": signature,
            "task_records": [self._build_task_record_summary(record) for record in ranked],
        }

    def evaluate_failure_guards(
        self,
        *,
        goal: str,
        observation: dict[str, Any] | None,
        action_fingerprints: list[str],
    ) -> list[dict[str, Any]]:
        return []

    def consolidate_task(self, *, state, events: list[dict[str, Any]], final_answer: str) -> dict[str, Any]:
        return {}

    def store_locator(self, payload: dict[str, Any]) -> dict[str, Any]:
        append_jsonl(self.locators_path, payload)
        return payload

    def list_task_records(self) -> list[TaskMemoryRecord]:
        return [self._normalise_task_record_time_units(TaskMemoryRecord.from_dict(item)) for item in self._read_jsonl(self.task_records_path)]

    def get_task_record(self, record_id: str) -> TaskMemoryRecord | None:
        for record in self.list_task_records():
            if record.record_id == record_id:
                return record
        return None

    def get_task_record_view(self, record_id: str) -> dict[str, Any] | None:
        record = self.get_task_record(record_id)
        if record is None:
            return None
        return self._build_task_record_view(record)

    def commit_task_record(
        self,
        *,
        user_query: str,
        task_description: str,
        sequence: list[Mapping[str, Any]] | list[SequenceStepRecord],
        run_status: str,
        run_note: str,
        elapsed_time: float,
        change_summary: str = "",
        change_reason: str = "",
        draft_sequence: list[Mapping[str, Any]] | None = None,
        task_type: str | None = None,
        parameter_schema: Mapping[str, Any] | None = None,
        start_state_requirements: list[str] | None = None,
        optimization_summary: Mapping[str, Any] | None = None,
        record_id: str | None = None,
        base_version_id: str | None = None,
    ) -> dict[str, Any]:
        records = {record.record_id: record for record in self.list_task_records()}
        normalized_sequence = self._normalise_sequence(sequence)
        normalized_draft_sequence = self._normalise_draft_sequence(draft_sequence)
        target_record = records.get(record_id) if record_id else None
        created_new_record = target_record is None
        if target_record is None:
            target_record = TaskMemoryRecord(
                record_id=record_id or self._new_record_id(user_query, task_description),
                user_query=user_query,
                task_description=task_description,
                versions=[],
                task_type=task_type,
                parameter_schema=deepcopy(dict(parameter_schema)) if parameter_schema is not None else None,
                start_state_requirements=list(start_state_requirements) if start_state_requirements is not None else None,
                optimization_summary=deepcopy(dict(optimization_summary)) if optimization_summary is not None else None,
                created_at=now_iso(),
                updated_at=now_iso(),
            )

        baseline_version = self._resolve_commit_base_version(target_record, base_version_id)
        run_record = RunRecord(
            run_id=f"run-{uuid.uuid4().hex[:12]}",
            status=run_status,
            elapsed_time=self._normalise_elapsed_seconds(elapsed_time),
            note=run_note,
            created_at=now_iso(),
        )

        should_append_run = bool(baseline_version) and (
            run_status != "success"
            or (
                self._sequence_signature(baseline_version.sequence) == self._sequence_signature(normalized_sequence)
                and self._draft_sequence_signature(baseline_version.draft_sequence)
                == self._draft_sequence_signature(normalized_draft_sequence)
            )
        )
        if should_append_run:
            updated_record = self._append_run_to_version(target_record, baseline_version.version_id, run_record)
            records[updated_record.record_id] = updated_record
            self._rewrite_task_records(records.values())
            return {
                "action": "append_run",
                "record": updated_record.to_dict(),
                "version_id": baseline_version.version_id,
                "run_record": run_record.to_dict(),
            }

        parent_version_id = baseline_version.version_id if baseline_version else None
        new_version = SequenceVersionRecord(
            version_id=f"version-{uuid.uuid4().hex[:12]}",
            parent_version_id=parent_version_id,
            change_summary=change_summary,
            change_reason=change_reason,
            sequence=normalized_sequence,
            run_records=[run_record],
            draft_sequence=normalized_draft_sequence,
            created_at=now_iso(),
            updated_at=now_iso(),
        )
        updated_versions = [*target_record.versions, new_version]
        updated_record = TaskMemoryRecord(
            record_id=target_record.record_id,
            user_query=user_query,
            task_description=task_description,
            versions=updated_versions,
            task_type=task_type if task_type is not None else target_record.task_type,
            parameter_schema=(
                deepcopy(dict(parameter_schema))
                if parameter_schema is not None
                else deepcopy(target_record.parameter_schema)
            ),
            start_state_requirements=(
                list(start_state_requirements)
                if start_state_requirements is not None
                else (list(target_record.start_state_requirements) if target_record.start_state_requirements is not None else None)
            ),
            optimization_summary=(
                deepcopy(dict(optimization_summary))
                if optimization_summary is not None
                else deepcopy(target_record.optimization_summary)
            ),
            root_version_id=target_record.root_version_id or new_version.version_id,
            latest_version_id=new_version.version_id,
            latest_success_version_id=(
                new_version.version_id
                if run_status == "success"
                else self._latest_success_version_id(updated_versions, target_record.latest_success_version_id)
            ),
            created_at=target_record.created_at or now_iso(),
            updated_at=now_iso(),
        )
        records[updated_record.record_id] = updated_record
        self._rewrite_task_records(records.values())
        return {
            "action": "create_record" if created_new_record else "append_version",
            "record": updated_record.to_dict(),
            "version_id": new_version.version_id,
            "run_record": run_record.to_dict(),
        }

    def derive_sequence_from_events(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        steps: list[dict[str, Any]] = []
        for event in events:
            if event.get("type") != "action":
                continue
            action = event.get("action") or {}
            action_name = action.get("fingerprint") or action.get("type") or "action"
            status = event.get("primitive_status") or event.get("status") or "unknown"
            steps.append(
                {
                    "action_name": str(action_name),
                    "status": str(status),
                    "duration": round(float(event.get("duration_ms", 0.0)) / 1000.0, 3),
                }
            )
        return steps

    def derive_draft_sequence_from_events(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        draft: list[dict[str, Any]] = []
        for event in events:
            event_type = event.get("type")
            if event_type == "batch":
                draft.append(self._draft_batch_step(event))
                continue
            if event_type == "action":
                if event.get("batch_id"):
                    continue
                draft.append(self._draft_action_step(event))
                continue
            if event_type == "wait_stable":
                draft.append(self._draft_wait_stable_step(event))
        return draft

    def _rank_task_records(self, query_tokens: list[str], limit: int) -> list[TaskMemoryRecord]:
        ranked: list[tuple[float, TaskMemoryRecord]] = []
        for record in self.list_task_records():
            haystack = " ".join(
                [
                    record.user_query,
                    record.task_description,
                    record.task_type or "",
                    " ".join((record.parameter_schema or {}).keys()),
                ]
            )
            score = jaccard_similarity(query_tokens, tokenise(haystack))
            if score <= 0:
                continue
            ranked.append((score, record))
        ranked.sort(
            key=lambda item: (
                item[1].updated_at or "",
                round(item[0], 3),
            ),
            reverse=True,
        )
        return [record for _, record in ranked[:limit]]

    def _rewrite_task_records(self, records: Iterable[TaskMemoryRecord]) -> None:
        self._rewrite_jsonl(self.task_records_path, [record.to_dict() for record in records])

    def _normalise_sequence(
        self,
        sequence: list[Mapping[str, Any]] | list[SequenceStepRecord],
    ) -> list[SequenceStepRecord]:
        normalised: list[SequenceStepRecord] = []
        for item in sequence:
            if isinstance(item, SequenceStepRecord):
                normalised.append(item)
            else:
                normalised.append(SequenceStepRecord.from_dict(item))
        step_durations = [float(step.duration) for step in normalised]
        uses_legacy_milliseconds = bool(step_durations) and max(step_durations) >= LEGACY_STEP_DURATION_MS_THRESHOLD
        return [
            SequenceStepRecord(
                action_name=step.action_name,
                status=step.status,
                duration=self._normalise_step_duration_seconds(step.duration, assume_milliseconds=uses_legacy_milliseconds),
            )
            for step in normalised
        ]

    def _normalise_draft_sequence(self, draft_sequence: list[Mapping[str, Any]] | None) -> list[dict[str, Any]] | None:
        if draft_sequence is None:
            return None
        normalised: list[dict[str, Any]] = []
        for item in draft_sequence:
            if not isinstance(item, Mapping):
                continue
            normalised.append(deepcopy(dict(item)))
        return normalised

    def _normalise_task_record_time_units(self, record: TaskMemoryRecord) -> TaskMemoryRecord:
        normalized_versions: list[SequenceVersionRecord] = []
        for version in record.versions:
            step_durations = [float(step.duration) for step in version.sequence]
            uses_legacy_milliseconds = bool(step_durations) and max(step_durations) >= LEGACY_STEP_DURATION_MS_THRESHOLD
            normalized_versions.append(
                SequenceVersionRecord(
                    version_id=version.version_id,
                    parent_version_id=version.parent_version_id,
                    change_summary=version.change_summary,
                    change_reason=version.change_reason,
                    sequence=[
                        SequenceStepRecord(
                            action_name=step.action_name,
                            status=step.status,
                            duration=self._normalise_step_duration_seconds(
                                step.duration,
                                assume_milliseconds=uses_legacy_milliseconds,
                            ),
                        )
                        for step in version.sequence
                    ],
                    run_records=[
                        RunRecord(
                            run_id=run.run_id,
                            status=run.status,
                            elapsed_time=self._normalise_elapsed_seconds(run.elapsed_time),
                            note=run.note,
                            created_at=run.created_at,
                        )
                        for run in version.run_records
                    ],
                    draft_sequence=self._normalise_draft_sequence(version.draft_sequence),
                    created_at=version.created_at,
                    updated_at=version.updated_at,
                )
            )
        return TaskMemoryRecord(
            record_id=record.record_id,
            user_query=record.user_query,
            task_description=record.task_description,
            versions=normalized_versions,
            task_type=record.task_type,
            parameter_schema=deepcopy(record.parameter_schema),
            start_state_requirements=(list(record.start_state_requirements) if record.start_state_requirements is not None else None),
            optimization_summary=deepcopy(record.optimization_summary),
            root_version_id=record.root_version_id,
            latest_version_id=record.latest_version_id,
            latest_success_version_id=record.latest_success_version_id,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def _normalise_step_duration_seconds(self, value: float, *, assume_milliseconds: bool) -> float:
        duration = float(value or 0.0)
        if assume_milliseconds:
            duration /= 1000.0
        return round(duration, 3)

    def _normalise_elapsed_seconds(self, value: float) -> float:
        elapsed = float(value or 0.0)
        if elapsed >= LEGACY_RUN_ELAPSED_MS_THRESHOLD:
            elapsed /= 1000.0
        return round(elapsed, 3)

    def _sequence_signature(self, sequence: list[SequenceStepRecord]) -> tuple[str, ...]:
        return tuple(step.action_name for step in sequence)

    def _draft_sequence_signature(self, draft_sequence: list[dict[str, Any]] | None) -> str:
        return json.dumps(draft_sequence or [], sort_keys=True, separators=(",", ":"))

    def _resolve_commit_base_version(
        self,
        record: TaskMemoryRecord,
        base_version_id: str | None = None,
    ) -> SequenceVersionRecord | None:
        if base_version_id:
            selected = self._find_version_by_id(record, base_version_id)
            if selected is None:
                raise ValueError(f"Unknown base_version_id: {base_version_id}")
            return selected
        latest_success = self._find_version_by_id(record, record.latest_success_version_id)
        if latest_success:
            return latest_success
        if record.latest_version_id:
            return self._find_version_by_id(record, record.latest_version_id)
        return record.versions[-1] if record.versions else None

    def _find_version_by_id(self, record: TaskMemoryRecord, version_id: str | None) -> SequenceVersionRecord | None:
        if not version_id:
            return None
        for version in record.versions:
            if version.version_id == version_id:
                return version
        return None

    def _latest_success_version_id(self, versions: list[SequenceVersionRecord], fallback: str | None = None) -> str | None:
        for version in reversed(versions):
            if any(run.status == "success" for run in reversed(version.run_records)):
                return version.version_id
        return fallback

    def _new_record_id(self, user_query: str, task_description: str) -> str:
        seed = f"{user_query}|{task_description}|{uuid.uuid4().hex}"
        return f"taskmem-{sha1(seed.encode('utf-8')).hexdigest()[:12]}"

    def _build_task_record_summary(self, record: TaskMemoryRecord) -> dict[str, Any]:
        return {
            "record_id": record.record_id,
            "user_query": record.user_query,
            "task_description": record.task_description,
            "task_type": record.task_type,
            "parameter_schema": deepcopy(record.parameter_schema) if record.parameter_schema is not None else None,
            "start_state_requirements": list(record.start_state_requirements) if record.start_state_requirements is not None else None,
            "optimization_summary": deepcopy(record.optimization_summary) if record.optimization_summary is not None else None,
            "updated_at": record.updated_at,
            "success_versions": [self._build_success_version_summary(version) for version in self._success_versions(record)],
            "recent_failures": self._recent_failures(record),
            "root_version_id": record.root_version_id,
            "latest_version_id": record.latest_version_id,
            "latest_success_version_id": record.latest_success_version_id,
        }

    def _build_task_record_view(self, record: TaskMemoryRecord) -> dict[str, Any]:
        return {
            "record_id": record.record_id,
            "user_query": record.user_query,
            "task_description": record.task_description,
            "task_type": record.task_type,
            "parameter_schema": deepcopy(record.parameter_schema) if record.parameter_schema is not None else None,
            "start_state_requirements": list(record.start_state_requirements) if record.start_state_requirements is not None else None,
            "optimization_summary": deepcopy(record.optimization_summary) if record.optimization_summary is not None else None,
            "root_version_id": record.root_version_id,
            "latest_version_id": record.latest_version_id,
            "latest_success_version_id": record.latest_success_version_id,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "versions": [version.to_dict() for version in record.versions],
        }

    def _success_versions(self, record: TaskMemoryRecord) -> list[SequenceVersionRecord]:
        versions = [version for version in record.versions if any(run.status == "success" for run in version.run_records)]
        return list(reversed(versions))

    def _build_success_version_summary(self, version: SequenceVersionRecord) -> dict[str, Any]:
        success_runs = [run for run in version.run_records if run.status == "success"]
        latest_success_run = success_runs[-1] if success_runs else None
        failure_runs = [run for run in version.run_records if run.status != "success"]
        return {
            "version_id": version.version_id,
            "parent_version_id": version.parent_version_id,
            "change_summary": version.change_summary,
            "change_reason": version.change_reason,
            "sequence": [step.to_dict() for step in version.sequence],
            "draft_sequence": deepcopy(version.draft_sequence) if version.draft_sequence is not None else None,
            "planning_summary": self._planning_summary(version, success_runs, failure_runs),
            "success_run_count": len(success_runs),
            "failure_run_count": len(failure_runs),
            "latest_success_run": latest_success_run.to_dict() if latest_success_run else None,
            "created_at": version.created_at,
            "updated_at": version.updated_at,
        }

    def _recent_failures(self, record: TaskMemoryRecord) -> list[dict[str, Any]]:
        failures: list[dict[str, Any]] = []
        ordinal = 0
        for version in record.versions:
            for run in version.run_records:
                if run.status == "success":
                    continue
                failures.append(
                    {
                        "version_id": version.version_id,
                        "status": run.status,
                        "elapsed_time": run.elapsed_time,
                        "note": run.note,
                        "created_at": run.created_at,
                        "_ordinal": ordinal,
                    }
                )
                ordinal += 1
        failures.sort(key=lambda item: ((item.get("created_at") or ""), item["_ordinal"]), reverse=True)
        return [{key: value for key, value in item.items() if key != "_ordinal"} for item in failures[:RECENT_FAILURE_LIMIT]]

    def _append_run_to_version(
        self,
        record: TaskMemoryRecord,
        version_id: str,
        run_record: RunRecord,
    ) -> TaskMemoryRecord:
        updated_versions: list[SequenceVersionRecord] = []
        for version in record.versions:
            if version.version_id == version_id:
                updated_versions.append(
                    SequenceVersionRecord(
                        version_id=version.version_id,
                        parent_version_id=version.parent_version_id,
                        change_summary=version.change_summary,
                        change_reason=version.change_reason,
                        sequence=version.sequence,
                        run_records=[*version.run_records, run_record],
                        draft_sequence=version.draft_sequence,
                        created_at=version.created_at,
                        updated_at=now_iso(),
                    )
                )
            else:
                updated_versions.append(version)
        return TaskMemoryRecord(
            record_id=record.record_id,
            user_query=record.user_query,
            task_description=record.task_description,
            versions=updated_versions,
            task_type=record.task_type,
            parameter_schema=deepcopy(record.parameter_schema),
            start_state_requirements=(list(record.start_state_requirements) if record.start_state_requirements is not None else None),
            optimization_summary=deepcopy(record.optimization_summary),
            root_version_id=record.root_version_id,
            latest_version_id=record.latest_version_id,
            latest_success_version_id=self._latest_success_version_id(updated_versions, record.latest_success_version_id),
            created_at=record.created_at,
            updated_at=now_iso(),
        )

    def _draft_action_step(self, event: Mapping[str, Any]) -> dict[str, Any]:
        action = self._compact_action_payload(event.get("action") or {})
        return {
            "type": "action",
            "status": str(event.get("status") or event.get("primitive_status") or "unknown"),
            "duration": round(float(event.get("duration_ms", 0.0)) / 1000.0, 3),
            "payload": action,
            "semantic_reason": ((event.get("semantic_evaluation") or {}).get("reason")),
        }

    def _draft_batch_step(self, event: Mapping[str, Any]) -> dict[str, Any]:
        batch = deepcopy(dict(event.get("batch") or {}))
        return {
            "type": "batch",
            "status": str(event.get("status") or "unknown"),
            "duration": round(float(event.get("duration_ms", 0.0)) / 1000.0, 3),
            "payload": batch,
            "semantic_reason": ((event.get("semantic_evaluation") or {}).get("reason")),
        }

    def _draft_wait_stable_step(self, event: Mapping[str, Any]) -> dict[str, Any]:
        wait_result = event.get("wait_result") or {}
        return {
            "type": "wait_stable",
            "status": str(event.get("status") or "unknown"),
            "duration": round(float(event.get("duration_ms", 0.0)) / 1000.0, 3),
            "stable_seconds": wait_result.get("stable_duration"),
            "elapsed_seconds": wait_result.get("elapsed_seconds"),
            "diff_threshold": wait_result.get("diff_threshold"),
        }

    def _compact_action_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        action = deepcopy(dict(payload))
        action.pop("fingerprint", None)
        return action

    def _planning_summary(
        self,
        version: SequenceVersionRecord,
        success_runs: list[RunRecord],
        failure_runs: list[RunRecord],
    ) -> dict[str, Any]:
        draft_sequence = version.draft_sequence or []
        draft_action_count = 0
        draft_batch_count = 0
        observation_checkpoints = 0
        for step in draft_sequence:
            if step.get("type") == "batch":
                draft_batch_count += 1
                payload = step.get("payload") or {}
                draft_action_count += len(payload.get("actions") or [])
                if payload.get("observe_after", True):
                    observation_checkpoints += 1
            elif step.get("type") == "action":
                draft_action_count += 1
            elif step.get("type") == "wait_stable":
                observation_checkpoints += 1
        latest_success_run = success_runs[-1] if success_runs else None
        return {
            "raw_step_count": len(version.sequence),
            "draft_step_count": len(draft_sequence),
            "draft_batch_count": draft_batch_count,
            "draft_action_count": draft_action_count,
            "observation_checkpoints": observation_checkpoints,
            "success_run_count": len(success_runs),
            "failure_run_count": len(failure_runs),
            "latest_success_elapsed_time": latest_success_run.elapsed_time if latest_success_run else None,
        }
