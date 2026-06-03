# LBH V2 Memory

LBH V2 stores memory as JSONL files under `memories/`.

## Memory types

- `episodes.jsonl`
  Summaries of completed tasks, including window-title history, action fingerprints, latency summary, and failure events.
- `failure_guards.jsonl`
  Guard records for semantically failed or repeatedly unproductive action patterns.
- `skills.jsonl`
  Candidate reusable action sequences derived from successful traces and successful batches.
- `locator_memory.jsonl`
  Parsed locator outputs for repeated target finding.

## Guard behavior

- Guards can match a single primitive fingerprint such as `click:left:resized_image`.
- Guards can also match a whole batch sequence such as `sequence:type_text:url -> press:enter`.
- `memory-mode off` disables automatic references.
- `memory-mode warn` returns matches without blocking execution.
- `memory-mode block` blocks high-confidence matches unless overridden.

## Consolidation rules

- Successful batches can create positive skill candidates.
- Semantically failed batches generate failure guard candidates.
- Semantically failed batches do not generate positive skill candidates.
- Non-visual actions such as `clipboard_get` are not treated as failures just because the screen did not change.

## Practical guidance

- If a navigation batch fails semantically, encode the failure as a batch guard and attach a safer replacement pattern.
- Prefer clipboard-based URL navigation so memory can distinguish `type_text:url` failures from `clipboard_set:url` successes.
