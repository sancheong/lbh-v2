# Migration map from the old desktop-rpa-agent LBH

## Old components

```text
command_router.py local-browser
local_gui_cli.py
rpa_cli.py
local_gui_runner.py
task_cli.py
memory_cli.py
```

## V2 replacements

| Old concept | V2 module | Notes |
|---|---|---|
| `task_cli.py new/log` | `lbh.storage.TaskStore` | Task state and events are first-class. |
| `rpa_cli.py observe-desktop` | `lbh.capture.PyAutoGuiCapture` | Resize is mandatory. |
| `rpa_cli.py click/type/press/hotkey` | `lbh.actions.PyAutoGuiExecutor` | Executor accepts explicit coordinate spaces. |
| `local_gui_cli.py finalize_action` | `lbh.runtime.LBHRuntime` | Observation after action is configurable. |
| `memory_cli.py` | `lbh.memory.MemoryStore` | Memory can block actions and propose skills. |
| `local_gui_runner.py` | future `verify.py` / graph layer | V2 scaffold leaves high-level verification to the controller initially. |

## What should not be migrated directly

- implicit coordinate assumptions
- subprocess-per-primitive action overhead
- automatic observe after every primitive
- natural-language-only memory
- hardcoded ChatGPT macro coordinates as core runtime behavior

## What should be carried forward conceptually

- task folders
- event logs
- screenshot evidence
- suspend/resume idea
- title/image-diff progress checks
- memory-driven improvement
