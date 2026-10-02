from collections.abc import Iterable
from typing import Any

from tools.mcp_tool_registry import MCP_TOOL_REGISTRY, MCPToolRegistry

from .mcp_tool_schemas import mcp_tool_to_openai_schema


async def discover_mcp_tools(
    clients: Iterable[Any],
    registry: MCPToolRegistry = MCP_TOOL_REGISTRY,
) -> list[dict[str, Any]]:
    """Discover, register, and adapt all tools exposed by connected clients."""
    schemas: list[dict[str, Any]] = []
    for client in clients:
        discovered = []
        result = await client.list_tools()
        discovered.extend(result.tools)

        cursor = getattr(result, "next_cursor", None)
        while cursor is not None:
            result = await client.list_tools(cursor=cursor)
            discovered.extend(result.tools)
            cursor = getattr(result, "next_cursor", None)

        registry.register_discovered_tools(client, discovered)
        schemas.extend(mcp_tool_to_openai_schema(tool) for tool in discovered)

    return schemas
