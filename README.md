# LBH V2

LBH V2 is a visible-desktop browser runtime for Codex.

The core loop is:

```text
desktop screenshot -> Codex interpretation -> desktop GUI action -> log
```

This repository provides:

- `python -m lbh.cli` entrypoint for Codex routing
- resized screenshots by default
- explicit coordinate-space contracts
- primitive GUI actions
- dynamic action batches
- task lifecycle commands
- actionable memory guards and skill candidates
- wait-stable and benchmark utilities

## Quick start

```powershell
pip install -r requirements.txt
python -m lbh.cli start "Open Chrome, go to ChatGPT, ask a short question, capture the answer."
python -m lbh.cli observe --task <task-id>
python -m lbh.cli action --task <task-id> --action-file examples\click_resized_point.json
python -m lbh.cli batch --task <task-id> --actions examples\navigate_chatgpt_batch.json
```

## Important paths

- [docs/CODEX_LBH_V2_SYSTEM_PROMPT.md](docs/CODEX_LBH_V2_SYSTEM_PROMPT.md)
- [docs/CHATGPT_SMOKE_TASK.md](docs/CHATGPT_SMOKE_TASK.md)
- [docs/BENCHMARKING.md](docs/BENCHMARKING.md)
- [docs/V1_TO_V2_MIGRATION.md](docs/V1_TO_V2_MIGRATION.md)

## Commands

- `start` and `task-new`
- `observe`
- `action`
- `batch`
- `finish`
- `suspend`
- `resume`
- `status`
- `memory-search`
- `wait-stable`
- `benchmark`
- `locator-contract`
- `locate-parse`
- `skills`
