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
