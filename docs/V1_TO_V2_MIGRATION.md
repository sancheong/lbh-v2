# V1 To V2 Migration

LBH V2 keeps the visible desktop control model from V1, but changes the runtime contract to remove coordinate ambiguity and reduce overhead.

## Command mapping

V2 uses:

```powershell
python -m lbh.cli start "goal text"
python -m lbh.cli observe --task <task-id>
python -m lbh.cli action --task <task-id> --json "{...}"
python -m lbh.cli action --task <task-id> --stdin-json
python -m lbh.cli batch --task <task-id> --json "{...}"
python -m lbh.cli batch --task <task-id> --stdin-json
python -m lbh.cli finish --task <task-id> --answer "..."
```

## What changed

- coordinate system is explicit
- resized screenshots are the default contract
- dynamic batches are first-class
- memory is passive task-record storage with executable low-level GUI drafts
- task storage is cleaner
- low-level mouse primitives include `move_to`, `mouse_down`, `mouse_up`, `drag`, and `scroll`

## How to avoid coordinate mistakes

- Never send raw desktop coordinates for model-located targets.
- Always use `resized_image` points unless the runtime explicitly requests otherwise.
- Observe again before using coordinates from a stale screenshot.
- Let LBH V2 do the conversion to desktop pixels.
