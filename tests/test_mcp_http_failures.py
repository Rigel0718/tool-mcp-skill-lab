import asyncio
import json
from contextlib import AsyncExitStack
from types import SimpleNamespace

import httpx2
import pytest
from mcp.types import Tool, ToolAnnotations

from code_agent import code_agent
from context import ExecutionContext
from mcp_clients import MCPClient, MCPServerConfig, connect_mcp_servers
from tools import (
    ApprovalPolicy,
    MCPCommunicationError,
    MCPToolExecutionError,
    MCP_TOOL_REGISTRY,
    PermissionPolicy,
    RetryExecutor,
    RetryPolicy,
    execute_tools_via_gateway,
)
from code_agent.tool_discovery import discover_mcp_tools


@pytest.fixture(autouse=True)
def clean_registry():
    MCP_TOOL_REGISTRY.clear()
    yield
    MCP_TOOL_REGISTRY.clear()


def remote_tool(idempotent=True):
    return Tool(
        name="search",
        inputSchema={"type": "object", "properties": {}},
        annotations=ToolAnnotations(
            readOnlyHint=idempotent,
            destructiveHint=not idempotent,
            idempotentHint=idempotent,
        ),
    )


def call(name="postgres_search"):
    return SimpleNamespace(
        type="function_call", name=name, arguments="{}", call_id="http-call"
    )


def install_retry(monkeypatch):
    monkeypatch.setattr(
        "tools.tool_gateway.retry_executor",
        RetryExecutor(RetryPolicy(), sleep=lambda _: None),
    )


def test_multiple_servers_agent_gateway_http_503_retry_and_output(monkeypatch):
    install_retry(monkeypatch)
    calls = []

    def respond(request):
        message = json.loads(request.content)
        if message["method"] == "tools/list":
            result = {
                "tools": [remote_tool().model_dump(by_alias=True, exclude_none=True)],
                "cacheScope": "public", "resultType": "complete", "ttlMs": 0,
            }
        else:
            calls.append((request.url.host, message["params"]["name"]))
            if len(calls) == 1:
                return httpx2.Response(503, text="temporarily unavailable")
            result = {
                "content": [{"type": "text", "text": "recovered"}],
                "resultType": "complete",
            }
        return httpx2.Response(200, json={
            "jsonrpc": "2.0", "id": message["id"], "result": result,
        })

    responses = iter([
        SimpleNamespace(output=[call()], output_text=""),
        SimpleNamespace(output=[], output_text="Done"),
    ])
    monkeypatch.setattr(code_agent, "call_openai_model", lambda *a, **kw: next(responses))

    async def run():
        history = []
        async with AsyncExitStack() as stack:
            http_clients = []
            clients = []
            for host in ("code.example", "postgres.example"):
                http = await stack.enter_async_context(httpx2.AsyncClient(
                    transport=httpx2.MockTransport(respond)
                ))
                http_clients.append(http)
                client = await stack.enter_async_context(MCPClient(
                    f"http://{host}/mcp", http_client=http, mode="2026-07-28",
                ))
                clients.append(client)
            schemas = await discover_mcp_tools(clients, namespaces=["code", "postgres"])
            result = await code_agent.run_agent(
                history, ExecutionContext(user_id="user"),
                PermissionPolicy({"user": {"postgres_search"}}),
                ApprovalPolicy({}), schemas,
            )
            assert result == "Done"
            assert history[-1]["output"] == "recovered"
        assert all(http.is_closed for http in http_clients)
        assert all(not http.event_hooks["response"] for http in http_clients)

    asyncio.run(run())
    assert calls == [("postgres.example", "search"), ("postgres.example", "search")]


@pytest.mark.parametrize("idempotent", [True, False])
def test_http_503_is_communication_failure_but_unsafe_tool_is_not_retried(
    monkeypatch, idempotent,
):
    install_retry(monkeypatch)
    attempts = []

    def respond(request):
        message = json.loads(request.content)
        attempts.append(message)
        return httpx2.Response(503, text="proxy unavailable")

    class Approved:
        def requires_approval(self, *args):
            return False

    async def run():
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(respond)) as http:
            async with MCPClient(
                "http://mcp.example/mcp", http_client=http, mode="2026-07-28",
            ) as client:
                MCP_TOOL_REGISTRY.register_discovered_tools(client, [remote_tool(idempotent)], "postgres")
                with pytest.raises(MCPCommunicationError, match="HTTP 503"):
                    await execute_tools_via_gateway(
                        call(), ExecutionContext(user_id="user"),
                        PermissionPolicy({"user": {"postgres_search"}}), Approved(),
                    )
            assert not http.is_closed
            assert not http.event_hooks["response"]

    asyncio.run(run())
    assert len(attempts) == (3 if idempotent else 1)


@pytest.mark.parametrize("prior_outage", [False, True])
def test_genuine_jsonrpc_internal_error_is_not_transient_even_with_http_500(
    monkeypatch, prior_outage,
):
    install_retry(monkeypatch)
    attempts = []

    def respond(request):
        message = json.loads(request.content)
        attempts.append(message)
        if prior_outage and len(attempts) == 1:
            return httpx2.Response(503, text="proxy unavailable")
        return httpx2.Response(500, json={
            "jsonrpc": "2.0", "id": message["id"],
            "error": {"code": -32603, "message": "genuine internal error"},
        })

    async def run():
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(respond)) as http:
            async with MCPClient(
                "http://mcp.example/mcp", http_client=http, mode="2026-07-28",
            ) as client:
                MCP_TOOL_REGISTRY.register_discovered_tools(client, [remote_tool()], "postgres")
                with pytest.raises(MCPToolExecutionError, match="genuine internal error"):
                    await execute_tools_via_gateway(
                        call(), ExecutionContext(user_id="user"),
                        PermissionPolicy({"user": {"postgres_search"}}), ApprovalPolicy({}),
                    )

    asyncio.run(run())
    assert len(attempts) == (2 if prior_outage else 1)


def test_http_503_during_sdk_handshake_is_transient_and_removes_hook():
    async def run():
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(
            lambda request: httpx2.Response(503, text="proxy unavailable")
        )) as http:
            with pytest.raises(MCPCommunicationError):
                async with MCPClient(
                    "http://mcp.example/mcp", http_client=http, read_timeout_seconds=0.2,
                ):
                    pytest.fail("Handshake must fail")
            assert not http.is_closed
            assert not http.event_hooks["response"]

    asyncio.run(run())


def test_owned_http_client_closes_after_failed_handshake(monkeypatch):
    async def run():
        http = httpx2.AsyncClient(transport=httpx2.MockTransport(
            lambda request: httpx2.Response(503, text="proxy unavailable")
        ))
        monkeypatch.setattr("mcp_clients.client.create_mcp_http_client", lambda: http)
        with pytest.raises(MCPCommunicationError):
            async with MCPClient("http://mcp.example/mcp", read_timeout_seconds=0.2):
                pytest.fail("Handshake must fail")
        assert http.is_closed
        assert not http.event_hooks["response"]

    asyncio.run(run())


def test_real_http_discovery_deadline_closes_mcp_streams_and_removes_hook():
    async def run():
        async def no_response(request):
            await asyncio.Event().wait()

        async with httpx2.AsyncClient(transport=httpx2.MockTransport(no_response)) as http:
            async with AsyncExitStack() as stack:
                schemas = await connect_mcp_servers(
                    [MCPServerConfig("hung", "hung", "http://mcp.example/mcp", False, 0.02)],
                    stack,
                    client_factory=lambda url: MCPClient(
                        url, http_client=http, mode="2026-07-28",
                    ),
                )
                assert schemas == []
            assert not http.is_closed
            assert not http.event_hooks["response"]

    asyncio.run(run())


def test_simultaneous_sdk_calls_do_not_share_http_failure_status():
    async def run():
        async def respond(request):
            message = json.loads(request.content)
            await asyncio.sleep(0)
            if message["params"]["name"] == "temporary":
                return httpx2.Response(503, text="proxy unavailable")
            return httpx2.Response(500, json={
                "jsonrpc": "2.0", "id": message["id"],
                "error": {"code": -32603, "message": "genuine internal error"},
            })

        async with httpx2.AsyncClient(transport=httpx2.MockTransport(respond)) as http:
            async with MCPClient(
                "http://mcp.example/mcp", http_client=http, mode="2026-07-28",
            ) as client:
                temporary, internal = await asyncio.gather(
                    client.call_tool("temporary", {}),
                    client.call_tool("internal", {}),
                    return_exceptions=True,
                )
                assert isinstance(temporary, MCPCommunicationError)
                assert isinstance(internal, MCPToolExecutionError)

    asyncio.run(run())
