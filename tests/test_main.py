import asyncio
import logging
import pytest
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main
from hitl import ApprovalRequest, ApprovalStatus, PendingApproval
from tools import ApprovalPolicy, PermissionPolicy, MCP_TOOL_REGISTRY
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


def test_configure_logging_uses_info_and_expected_format(monkeypatch):
    received = {}

    monkeypatch.setattr(
        main.logging,
        "basicConfig",
        lambda **kwargs: received.update(kwargs),
    )

    main.configure_logging()

    assert received == {
        "level": logging.INFO,
        "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
    }


def test_mcp_connection_configuration_is_separate_from_tool_discovery(monkeypatch):
    monkeypatch.setenv("CODE_MCP_ENABLED", "1")
    monkeypatch.setenv("MCP_SERVER_URL", "http://postgres.example/mcp")

    configs = main.configured_mcp_servers()

    assert [(item.name, item.namespace, item.required) for item in configs] == [
        ("code-tools", "code", True),
        ("postgres", "postgres", False),
    ]
    assert all(not hasattr(item, "tools") for item in configs)


def test_main_cleans_registry_when_startup_fails(monkeypatch):
    from mcp.types import Tool

    async def fail_startup(configs, stack):
        MCP_TOOL_REGISTRY.register_discovered_tools(
            object(), [Tool(name="search", inputSchema={"type": "object"})], "partial"
        )
        raise ConnectionError("required startup failed")

    monkeypatch.setattr(main, "connect_mcp_servers", fail_startup)
    with pytest.raises(ConnectionError, match="required startup failed"):
        asyncio.run(main.async_main())
    assert MCP_TOOL_REGISTRY.get("partial_search") is None


def test_execution_context_generates_distinct_run_ids():
    first = ExecutionContext(user_id="test_user")
    second = ExecutionContext(user_id="test_user")

    assert first.run_id
    assert second.run_id
    assert first.run_id != second.run_id


def test_approve_executes_via_gateway_before_resume(monkeypatch):
    pending, request = make_pending()
    messages = []
    events = []
    contexts = []
    results = iter([pending, "Done"])

    async def fake_run_agent(*args):
        events.append("run_agent")
        contexts.append(args[1])
        return next(results)

    async def fake_gateway(received_request, context, permission_policy):
        events.append("gateway")
        contexts.append(context)
        assert received_request is request
        assert received_request.status is ApprovalStatus.APPROVED
        return "removed"

    monkeypatch.setattr(main, "run_agent", fake_run_agent)
    monkeypatch.setattr(main, "execute_approved_tool_via_gateway", fake_gateway)
    monkeypatch.setattr("builtins.input", lambda prompt: "approve")

    result = asyncio.run(
        main.agent_run_orchestration_loop(messages, *dependencies())
    )

    assert result == "Done"
    assert events == ["run_agent", "gateway", "run_agent"]
    assert contexts[0] is contexts[1] is contexts[2]
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

    async def fake_run_agent(*args):
        events.append("run_agent")
        return next(results)

    monkeypatch.setattr(main, "run_agent", fake_run_agent)
    monkeypatch.setattr(
        main,
        "execute_approved_tool_via_gateway",
        lambda *args: (_ for _ in ()).throw(AssertionError("must not execute")),
    )
    monkeypatch.setattr("builtins.input", lambda prompt: next(choices))

    result = asyncio.run(
        main.agent_run_orchestration_loop(messages, *dependencies())
    )

    assert result == "Alternative complete"
    assert request.status is ApprovalStatus.REJECTED
    assert events == ["run_agent", "run_agent"]
    assert messages[-1]["output"] == "Tool call rejected by the user."


def test_reject_and_stop_records_rejection_without_resume(monkeypatch):
    pending, request = make_pending()
    messages = []
    run_calls = 0
    choices = iter(["reject", "stop"])

    async def fake_run_agent(*args):
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

    result = asyncio.run(
        main.agent_run_orchestration_loop(messages, *dependencies())
    )

    assert result is None
    assert request.status is ApprovalStatus.REJECTED
    assert run_calls == 1
    assert messages[-1]["output"] == "Tool call rejected by the user."
