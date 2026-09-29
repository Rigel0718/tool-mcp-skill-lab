import logging
from types import SimpleNamespace

from tools.code_tools import read_file, run_command


def test_run_command_executes_without_interactive_approval(monkeypatch):
    completed = SimpleNamespace(stdout="ok\n", stderr="", returncode=0)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("run_command must not request approval")

    monkeypatch.setattr("builtins.input", fail_if_called)
    monkeypatch.setattr(
        "tools.code_tools.subprocess.run",
        lambda *args, **kwargs: completed,
    )

    assert run_command("git status") == "ok"


def test_read_file_logs_debug_processing(tmp_path, caplog):
    path = tmp_path / "example.txt"
    path.write_text("hello", encoding="utf-8")

    with caplog.at_level(logging.DEBUG, logger="tools.code_tools"):
        assert read_file(path) == "hello"

    messages = [record.getMessage() for record in caplog.records]
    assert messages == [
        f"reading file path={path}",
        f"finished reading file path={path} characters=5",
    ]


def test_read_file_debug_logs_are_hidden_at_info_level(tmp_path, caplog):
    path = tmp_path / "example.txt"
    path.write_text("hello", encoding="utf-8")

    with caplog.at_level(logging.INFO, logger="tools.code_tools"):
        assert read_file(path) == "hello"

    assert not caplog.records
