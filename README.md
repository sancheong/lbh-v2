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
- semantic expectations for actions and batches
- task lifecycle commands
- actionable memory guards and skill candidates
- wait-stable and benchmark utilities
- benchmark reporting for latency breakdowns

## Quick start

```powershell
pip install -r requirements.txt
python -m lbh.cli start "Open Chrome, go to ChatGPT, ask a short question, capture the answer."
python -m lbh.cli observe --task <task-id>
python -m lbh.cli action --task <task-id> --action-file examples\click_resized_point.json
python -m lbh.cli batch --task <task-id> --actions examples\navigate_chatgpt_batch.json
python -m lbh.cli wait-stable --task <task-id> --seconds 3 --timeout 60
python -m lbh.cli benchmark-report --task <task-id>
```

## Important paths

- [docs/CODEX_LBH_V2_SYSTEM_PROMPT.md](docs/CODEX_LBH_V2_SYSTEM_PROMPT.md)
- [docs/CHATGPT_SMOKE_TASK.md](docs/CHATGPT_SMOKE_TASK.md)
- [docs/BENCHMARKING.md](docs/BENCHMARKING.md)
- [docs/MEMORY_V2.md](docs/MEMORY_V2.md)
- [docs/SEMANTIC_EXPECTATIONS.md](docs/SEMANTIC_EXPECTATIONS.md)
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
- `benchmark-report`
- `locator-contract`
- `locate-parse`
- `skills`
