import json
from types import SimpleNamespace

import pytest

from approval_config import AUTO_APPROVED_COMMANDS
from context import ExecutionContext
from tools import ApprovalPolicy


@pytest.fixture
def approval_policy():
    return ApprovalPolicy(AUTO_APPROVED_COMMANDS)


@pytest.fixture
def context():
    return ExecutionContext(user_id="test_user")


def make_tool_call(name, arguments):
    return SimpleNamespace(name=name, arguments=json.dumps(arguments))


@pytest.mark.parametrize("tool_name", ["list_files", "read_file"])
def test_read_only_tools_do_not_require_approval(
    approval_policy,
    context,
    tool_name,
):
    tool_call = make_tool_call(tool_name, {"path": "example.txt"})

    assert not approval_policy.requires_approval(context, tool_call)


def test_new_file_does_not_require_approval(
    approval_policy,
    context,
    tmp_path,
):
    tool_call = make_tool_call(
        "write_file",
        {"path": str(tmp_path / "new.txt"), "content": "new"},
    )

    assert not approval_policy.requires_approval(context, tool_call)


def test_existing_path_requires_approval(
    approval_policy,
    context,
    tmp_path,
):
    existing_file = tmp_path / "existing.txt"
    existing_file.write_text("existing", encoding="utf-8")
    tool_call = make_tool_call(
        "write_file",
        {"path": str(existing_file), "content": "replacement"},
    )

    assert approval_policy.requires_approval(context, tool_call)


def test_relative_write_path_uses_process_working_directory(
    approval_policy,
    context,
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "existing.txt").touch()
    tool_call = make_tool_call(
        "write_file",
        {"path": "existing.txt", "content": "replacement"},
    )

    assert approval_policy.requires_approval(context, tool_call)


@pytest.mark.parametrize(
    "command",
    [
        "git status",
        "git status --short",
        "git diff",
        "git diff --staged",
        "git log",
        "git log --oneline",
        "pytest",
        "pytest tests/",
        "pytest -v",
    ],
)
def test_allowlisted_commands_do_not_require_approval(
    approval_policy,
    context,
    command,
):
    tool_call = make_tool_call("run_command", {"command": command})

    assert not approval_policy.requires_approval(context, tool_call)


@pytest.mark.parametrize(
    "command",
    [
        "git checkout -- example.txt",
        "git reset --hard",
        "rm example.txt",
        "python -m pytest",
        "git status && rm example.txt",
        "pytest; rm example.txt",
        "pytest $(rm example.txt)",
        "pytest > result.txt",
        "pytest 2>> errors.txt",
        "pytest\nrm example.txt",
    ],
)
def test_non_allowlisted_or_compound_commands_require_approval(
    approval_policy,
    context,
    command,
):
    tool_call = make_tool_call("run_command", {"command": command})

    assert approval_policy.requires_approval(context, tool_call)


def test_allowlist_can_be_changed_without_changing_policy(context):
    approval_policy = ApprovalPolicy({"ruff": None, "git": {"branch"}})

    assert not approval_policy.requires_approval(
        context,
        make_tool_call("run_command", {"command": "ruff check ."}),
    )
    assert not approval_policy.requires_approval(
        context,
        make_tool_call("run_command", {"command": "git branch --show-current"}),
    )
    assert approval_policy.requires_approval(
        context,
        make_tool_call("run_command", {"command": "git status"}),
    )


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("write_file", "{invalid"),
        ("write_file", json.dumps({"content": "missing path"})),
        ("write_file", json.dumps({"path": "missing content"})),
        (
            "write_file",
            json.dumps({"path": "new", "content": "new", "extra": True}),
        ),
        ("run_command", "{invalid"),
        ("run_command", json.dumps({})),
        ("run_command", json.dumps({"command": "pytest", "extra": True})),
    ],
)
def test_invalid_arguments_are_left_for_executor_validation(
    approval_policy,
    context,
    name,
    arguments,
):
    tool_call = SimpleNamespace(name=name, arguments=arguments)

    assert not approval_policy.requires_approval(context, tool_call)


def test_unknown_tool_requires_approval(approval_policy, context):
    tool_call = make_tool_call("unknown_tool", {})

    assert approval_policy.requires_approval(context, tool_call)
