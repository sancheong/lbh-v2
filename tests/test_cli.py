from lbh.cli import build_parser


def test_cli_parser_accepts_task_new():
    parser = build_parser()
    args = parser.parse_args(["task-new", "Open Chrome.", "--id", "task-1"])
    assert args.goal == "Open Chrome."
    assert args.id == "task-1"


def test_cli_parser_accepts_batch():
    parser = build_parser()
    args = parser.parse_args(["batch", "--task", "task-1", "--actions", "batch.json"])
    assert args.task == "task-1"
    assert args.actions == "batch.json"


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
