import asyncio
from contextlib import AsyncExitStack

import pytest
from mcp.server.mcpserver import MCPServer
from mcp.types import ListToolsResult, Tool

from mcp_clients import MCPClient, MCPServerConfig, connect_mcp_servers
from tools import MCPToolRegistry, ToolNameCollisionError


SEARCH = Tool(name="search", inputSchema={"type": "object"})


class Client:
    def __init__(self, target):
        self.target = target
        self.closes = 0

    async def __aenter__(self):
        if self.target == "down":
            raise ConnectionError("down")
        return self

    async def __aexit__(self, *args):
        self.closes += 1

    async def list_tools(self, **kwargs):
        if self.target == "bad-discovery":
            raise RuntimeError("discovery failed")
        if self.target == "hung":
            await asyncio.Event().wait()
        return ListToolsResult(tools=[SEARCH])


@pytest.mark.parametrize("use_sdk", [False, True])
def test_discovery_cancellation_closes_current_client_and_propagates(use_sdk):
    async def run():
        entered = asyncio.Event()
        clients = []
        registry = MCPToolRegistry()

        base = MCPClient if use_sdk else Client

        class WaitingClient(base):
            closes = 0

            async def list_tools(self, **kwargs):
                entered.set()
                await asyncio.Event().wait()

            async def __aexit__(self, *args):
                self.closes += 1
                if use_sdk:
                    return await super().__aexit__(*args)

        def factory(target):
            client = WaitingClient(target)
            clients.append(client)
            return client

        async def startup():
            async with AsyncExitStack() as stack:
                await connect_mcp_servers(
                    [MCPServerConfig("waiting", "waiting", MCPServer("waiting"))],
                    stack, registry, factory,
                )

        task = asyncio.create_task(startup())
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert clients[0].closes == 1
        assert registry.get("waiting_search") is None

    asyncio.run(run())


@pytest.mark.parametrize("failure", ["down", "bad-discovery"])
def test_required_failure_removes_closed_registrations_and_allows_restart(failure):
    async def run():
        registry = MCPToolRegistry()
        clients = []

        def factory(target):
            client = Client(target)
            clients.append(client)
            return client

        with pytest.raises((ConnectionError, RuntimeError)):
            async with AsyncExitStack() as stack:
                await connect_mcp_servers([
                    MCPServerConfig("healthy", "healthy", "healthy", True),
                    MCPServerConfig("required", "required", failure, True),
                ], stack, registry, factory)
        assert clients[0].closes == 1
        assert registry.get("healthy_search") is None

        async with AsyncExitStack() as stack:
            schemas = await connect_mcp_servers(
                [MCPServerConfig("healthy", "healthy", "healthy", True)],
                stack, registry, factory,
            )
            assert [schema["name"] for schema in schemas] == ["healthy_search"]
        assert registry.get("healthy_search") is None

    asyncio.run(run())


def test_optional_global_collision_fails_startup_and_preserves_other_ownership():
    async def run():
        registry = MCPToolRegistry()
        unrelated = object()
        registry.register_discovered_tools(unrelated, [SEARCH], "other")
        clients = []

        def factory(target):
            client = Client(target)
            clients.append(client)
            return client

        with pytest.raises(ToolNameCollisionError):
            async with AsyncExitStack() as stack:
                await connect_mcp_servers([
                    MCPServerConfig("first", "same", "first", True),
                    MCPServerConfig("optional", "same", "optional"),
                ], stack, registry, factory)
        assert all(client.closes == 1 for client in clients)
        assert registry.get("same_search") is None
        assert registry.get("other_search").client is unrelated

    asyncio.run(run())


@pytest.mark.parametrize("required", [False, True])
def test_discovery_deadline_closes_client_and_applies_dependency(required):
    async def run():
        registry = MCPToolRegistry()
        clients = []

        def factory(target):
            client = Client(target)
            clients.append(client)
            return client

        async def startup():
            async with AsyncExitStack() as stack:
                return await connect_mcp_servers([
                    MCPServerConfig("hung", "hung", "hung", required, 0.01),
                    MCPServerConfig("healthy", "healthy", "healthy", True),
                ], stack, registry, factory)

        if required:
            with pytest.raises(TimeoutError):
                await startup()
            assert len(clients) == 1
        else:
            schemas = await startup()
            assert [schema["name"] for schema in schemas] == ["healthy_search"]
        assert all(client.closes == 1 for client in clients)
        assert registry.get("healthy_search") is None
        assert registry.get("hung_search") is None

    asyncio.run(run())


def test_sdk_discovery_deadline_unwinds_sdk_scopes_in_the_same_task():
    async def run():
        clients = []

        class WaitingSDKClient(MCPClient):
            async def list_tools(self, **kwargs):
                await asyncio.Event().wait()

        def factory(target):
            client = WaitingSDKClient(target)
            clients.append(client)
            return client

        async with AsyncExitStack() as stack:
            schemas = await connect_mcp_servers(
                [MCPServerConfig("sdk", "sdk", MCPServer("sdk"), False, 0.02)],
                stack, MCPToolRegistry(), factory,
            )
            assert schemas == []
        assert clients[0]._connected_client is None

    asyncio.run(run())


def test_connection_deadline_allows_optional_dependency_to_be_skipped():
    async def run():
        class HungConnect(Client):
            async def __aenter__(self):
                try:
                    await asyncio.Event().wait()
                finally:
                    self.connect_cancelled = True

        client = HungConnect("hung")
        async with AsyncExitStack() as stack:
            schemas = await connect_mcp_servers(
                [MCPServerConfig("hung", "hung", "hung", False, 0.01)],
                stack, MCPToolRegistry(), lambda _: client,
            )
            assert schemas == []
        # Failed context entry owns its partial cleanup; __aexit__ is not
        # called for a context that has not finished __aenter__.
        assert client.connect_cancelled
        assert client.closes == 0

    asyncio.run(run())
