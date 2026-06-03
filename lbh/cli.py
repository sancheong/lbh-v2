from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from .common import coerce_json_input
from .memory import MemoryStore
from .runtime import LBHRuntime
from .task_store import TaskStore


def emit(payload: dict[str, Any], exit_code: int = 0) -> None:
    print(json.dumps(payload, ensure_ascii=True, indent=2))
    raise SystemExit(exit_code)


def _bool_override(parser: argparse.ArgumentParser, name: str, default: bool) -> None:
    parser.add_argument(f"--{name}", dest=name.replace("-", "_"), action="store_true")
    parser.add_argument(f"--no-{name}", dest=name.replace("-", "_"), action="store_false")
    parser.set_defaults(**{name.replace("-", "_"): default})


def runtime_from_args(args) -> LBHRuntime:
    tasks_dir = Path(getattr(args, "tasks_dir", "tasks"))
    root_dir = tasks_dir if tasks_dir.is_absolute() else Path.cwd() / tasks_dir
    memory_dir = root_dir.parent / "memories"
    memory_mode = getattr(args, "memory_mode", None) or ("warn" if getattr(args, "use_memory", False) else "off")
    return LBHRuntime(
        task_store=TaskStore(tasks_dir=root_dir),
        memory_store=MemoryStore(memory_dir=memory_dir),
        memory_reference_enabled=memory_mode != "off",
        memory_mode=memory_mode,
    )


def cmd_start(runtime: LBHRuntime, args) -> dict[str, Any]:
    return runtime.create_task(
        args.goal,
        task_id=args.id,
        model_max_width=args.model_max_width,
        jpeg_quality=args.jpeg_quality,
        force=args.force,
    )


def cmd_observe(runtime: LBHRuntime, args) -> dict[str, Any]:
    return runtime.observe(args.task, save_full_resolution=args.save_original)


def cmd_action(runtime: LBHRuntime, args) -> dict[str, Any]:
    payload = _coerce_cli_json(args.json or args.action_json or args.action_file, use_stdin=args.stdin_json)
    return runtime.execute_action(
        args.task,
        payload,
        observe_after=args.observe_after,
        ignore_guards=args.ignore_guards,
    )


def cmd_batch(runtime: LBHRuntime, args) -> dict[str, Any]:
    payload = _coerce_cli_json(args.json or args.actions, use_stdin=args.stdin_json)
    if not args.observe_after:
        if isinstance(payload, list):
            payload = {"actions": payload, "observe_after": False}
        else:
            payload = {**payload, "observe_after": False}
    return runtime.execute_batch(args.task, payload, ignore_guards=args.ignore_guards)


def cmd_finish(runtime: LBHRuntime, args) -> dict[str, Any]:
    return runtime.finish(args.task, args.answer)


def cmd_suspend(runtime: LBHRuntime, args) -> dict[str, Any]:
    return runtime.suspend(
        args.task,
        reason_code=args.reason_code,
        user_action=args.user_action,
        done_when=args.done_when,
        resume_action=args.resume_action,
    )


def cmd_resume(runtime: LBHRuntime, args) -> dict[str, Any]:
    return runtime.resume(args.task, note=args.note, observe_after=args.observe_after)


def cmd_status(runtime: LBHRuntime, args) -> dict[str, Any]:
    return runtime.status(args.task, event_limit=args.events)


def cmd_memory_search(runtime: LBHRuntime, args) -> dict[str, Any]:
    return runtime.memory_search(args.task, query=args.query, limit=args.limit)


def cmd_memory_record(runtime: LBHRuntime, args) -> dict[str, Any]:
    return runtime.memory_record(args.task, record_id=args.record_id)


def cmd_memory_select(runtime: LBHRuntime, args) -> dict[str, Any]:
    return runtime.memory_select(args.task, record_id=args.record_id)


def cmd_memory_commit(runtime: LBHRuntime, args) -> dict[str, Any]:
    payload = _coerce_cli_json(args.json or args.memory_json or args.memory_file, use_stdin=args.stdin_json)
    return runtime.memory_commit(args.task, payload)


def _coerce_cli_json(value: str | None, *, use_stdin: bool = False) -> Any:
    if use_stdin:
        return json.loads(sys.stdin.read())
    if value is None:
        raise ValueError("A JSON payload or --stdin-json is required.")
    return coerce_json_input(value)


def cmd_wait_stable(runtime: LBHRuntime, args) -> dict[str, Any]:
    return runtime.wait_stable(
        args.task,
        stable_seconds=args.seconds,
        timeout_seconds=args.timeout,
        interval_seconds=args.interval,
        diff_threshold=args.diff_threshold,
    )


def cmd_benchmark(runtime: LBHRuntime, args) -> dict[str, Any]:
    action_payload = coerce_json_input(args.action_json) if args.action_json else None
    batch_payload = coerce_json_input(args.batch_json) if args.batch_json else None
    return runtime.benchmark(
        args.task,
        action_payload=action_payload,
        batch_payload=batch_payload,
        stable_seconds=args.stable_seconds,
        timeout_seconds=args.timeout,
        interval_seconds=args.interval,
        sample_count=args.sample_count,
        ignore_guards=args.ignore_guards,
    )


def cmd_benchmark_report(runtime: LBHRuntime, args) -> dict[str, Any]:
    return runtime.benchmark_report(args.task, top_n=args.top)


def cmd_locator_contract(runtime: LBHRuntime, args) -> dict[str, Any]:
    return runtime.locator_contract(args.task, args.target)


def cmd_locate_parse(runtime: LBHRuntime, args) -> dict[str, Any]:
    text = Path(args.response_file).read_text(encoding="utf-8-sig") if args.response_file else args.response_text
    return runtime.locate_parse(args.task, text)


def cmd_skills(runtime: LBHRuntime, args) -> dict[str, Any]:
    return runtime.skills(args.task, consolidate=args.consolidate)


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--tasks-dir", default="tasks")
    parser.add_argument("--model-max-width", type=int, default=1280)
    parser.add_argument("--jpeg-quality", type=int, default=80)
    parser.add_argument("--save-original", action="store_true")
    parser.add_argument("--use-memory", action="store_true")
    parser.add_argument("--memory-mode", choices=["off", "warn", "block"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LBH V2 Local Browser Harness runtime")
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start")
    add_common(start)
    start.add_argument("goal")
    start.add_argument("--id")
    start.add_argument("--force", action="store_true")
    start.set_defaults(func=cmd_start)

    task_new = sub.add_parser("task-new")
    add_common(task_new)
    task_new.add_argument("goal")
    task_new.add_argument("--id")
    task_new.add_argument("--force", action="store_true")
    task_new.set_defaults(func=cmd_start)

    observe = sub.add_parser("observe")
    add_common(observe)
    observe.add_argument("--task", required=True)
    observe.set_defaults(func=cmd_observe)

    action = sub.add_parser("action")
    add_common(action)
    action.add_argument("--task", required=True)
    group = action.add_mutually_exclusive_group(required=True)
    group.add_argument("--json")
    group.add_argument("--action-json")
    group.add_argument("--action-file")
    group.add_argument("--stdin-json", action="store_true")
    _bool_override(action, "observe-after", True)
    action.add_argument("--ignore-guards", action="store_true")
    action.add_argument("--ignore-memory-guards", dest="ignore_guards", action="store_true")
    action.set_defaults(func=cmd_action)

    batch = sub.add_parser("batch")
    add_common(batch)
    batch.add_argument("--task", required=True)
    group = batch.add_mutually_exclusive_group(required=True)
    group.add_argument("--json")
    group.add_argument("--actions")
    group.add_argument("--stdin-json", action="store_true")
    _bool_override(batch, "observe-after", True)
    batch.add_argument("--ignore-guards", action="store_true")
    batch.add_argument("--ignore-memory-guards", dest="ignore_guards", action="store_true")
    batch.set_defaults(func=cmd_batch)

    finish = sub.add_parser("finish")
    add_common(finish)
    finish.add_argument("--task", required=True)
    finish.add_argument("--answer", required=True)
    finish.set_defaults(func=cmd_finish)

    suspend = sub.add_parser("suspend")
    add_common(suspend)
    suspend.add_argument("--task", required=True)
    suspend.add_argument("--reason-code", required=True)
    suspend.add_argument("--user-action", required=True)
    suspend.add_argument("--done-when")
    suspend.add_argument("--resume-action")
    suspend.set_defaults(func=cmd_suspend)

    resume = sub.add_parser("resume")
    add_common(resume)
    resume.add_argument("--task", required=True)
    resume.add_argument("--note", required=True)
    _bool_override(resume, "observe-after", True)
    resume.set_defaults(func=cmd_resume)

    status = sub.add_parser("status")
    add_common(status)
    status.add_argument("--task", required=True)
    status.add_argument("--events", type=int, default=5)
    status.set_defaults(func=cmd_status)

    memory_search = sub.add_parser("memory-search")
    add_common(memory_search)
    memory_search.add_argument("--task", required=True)
    memory_search.add_argument("--query")
    memory_search.add_argument("--limit", type=int, default=5)
    memory_search.set_defaults(func=cmd_memory_search)

    memory_record = sub.add_parser("memory-record")
    add_common(memory_record)
    memory_record.add_argument("--task", required=True)
    memory_record.add_argument("--record-id")
    memory_record.set_defaults(func=cmd_memory_record)

    memory_select = sub.add_parser("memory-select")
    add_common(memory_select)
    memory_select.add_argument("--task", required=True)
    memory_select.add_argument("--record-id", required=True)
    memory_select.set_defaults(func=cmd_memory_select)

    memory_commit = sub.add_parser("memory-commit")
    add_common(memory_commit)
    memory_commit.add_argument("--task", required=True)
    group = memory_commit.add_mutually_exclusive_group(required=True)
    group.add_argument("--json")
    group.add_argument("--memory-json")
    group.add_argument("--memory-file")
    group.add_argument("--stdin-json", action="store_true")
    memory_commit.set_defaults(func=cmd_memory_commit)

    wait_stable = sub.add_parser("wait-stable")
    add_common(wait_stable)
    wait_stable.add_argument("--task", required=True)
    wait_stable.add_argument("--seconds", type=float, required=True)
    wait_stable.add_argument("--timeout", type=float, required=True)
    wait_stable.add_argument("--interval", type=float, default=1.0)
    wait_stable.add_argument("--diff-threshold", type=float, default=0.01)
    wait_stable.set_defaults(func=cmd_wait_stable)

    benchmark = sub.add_parser("benchmark")
    add_common(benchmark)
    benchmark.add_argument("--task", required=True)
    benchmark.add_argument("--action-json")
    benchmark.add_argument("--batch-json")
    benchmark.add_argument("--stable-seconds", type=float)
    benchmark.add_argument("--timeout", type=float, default=60.0)
    benchmark.add_argument("--interval", type=float, default=1.0)
    benchmark.add_argument("--sample-count", type=int, default=5000)
    benchmark.add_argument("--ignore-guards", action="store_true")
    benchmark.add_argument("--ignore-memory-guards", dest="ignore_guards", action="store_true")
    benchmark.set_defaults(func=cmd_benchmark)

    benchmark_report = sub.add_parser("benchmark-report")
    add_common(benchmark_report)
    benchmark_report.add_argument("--task", required=True)
    benchmark_report.add_argument("--top", type=int, default=5)
    benchmark_report.set_defaults(func=cmd_benchmark_report)

    locator = sub.add_parser("locator-contract")
    add_common(locator)
    locator.add_argument("--task", required=True)
    locator.add_argument("--target", required=True)
    locator.set_defaults(func=cmd_locator_contract)

    locate_parse = sub.add_parser("locate-parse")
    add_common(locate_parse)
    locate_parse.add_argument("--task", required=True)
    group = locate_parse.add_mutually_exclusive_group(required=True)
    group.add_argument("--response-text")
    group.add_argument("--response-file")
    locate_parse.set_defaults(func=cmd_locate_parse)

    skills = sub.add_parser("skills")
    add_common(skills)
    skills.add_argument("--task")
    skills.add_argument("--consolidate", action="store_true")
    skills.set_defaults(func=cmd_skills)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    runtime = runtime_from_args(args)
    try:
        emit(args.func(runtime, args))
    except Exception as exc:
        emit({"status": "error", "error_type": exc.__class__.__name__, "message": str(exc)}, exit_code=1)


if __name__ == "__main__":
    main()
