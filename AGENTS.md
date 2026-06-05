# Agent Operating Rules

This repository is the **LBH V2 runtime** itself.

`AGENTS.md` is the primary execution contract for agents working in this repo.
Follow it first.

For detailed action-selection guidance, see [docs/CODEX_LBH_V2_SYSTEM_PROMPT.md](C:/developer/lbh_v2/docs/CODEX_LBH_V2_SYSTEM_PROMPT.md).
For memory schema details, see [docs/MEMORY_V2.md](C:/developer/lbh_v2/docs/MEMORY_V2.md).

## Default route

When the user asks for any of the following in this workspace:

- `LBH`
- `LBH V2`
- `local browser harness`
- `local-browser-harness`
- `local Chrome`
- `browser subagent`

use this repository's runtime:

```powershell
python -m lbh.cli ...
```

Do not switch to another repository for those requests unless the user explicitly asks for:

- a legacy harness
- `desktop-rpa-agent`
- V1 behavior

## Do not substitute other browser tools

For LBH requests in this repo:

- do not use the Codex in-app Browser plugin
- do not use Playwright or DOM automation
- do not use Selenium
- do not use browser DevTools protocols as the primary control path

The required control loop is:

```text
desktop screenshot -> model interpretation -> GUI action -> log -> observe/evaluate
```

## Required task-start checklist

Before the first meaningful `action` or `batch` on a task:

1. Run `memory-search`.
2. If a matching task record exists, run `memory-select`.
3. If the task record matters for execution planning, run `memory-record`.
4. Compare the current start state against available `success_versions`.
5. Decide which success version, if any, will be used as the draft for this run.

Do not skip this loop and improvise from scratch when relevant memory exists.

## Required task-end checklist

Before considering the task complete:

1. Decide whether the final sequence matches an existing version or evolved from a specific success version.
2. Run `memory-commit`.
3. If a specific success version was the draft, pass `base_version_id`.
4. Run `finish` once the final result is actually captured.

Do not leave the task in memory without explicitly closing the task lifecycle unless the task must remain open.

## Input and payload rules

- Prefer inline `--json` / `--memory-json` payloads or `--stdin-json`.
- Do not create scratch JSON files for one-off command payloads unless there is no reasonable alternative.
- Prefer `clipboard_set` + `ctrl+v` for URLs.
- Prefer `clipboard_set` + `ctrl+v` for prompt text and other meaningful text entry.
- Do not use `type_text` for URLs unless paste is unavailable and the risk is acceptable.
- Treat prompt submission via `type_text` as lower quality than clipboard-paste submission.

## Canonical commands

Start a task:

```powershell
python -m lbh.cli start "goal text"
```

Observe:

```powershell
python -m lbh.cli observe --task <task-id>
```

Primitive action:

```powershell
python -m lbh.cli action --task <task-id> --json "{...}"
python -m lbh.cli action --task <task-id> --stdin-json
```

Dynamic batch:

```powershell
python -m lbh.cli batch --task <task-id> --json "{...}"
python -m lbh.cli batch --task <task-id> --stdin-json
```

Memory workflow:

```powershell
python -m lbh.cli memory-search --task <task-id>
python -m lbh.cli memory-select --task <task-id> --record-id <record-id>
python -m lbh.cli memory-record --task <task-id> --record-id <record-id>
python -m lbh.cli memory-commit --task <task-id> --memory-json "{...}"
python -m lbh.cli memory-commit --task <task-id> --stdin-json
```

Finish or suspend:

```powershell
python -m lbh.cli finish --task <task-id> --answer "short result"
python -m lbh.cli suspend --task <task-id> --reason-code login_required --user-action "Complete the manual step, then resume."
python -m lbh.cli resume --task <task-id> --note "The manual step is complete."
```

## Coordinate rule

Model-produced coordinates must be in `resized_image` space unless the runtime explicitly asks for another space.

Do not ask the model to return desktop coordinates directly.
