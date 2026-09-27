from context import ExecutionContext

from .approval_policy import ApprovalPolicy
from .permission_policy import PermissionPolicy
from .tool_errors import ApprovalRequiredError, PermissionDeniedError
from .tool_executor import execute_tool


def execute_tools_via_gateway(
    tool_call,
    context: ExecutionContext,
    permission_policy: PermissionPolicy,
    approval_policy: ApprovalPolicy,
):
    if not permission_policy.is_allowed(context, tool_call.name):
        raise PermissionDeniedError(
            f"User '{context.user_id}' is not allowed to use "
            f"tool '{tool_call.name}'"
        )

    if approval_policy.requires_approval(context, tool_call):
        raise ApprovalRequiredError(
            f"Tool call '{tool_call.name}' requires approval"
        )

    return execute_tool(tool_call)
