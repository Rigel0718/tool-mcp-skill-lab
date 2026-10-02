from typing import Any

from mcp import Client


class MCPClient:
    """Own one MCP connection while leaving transport details to the SDK."""

    def __init__(self, server: Any, **client_options: Any) -> None:
        self._client = Client(server, **client_options)
        self._connected_client: Client | None = None

    async def __aenter__(self) -> "MCPClient":
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
        return await self._connection().list_tools(cursor=cursor)

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
    ):
        return await self._connection().call_tool(name, arguments)
