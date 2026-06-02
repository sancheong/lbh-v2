# Agent Operating Rules

This repository is the **LBH V2 runtime** itself.

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
python -m lbh.cli action --task <task-id> --action-file action.json
```

Dynamic batch:

```powershell
python -m lbh.cli batch --task <task-id> --actions batch.json
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
