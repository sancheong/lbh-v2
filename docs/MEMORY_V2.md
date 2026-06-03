# LBH V2 Memory

LBH V2 now uses a passive task-record memory model.

## Core principle

- Memory is a storage layer.
- Codex is the interpreter.
- Memory does not classify, recommend, or auto-plan.

## Stored structure

Memory lives under `memories/task_records.jsonl`.

Each task record contains:

- `user_query`
- `task_description`
- `versions`
- `root_version_id`
- `latest_version_id`
- `latest_success_version_id`

Each version contains:

- `change_summary`
- `change_reason`
- `sequence`
- `run_records`

Each sequence step contains:

- `action_name`
- `status`
- `duration` (seconds)

Each run record contains:

- `status`
- `elapsed_time` (seconds)
- `note`

## Operational flow

1. Run `memory-search` at task start.
2. Read the returned task record summaries.
3. Select a record with `memory-select` when the task matches.
4. Compare the current start state against the record's `success_versions`.
5. Choose the success version that best fits the current state and, if needed, inspect the full history with `memory-record`.
6. Execute and adapt the sequence as needed.
7. Commit the result with `memory-commit`, passing `base_version_id` when a specific success version was used as the draft.

When providing timing fields to `memory-commit`, record them in seconds rather than milliseconds.

## Sequence evolution

- The root version should stay as close as practical to the raw executed trace.
- Later versions may use a refined sequence when Codex is intentionally evolving the draft.
- If the final sequence is unchanged, append only a new run record.
- If the final sequence changed through merge, delete, or add, append a new version.
- Failed executions stay in run history even when the attempted sequence diverged from the latest successful draft.
- The direct parent for a new version is the chosen draft version when `base_version_id` is supplied; otherwise it falls back to the latest successful version.
- The root version is preserved even if it was a failure.
- `memory-search` does not pick a single global best draft. It exposes success-version candidates and leaves the final choice to Codex.

## Semantic failures

`semantic_failure` is not treated as a memory-layer planning rule.

Instead, it is used as a signal that the current sequence is still unstable or hard to confirm.

Codex should use semantic-failure signals to improve the next version by preferring:

- browser-default interactions such as `ctrl+l`, paste, and `enter`
- explicit visible targets over fragile focus traversal
- copy buttons over `ctrl+a` / `ctrl+c` when possible
- steps whose success is easier to confirm from normal GUI evidence

The goal is not to eliminate semantic failures completely. The goal is to evolve toward more stable and more confirmable GUI sequences.
