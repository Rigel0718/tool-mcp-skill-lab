from collections.abc import Iterable
from typing import Any

from tools.mcp_tool_registry import MCP_TOOL_REGISTRY, MCPToolRegistry

from .mcp_tool_schemas import mcp_tool_to_openai_schema


async def list_mcp_tools(client: Any) -> list[Any]:
    """Collect every page before mutating the application registry."""
    discovered = []
    result = await client.list_tools()
    discovered.extend(result.tools)
    cursor = getattr(result, "next_cursor", None)
    while cursor is not None:
        result = await client.list_tools(cursor=cursor)
        discovered.extend(result.tools)
        cursor = getattr(result, "next_cursor", None)
    return discovered


async def discover_mcp_tools(
    clients: Iterable[Any],
    registry: MCPToolRegistry = MCP_TOOL_REGISTRY,
    namespaces: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """Discover, register, and adapt all tools exposed by connected clients."""
    schemas: list[dict[str, Any]] = []
    clients = list(clients)
    namespaces = list(namespaces or ("" for _ in clients))
    if len(clients) != len(namespaces):
        raise ValueError("Each MCP client must have exactly one namespace")

    for client, namespace in zip(clients, namespaces, strict=True):
        discovered = await list_mcp_tools(client)

        server_schemas = [
            mcp_tool_to_openai_schema(
                tool,
                registry.global_name(namespace, tool.name),
            )
            for tool in discovered
        ]
        registry.register_discovered_tools(client, discovered, namespace)
        schemas.extend(server_schemas)

    return schemas
