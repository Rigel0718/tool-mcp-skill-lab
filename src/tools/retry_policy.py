from dataclasses import dataclass, field

from .tool_errors import TransientToolError
from .mcp_tool_registry import MCP_TOOL_REGISTRY, MCPToolRegistry


DEFAULT_RETRY_SAFE_TOOLS = frozenset({"list_files", "read_file"})


@dataclass(frozen=True)
class RetryPolicy:
    """Decide whether a failed tool call may be retried."""

    max_retries: int = 2
    initial_delay_seconds: float = 1.0
    retry_safe_tools: frozenset[str] = field(
        default_factory=lambda: DEFAULT_RETRY_SAFE_TOOLS
    )
    mcp_registry: MCPToolRegistry = field(
        default=MCP_TOOL_REGISTRY,
        compare=False,
        repr=False,
    )

    def is_retry_safe(self, tool_name: str) -> bool:
        if tool_name in self.retry_safe_tools:
            return True

        registration = self.mcp_registry.get(tool_name)
        if registration is None or registration.annotations is None:
            return False

        annotations = registration.annotations
        if annotations.destructive_hint is True:
            return False
        return (
            annotations.idempotent_hint is True
            or annotations.read_only_hint is True
        )

    def should_retry(self, tool_call, error: Exception, retry_count: int) -> bool:
        return (
            isinstance(error, TransientToolError)
            and self.is_retry_safe(tool_call.name)
            and retry_count < self.max_retries
        )

    def delay_seconds(self, retry_count: int) -> float:
        """Return the delay before the next retry (zero-based retry count)."""
        return self.initial_delay_seconds * (2 ** retry_count)
