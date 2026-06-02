# LBH V2 Design

## Scope

LBH V2 rebuilds only the Local Browser Harness core from the previous prototype.

It is not a ChatGPT patch workflow, not a browser DOM automation layer, and not a full Codex replacement. It is a strict desktop GUI runtime that an external brain can drive.

## Old LBH problem summary

The previous LBH had these effective behaviors:

```text
command_router.py local-browser
→ local_gui_cli.py start/observe/click/type/press/hotkey
→ rpa_cli.py pyautogui execution
→ local_gui_runner.py progress evaluation
→ memory_cli.py lesson storage
```

That prototype was useful, but several responsibilities leaked across boundaries:

- capture and action execution were both exposed through CLI subprocesses
- coordinate spaces were not first-class values
- resizing was optional and not end-to-end safe
- every primitive action triggered full observe/evaluate
- memory rarely changed future behavior
- repeated failure patterns were stored as natural language but not enforced

## V2 architecture

```text
External brain: Codex / LangGraph / LLM controller
          │
          ▼
LBH Runtime API / CLI
          │
          ├─ Capture Layer
          │   screenshot -> forced resize -> observation JSON
          │
          ├─ Coordinate Layer
          │   resized_image / crop_image -> desktop transforms
          │
          ├─ Action Layer
          │   pyautogui primitive actions only
          │
          ├─ Batch Layer
          │   dynamically generated primitive sequences
          │
          ├─ Memory Layer
          │   failure guards / skill candidates / episode traces
          │
          └─ Storage Layer
              task state, screenshots, events.jsonl, locator cache
```

## Coordinate contract

All model-visible screenshots use `resized_image` space.

The model must return:

```json
{
  "center": {"x": 640, "y": 520, "space": "resized_image"},
  "confidence": 0.86
}
```

The runtime then converts to desktop space:

```python
desktop_x = round(image_x * desktop_width / image_width)
desktop_y = round(image_y * desktop_height / image_height)
```

The executor never clicks `resized_image` coordinates directly.

## Dynamic action batches

V2 does not require pre-authored phases. Instead, it supports dynamic action batches created by the brain at runtime.

Example:

```json
{
  "actions": [
    {"type": "hotkey", "keys": ["ctrl", "l"]},
    {"type": "clipboard_set", "text": "https://chatgpt.com"},
    {"type": "hotkey", "keys": ["ctrl", "v"]},
    {"type": "press", "key": "enter"},
    {"type": "wait", "seconds": 3}
  ],
  "observe_after": true,
  "reason": "Chrome is active; URL navigation is deterministic until page load."
}
```

This keeps primitive flexibility while reducing the number of expensive observation checkpoints.

## Memory design

V2 memory is control-oriented.

### Episode memory

Stores what actually happened:

- situation signature
- action batch
- outcome
- latency
- before/after observations

### Failure guards

Prevent repeated bad actions. A failure guard can block a proposed action batch before execution.

### Skill memory

Stores repeated successful action sequences as candidates. Skills are not automatically trusted forever; they are proposed based on preconditions and statistics.

### Locator memory

Caches target coordinates for the same screenshot hash and active window title.

## Recommended controller loop

```text
observe
→ retrieve memory
→ brain proposes atomic action or action batch
→ memory guard checks proposal
→ execute
→ observe after checkpoint
→ verify
→ record episode
→ optionally consolidate skills
```

## Why not hardcode ChatGPT phases?

Some repeated workflows can become skills, but V2 should not start by hardcoding every phase. The external brain should remain able to handle unknown GUI states with primitives.

The progression is:

```text
primitive actions
→ dynamic batches
→ skill candidates
→ approved reusable skills
```
