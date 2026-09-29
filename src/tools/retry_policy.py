from dataclasses import dataclass, field

from .tool_errors import TransientToolError


DEFAULT_RETRY_SAFE_TOOLS = frozenset({"list_files", "read_file"})


@dataclass(frozen=True)
class RetryPolicy:
    """Decide whether a failed tool call may be retried."""

    max_retries: int = 2
    initial_delay_seconds: float = 1.0
    retry_safe_tools: frozenset[str] = field(
        default_factory=lambda: DEFAULT_RETRY_SAFE_TOOLS
    )

    def should_retry(self, tool_call, error: Exception, retry_count: int) -> bool:
        return (
            isinstance(error, TransientToolError)
            and tool_call.name in self.retry_safe_tools
            and retry_count < self.max_retries
        )

    def delay_seconds(self, retry_count: int) -> float:
        """Return the delay before the next retry (zero-based retry count)."""
        return self.initial_delay_seconds * (2 ** retry_count)
