# Using LBH V2 with Codex or another brain

LBH V2 intentionally does not contain the high-level brain. The brain should use the runtime as a tool.

## Basic loop

1. Create task

```powershell
python -m lbh.cli task-new "Ask ChatGPT a short question" --id chatgpt-smoke
```

2. Observe

```powershell
python -m lbh.cli observe --task chatgpt-smoke
```

The result contains:

- `image_path`
- `image_width`
- `image_height`
- `desktop_width`
- `desktop_height`
- scale factors
- active window metadata

3. Ask the brain to propose an action batch

The brain should return JSON like:

```json
{
  "actions": [
    {"type": "click", "point": {"x": 640, "y": 520, "space": "resized_image"}, "reason": "focus composer"},
    {"type": "clipboard_set", "text": "Hello"},
    {"type": "hotkey", "keys": ["ctrl", "v"]},
    {"type": "press", "key": "enter"}
  ],
  "observe_after": true,
  "reason": "Composer is visible and deterministic input can be batched."
}
```

4. Execute batch

```powershell
python -m lbh.cli batch --task chatgpt-smoke --actions actions.json --observe-after
```

5. Repeat until done.

## Locator contract

Use this command to generate a prompt for locating a GUI element:

```powershell
python -m lbh.cli locator-contract --task chatgpt-smoke --target "ChatGPT composer"
```

Codex should inspect the image and return JSON:

```json
{
  "target": "ChatGPT composer",
  "center": {"x": 742, "y": 668, "space": "resized_image"},
  "bbox": {"x1": 421, "y1": 635, "x2": 1051, "y2": 701, "space": "resized_image"},
  "confidence": 0.89,
  "source": "llm",
  "reason": "Large input box at the bottom center."
}
```

Then parse and cache it:

```powershell
python -m lbh.cli locate-parse --task chatgpt-smoke --response-file locator_response.json
```

## Brain policy suggestions

Use atomic actions when:

- the GUI is unfamiliar
- target identity is uncertain
- a modal or permission gate may appear
- action is destructive or irreversible

Use action batches when:

- the active surface is clear
- sequence is deterministic
- next observation checkpoint is obvious
- there is a memory-backed skill candidate

Never ask the model for desktop coordinates. Always use `resized_image` coordinates.
