from context import ExecutionContext

from .permission_policy import PermissionPolicy
from .tool_errors import PermissionDeniedError
from .tool_executor import execute_tool


def execute_tools_via_gateway(
    tool_call,
    context: ExecutionContext,
    permission_policy: PermissionPolicy,
):
    if not permission_policy.is_allowed(context, tool_call.name):
        raise PermissionDeniedError(
            f"User '{context.user_id}' is not allowed to use "
            f"tool '{tool_call.name}'"
        )

    return execute_tool(tool_call)
