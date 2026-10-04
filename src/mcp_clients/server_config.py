from dataclasses import dataclass
from math import isfinite
from typing import Any


@dataclass(frozen=True)
class MCPServerConfig:
    """Application-level configuration for one MCP server dependency."""

    name: str
    namespace: str
    server: Any
    required: bool = False
    startup_timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if not isfinite(self.startup_timeout_seconds) or self.startup_timeout_seconds <= 0:
            raise ValueError("MCP startup timeout must be finite and positive")
