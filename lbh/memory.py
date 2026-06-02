from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha1
from statistics import median
from typing import Any, Iterable

from .common import MEMORY_DIR, append_jsonl, ensure_dir, now_iso, tokenise


def jaccard_similarity(left: Iterable[str], right: Iterable[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)


class MemoryStore:
    def __init__(self, memory_dir=MEMORY_DIR):
        self.memory_dir = ensure_dir(memory_dir)
        self.episodes_path = self.memory_dir / "episodes.jsonl"
        self.failure_guards_path = self.memory_dir / "failure_guards.jsonl"
        self.skills_path = self.memory_dir / "skills.jsonl"
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

    def build_situation_signature(self, goal: str, observation: dict[str, Any] | None = None) -> dict[str, Any]:
        active_title = ""
        screenshot_hash = None
        if observation:
            active_window = observation.get("active_window") or {}
            active_title = str(active_window.get("title") or "")
            screenshot_hash = observation.get("image_sha256")
        signature = " | ".join(part for part in (goal.strip(), active_title.strip()) if part)
        return {
            "signature": signature or goal.strip(),
            "tokens": tokenise(signature or goal),
            "active_window_title": active_title,
            "screenshot_hash": screenshot_hash,
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
        episodes = self._rank_records(
            self._read_jsonl(self.episodes_path),
            query_tokens,
            lambda item: " ".join([item.get("goal", ""), item.get("final_answer", ""), item.get("situation_signature", "")]),
            limit,
        )
        guards = self._rank_records(
            self._read_jsonl(self.failure_guards_path),
            query_tokens,
            lambda item: " ".join(
                [
                    item.get("situation_signature", ""),
                    item.get("bad_action_pattern", ""),
                    item.get("reason", ""),
                    item.get("replacement_suggestion", ""),
                ]
            ),
            limit,
        )
        skills = self._rank_records(
            self._read_jsonl(self.skills_path),
            query_tokens,
            lambda item: " ".join(
                [
                    item.get("name", ""),
                    item.get("precondition_signature", ""),
                    " ".join(item.get("action_sequence", [])),
                    item.get("postcondition_signature", ""),
                ]
            ),
            limit,
        )
        return {
            "query_signature": signature,
            "episodes": episodes,
            "failure_guards": guards,
            "skills": skills,
        }

    def evaluate_failure_guards(
        self,
        *,
        goal: str,
        observation: dict[str, Any] | None,
        action_fingerprints: list[str],
    ) -> list[dict[str, Any]]:
        signature = self.build_situation_signature(goal, observation)
        matches: list[dict[str, Any]] = []
        for guard in self._read_jsonl(self.failure_guards_path):
            situation_score = jaccard_similarity(
                signature["tokens"],
                guard.get("situation_tokens") or tokenise(guard.get("situation_signature", "")),
            )
            for fingerprint in action_fingerprints:
                pattern = guard.get("action_fingerprint") or guard.get("bad_action_pattern", "")
                if not pattern:
                    continue
                action_score = 1.0 if fingerprint == pattern else 0.65 if fingerprint.split(":")[0] == pattern.split(":")[0] else 0.0
                if action_score == 0.0 or situation_score < 0.2:
                    continue
                matches.append(
                    {
                        "guard_id": guard.get("id"),
                        "decision": "block" if float(guard.get("confidence", 0.75)) >= 0.85 and int(guard.get("support_count", 1)) >= 3 else "warn",
                        "score": round((0.6 * action_score) + (0.4 * situation_score), 3),
                        "confidence": float(guard.get("confidence", 0.75)),
                        "support_count": int(guard.get("support_count", 1)),
                        "failure_rate": float(guard.get("failure_rate", 1.0)),
                        "reason": guard.get("reason"),
                        "replacement_suggestion": guard.get("replacement_suggestion"),
                        "action_fingerprint": fingerprint,
                        "situation_signature": guard.get("situation_signature"),
                    }
                )
        return sorted(matches, key=lambda item: (item["decision"] == "block", item["score"], item["confidence"]), reverse=True)

    def consolidate_task(self, *, state, events: list[dict[str, Any]], final_answer: str) -> dict[str, Any]:
        updates = {"episode": None, "failure_guards": [], "skills": []}
        episode = self._build_episode(state=state, events=events, final_answer=final_answer)
        append_jsonl(self.episodes_path, episode)
        updates["episode"] = episode
        updates["failure_guards"] = self._update_failure_guards(state.goal, events)
        updates["skills"] = self._update_skill_candidates(state.goal, events)
        return updates

    def store_locator(self, payload: dict[str, Any]) -> dict[str, Any]:
        append_jsonl(self.locators_path, payload)
        return payload

    def _rank_records(self, records: list[dict[str, Any]], query_tokens: list[str], text_fn, limit: int) -> list[dict[str, Any]]:
        ranked = []
        for record in records:
            score = jaccard_similarity(query_tokens, tokenise(text_fn(record)))
            if score <= 0:
                continue
            ranked.append({"score": round(score, 3), **record})
        ranked.sort(key=lambda item: item["score"], reverse=True)
        return ranked[:limit]

    def _build_episode(self, *, state, events: list[dict[str, Any]], final_answer: str) -> dict[str, Any]:
        observation_titles = [
            event.get("observation", {}).get("active_window", {}).get("title")
            for event in events
            if event.get("type") == "observation"
        ]
        action_fingerprints = [
            event.get("action", {}).get("fingerprint")
            for event in events
            if event.get("type") == "action"
        ]
        latencies = [event.get("duration_ms") for event in events if isinstance(event.get("duration_ms"), (int, float))]
        situation = self.build_situation_signature(state.goal, state.latest_observation)
        return {
            "id": f"episode-{state.task_id}-{sha1(state.task_id.encode('utf-8')).hexdigest()[:10]}",
            "task_id": state.task_id,
            "created_at": now_iso(),
            "goal": state.goal,
            "status": state.status,
            "final_answer": final_answer,
            "observation_titles": [title for title in observation_titles if title],
            "action_fingerprints": [fingerprint for fingerprint in action_fingerprints if fingerprint],
            "situation_signature": situation["signature"],
            "latency_summary_ms": {
                "count": len(latencies),
                "total": round(sum(latencies), 3) if latencies else 0,
                "median": round(median(latencies), 3) if latencies else 0,
            },
            "failure_events": [
                event["summary"]
                for event in events
                if event.get("status") == "error" or event.get("evaluation", {}).get("expectation_match") is False
            ],
        }

    def _update_failure_guards(self, goal: str, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        aggregated: dict[tuple[str, str], dict[str, Any]] = {}
        for event in events:
            if event.get("type") != "action":
                continue
            fingerprint = event.get("action", {}).get("fingerprint")
            if not fingerprint:
                continue
            failure_reason = None
            evaluation = event.get("evaluation") or {}
            if event.get("status") == "error":
                failure_reason = (event.get("error") or {}).get("message") or event["summary"]
            elif evaluation.get("expectation_match") is False:
                failure_reason = "Expected active window title did not match after the action."
            elif evaluation.get("changed") is False and evaluation.get("no_progress_streak", 0) > 0:
                failure_reason = "The action produced no visible progress in a similar state."
            if not failure_reason:
                continue
            situation = self.build_situation_signature(goal, event.get("pre_observation"))
            key = (situation["signature"], fingerprint)
            entry = aggregated.setdefault(
                key,
                {
                    "id": f"guard-{sha1('|'.join(key).encode('utf-8')).hexdigest()[:12]}",
                    "created_at": now_iso(),
                    "updated_at": now_iso(),
                    "situation_signature": situation["signature"],
                    "situation_tokens": situation["tokens"],
                    "bad_action_pattern": fingerprint,
                    "action_fingerprint": fingerprint,
                    "reason": failure_reason,
                    "replacement_suggestion": "Capture a fresh observation and choose a different low-risk action before retrying.",
                    "support_count": 0,
                    "failure_count": 0,
                },
            )
            entry["support_count"] += 1
            entry["failure_count"] += 1
            entry["updated_at"] = now_iso()

        existing = {item["id"]: item for item in self._read_jsonl(self.failure_guards_path)}
        updates: list[dict[str, Any]] = []
        for record in aggregated.values():
            current = existing.get(record["id"], {})
            merged_support = int(current.get("support_count", 0)) + int(record["support_count"])
            merged_failures = int(current.get("failure_count", 0)) + int(record["failure_count"])
            merged = {
                **current,
                **record,
                "support_count": merged_support,
                "failure_count": merged_failures,
                "failure_rate": round(merged_failures / merged_support if merged_support else 1.0, 3),
                "confidence": round(min(0.99, 0.55 + (merged_support * 0.1)), 3),
            }
            existing[record["id"]] = merged
            updates.append(merged)
        self._rewrite_jsonl(self.failure_guards_path, existing.values())
        return updates

    def _update_skill_candidates(self, goal: str, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        traces = [
            {
                "fingerprint": event.get("action", {}).get("fingerprint"),
                "duration_ms": float(event.get("duration_ms", 0)),
                "pre_title": ((event.get("pre_observation") or {}).get("active_window") or {}).get("title"),
                "post_title": ((event.get("post_observation") or {}).get("active_window") or {}).get("title"),
            }
            for event in events
            if event.get("type") == "action" and event.get("status") == "success" and event.get("action", {}).get("fingerprint")
        ]
        candidates = generate_skill_candidates_from_traces(goal, traces)
        existing = {item["id"]: item for item in self._read_jsonl(self.skills_path)}
        updates: list[dict[str, Any]] = []
        for candidate in candidates:
            current = existing.get(candidate["id"], {})
            merged_success = int(current.get("success_count", 0)) + int(candidate["success_count"])
            merged_total = int(current.get("total_count", 0)) + int(candidate["total_count"])
            merged_latencies = list(current.get("latency_samples", [])) + list(candidate["latency_samples"])
            merged = {
                **current,
                **candidate,
                "updated_at": now_iso(),
                "success_count": merged_success,
                "total_count": merged_total,
                "median_latency_ms": round(median(merged_latencies), 3) if merged_latencies else 0.0,
                "latency_samples": merged_latencies,
                "status": current.get("status", candidate.get("status", "candidate")),
            }
            existing[candidate["id"]] = merged
            updates.append(merged)
        self._rewrite_jsonl(self.skills_path, existing.values())
        return updates

    def _rewrite_jsonl(self, path, records: Iterable[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        for record in records:
            append_jsonl(path, record)


def generate_skill_candidates_from_traces(goal: str, traces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(traces) < 4:
        return []
    patterns: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for size in range(2, min(5, len(traces) + 1)):
        for index in range(0, len(traces) - size + 1):
            window = traces[index : index + size]
            signature = tuple(item["fingerprint"] for item in window)
            patterns[signature].append(
                {
                    "pre_title": window[0].get("pre_title") or "",
                    "post_title": window[-1].get("post_title") or "",
                    "latency_ms": sum(item.get("duration_ms", 0.0) for item in window),
                }
            )
    candidates: list[dict[str, Any]] = []
    for action_sequence, occurrences in patterns.items():
        if len(occurrences) < 2:
            continue
        pre_title = Counter(item["pre_title"] for item in occurrences if item["pre_title"]).most_common(1)
        post_title = Counter(item["post_title"] for item in occurrences if item["post_title"]).most_common(1)
        precondition_signature = pre_title[0][0] if pre_title else goal
        postcondition_signature = post_title[0][0] if post_title else ""
        latency_samples = [round(item["latency_ms"], 3) for item in occurrences]
        sequence_slug = "-".join(step.replace(":", "-") for step in action_sequence)[:80]
        candidates.append(
            {
                "id": f"skill-{sha1((precondition_signature + '|' + '|'.join(action_sequence)).encode('utf-8')).hexdigest()[:12]}",
                "created_at": now_iso(),
                "updated_at": now_iso(),
                "name": f"candidate-{sequence_slug}",
                "precondition_signature": precondition_signature,
                "action_sequence": list(action_sequence),
                "postcondition_signature": postcondition_signature,
                "status": "candidate",
                "success_count": len(occurrences),
                "total_count": len(occurrences),
                "median_latency_ms": round(median(latency_samples), 3),
                "latency_samples": latency_samples,
            }
        )
    candidates.sort(key=lambda item: (item["success_count"], len(item["action_sequence"])), reverse=True)
    return candidates
