from enum import Enum
from context import ExecutionContext
from tools import execute_tool


class ToolPermission(Enum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"


TOOL_PERMISSION_REGISTRY = {
    "list_files": ToolPermission.READ,
    "read_file": ToolPermission.READ,
    "write_file": ToolPermission.WRITE,
    "run_command": ToolPermission.EXECUTE,
}


def execute_tools_via_gateway(
        tool_call,
        context : ExecutionContext,
):
    return execute_tool(tool_call)