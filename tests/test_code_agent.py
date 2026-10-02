import asyncio
import json
import subprocess
import sys
from types import SimpleNamespace
from pathlib import Path

from code_agent import code_agent
from context import ExecutionContext
from hitl import ApprovalStatus, PendingApproval
from approval_config import AUTO_APPROVED_COMMANDS
from tools import (
    ApprovalPolicy,
    ApprovalRequiredError,
    PermissionDeniedError,
    PermissionPolicy,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def async_gateway_result(result):
    async def gateway(*args):
        return result

    return gateway


def async_gateway_error(error):
    async def gateway(*args):
        raise error

    return gateway


def test_main_starts_and_exits_successfully():
    result = subprocess.run(
        [sys.executable, "main.py"],
        cwd=PROJECT_ROOT,
        input="exit\n",
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Mini agent ready" in result.stdout


def test_run_agent_executes_tool_and_returns_final_text(monkeypatch):
    responses = iter(
        [
            SimpleNamespace(
                output=[
                    SimpleNamespace(
                        type="function_call",
                        name="list_files",
                        arguments=json.dumps({"path": "."}),
                        call_id="call-1",
                    )
                ],
                output_text="",
            ),
            SimpleNamespace(output=[], output_text="Done"),
        ]
    )

    monkeypatch.setattr(
        code_agent,
        "call_openai_model",
        lambda history, schemas, raw_response: next(responses),
    )
    monkeypatch.setattr(
        code_agent,
        "execute_tools_via_gateway",
        async_gateway_result('["a.py"]'),
    )
    history = [{"role": "user", "content": "List files"}]
    context = ExecutionContext(user_id="test_user")
    permission_policy = PermissionPolicy({"test_user": {"list_files"}})
    approval_policy = ApprovalPolicy(AUTO_APPROVED_COMMANDS)

    assert (
        asyncio.run(code_agent.run_agent(
            history,
            context,
            permission_policy,
            approval_policy,
        ))
        == "Done"
    )
    assert history[-1] == {
        "type": "function_call_output",
        "call_id": "call-1",
        "output": '["a.py"]',
    }


def test_run_agent_returns_permission_denial_to_model(monkeypatch):
    responses = iter(
        [
            SimpleNamespace(
                output=[
                    SimpleNamespace(
                        type="function_call",
                        name="write_file",
                        arguments=json.dumps({
                            "path": "example.txt",
                            "content": "example",
                        }),
                        call_id="call-1",
                    )
                ],
                output_text="",
            ),
            SimpleNamespace(output=[], output_text="Permission denied"),
        ]
    )

    monkeypatch.setattr(
        code_agent,
        "call_openai_model",
        lambda history, schemas, raw_response: next(responses),
    )
    monkeypatch.setattr(
        code_agent,
        "execute_tools_via_gateway",
        async_gateway_error(PermissionDeniedError("not allowed")),
    )
    history = [{"role": "user", "content": "Write a file"}]
    context = ExecutionContext(user_id="test_user")
    permission_policy = PermissionPolicy({"test_user": set()})
    approval_policy = ApprovalPolicy(AUTO_APPROVED_COMMANDS)

    assert (
        asyncio.run(code_agent.run_agent(
            history,
            context,
            permission_policy,
            approval_policy,
        ))
        == "Permission denied"
    )
    assert history[-1] == {
        "type": "function_call_output",
        "call_id": "call-1",
        "output": "Tool error: not allowed",
    }


def test_run_agent_returns_pending_approval_without_resuming(monkeypatch):
    tool_call = SimpleNamespace(
        type="function_call",
        name="run_command",
        arguments=json.dumps({"command": "rm example.txt"}),
        call_id="call-1",
    )
    model_calls = 0

    def fake_model(history, schemas, raw_response):
        nonlocal model_calls
        model_calls += 1
        return SimpleNamespace(output=[tool_call], output_text="")

    monkeypatch.setattr(code_agent, "call_openai_model", fake_model)
    monkeypatch.setattr(
        code_agent,
        "execute_tools_via_gateway",
        async_gateway_error(ApprovalRequiredError("approval required")),
    )
    history = [{"role": "user", "content": "Remove a file"}]
    context = ExecutionContext(user_id="test_user")
    permission_policy = PermissionPolicy({"test_user": {"run_command"}})
    approval_policy = ApprovalPolicy(AUTO_APPROVED_COMMANDS)

    result = asyncio.run(code_agent.run_agent(
        history,
        context,
        permission_policy,
        approval_policy,
    ))

    assert isinstance(result, PendingApproval)
    assert result.approval_request.tool_call is tool_call
    assert result.approval_request.reason == "approval required"
    assert result.approval_request.status is ApprovalStatus.PENDING
    assert model_calls == 1
    assert not any(
        isinstance(item, dict) and item.get("type") == "function_call_output"
        for item in history
    )
