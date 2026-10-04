# tools/errors.py

class ToolError(Exception):
    pass


class ToolNotFoundError(ToolError):
    pass


class ToolNameCollisionError(ToolError):
    pass


class ToolArgumentsError(ToolError):
    pass


class ToolExecutionError(ToolError):
    pass


class TransientToolError(ToolExecutionError):
    """A tool failure that is explicitly safe to consider for retry."""


class MCPCommunicationError(TransientToolError):
    """A transient failure while communicating with an MCP server."""


class MCPToolExecutionError(ToolExecutionError):
    """An MCP tool returned a protocol-level execution failure."""


class ToolTimeoutError(ToolError):
    pass


class PermissionDeniedError(ToolError):
    pass


class ApprovalRequiredError(ToolError):
    pass
