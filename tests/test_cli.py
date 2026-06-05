from lbh.cli import build_parser


def test_cli_parser_accepts_task_new():
    parser = build_parser()
    args = parser.parse_args(["task-new", "Open Chrome.", "--id", "task-1"])
    assert args.goal == "Open Chrome."
    assert args.id == "task-1"


def test_cli_parser_accepts_batch():
    parser = build_parser()
    args = parser.parse_args(["batch", "--task", "task-1", "--json", "{\"actions\":[{\"type\":\"press\",\"key\":\"enter\",\"reason\":\"Continue.\"}]}"])
    assert args.task == "task-1"
    assert args.json


def test_cli_parser_accepts_benchmark_report_and_memory_mode():
    parser = build_parser()
    args = parser.parse_args(["benchmark-report", "--task", "task-1", "--top", "3", "--memory-mode", "warn"])
    assert args.task == "task-1"
    assert args.top == 3
    assert args.memory_mode == "warn"


def test_cli_parser_accepts_memory_commit():
    parser = build_parser()
    args = parser.parse_args(["memory-commit", "--task", "task-1", "--memory-json", "{\"run_status\":\"success\"}"])
    assert args.task == "task-1"
    assert args.memory_json == "{\"run_status\":\"success\"}"


def test_cli_parser_accepts_stdin_json_for_action_batch_and_memory_commit():
    parser = build_parser()

    action_args = parser.parse_args(["action", "--task", "task-1", "--stdin-json"])
    batch_args = parser.parse_args(["batch", "--task", "task-1", "--stdin-json"])
    memory_args = parser.parse_args(["memory-commit", "--task", "task-1", "--stdin-json"])

    assert action_args.stdin_json is True
    assert batch_args.stdin_json is True
    assert memory_args.stdin_json is True


def test_cli_parser_accepts_memory_record_and_select():
    parser = build_parser()

    record_args = parser.parse_args(["memory-record", "--task", "task-1", "--record-id", "taskmem-123"])
    select_args = parser.parse_args(["memory-select", "--task", "task-1", "--record-id", "taskmem-123"])

    assert record_args.task == "task-1"
    assert record_args.record_id == "taskmem-123"
    assert select_args.task == "task-1"
    assert select_args.record_id == "taskmem-123"
