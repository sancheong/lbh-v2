# LBH V2 Benchmarking

LBH V2 is designed to be faster than V1 by reducing unnecessary screenshot, LLM, and action overhead.

## Why V2 should be faster

- Screenshots are resized by default.
- Coordinates are converted explicitly instead of relying on ad hoc click helpers.
- Dynamic batches reduce full observe/evaluate cycles between deterministic primitives.
- `wait-stable` avoids asking the model whether a page has stopped moving.
- Passive task-record memory reduces repeated rediscovery when a stable successful version already exists.
- Optimized `draft_sequence` records reduce profile chooser, duplicate navigation, and per-click observation checkpoints.
- Low-level `scroll` and `drag` primitives avoid substituting high-level browser automation when a GUI movement is deterministic.

## Benchmark command

```powershell
python -m lbh.cli benchmark --task <task-id>
python -m lbh.cli benchmark --task <task-id> --action-json examples\click_resized_point.json
python -m lbh.cli benchmark --task <task-id> --batch-json examples\navigate_chatgpt_batch.json --stable-seconds 3 --timeout 60
python -m lbh.cli benchmark-report --task <task-id>
```

## Reported metrics

- screenshot width and height
- screenshot byte size
- coordinate transform overhead
- primitive action timing when supplied
- batch timing when supplied
- `wait-stable` timing when requested

## Benchmark report fields

- total task wall-clock time
- observation count and total observation time
- primitive action count and total action time
- batch count and total batch time
- approximate Codex decision points from observation count
- failed or semantically failed event count
- sequence improvement signals derived from semantic failures
- recovery count after failures
- memory consolidation time
- screenshot byte sizes
- most expensive events

## Recommended usage

- Use explicit expectations on navigation and submit batches so semantic failures show up in the report.
- Treat semantic failures in the report as sequence-improvement signals, not as proof that the entire task failed.
- Use `wait-stable` instead of repeated visual checks when waiting for navigation or response completion.
- Prefer clipboard paste for URLs and long prompts to avoid IME-related recovery loops.
- Compare `planning_summary.draft_action_count` and `planning_summary.observation_checkpoints` before and after memory consolidation.
