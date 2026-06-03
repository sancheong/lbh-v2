# LBH V2 Semantic Expectations

Semantic expectations let a primitive action or dynamic batch fail even when the raw OS primitives executed correctly.

## Supported fields

- `title_contains_any`
- `title_contains_all`
- `title_not_contains_any`
- `forbidden_title_contains_any`
- `require_changed`
- `allow_no_visual_change`
- `visual_change_expected`
- `success_hints_any`
- `failure_hints_any`
- `expected_clipboard_contains`
- `expected_clipboard_equals`
- `image_diff_threshold`

## Navigation example

```json
{
  "observe_after": true,
  "expectation": {
    "title_contains_any": ["ChatGPT"],
    "title_not_contains_any": ["Google Search", "Search"],
    "require_changed": true
  },
  "actions": [
    {"type": "hotkey", "keys": ["ctrl", "l"], "reason": "Focus address bar"},
    {"type": "clipboard_set", "text": "https://chatgpt.com", "reason": "Prepare URL"},
    {"type": "hotkey", "keys": ["ctrl", "v"], "reason": "Paste URL"},
    {"type": "press", "key": "enter", "reason": "Navigate"},
    {"type": "wait", "seconds": 3, "reason": "Allow navigation"}
  ]
}
```

If the final title is a search page, the batch becomes `semantic_failure`.

That does not automatically mean the whole task failed. In LBH V2, mid-task semantic failures are treated as sequence-improvement signals when the final task can still be recovered.

## Non-visual actions

- `clipboard_set`
- `clipboard_get`
- `wait`

These actions can succeed without any visible screen change. Do not require visual change for them unless you have an explicit reason.

## Submit example

```json
{
  "observe_after": true,
  "expectation": {
    "require_changed": true,
    "allow_no_visual_change": false
  },
  "actions": [
    {"type": "clipboard_set", "text": "Reply with exactly OK.", "reason": "Prepare prompt"},
    {"type": "click", "point": {"x": 640, "y": 690, "space": "resized_image"}, "reason": "Focus composer"},
    {"type": "hotkey", "keys": ["ctrl", "v"], "reason": "Paste prompt"},
    {"type": "press", "key": "enter", "reason": "Submit prompt"}
  ]
}
```

## Principle

- Primitive execution success is not semantic success.
- Screen change alone is not semantic success.
- Explicit expectations should be attached whenever the next visible state matters.
- A semantic failure in the middle of a task should usually push Codex toward a more confirmable next version, not toward special-case memory rules.
- Prefer GUI and browser common sense when reducing semantic failures:
  - paste for URLs and long text
  - explicit clicks over fragile focus traversal
  - browser-provided copy controls over generic select-all copying
