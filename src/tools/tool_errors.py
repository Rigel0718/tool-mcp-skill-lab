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


class ToolTimeoutError(ToolError):
    pass


class PermissionDeniedError(ToolError):
    pass


class ApprovalRequiredError(ToolError):
    pass
