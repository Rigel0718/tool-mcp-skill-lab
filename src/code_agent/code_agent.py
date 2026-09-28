from typing import Any

from context import ExecutionContext
from hitl import ApprovalRequest, PendingApproval
from tools import (
    ApprovalPolicy,
    ApprovalRequiredError,
    PermissionPolicy,
    ToolError,
    execute_tools_via_gateway,
)
from tools.code_tools_schemas import TOOL_SCHEMAS

from .openai_llm import call_openai_model


MAX_TOOL_ROUNDS = 20


def run_agent(
    history: list[Any],
    context: ExecutionContext,
    permission_policy: PermissionPolicy,
    approval_policy: ApprovalPolicy,
    tool_schemas: list[dict[str, Any]] = TOOL_SCHEMAS,
) -> str | PendingApproval:
    """Run the model/tool loop and append all new items to ``history``."""
    for _ in range(MAX_TOOL_ROUNDS):
        response = call_openai_model(history, tool_schemas, raw_response=True)
        history.extend(response.output)

        tool_calls = [
            item for item in response.output if item.type == "function_call"
        ]
        if not tool_calls:
            return response.output_text

        for tool_call in tool_calls:
            try:
                result = execute_tools_via_gateway(
                    tool_call,
                    context,
                    permission_policy,
                    approval_policy,
                )
            except ApprovalRequiredError as error:
                return PendingApproval(
                    approval_request=ApprovalRequest(
                        tool_call=tool_call,
                        reason=str(error),
                    )
                )
            except ToolError as e:
                # Returning tool failures lets the model recover or explain them.
                result = f"Tool error: {e}"

            history.append({
                "type": "function_call_output",
                "call_id": tool_call.call_id,
                "output": result,
            })

    raise RuntimeError(f"Agent exceeded {MAX_TOOL_ROUNDS} tool rounds")
