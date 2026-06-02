# LBH V2 — Local Browser Harness Runtime

LBH V2 is a clean-room rebuild scaffold for the **Local Browser Harness** part of the previous `desktop-rpa-agent` repository.

It deliberately focuses on the LBH core only:

- visible desktop screenshot capture
- enforced screenshot resizing
- explicit coordinate-space conversion
- atomic GUI actions
- dynamic action batches
- action/result event logs
- memory for failure guards and reusable skills
- task folders and reproducible traces

It intentionally does **not** include Playwright/CDP/browser DOM automation. The design target is still:

```text
desktop screenshot -> model/Codex interpretation -> pyautogui action -> log
```

## Why V2 exists

The previous LBH prototype proved the idea, but mixed too many responsibilities:

- screenshot capture and coordinate conversion were implicit
- resized screenshot support existed but was not enforced end-to-end
- every primitive action triggered expensive observe/evaluate cycles
- memory was mostly natural-language lesson storage, not action control
- repeated failures were not reliably prevented

V2 treats LBH as a runtime with explicit contracts.

## Core principles

### 1. Enforced resizing

The model never receives raw full-resolution desktop screenshots by default.

```text
desktop screenshot -> resized image -> model returns resized-image coordinates -> runtime converts to desktop coordinates
```

Default:

```yaml
model_max_width: 1280
jpeg_quality: 75
model_output_space: resized_image
action_input_space: desktop
```

### 2. Coordinates are never implicit

All points and bounding boxes carry a `space` field:

```json
{"x": 640, "y": 520, "space": "resized_image"}
```

The executor only clicks desktop-space coordinates.

### 3. Primitive actions remain available

LBH V2 keeps atomic actions:

- click
- double_click
- type_text
- press
- hotkey
- wait
- clipboard_set
- window_activate

### 4. Speed comes from dynamic batches, not hardcoded phases

Instead of hardcoding every workflow as a phase, the brain can propose an action batch up to the next observation checkpoint:

```json
{
  "actions": [
    {"type": "hotkey", "keys": ["ctrl", "l"]},
    {"type": "clipboard_set", "text": "https://chatgpt.com"},
    {"type": "hotkey", "keys": ["ctrl", "v"]},
    {"type": "press", "key": "enter"},
    {"type": "wait", "seconds": 3}
  ],
  "observe_after": true
}
```

This preserves flexibility while avoiding a full observe after every primitive action.

### 5. Memory must affect execution

V2 memory is not just a note store. It has control roles:

- **Episode memory**: full traces
- **Failure guards**: veto or warn about repeated bad actions
- **Locator memory**: reusable element-location hints
- **Skill memory**: successful atomic action sequences that can be proposed as reusable batches

## Quick start

Install dependencies in a Windows environment:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

Create a task:

```powershell
python -m lbh.cli task-new "Open Chrome and ask ChatGPT a short question"
```

Observe desktop:

```powershell
python -m lbh.cli observe --task tasks\<task-id>
```

Execute a batch from JSON:

```powershell
python -m lbh.cli batch --task tasks\<task-id> --actions actions.json --observe-after
```

Generate a locator prompt contract for Codex/LLM:

```powershell
python -m lbh.cli locator-contract --task tasks\<task-id> --target "ChatGPT composer"
```

## Status

This ZIP is a V2 scaffold, not a fully tuned production agent. The runtime, coordinate contract, task logging, action executor, and memory schema are implemented. The actual high-level brain is intentionally left outside: Codex, LangGraph, or another LLM controller should call this runtime through the JSON contracts.
