from contextlib import AsyncExitStack, asynccontextmanager
from contextvars import ContextVar
from typing import Any

import anyio
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client
from mcp.shared.exceptions import MCPError
from mcp_types import (
    CONNECTION_CLOSED,
    INTERNAL_ERROR,
    REQUEST_TIMEOUT,
    JSONRPCError,
    jsonrpc_message_adapter,
)

from tools.tool_errors import MCPCommunicationError, MCPToolExecutionError


COMMUNICATION_ERROR_CODES = frozenset({CONNECTION_CLOSED, REQUEST_TIMEOUT})


def translate_mcp_exception(
    error: Exception, *, http_status: int | None = None,
) -> Exception:
    """Translate SDK/transport failures without making every MCP error retryable."""
    if isinstance(error, MCPError):
        if error.code == INTERNAL_ERROR and http_status is not None:
            return MCPCommunicationError(f"MCP server unavailable: HTTP {http_status}")
        if error.code in COMMUNICATION_ERROR_CODES:
            return MCPCommunicationError(str(error))
        return MCPToolExecutionError(str(error))

    if isinstance(error, httpx2.HTTPStatusError):
        if error.response.status_code >= 500:
            return MCPCommunicationError(str(error))
        return MCPToolExecutionError(str(error))

    communication_types = (
        TimeoutError,
        ConnectionError,
        OSError,
        anyio.BrokenResourceError,
        anyio.ClosedResourceError,
        anyio.EndOfStream,
        httpx2.TimeoutException,
        httpx2.NetworkError,
    )
    if isinstance(error, communication_types):
        return MCPCommunicationError(str(error))

    nested = getattr(error, "exceptions", ())
    if nested and all(
        isinstance(
            translate_mcp_exception(item, http_status=http_status),
            MCPCommunicationError,
        )
        for item in nested
    ):
        return MCPCommunicationError(str(error))

    return MCPToolExecutionError(str(error))


class MCPClient:
    """Own one MCP connection while leaving transport details to the SDK."""

    def __init__(
        self,
        server: Any,
        *,
        http_client: httpx2.AsyncClient | None = None,
        **client_options: Any,
    ) -> None:
        # The SDK propagates request context through its transport tasks.
        # A mutable per-operation cell retains status without changing MCP
        # messages or confusing simultaneous calls to this connection.
        self._http_failure: ContextVar[dict[str, int | None] | None] = ContextVar(
            "mcp_http_failure", default=None
        )
        target = self._http_transport(server, http_client) if isinstance(server, str) else server
        self._client = Client(target, **client_options)
        self._connected_client: Client | None = None

    async def _observe_http_response(self, response: httpx2.Response) -> None:
        state = self._http_failure.get()
        if state is None or response.request.method != "POST":
            return
        state["status"] = None
        if response.status_code < 500:
            return
        # Preserve genuine JSON-RPC server errors: HTTP 500 can legitimately
        # carry INTERNAL_ERROR, which does not mean a transient outage.
        message = None
        if response.headers.get("content-type", "").lower().startswith("application/json"):
            body = await response.aread()
            try:
                message = jsonrpc_message_adapter.validate_json(body, by_name=False)
            except ValueError:
                pass
        if not isinstance(message, JSONRPCError):
            state["status"] = response.status_code

    @asynccontextmanager
    async def _http_transport(self, url: str, http_client: httpx2.AsyncClient | None):
        async with AsyncExitStack() as stack:
            client = http_client
            if client is None:
                client = await stack.enter_async_context(create_mcp_http_client())
            # An injected HTTP client stays caller-owned; only our hook and
            # MCP streams belong to this connection.
            hooks = client.event_hooks["response"]
            hooks.append(self._observe_http_response)
            stack.callback(hooks.remove, self._observe_http_response)
            streams = await stack.enter_async_context(
                streamable_http_client(url, http_client=client)
            )
            yield streams

    @asynccontextmanager
    async def _operation(self):
        state: dict[str, int | None] = {"status": None}
        token = self._http_failure.set(state)
        try:
            yield
        except Exception as error:
            raise translate_mcp_exception(error, http_status=state["status"]) from error
        finally:
            self._http_failure.reset(token)

    async def __aenter__(self) -> "MCPClient":
        async with self._operation():
            self._connected_client = await self._client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        try:
            await self._client.__aexit__(exc_type, exc, traceback)
        finally:
            self._connected_client = None

    def _connection(self) -> Client:
        if self._connected_client is None:
            raise RuntimeError("MCP client is not connected")
        return self._connected_client

    async def list_tools(self, *, cursor: str | None = None):
        async with self._operation():
            return await self._connection().list_tools(cursor=cursor)

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
    ):
        async with self._operation():
            return await self._connection().call_tool(name, arguments)
