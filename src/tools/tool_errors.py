# tools/errors.py

class ToolError(Exception):
    pass


class ToolNotFoundError(ToolError):
    pass


class ToolArgumentsError(ToolError):
    pass


class ToolExecutionError(ToolError):
    pass


class ToolTimeoutError(ToolError):
    pass