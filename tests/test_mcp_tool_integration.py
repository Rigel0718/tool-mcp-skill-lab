import asyncio
import json
import logging
from types import SimpleNamespace

import pytest
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool

from code_agent import code_agent
from code_agent.mcp_tool_schemas import mcp_tool_to_openai_schema
from code_agent.tool_discovery import discover_mcp_tools
from context import ExecutionContext
from mcp_clients.client import MCPClient
from tools import (
    ApprovalPolicy,
    ApprovalRequiredError,
    MCP_TOOL_REGISTRY,
    MCPToolRegistry,
    PermissionDeniedError,
    PermissionPolicy,
    RetryExecutor,
    RetryPolicy,
    ToolExecutionError,
    ToolNameCollisionError,
    TransientToolError,
    execute_tools_via_gateway,
)
from tools.code_tools_schemas import TOOL_SCHEMAS
from tools.tool_executor import execute_tool


SEARCH_TOOL = Tool(
    name="search_runs",
    description="Search agent runs.",
    inputSchema={
        "type": "object",
        "properties": {"limit": {"type": "integer"}},
        "required": ["limit"],
        "additionalProperties": False,
    },
)


class FakeMCPClient:
    def __init__(self, tools=(SEARCH_TOOL,), results=None):
        self.tools = list(tools)
        self.results = list(results or [
            CallToolResult(content=[TextContent(type="text", text="found")])
        ])
        self.calls = []
        self.list_calls = []

    async def list_tools(self, *, cursor=None):
        self.list_calls.append(cursor)
        return ListToolsResult(tools=self.tools)

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        result = self.results[min(len(self.calls) - 1, len(self.results) - 1)]
        if isinstance(result, Exception):
            raise result
        return result


class NeverApprove:
    def requires_approval(self, context, tool_call):
        return False


def make_call(name="search_runs", arguments=None):
    return SimpleNamespace(
        type="function_call",
        name=name,
        arguments=json.dumps(arguments or {"limit": 5}),
        call_id="call-1",
    )


@pytest.fixture(autouse=True)
def clean_global_mcp_registry():
    MCP_TOOL_REGISTRY.clear()
    yield
    MCP_TOOL_REGISTRY.clear()


def test_mcp_tool_schema_is_adapted_directly_to_openai_schema():
    assert mcp_tool_to_openai_schema(SEARCH_TOOL) == {
        "type": "function",
        "name": "search_runs",
        "description": "Search agent runs.",
        "parameters": SEARCH_TOOL.input_schema,
    }


def test_discovery_registers_client_and_returns_agent_schema():
    client = FakeMCPClient()

    schemas = asyncio.run(discover_mcp_tools([client]))

    assert MCP_TOOL_REGISTRY.get_client("search_runs") is client
    assert MCP_TOOL_REGISTRY.get_definition("search_runs") is SEARCH_TOOL
    assert schemas == [mcp_tool_to_openai_schema(SEARCH_TOOL)]
    assert client.list_calls == [None]


def test_local_and_mcp_tool_name_collision_is_rejected():
    local_name = Tool(
        name="read_file",
        description="collision",
        inputSchema={"type": "object"},
    )

    with pytest.raises(ToolNameCollisionError, match="read_file"):
        asyncio.run(discover_mcp_tools([FakeMCPClient([local_name])]))

    assert "read_file" not in MCP_TOOL_REGISTRY


def test_tools_from_two_mcp_clients_cannot_share_a_name():
    first = FakeMCPClient()
    second = FakeMCPClient()

    asyncio.run(discover_mcp_tools([first]))
    with pytest.raises(ToolNameCollisionError, match="search_runs"):
        asyncio.run(discover_mcp_tools([second]))

    assert MCP_TOOL_REGISTRY.get_client("search_runs") is first


def test_execute_tool_routes_mcp_call_to_registered_client():
    client = FakeMCPClient()
    asyncio.run(discover_mcp_tools([client]))

    result = asyncio.run(execute_tool(make_call()))

    assert result == "found"
    assert client.calls == [("search_runs", {"limit": 5})]


def test_mcp_client_failure_becomes_existing_tool_execution_error():
    client = FakeMCPClient(results=[RuntimeError("connection lost")])
    asyncio.run(discover_mcp_tools([client]))

    with pytest.raises(ToolExecutionError, match="connection lost"):
        asyncio.run(execute_tool(make_call()))


def test_permission_denies_mcp_tool_before_client_call():
    client = FakeMCPClient()
    asyncio.run(discover_mcp_tools([client]))

    with pytest.raises(PermissionDeniedError):
        asyncio.run(execute_tools_via_gateway(
            make_call(),
            ExecutionContext(user_id="user"),
            PermissionPolicy({"user": set()}),
            NeverApprove(),
        ))

    assert client.calls == []


def test_mcp_tool_uses_existing_approval_boundary():
    client = FakeMCPClient()
    asyncio.run(discover_mcp_tools([client]))

    with pytest.raises(ApprovalRequiredError):
        asyncio.run(execute_tools_via_gateway(
            make_call(),
            ExecutionContext(user_id="user"),
            PermissionPolicy({"user": {"search_runs"}}),
            ApprovalPolicy({}),
        ))

    assert client.calls == []


def test_retry_policy_can_retry_explicit_transient_mcp_failure(monkeypatch):
    client = FakeMCPClient(results=[
        TransientToolError("temporary"),
        CallToolResult(content=[TextContent(type="text", text="recovered")]),
    ])
    asyncio.run(discover_mcp_tools([client]))

    async def no_sleep(delay):
        return None

    retry = RetryExecutor(
        RetryPolicy(retry_safe_tools=frozenset({"search_runs"})),
        sleep=no_sleep,
    )
    monkeypatch.setattr("tools.tool_gateway.retry_executor", retry)

    result = asyncio.run(execute_tools_via_gateway(
        make_call(),
        ExecutionContext(user_id="user"),
        PermissionPolicy({"user": {"search_runs"}}),
        NeverApprove(),
    ))

    assert result == "recovered"
    assert len(client.calls) == 2


def test_gateway_application_logging_also_wraps_mcp_execution(caplog):
    client = FakeMCPClient()
    asyncio.run(discover_mcp_tools([client]))

    with caplog.at_level(logging.INFO, logger="tools.tool_gateway"):
        asyncio.run(execute_tools_via_gateway(
            make_call(),
            ExecutionContext(user_id="user", run_id="run-mcp"),
            PermissionPolicy({"user": {"search_runs"}}),
            NeverApprove(),
        ))

    messages = [record.getMessage() for record in caplog.records]
    assert any("tool_name=search_runs" in message for message in messages)
    assert any("result=started" in message for message in messages)
    assert any("result=success" in message for message in messages)


def test_agent_receives_local_and_mcp_schemas_and_appends_mcp_output(monkeypatch):
    client = FakeMCPClient()
    mcp_schemas = asyncio.run(discover_mcp_tools([client]))
    schemas = [*TOOL_SCHEMAS, *mcp_schemas]
    received_schemas = []
    responses = iter([
        SimpleNamespace(output=[make_call()], output_text=""),
        SimpleNamespace(output=[], output_text="Done"),
    ])

    def fake_model(history, tool_schemas, raw_response):
        received_schemas.append(tool_schemas)
        return next(responses)

    monkeypatch.setattr(code_agent, "call_openai_model", fake_model)

    history = [{"role": "user", "content": "Search runs"}]
    result = asyncio.run(code_agent.run_agent(
        history,
        ExecutionContext(user_id="user"),
        PermissionPolicy({"user": {"search_runs"}}),
        NeverApprove(),
        schemas,
    ))

    assert result == "Done"
    assert {schema["name"] for schema in received_schemas[0]} == {
        "list_files", "read_file", "write_file", "run_command", "search_runs"
    }
    assert history[-1] == {
        "type": "function_call_output",
        "call_id": "call-1",
        "output": "found",
    }


def test_mcp_client_context_owns_connection_lifecycle(monkeypatch):
    events = []

    class FakeSDKClient:
        def __init__(self, server, **options):
            events.append(("created", server))

        async def __aenter__(self):
            events.append("connected")
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            events.append("closed")

        async def list_tools(self, **kwargs):
            return ListToolsResult(tools=[])

    monkeypatch.setattr("mcp_clients.client.Client", FakeSDKClient)

    async def use_client():
        async with MCPClient("http://mcp.example") as client:
            await client.list_tools()

    asyncio.run(use_client())

    assert events == [
        ("created", "http://mcp.example"),
        "connected",
        "closed",
    ]
