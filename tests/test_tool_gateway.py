import json
from types import SimpleNamespace

import pytest

from tools import (
    PermissionDeniedError,
    PermissionPolicy,
    execute_tools_via_gateway,
)
from context import ExecutionContext


def make_tool_call(name, arguments):
    return SimpleNamespace(
        type="function_call",
        name=name,
        arguments=json.dumps(arguments),
        call_id="call-1",
    )


def test_execute_tools_via_gateway_allows_permitted_tool(tmp_path):
    test_context = ExecutionContext(user_id="test_user")
    permission_policy = PermissionPolicy({
        "test_user": {"list_files"},
    })
    (tmp_path / "example.txt").touch()
    test_tool_call = make_tool_call(
        "list_files",
        {"path": str(tmp_path)},
    )

    result = execute_tools_via_gateway(
        test_tool_call,
        test_context,
        permission_policy,
    )

    assert result == "example.txt"


def test_execute_tools_via_gateway_denies_unpermitted_tool(monkeypatch):
    test_context = ExecutionContext(user_id="test_user")
    permission_policy = PermissionPolicy({"test_user": {"read_file"}})
    test_tool_call = make_tool_call("write_file", {})
    executor_called = False

    def fake_execute_tool(tool_call):
        nonlocal executor_called
        executor_called = True

    monkeypatch.setattr("tools.tool_gateway.execute_tool", fake_execute_tool)

    with pytest.raises(PermissionDeniedError):
        execute_tools_via_gateway(
            test_tool_call,
            test_context,
            permission_policy,
        )

    assert executor_called is False


def test_permission_policy_distinguishes_users():
    permission_policy = PermissionPolicy({
        "reader": {"read_file"},
        "writer": {"write_file"},
    })

    assert permission_policy.is_allowed(
        ExecutionContext(user_id="reader"),
        "read_file",
    )
    assert not permission_policy.is_allowed(
        ExecutionContext(user_id="writer"),
        "read_file",
    )


def test_permission_policy_denies_unknown_user():
    permission_policy = PermissionPolicy({
        "known_user": {"list_files"},
    })

    assert not permission_policy.is_allowed(
        ExecutionContext(user_id="unknown_user"),
        "list_files",
    )
