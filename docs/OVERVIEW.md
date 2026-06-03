# LBH V2 Overview

LBH V2 is a visible-desktop browser runtime for Codex.

## Quick start

```powershell
pip install -r requirements.txt
python -m lbh.cli start "Open Chrome, go to ChatGPT, ask a short question, capture the answer."
python -m lbh.cli observe --task <task-id>
python -m lbh.cli action --task <task-id> --action-file examples\click_resized_point.json
python -m lbh.cli batch --task <task-id> --actions examples\navigate_chatgpt_batch.json
python -m lbh.cli suspend --task <task-id> --reason-code login_required --user-action "Complete the login flow manually, then resume."
python -m lbh.cli resume --task <task-id> --note "The user completed login."
python -m lbh.cli finish --task <task-id> --answer "Captured the visible result."
```

## Known limitations

- GUI execution still depends on Windows desktop state, focus, and z-order.
- The runtime does not replace Codex visual reasoning.
- Locator memory is secondary to screenshot interpretation.
- `wait-stable` is generic image-diff logic, not semantic page understanding.

## V1 parity checklist

- [x] Start tasks
- [x] Observe visible desktop
- [x] Execute primitive actions
- [x] Finish tasks
- [x] Suspend and resume tasks
- [x] Event logging
- [x] Basic progress evaluation

## V2 improvements checklist

- [x] Resized screenshots by default
- [x] Explicit coordinate-space contracts
- [x] Resized-image to desktop conversion
- [x] Dynamic action batches
- [x] Observation not forced after every primitive
- [x] Passive task-record memory
- [x] Task-card memory summaries
- [x] Explicit memory select / record / commit flow
- [x] `wait-stable`
- [x] Benchmark command
- [x] Benchmark report command
- [x] Batch semantic expectations
- [x] Codex-facing prompt contract
