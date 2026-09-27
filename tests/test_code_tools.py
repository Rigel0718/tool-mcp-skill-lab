from types import SimpleNamespace

from tools.code_tools import run_command


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
