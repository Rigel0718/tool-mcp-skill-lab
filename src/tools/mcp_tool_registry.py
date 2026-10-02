from collections.abc import Iterable
from typing import Any

from .tool_errors import ToolNameCollisionError
from .tool_registry import TOOL_REGISTRY


class MCPToolRegistry:
    """Keep discovered MCP tool definitions associated with their clients."""

    def __init__(self) -> None:
        self._clients: dict[str, Any] = {}
        self._definitions: dict[str, Any] = {}

    def register_discovered_tools(
        self,
        client: Any,
        tools: Iterable[Any],
    ) -> None:
        tools = list(tools)
        names = [tool.name for tool in tools]
        duplicate_names = {name for name in names if names.count(name) > 1}
        collisions = (
            set(names) & (set(TOOL_REGISTRY) | set(self._clients))
        ) | duplicate_names
        if collisions:
            names_text = ", ".join(sorted(collisions))
            raise ToolNameCollisionError(
                f"Tool name collision detected: {names_text}"
            )

        for tool in tools:
            self._clients[tool.name] = client
            self._definitions[tool.name] = tool

    def get_client(self, tool_name: str) -> Any | None:
        return self._clients.get(tool_name)

    def get_definition(self, tool_name: str) -> Any | None:
        return self._definitions.get(tool_name)

    def __contains__(self, tool_name: str) -> bool:
        return tool_name in self._clients

    def clear(self) -> None:
        self._clients.clear()
        self._definitions.clear()


MCP_TOOL_REGISTRY = MCPToolRegistry()
