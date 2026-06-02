from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .config import DEFAULT_CONFIG, LBHConfig, ScreenshotConfig
from .models import ActionBatch, AtomicAction, LocatorResult
from .runtime import LBHRuntime


def emit(payload, exit_code=0):
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    raise SystemExit(exit_code)


def runtime_from_args(args) -> LBHRuntime:
    screenshot = ScreenshotConfig(
        model_max_width=args.model_max_width,
        jpeg_quality=args.jpeg_quality,
        save_original=args.save_original,
    )
    config = LBHConfig(tasks_dir=Path(args.tasks_dir), screenshot=screenshot)
    return LBHRuntime(config)


def add_common(parser):
    parser.add_argument("--tasks-dir", default="tasks")
    parser.add_argument("--model-max-width", type=int, default=1280)
    parser.add_argument("--jpeg-quality", type=int, default=75)
    parser.add_argument("--save-original", action="store_true")


def cmd_task_new(args):
    rt = runtime_from_args(args)
    state = rt.create_task(args.goal, task_id=args.id, force=args.force)
    return {"status": "success", "state": state.to_dict()}


def cmd_observe(args):
    rt = runtime_from_args(args)
    obs = rt.observe(args.task)
    return {"status": "success", "observation": obs.to_dict()}


def cmd_action(args):
    rt = runtime_from_args(args)
    data = json.loads(Path(args.action_file).read_text(encoding="utf-8")) if args.action_file else json.loads(args.action_json)
    action = AtomicAction.from_dict(data)
    return rt.execute_action(args.task, action, observe_after=args.observe_after)


def cmd_batch(args):
    rt = runtime_from_args(args)
    data = json.loads(Path(args.actions).read_text(encoding="utf-8"))
    batch = ActionBatch.from_dict(data)
    batch.observe_after = args.observe_after
    return rt.execute_batch(args.task, batch)


def cmd_locator_contract(args):
    rt = runtime_from_args(args)
    return rt.locator_contract(args.task, args.target)


def cmd_locate_parse(args):
    rt = runtime_from_args(args)
    text = Path(args.response_file).read_text(encoding="utf-8") if args.response_file else args.response_text
    return rt.locate_from_json(args.task, text)


def cmd_skills(args):
    rt = runtime_from_args(args)
    if args.consolidate:
        return rt.consolidate_skills()
    return rt.propose_skills(args.task)


def build_parser():
    parser = argparse.ArgumentParser(description="LBH V2 Local Browser Harness runtime")
    sub = parser.add_subparsers(dest="command", required=True)

    task_new = sub.add_parser("task-new")
    add_common(task_new)
    task_new.add_argument("goal")
    task_new.add_argument("--id")
    task_new.add_argument("--force", action="store_true")
    task_new.set_defaults(func=cmd_task_new)

    observe = sub.add_parser("observe")
    add_common(observe)
    observe.add_argument("--task", required=True)
    observe.set_defaults(func=cmd_observe)

    action = sub.add_parser("action")
    add_common(action)
    action.add_argument("--task", required=True)
    group = action.add_mutually_exclusive_group(required=True)
    group.add_argument("--action-json")
    group.add_argument("--action-file")
    action.add_argument("--observe-after", action=argparse.BooleanOptionalAction, default=True)
    action.set_defaults(func=cmd_action)

    batch = sub.add_parser("batch")
    add_common(batch)
    batch.add_argument("--task", required=True)
    batch.add_argument("--actions", required=True, help="JSON file containing either a list of actions or an ActionBatch object")
    batch.add_argument("--observe-after", action=argparse.BooleanOptionalAction, default=True)
    batch.set_defaults(func=cmd_batch)

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


def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        emit(args.func(args))
    except Exception as exc:
        emit({"status": "error", "error_type": exc.__class__.__name__, "message": str(exc)}, exit_code=1)


if __name__ == "__main__":
    main()
