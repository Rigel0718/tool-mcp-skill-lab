import asyncio
import logging
from collections.abc import Iterable
from contextlib import AsyncExitStack
from typing import Any, Callable

from code_agent.tool_discovery import discover_mcp_tools
from tools.mcp_tool_registry import MCP_TOOL_REGISTRY, MCPToolRegistry
from tools.tool_errors import ToolNameCollisionError

from .client import MCPClient
from .server_config import MCPServerConfig


logger = logging.getLogger(__name__)


async def connect_mcp_servers(
    configs: Iterable[MCPServerConfig],
    stack: AsyncExitStack,
    registry: MCPToolRegistry = MCP_TOOL_REGISTRY,
    client_factory: Callable[[Any], Any] = MCPClient,
) -> list[dict[str, Any]]:
    """Connect and discover configured servers with required/optional semantics."""
    schemas: list[dict[str, Any]] = []
    for config in configs:
        try:
            async with AsyncExitStack() as server_stack:
                # Keep SDK context entry/exit in this task. wait_for() would
                # enter the SDK's AnyIO scopes in a different task.
                async with asyncio.timeout(config.startup_timeout_seconds):
                    client = await server_stack.enter_async_context(
                        client_factory(config.server)
                    )
                    server_schemas = await discover_mcp_tools(
                        [client], registry, [config.namespace]
                    )

                connected_stack = server_stack.pop_all()
                stack.push_async_callback(connected_stack.aclose)
                stack.callback(registry.unregister_client, client)
        except ToolNameCollisionError:
            # A global identity error is an application configuration error,
            # regardless of this server's availability dependency.
            raise
        except Exception:
            if config.required:
                logger.error(
                    "required MCP server startup failed server_name=%s",
                    config.name,
                )
                raise
            logger.warning(
                "optional MCP server unavailable server_name=%s",
                config.name,
                exc_info=True,
            )
            continue

        schemas.extend(server_schemas)
        logger.info(
            "MCP server ready server_name=%s tool_count=%d",
            config.name,
            len(server_schemas),
        )
    return schemas
