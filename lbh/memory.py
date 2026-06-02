from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from .config import LBHConfig, DEFAULT_CONFIG
from .models import AtomicAction, ActionBatch, Observation


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def action_signature(action: AtomicAction) -> str:
    if action.type in {"click", "double_click"}:
        # Coordinates are intentionally generalized.
        return f"{action.type}:point:{action.button}"
    if action.type == "hotkey":
        return "hotkey:" + "+".join(k.lower() for k in (action.keys or []))
    if action.type == "press":
        return f"press:{_norm(action.key)}"
    if action.type == "type_text":
        return "type_text:<text>"
    if action.type == "clipboard_set":
        return "clipboard_set:<text>"
    if action.type == "window_activate":
        return f"window_activate:{_norm(action.title_contains)}"
    return action.type


def batch_signature(batch: ActionBatch) -> str:
    return " | ".join(action_signature(a) for a in batch.actions)


@dataclass
class SituationSignature:
    goal_tags: list[str]
    active_window_title: str | None
    screenshot_hash: str | None = None
    app_hint: str | None = None
    url_hint: str | None = None

    @classmethod
    def from_observation(cls, goal: str, observation: dict[str, Any] | Observation | None) -> "SituationSignature":
        if isinstance(observation, Observation):
            payload = observation.to_dict()
        else:
            payload = observation or {}
        active = payload.get("active_window") or {}
        return cls(
            goal_tags=[t for t in _norm(goal).replace("/", " ").replace("-", " ").split() if len(t) >= 3][:12],
            active_window_title=active.get("title"),
            screenshot_hash=payload.get("screenshot_hash"),
        )

    def score_against(self, other: "SituationSignature") -> float:
        score = 0.0
        if self.active_window_title and other.active_window_title:
            if _norm(self.active_window_title) == _norm(other.active_window_title):
                score += 2.0
            elif _norm(self.active_window_title) in _norm(other.active_window_title) or _norm(other.active_window_title) in _norm(self.active_window_title):
                score += 1.0
        left = set(self.goal_tags)
        right = set(other.goal_tags)
        if left and right:
            score += len(left & right) / max(1, len(left | right))
        if self.screenshot_hash and other.screenshot_hash and self.screenshot_hash == other.screenshot_hash:
            score += 2.0
        return round(score, 3)


@dataclass
class EpisodeRecord:
    id: str
    created_at: str
    task_id: str
    goal: str
    situation: dict[str, Any]
    action_batch: dict[str, Any]
    outcome: str
    latency_ms: int | None = None
    observation_before: dict[str, Any] | None = None
    observation_after: dict[str, Any] | None = None
    notes: str | None = None


@dataclass
class FailureGuard:
    id: str
    created_at: str
    situation: dict[str, Any]
    bad_action_signature: str
    reason: str
    replacement_batch: dict[str, Any] | None
    support: int = 1
    failure_rate: float = 1.0
    status: str = "active"


@dataclass
class SkillMemory:
    id: str
    created_at: str
    name: str
    preconditions: dict[str, Any]
    action_batch: dict[str, Any]
    postcondition: dict[str, Any] | None
    support: int
    success_rate: float
    median_latency_ms: int | None = None
    status: str = "candidate"


class MemoryStore:
    def __init__(self, config: LBHConfig = DEFAULT_CONFIG):
        self.config = config
        self.root = Path(config.memory.memory_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        self.episodes_path = self.root / "episodes.jsonl"
        self.failure_guards_path = self.root / "failure_guards.jsonl"
        self.skills_path = self.root / "skills.jsonl"

    def _append(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _read_jsonl(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        out = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    def remember_episode(self, record: EpisodeRecord) -> None:
        self._append(self.episodes_path, asdict(record))

    def remember_failure_guard(self, guard: FailureGuard) -> None:
        self._append(self.failure_guards_path, asdict(guard))

    def remember_skill(self, skill: SkillMemory) -> None:
        self._append(self.skills_path, asdict(skill))

    def find_relevant_failure_guards(self, situation: SituationSignature, proposed_batch: ActionBatch, limit: int = 5) -> list[dict[str, Any]]:
        proposed_sig = batch_signature(proposed_batch)
        scored: list[tuple[float, dict[str, Any]]] = []
        for guard in self._read_jsonl(self.failure_guards_path):
            if guard.get("status", "active") != "active":
                continue
            if guard.get("bad_action_signature") not in proposed_sig:
                continue
            guard_sit = SituationSignature(**guard.get("situation", {}))
            score = situation.score_against(guard_sit)
            if score > 0:
                scored.append((score, guard))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [{**guard, "score": score} for score, guard in scored[:limit]]

    def propose_skills(self, situation: SituationSignature, limit: int = 5) -> list[dict[str, Any]]:
        scored: list[tuple[float, dict[str, Any]]] = []
        for skill in self._read_jsonl(self.skills_path):
            if skill.get("status") not in {"candidate", "approved"}:
                continue
            pre = skill.get("preconditions") or {}
            active_title = _norm(pre.get("active_window_title_contains"))
            score = 0.0
            if active_title and situation.active_window_title and active_title in _norm(situation.active_window_title):
                score += 2.0
            goal_tags = set(pre.get("goal_tags") or [])
            if goal_tags:
                score += len(goal_tags & set(situation.goal_tags)) / max(1, len(goal_tags))
            score += min(float(skill.get("success_rate", 0.0)), 1.0)
            if score > 0:
                scored.append((score, skill))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [{**skill, "score": score} for score, skill in scored[:limit]]

    def consolidate_simple_skills(self) -> list[SkillMemory]:
        """Mine repeated successful action batches from episodes.

        This is intentionally conservative. It only promotes exact repeated batch
        signatures into skill candidates.
        """

        episodes = self._read_jsonl(self.episodes_path)
        buckets: dict[str, list[dict[str, Any]]] = {}
        for ep in episodes:
            if ep.get("outcome") != "success":
                continue
            batch = ActionBatch.from_dict(ep.get("action_batch") or {"actions": []})
            sig = batch_signature(batch)
            if not sig:
                continue
            buckets.setdefault(sig, []).append(ep)

        created: list[SkillMemory] = []
        existing_sigs = {
            batch_signature(ActionBatch.from_dict(item.get("action_batch") or {"actions": []}))
            for item in self._read_jsonl(self.skills_path)
        }
        for sig, eps in buckets.items():
            if len(eps) < self.config.memory.min_skill_support:
                continue
            if sig in existing_sigs:
                continue
            latencies = sorted(ep.get("latency_ms") or 0 for ep in eps if ep.get("latency_ms"))
            median = latencies[len(latencies) // 2] if latencies else None
            first = eps[0]
            situation = first.get("situation") or {}
            skill = SkillMemory(
                id=f"skill-{abs(hash(sig))}",
                created_at=now_iso(),
                name="skill_" + str(abs(hash(sig)))[:8],
                preconditions={
                    "active_window_title_contains": situation.get("active_window_title"),
                    "goal_tags": situation.get("goal_tags", []),
                },
                action_batch=first.get("action_batch") or {},
                postcondition=None,
                support=len(eps),
                success_rate=1.0,
                median_latency_ms=median,
                status="candidate",
            )
            self.remember_skill(skill)
            created.append(skill)
        return created
