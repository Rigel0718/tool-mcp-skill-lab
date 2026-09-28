import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main
from hitl import ApprovalRequest, ApprovalStatus, PendingApproval
from tools import ApprovalPolicy, PermissionPolicy
from context import ExecutionContext


def make_pending():
    tool_call = SimpleNamespace(
        name="run_command",
        arguments='{"command": "rm file"}',
        call_id="call-1",
    )
    request = ApprovalRequest(tool_call=tool_call, reason="approval required")
    return PendingApproval(request), request


def dependencies():
    return (
        ExecutionContext(user_id="test_user"),
        PermissionPolicy({"test_user": {"run_command"}}),
        ApprovalPolicy({}),
    )


def test_approve_executes_via_gateway_before_resume(monkeypatch):
    pending, request = make_pending()
    messages = []
    events = []
    results = iter([pending, "Done"])

    def fake_run_agent(*args):
        events.append("run_agent")
        return next(results)

    def fake_gateway(received_request, context, permission_policy):
        events.append("gateway")
        assert received_request is request
        assert received_request.status is ApprovalStatus.APPROVED
        return "removed"

    monkeypatch.setattr(main, "run_agent", fake_run_agent)
    monkeypatch.setattr(main, "execute_approved_tool_via_gateway", fake_gateway)
    monkeypatch.setattr("builtins.input", lambda prompt: "approve")

    result = main.agent_run_orchestration_loop(messages, *dependencies())

    assert result == "Done"
    assert events == ["run_agent", "gateway", "run_agent"]
    assert messages == [{
        "type": "function_call_output",
        "call_id": "call-1",
        "output": "removed",
    }]


def test_reject_and_continue_records_rejection_then_resumes(monkeypatch):
    pending, request = make_pending()
    messages = []
    events = []
    results = iter([pending, "Alternative complete"])
    choices = iter(["reject", "continue"])

    def fake_run_agent(*args):
        events.append("run_agent")
        return next(results)

    monkeypatch.setattr(main, "run_agent", fake_run_agent)
    monkeypatch.setattr(
        main,
        "execute_approved_tool_via_gateway",
        lambda *args: (_ for _ in ()).throw(AssertionError("must not execute")),
    )
    monkeypatch.setattr("builtins.input", lambda prompt: next(choices))

    result = main.agent_run_orchestration_loop(messages, *dependencies())

    assert result == "Alternative complete"
    assert request.status is ApprovalStatus.REJECTED
    assert events == ["run_agent", "run_agent"]
    assert messages[-1]["output"] == "Tool call rejected by the user."


def test_reject_and_stop_records_rejection_without_resume(monkeypatch):
    pending, request = make_pending()
    messages = []
    run_calls = 0
    choices = iter(["reject", "stop"])

    def fake_run_agent(*args):
        nonlocal run_calls
        run_calls += 1
        return pending

    monkeypatch.setattr(main, "run_agent", fake_run_agent)
    monkeypatch.setattr(
        main,
        "execute_approved_tool_via_gateway",
        lambda *args: (_ for _ in ()).throw(AssertionError("must not execute")),
    )
    monkeypatch.setattr("builtins.input", lambda prompt: next(choices))

    result = main.agent_run_orchestration_loop(messages, *dependencies())

    assert result is None
    assert request.status is ApprovalStatus.REJECTED
    assert run_calls == 1
    assert messages[-1]["output"] == "Tool call rejected by the user."
