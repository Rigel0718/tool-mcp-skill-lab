from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .tool_errors import ToolNameCollisionError
from .tool_registry import TOOL_REGISTRY


@dataclass(frozen=True)
class MCPToolRegistration:
    global_name: str
    remote_name: str
    client: Any
    definition: Any

    @property
    def annotations(self):
        return getattr(self.definition, "annotations", None)


class MCPToolRegistry:
    """Keep discovered MCP tool definitions associated with their clients."""

    def __init__(self) -> None:
        self._registrations: dict[str, MCPToolRegistration] = {}

    def register_discovered_tools(
        self,
        client: Any,
        tools: Iterable[Any],
        namespace: str = "",
    ) -> None:
        tools = list(tools)
        names = [self.global_name(namespace, tool.name) for tool in tools]
        duplicate_names = {name for name in names if names.count(name) > 1}
        collisions = (
            set(names) & (set(TOOL_REGISTRY) | set(self._registrations))
        ) | duplicate_names
        if collisions:
            names_text = ", ".join(sorted(collisions))
            raise ToolNameCollisionError(
                f"Tool name collision detected: {names_text}"
            )

        for global_name, tool in zip(names, tools, strict=True):
            self._registrations[global_name] = MCPToolRegistration(
                global_name=global_name,
                remote_name=tool.name,
                client=client,
                definition=tool,
            )

    @staticmethod
    def global_name(namespace: str, remote_name: str) -> str:
        return f"{namespace}_{remote_name}" if namespace else remote_name

    def get(self, tool_name: str) -> MCPToolRegistration | None:
        return self._registrations.get(tool_name)

    def get_client(self, tool_name: str) -> Any | None:
        registration = self.get(tool_name)
        return registration.client if registration else None

    def get_definition(self, tool_name: str) -> Any | None:
        registration = self.get(tool_name)
        return registration.definition if registration else None

    def __contains__(self, tool_name: str) -> bool:
        return tool_name in self._registrations

    def clear(self) -> None:
        self._registrations.clear()

    def unregister_client(self, client: Any) -> None:
        """Remove only registrations owned by this connection."""
        names = [
            name for name, registration in self._registrations.items()
            if registration.client is client
        ]
        for name in names:
            del self._registrations[name]


MCP_TOOL_REGISTRY = MCPToolRegistry()
