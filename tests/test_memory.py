import json

from lbh.memory import MemoryStore, generate_skill_candidates_from_traces


def test_failure_guard_matching_blocks_repeat(tmp_path):
    store = MemoryStore(memory_dir=tmp_path / "memories")
    guard = {
        "id": "guard-1",
        "situation_signature": "Open Chrome | ChatGPT",
        "situation_tokens": ["open", "chrome", "chatgpt"],
        "bad_action_pattern": "click:left:resized_image",
        "action_fingerprint": "click:left:resized_image",
        "reason": "The same click repeatedly missed.",
        "replacement_suggestion": "Observe again and choose a different target.",
        "support_count": 3,
        "failure_rate": 1.0,
        "confidence": 0.95,
    }
    store.failure_guards_path.write_text(json.dumps(guard) + "\n", encoding="utf-8")
    matches = store.evaluate_failure_guards(
        goal="Open Chrome and continue to ChatGPT.",
        observation={"active_window": {"title": "ChatGPT - Chrome"}},
        action_fingerprints=["click:left:resized_image"],
    )
    assert matches[0]["decision"] == "block"


def test_skill_candidate_generation():
    traces = [
        {"fingerprint": "hotkey:ctrl+l", "duration_ms": 10, "pre_title": "Chrome", "post_title": "Chrome"},
        {"fingerprint": "clipboard_set", "duration_ms": 5, "pre_title": "Chrome", "post_title": "Chrome"},
        {"fingerprint": "hotkey:ctrl+l", "duration_ms": 10, "pre_title": "Chrome", "post_title": "Chrome"},
        {"fingerprint": "clipboard_set", "duration_ms": 5, "pre_title": "Chrome", "post_title": "Chrome"},
    ]
    candidates = generate_skill_candidates_from_traces("Open Chrome.", traces)
    assert candidates
