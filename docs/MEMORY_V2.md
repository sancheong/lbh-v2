# LBH V2 Memory

LBH V2 now uses a passive task-record memory model.

This document describes the memory structure and its invariants.
For required operational workflow, see [AGENTS.md](C:/developer/lbh_v2/AGENTS.md).
For detailed runtime decision guidance, see [docs/CODEX_LBH_V2_SYSTEM_PROMPT.md](C:/developer/lbh_v2/docs/CODEX_LBH_V2_SYSTEM_PROMPT.md).

## Core principle

- Memory is a storage layer.
- Codex is the interpreter.
- Memory does not classify, recommend, or auto-plan.
- Memory preserves enough executable draft context for Codex to make the next planning decision without rebuilding the whole trace from raw history.

## Stored structure

Memory lives under `memories/task_records.jsonl`.
Legacy `episodes.jsonl`, `failure_guards.jsonl`, and `skills.jsonl` files are retired and should not be recreated for normal task-record memory.

Each task record contains:

- `task_type`
- `user_query`
- `task_description`
- `parameter_schema`
- `start_state_requirements`
- `optimization_summary`
- `versions`
- `root_version_id`
- `latest_version_id`
- `latest_success_version_id`

Each version contains:

- `change_summary`
- `change_reason`
- `sequence`
- `draft_sequence`
- `run_records`

Each sequence step contains:

- `action_name`
- `status`
- `duration` (seconds)

Each draft sequence step contains:

- `type` (`batch`, `action`, or `wait_stable`)
- `status`
- `duration` (seconds)
- `payload` for executable `batch` and `action` steps, including coordinates, text, expectations, and `observe_after` policy when available
- `semantic_reason` when the draft step came from a semantically evaluated action or batch
- optional notes for Codex-only interpretation, such as replacing parameter placeholders before execution

Each run record contains:

- `status`
- `elapsed_time` (seconds)
- `note`

Task-type metadata is advisory but should be concrete enough to reduce planning time:

- `task_type` is a stable identifier for matching similar user goals.
- `parameter_schema` names values Codex must substitute before executing the draft.
- `start_state_requirements` tells Codex when the draft is safe to use.
- `optimization_summary` records which historical costs were removed and which metrics improved.

## Sequence evolution

- The root version should stay as close as practical to the raw executed trace.
- Later versions may use a refined sequence when Codex is intentionally evolving the draft.
- `sequence` is the compact raw fingerprint trace used for compatibility and equality checks.
- `draft_sequence` is the Codex-facing executable planning substrate. It should keep batch boundaries, action payloads, expectations, and semantic reasons.
- Optimized memory should favor one short deterministic low-level GUI path per task type over many historical variants.
- Do not store fallback branches, modal retries, DOM automation, DevTools routes, or file-system edits as executable memory drafts.
- If a variable value is needed, store an obvious placeholder such as `{{repo_name}}`; Codex must substitute it before execution.
- If the final sequence is unchanged, append only a new run record.
- If the final sequence or executable draft changed through merge, delete, or add, append a new version.
- Failed executions stay in run history even when the attempted sequence diverged from the latest successful draft.
- The direct parent for a new version is the chosen draft version when `base_version_id` is supplied; otherwise it falls back to the latest successful version.
- The root version is preserved even if it was a failure.
- `memory-search` does not pick a single global best draft. It exposes success-version candidates and leaves the final choice to Codex.
- A successful version that used `type_text` to enter prompt text should be treated as lower-quality than a clipboard-paste based prompt path, because IME/input corruption risk is higher.
- Timing fields stored through `memory-commit` are in seconds, not milliseconds.

## Semantic failures

`semantic_failure` is not treated as a memory-layer planning rule.

Instead, it is used as a signal that the current sequence is still unstable or hard to confirm.

Codex should use semantic-failure signals to improve the next `draft_sequence` by preferring:

- browser-default interactions such as `ctrl+l`, paste, and `enter`
- explicit visible targets over fragile focus traversal
- copy buttons over `ctrl+a` / `ctrl+c` when possible
- direct profile-specific launch commands through the GUI when they remove repeated profile chooser and navigation steps
- steps whose success is easier to confirm from normal GUI evidence

The goal is not to eliminate semantic failures completely. The goal is to evolve toward more stable and more confirmable GUI sequences.
