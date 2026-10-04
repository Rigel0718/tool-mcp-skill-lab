import asyncio
import json
import logging
from contextlib import AsyncExitStack
from types import SimpleNamespace

import pytest
import httpx2
from mcp.types import (
    CallToolResult,
    ListToolsResult,
    TextContent,
    Tool,
    ToolAnnotations,
)

from code_agent import code_agent
from code_agent.mcp_tool_schemas import mcp_tool_to_openai_schema
from code_agent.tool_discovery import discover_mcp_tools
from context import ExecutionContext
from mcp_clients import MCPServerConfig, connect_mcp_servers
from mcp_clients.client import MCPClient, translate_mcp_exception
from tools import (
    ApprovalPolicy,
    ApprovalRequiredError,
    MCP_TOOL_REGISTRY,
    MCPCommunicationError,
    MCPToolExecutionError,
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


def test_two_servers_can_register_same_local_name_with_global_namespaces():
    first = FakeMCPClient()
    second = FakeMCPClient()

    schemas = asyncio.run(discover_mcp_tools(
        [first, second], namespaces=["code", "postgres"]
    ))

    assert {schema["name"] for schema in schemas} == {
        "code_search_runs", "postgres_search_runs"
    }
    assert MCP_TOOL_REGISTRY.get("code_search_runs").remote_name == "search_runs"
    assert MCP_TOOL_REGISTRY.get("postgres_search_runs").client is second


def test_global_name_routes_to_correct_client_and_remote_local_name():
    code = FakeMCPClient(results=[
        CallToolResult(content=[TextContent(type="text", text="code")])
    ])
    postgres = FakeMCPClient(results=[
        CallToolResult(content=[TextContent(type="text", text="postgres")])
    ])
    asyncio.run(discover_mcp_tools(
        [code, postgres], namespaces=["code", "postgres"]
    ))

    result = asyncio.run(execute_tool(make_call("postgres_search_runs")))

    assert result == "postgres"
    assert code.calls == []
    assert postgres.calls == [("search_runs", {"limit": 5})]


def test_duplicate_global_name_is_rejected_even_with_namespaces():
    first = FakeMCPClient()
    second = FakeMCPClient()

    asyncio.run(discover_mcp_tools([first], namespaces=["shared"]))
    with pytest.raises(ToolNameCollisionError, match="shared_search_runs"):
        asyncio.run(discover_mcp_tools([second], namespaces=["shared"]))


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


def annotated_tool(*, read_only, destructive, idempotent):
    return SEARCH_TOOL.model_copy(update={
        "annotations": ToolAnnotations(
            readOnlyHint=read_only,
            destructiveHint=destructive,
            idempotentHint=idempotent,
        )
    })


def test_read_only_mcp_metadata_is_used_by_existing_approval_policy():
    client = FakeMCPClient([annotated_tool(
        read_only=True, destructive=False, idempotent=True
    )])
    asyncio.run(discover_mcp_tools([client], namespaces=["postgres"]))

    result = asyncio.run(execute_tools_via_gateway(
        make_call("postgres_search_runs"),
        ExecutionContext(user_id="user"),
        PermissionPolicy({"user": {"postgres_search_runs"}}),
        ApprovalPolicy({}),
    ))

    assert result == "found"


def test_destructive_mcp_metadata_still_requires_application_approval():
    client = FakeMCPClient([annotated_tool(
        read_only=False, destructive=True, idempotent=False
    )])
    asyncio.run(discover_mcp_tools([client], namespaces=["remote"]))

    with pytest.raises(ApprovalRequiredError):
        asyncio.run(execute_tools_via_gateway(
            make_call("remote_search_runs"),
            ExecutionContext(user_id="user"),
            PermissionPolicy({"user": {"remote_search_runs"}}),
            ApprovalPolicy({}),
        ))
    assert client.calls == []


def test_retry_safe_metadata_allows_transient_mcp_retry(monkeypatch):
    client = FakeMCPClient(
        [annotated_tool(read_only=True, destructive=False, idempotent=True)],
        [
            MCPCommunicationError("connection lost"),
            CallToolResult(content=[TextContent(type="text", text="recovered")]),
        ],
    )
    asyncio.run(discover_mcp_tools([client], namespaces=["postgres"]))

    async def no_sleep(delay):
        return None

    monkeypatch.setattr(
        "tools.tool_gateway.retry_executor",
        RetryExecutor(RetryPolicy(), sleep=no_sleep),
    )
    result = asyncio.run(execute_tools_via_gateway(
        make_call("postgres_search_runs"),
        ExecutionContext(user_id="user"),
        PermissionPolicy({"user": {"postgres_search_runs"}}),
        NeverApprove(),
    ))

    assert result == "recovered"
    assert len(client.calls) == 2


def test_non_retry_safe_mcp_tool_is_not_repeated_after_communication_failure(
    monkeypatch,
):
    client = FakeMCPClient(
        [annotated_tool(read_only=False, destructive=True, idempotent=False)],
        [MCPCommunicationError("response lost")],
    )
    asyncio.run(discover_mcp_tools([client], namespaces=["remote"]))
    monkeypatch.setattr(
        "tools.tool_gateway.retry_executor",
        RetryExecutor(RetryPolicy(), sleep=lambda delay: None),
    )

    with pytest.raises(MCPCommunicationError):
        asyncio.run(execute_tools_via_gateway(
            make_call("remote_search_runs"),
            ExecutionContext(user_id="user"),
            PermissionPolicy({"user": {"remote_search_runs"}}),
            NeverApprove(),
        ))
    assert len(client.calls) == 1


def test_mcp_exception_translation_distinguishes_communication_and_tool_failure():
    assert isinstance(translate_mcp_exception(ConnectionError("down")), MCPCommunicationError)
    assert isinstance(translate_mcp_exception(ValueError("bad response")), MCPToolExecutionError)

    request = httpx2.Request("GET", "http://mcp.example")
    unavailable = httpx2.HTTPStatusError(
        "unavailable",
        request=request,
        response=httpx2.Response(503, request=request),
    )
    denied = httpx2.HTTPStatusError(
        "denied",
        request=request,
        response=httpx2.Response(403, request=request),
    )
    assert isinstance(translate_mcp_exception(unavailable), MCPCommunicationError)
    assert isinstance(translate_mcp_exception(denied), MCPToolExecutionError)


def test_servers_publish_official_tool_annotations():
    from mcp_servers.code_tools_server import mcp as code_server
    from mcp_servers.postgres_server import mcp as postgres_server

    async def discover_annotations():
        async with MCPClient(code_server) as code_client:
            code_tools = (await code_client.list_tools()).tools
        async with MCPClient(postgres_server) as postgres_client:
            postgres_tools = (await postgres_client.list_tools()).tools
        return code_tools, postgres_tools

    code_tools, postgres_tools = asyncio.run(discover_annotations())
    code_by_name = {tool.name: tool for tool in code_tools}

    assert code_by_name["read_file"].annotations.read_only_hint is True
    assert code_by_name["write_file"].annotations.destructive_hint is True
    assert code_by_name["run_command"].annotations.idempotent_hint is False
    assert all(tool.annotations.read_only_hint is True for tool in postgres_tools)
    assert all(tool.annotations.idempotent_hint is True for tool in postgres_tools)


def test_code_and_postgres_mcp_servers_are_discovered_together():
    from mcp_servers.code_tools_server import mcp as code_server
    from mcp_servers.postgres_server import mcp as postgres_server

    async def discover_both():
        async with AsyncExitStack() as stack:
            code_client = await stack.enter_async_context(MCPClient(code_server))
            postgres_client = await stack.enter_async_context(MCPClient(postgres_server))
            return await discover_mcp_tools(
                [code_client, postgres_client],
                namespaces=["code", "postgres"],
            )

    schemas = asyncio.run(discover_both())

    assert {schema["name"] for schema in schemas} == {
        "code_list_files",
        "code_read_file",
        "code_write_file",
        "code_run_command",
        "postgres_search_runs",
        "postgres_get_run",
        "postgres_get_traces",
    }


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
    server_target = object()

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
        async with MCPClient(server_target) as client:
            await client.list_tools()

    asyncio.run(use_client())

    assert events == [
        ("created", server_target),
        "connected",
        "closed",
    ]


class ManagedFakeClient(FakeMCPClient):
    def __init__(self, server, events):
        super().__init__(server.get("tools", ()))
        self.server = server
        self.events = events

    async def __aenter__(self):
        self.events.append((self.server["name"], "enter"))
        if self.server.get("connect_error"):
            raise self.server["connect_error"]
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        self.events.append((self.server["name"], "close"))

    async def list_tools(self, *, cursor=None):
        if self.server.get("discovery_error"):
            raise self.server["discovery_error"]
        return await super().list_tools(cursor=cursor)


def run_server_startup(configs, events):
    async def run():
        async with AsyncExitStack() as stack:
            schemas = await connect_mcp_servers(
                configs,
                stack,
                client_factory=lambda server: ManagedFakeClient(server, events),
            )
            events.append(("application", "running"))
            return schemas

    return asyncio.run(run())


def test_required_server_startup_failure_fails_fast_and_closes_open_clients():
    events = []
    configs = [
        MCPServerConfig(
            "working", "working", {"name": "working", "tools": [SEARCH_TOOL]}, True
        ),
        MCPServerConfig(
            "required", "required", {
                "name": "required", "connect_error": ConnectionError("down")
            }, True
        ),
    ]

    with pytest.raises(ConnectionError, match="down"):
        run_server_startup(configs, events)

    assert ("application", "running") not in events
    assert ("working", "close") in events


def test_optional_server_failure_excludes_capability_and_continues():
    events = []
    configs = [
        MCPServerConfig(
            "optional", "optional", {
                "name": "optional", "discovery_error": RuntimeError("bad discovery")
            }, False
        ),
        MCPServerConfig(
            "working", "working", {"name": "working", "tools": [SEARCH_TOOL]}, True
        ),
    ]

    schemas = run_server_startup(configs, events)

    assert [schema["name"] for schema in schemas] == ["working_search_runs"]
    assert "optional_search_runs" not in MCP_TOOL_REGISTRY
    assert "working_search_runs" not in MCP_TOOL_REGISTRY
    assert ("optional", "close") in events
    assert ("working", "close") in events
    assert events.index(("application", "running")) < events.index(("working", "close"))


def test_all_connected_mcp_clients_are_closed_at_application_shutdown():
    events = []
    configs = [
        MCPServerConfig(
            "code", "code", {"name": "code", "tools": [SEARCH_TOOL]}, True
        ),
        MCPServerConfig(
            "postgres", "postgres", {"name": "postgres", "tools": [SEARCH_TOOL]}, False
        ),
    ]

    run_server_startup(configs, events)

    assert events.count(("code", "close")) == 1
    assert events.count(("postgres", "close")) == 1
