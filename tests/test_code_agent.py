import json
import subprocess
import sys
from types import SimpleNamespace
from pathlib import Path

from code_agent import code_agent
from context import ExecutionContext
from approval_config import AUTO_APPROVED_COMMANDS
from tools import (
    ApprovalPolicy,
    ApprovalRequiredError,
    PermissionDeniedError,
    PermissionPolicy,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


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
        lambda tool_call, context, permission_policy, approval_policy: '["a.py"]',
    )
    history = [{"role": "user", "content": "List files"}]
    context = ExecutionContext(user_id="test_user")
    permission_policy = PermissionPolicy({"test_user": {"list_files"}})
    approval_policy = ApprovalPolicy(AUTO_APPROVED_COMMANDS)

    assert (
        code_agent.run_agent(
            history,
            context,
            permission_policy,
            approval_policy,
        )
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
        lambda tool_call, context, permission_policy, approval_policy: (
            (_ for _ in ()).throw(PermissionDeniedError("not allowed"))
        ),
    )
    history = [{"role": "user", "content": "Write a file"}]
    context = ExecutionContext(user_id="test_user")
    permission_policy = PermissionPolicy({"test_user": set()})
    approval_policy = ApprovalPolicy(AUTO_APPROVED_COMMANDS)

    assert (
        code_agent.run_agent(
            history,
            context,
            permission_policy,
            approval_policy,
        )
        == "Permission denied"
    )
    assert history[-1] == {
        "type": "function_call_output",
        "call_id": "call-1",
        "output": "Tool error: not allowed",
    }


def test_run_agent_returns_approval_requirement_to_model(monkeypatch):
    responses = iter(
        [
            SimpleNamespace(
                output=[
                    SimpleNamespace(
                        type="function_call",
                        name="run_command",
                        arguments=json.dumps({"command": "rm example.txt"}),
                        call_id="call-1",
                    )
                ],
                output_text="",
            ),
            SimpleNamespace(output=[], output_text="Approval required"),
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
        lambda tool_call, context, permission_policy, approval_policy: (
            (_ for _ in ()).throw(ApprovalRequiredError("approval required"))
        ),
    )
    history = [{"role": "user", "content": "Remove a file"}]
    context = ExecutionContext(user_id="test_user")
    permission_policy = PermissionPolicy({"test_user": {"run_command"}})
    approval_policy = ApprovalPolicy(AUTO_APPROVED_COMMANDS)

    assert (
        code_agent.run_agent(
            history,
            context,
            permission_policy,
            approval_policy,
        )
        == "Approval required"
    )
    assert history[-1] == {
        "type": "function_call_output",
        "call_id": "call-1",
        "output": "Tool error: approval required",
    }
