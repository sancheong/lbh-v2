# ChatGPT Smoke Task With LBH V2

This is a smoke flow for **using LBH V2**, not a hardcoded ChatGPT-only implementation.

## Goal

1. Open Chrome.
2. Navigate to `https://chatgpt.com`.
3. Ask a short question.
4. Wait until the screen appears stable.
5. Copy or capture the answer.
6. Finish the task.

## Start

```powershell
python -m lbh.cli start "Open Chrome, go to ChatGPT, ask a short question, capture the answer."
python -m lbh.cli observe --task <task-id>
```

## Recommended flow

Open Chrome:

- Observe the desktop.
- If the Chrome icon or taskbar slot is clearly visible, send a single `click` or `double_click`.
- Re-observe because the first launch target is visually uncertain.

Navigate to ChatGPT:

```powershell
python -m lbh.cli batch --task <task-id> --actions examples\navigate_chatgpt_batch.json
```

The navigation batch should include an explicit expectation so that a search-results detour is reported as `semantic_failure` instead of `success`.

Ask the question:

- Re-observe after navigation.
- Click the composer with `resized_image` coordinates if it is clearly visible.
- Prefer `clipboard_set` + `ctrl+v` for prompts instead of `type_text`.
- Re-observe before sending if the state is still uncertain.

Wait for the answer without repeated LLM checks:

```powershell
python -m lbh.cli wait-stable --task <task-id> --seconds 3 --timeout 60
```

Finish:

```powershell
python -m lbh.cli finish --task <task-id> --answer "Captured the ChatGPT answer and verified the visible response."
```

## When to suspend

- login or re-authentication
- 2FA
- CAPTCHA
- permissions prompts
- uncertain account switching
- billing or subscription flows
