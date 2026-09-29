import logging

from context import ExecutionContext
from hitl import ApprovalRequest, ApprovalStatus

from .approval_policy import ApprovalPolicy
from .permission_policy import PermissionPolicy
from .tool_errors import ApprovalRequiredError, PermissionDeniedError, ToolError
from .tool_executor import execute_tool
from .retry_executor import RetryExecutor


logger = logging.getLogger(__name__)
retry_executor = RetryExecutor()


def _log_execution(tool_call, context: ExecutionContext, result: str) -> None:
    logger.info(
        "tool execution user_id=%s run_id=%s call_id=%s tool_name=%s result=%s",
        context.user_id,
        context.run_id,
        tool_call.call_id,
        tool_call.name,
        result,
    )


def execute_tools_via_gateway(
    tool_call,
    context: ExecutionContext,
    permission_policy: PermissionPolicy,
    approval_policy: ApprovalPolicy,
):
    _log_execution(tool_call, context, "started")

    if not permission_policy.is_allowed(context, tool_call.name):
        _log_execution(tool_call, context, "permission_denied")
        raise PermissionDeniedError(
            f"User '{context.user_id}' is not allowed to use "
            f"tool '{tool_call.name}'"
        )

    if approval_policy.requires_approval(context, tool_call):
        _log_execution(tool_call, context, "approval_required")
        raise ApprovalRequiredError(
            f"Tool call '{tool_call.name}' requires approval"
        )

    try:
        result = retry_executor.execute(tool_call, execute_tool)
    except ToolError:
        _log_execution(tool_call, context, "failed")
        raise

    _log_execution(tool_call, context, "success")
    return result


def execute_approved_tool_via_gateway(
    approval_request: ApprovalRequest,
    context: ExecutionContext,
    permission_policy: PermissionPolicy,
):
    if approval_request.status is not ApprovalStatus.APPROVED:
        raise ValueError("Approval request must be approved before execution")

    tool_call = approval_request.tool_call
    _log_execution(tool_call, context, "started")

    if not permission_policy.is_allowed(context, tool_call.name):
        _log_execution(tool_call, context, "permission_denied")
        raise PermissionDeniedError(
            f"User '{context.user_id}' is not allowed to use "
            f"tool '{tool_call.name}'"
        )

    try:
        result = retry_executor.execute(tool_call, execute_tool)
    except ToolError:
        _log_execution(tool_call, context, "failed")
        raise

    _log_execution(tool_call, context, "success")
    return result
