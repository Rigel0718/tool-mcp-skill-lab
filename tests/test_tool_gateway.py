import json
import logging
from types import SimpleNamespace

import pytest

from tools import (
    ApprovalPolicy,
    ApprovalRequiredError,
    PermissionDeniedError,
    PermissionPolicy,
    ToolArgumentsError,
    ToolExecutionError,
    execute_approved_tool_via_gateway,
    execute_tools_via_gateway,
)
from approval_config import AUTO_APPROVED_COMMANDS
from context import ExecutionContext
from hitl import ApprovalRequest, ApprovalStatus


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
    approval_policy = ApprovalPolicy(AUTO_APPROVED_COMMANDS)
    (tmp_path / "example.txt").touch()
    test_tool_call = make_tool_call(
        "list_files",
        {"path": str(tmp_path)},
    )

    result = execute_tools_via_gateway(
        test_tool_call,
        test_context,
        permission_policy,
        approval_policy,
    )

    assert result == "example.txt"


def test_gateway_logs_start_and_success_with_execution_context(
    tmp_path,
    caplog,
):
    context = ExecutionContext(user_id="test_user", run_id="run-123")
    permission_policy = PermissionPolicy({"test_user": {"list_files"}})
    approval_policy = ApprovalPolicy(AUTO_APPROVED_COMMANDS)
    tool_call = make_tool_call("list_files", {"path": str(tmp_path)})

    with caplog.at_level(logging.INFO, logger="tools.tool_gateway"):
        execute_tools_via_gateway(
            tool_call,
            context,
            permission_policy,
            approval_policy,
        )

    gateway_messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == "tools.tool_gateway"
    ]
    assert len(gateway_messages) == 2
    assert "result=started" in gateway_messages[0]
    assert "result=success" in gateway_messages[1]
    for message in gateway_messages:
        assert "user_id=test_user" in message
        assert "run_id=run-123" in message
        assert "call_id=call-1" in message
        assert "tool_name=list_files" in message


def test_gateway_logs_failed_without_error_details(monkeypatch, caplog):
    context = ExecutionContext(user_id="test_user", run_id="run-123")
    tool_call = make_tool_call("read_file", {"path": "missing.txt"})

    def fail_execution(received_call):
        raise ToolExecutionError("sensitive executor detail")

    monkeypatch.setattr("tools.tool_gateway.execute_tool", fail_execution)

    with caplog.at_level(logging.INFO, logger="tools.tool_gateway"):
        with pytest.raises(ToolExecutionError):
            execute_tools_via_gateway(
                tool_call,
                context,
                PermissionPolicy({"test_user": {"read_file"}}),
                ApprovalPolicy(AUTO_APPROVED_COMMANDS),
            )

    gateway_records = [
        record
        for record in caplog.records
        if record.name == "tools.tool_gateway"
    ]
    assert [record.levelno for record in gateway_records] == [
        logging.INFO,
        logging.INFO,
    ]
    assert "result=failed" in gateway_records[-1].getMessage()
    assert "sensitive executor detail" not in gateway_records[-1].getMessage()


def test_permission_and_approval_are_info_policy_outcomes(tmp_path, caplog):
    context = ExecutionContext(user_id="test_user", run_id="run-123")
    denied_call = make_tool_call("read_file", {"path": "example.txt"})
    existing_file = tmp_path / "existing.txt"
    existing_file.write_text("existing", encoding="utf-8")
    approval_call = make_tool_call(
        "write_file",
        {"path": str(existing_file), "content": "replacement"},
    )

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(PermissionDeniedError):
            execute_tools_via_gateway(
                denied_call,
                context,
                PermissionPolicy({"test_user": set()}),
                ApprovalPolicy(AUTO_APPROVED_COMMANDS),
            )
        with pytest.raises(ApprovalRequiredError):
            execute_tools_via_gateway(
                approval_call,
                context,
                PermissionPolicy({"test_user": {"write_file"}}),
                ApprovalPolicy(AUTO_APPROVED_COMMANDS),
            )

    messages = [record.getMessage() for record in caplog.records]
    assert any("result=permission_denied" in message for message in messages)
    assert any("result=approval_required" in message for message in messages)
    assert not any(record.levelno >= logging.ERROR for record in caplog.records)


def test_executor_error_detail_is_logged_once_across_gateway(caplog):
    context = ExecutionContext(user_id="test_user", run_id="run-123")
    tool_call = SimpleNamespace(
        name="list_files",
        arguments="{invalid",
        call_id="call-1",
    )

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(ToolArgumentsError):
            execute_tools_via_gateway(
                tool_call,
                context,
                PermissionPolicy({"test_user": {"list_files"}}),
                ApprovalPolicy(AUTO_APPROVED_COMMANDS),
            )

    error_records = [
        record for record in caplog.records if record.levelno == logging.ERROR
    ]
    assert len(error_records) == 1
    assert error_records[0].name == "tools.tool_executor"
    assert "error_type=ToolArgumentsError" in error_records[0].getMessage()
    assert any(
        record.name == "tools.tool_gateway"
        and "result=failed" in record.getMessage()
        for record in caplog.records
    )


def test_execute_tools_via_gateway_denies_unpermitted_tool(monkeypatch):
    test_context = ExecutionContext(user_id="test_user")
    permission_policy = PermissionPolicy({"test_user": {"read_file"}})
    approval_policy = ApprovalPolicy(AUTO_APPROVED_COMMANDS)
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
            approval_policy,
        )

    assert executor_called is False


def test_permission_denial_happens_before_approval_check(monkeypatch):
    test_context = ExecutionContext(user_id="test_user")
    permission_policy = PermissionPolicy({"test_user": set()})
    approval_checked = False

    class RecordingApprovalPolicy:
        def requires_approval(self, context, tool_call):
            nonlocal approval_checked
            approval_checked = True
            return False

    with pytest.raises(PermissionDeniedError):
        execute_tools_via_gateway(
            make_tool_call("read_file", {"path": "example.txt"}),
            test_context,
            permission_policy,
            RecordingApprovalPolicy(),
        )

    assert approval_checked is False


def test_approval_required_blocks_executor(monkeypatch, tmp_path):
    test_context = ExecutionContext(user_id="test_user")
    permission_policy = PermissionPolicy({"test_user": {"write_file"}})
    approval_policy = ApprovalPolicy(AUTO_APPROVED_COMMANDS)
    existing_file = tmp_path / "existing.txt"
    existing_file.write_text("existing", encoding="utf-8")
    executor_called = False

    def fake_execute_tool(tool_call):
        nonlocal executor_called
        executor_called = True

    monkeypatch.setattr("tools.tool_gateway.execute_tool", fake_execute_tool)

    with pytest.raises(ApprovalRequiredError):
        execute_tools_via_gateway(
            make_tool_call(
                "write_file",
                {"path": str(existing_file), "content": "replacement"},
            ),
            test_context,
            permission_policy,
            approval_policy,
        )

    assert executor_called is False


@pytest.mark.parametrize(
    "status",
    [ApprovalStatus.PENDING, ApprovalStatus.REJECTED],
)
def test_approved_gateway_rejects_request_without_approval(
    monkeypatch,
    status,
):
    request = ApprovalRequest(
        tool_call=make_tool_call("run_command", {"command": "rm file"}),
        reason="destructive command",
        status=status,
    )
    executor_called = False

    def fake_execute_tool(tool_call):
        nonlocal executor_called
        executor_called = True

    monkeypatch.setattr("tools.tool_gateway.execute_tool", fake_execute_tool)

    with pytest.raises(ValueError):
        execute_approved_tool_via_gateway(
            request,
            ExecutionContext(user_id="test_user"),
            PermissionPolicy({"test_user": {"run_command"}}),
        )

    assert executor_called is False


def test_approved_gateway_checks_permission_before_execution(monkeypatch):
    request = ApprovalRequest(
        tool_call=make_tool_call("run_command", {"command": "rm file"}),
        reason="destructive command",
        status=ApprovalStatus.APPROVED,
    )
    executor_called = False

    def fake_execute_tool(tool_call):
        nonlocal executor_called
        executor_called = True

    monkeypatch.setattr("tools.tool_gateway.execute_tool", fake_execute_tool)

    with pytest.raises(PermissionDeniedError):
        execute_approved_tool_via_gateway(
            request,
            ExecutionContext(user_id="test_user"),
            PermissionPolicy({"test_user": set()}),
        )

    assert executor_called is False


def test_approved_gateway_executes_original_call_without_approval_check(
    monkeypatch,
):
    tool_call = make_tool_call("run_command", {"command": "rm file"})
    request = ApprovalRequest(
        tool_call=tool_call,
        reason="destructive command",
        status=ApprovalStatus.APPROVED,
    )
    executed_call = None

    def fake_execute_tool(received_call):
        nonlocal executed_call
        executed_call = received_call
        return "removed"

    monkeypatch.setattr("tools.tool_gateway.execute_tool", fake_execute_tool)

    result = execute_approved_tool_via_gateway(
        request,
        ExecutionContext(user_id="test_user"),
        PermissionPolicy({"test_user": {"run_command"}}),
    )

    assert result == "removed"
    assert executed_call is tool_call


@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        ("run_command", "{invalid"),
        ("write_file", json.dumps({"path": "existing.txt"})),
    ],
)
def test_invalid_arguments_reach_executor_validation(tool_name, arguments):
    test_context = ExecutionContext(user_id="test_user")
    permission_policy = PermissionPolicy({"test_user": {tool_name}})
    approval_policy = ApprovalPolicy(AUTO_APPROVED_COMMANDS)
    tool_call = SimpleNamespace(
        type="function_call",
        name=tool_name,
        arguments=arguments,
        call_id="call-1",
    )

    from tools import ToolArgumentsError

    with pytest.raises(ToolArgumentsError):
        execute_tools_via_gateway(
            tool_call,
            test_context,
            permission_policy,
            approval_policy,
        )


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
