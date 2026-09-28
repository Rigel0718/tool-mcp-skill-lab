import sys
from pathlib import Path

# Keep this file directly runnable from a source checkout.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from code_agent import run_agent
from approval_config import AUTO_APPROVED_COMMANDS
from permission_config import TOOL_PERMISSIONS
from context import ExecutionContext
from hitl import ApprovalStatus, PendingApproval
from tools import (
    ApprovalPolicy,
    PermissionPolicy,
    ToolError,
    execute_approved_tool_via_gateway,
)

DEVELOPER_PROMPT = """You are a coding agent running in the user's terminal.
You can list files, read files, write files, and run shell commands.
Use your tools to complete the user's task, then briefly summarize what you did.
The working directory is the folder the user launched you from.
"""


def append_tool_output(messages, tool_call, output) -> None:
    messages.append({
        "type": "function_call_output",
        "call_id": tool_call.call_id,
        "output": output,
    })


def prompt_choice(prompt, choices) -> str:
    while True:
        choice = input(prompt).strip().lower()
        if choice in choices:
            return choice
        print(f"Please enter one of: {', '.join(choices)}")


def agent_run_orchestration_loop(
    messages,
    context,
    permission_policy,
    approval_policy,
) -> str | None:
    """Orchestrate one agent run across HITL interruptions and resumes."""
    while True:
        result = run_agent(
            messages,
            context,
            permission_policy,
            approval_policy,
        )
        if not isinstance(result, PendingApproval):
            return result

        request = result.approval_request
        tool_call = request.tool_call
        print(
            f"\nApproval required for tool '{tool_call.name}'.\n"
            f"Reason: {request.reason}\n"
            f"Arguments: {tool_call.arguments}"
        )
        decision = prompt_choice(
            "Approve or reject? [approve/reject]: ",
            ("approve", "reject"),
        )

        if decision == "approve":
            request.status = ApprovalStatus.APPROVED
            try:
                output = execute_approved_tool_via_gateway(
                    request,
                    context,
                    permission_policy,
                )
            except ToolError as error:
                output = f"Tool error: {error}"
            append_tool_output(messages, tool_call, output)
            continue

        request.status = ApprovalStatus.REJECTED
        append_tool_output(
            messages,
            tool_call,
            "Tool call rejected by the user.",
        )
        continuation = prompt_choice(
            "Continue this agent run? [continue/stop]: ",
            ("continue", "stop"),
        )
        if continuation == "stop":
            return None


def main():
    messages = [{"role": "developer", "content": DEVELOPER_PROMPT}]
    context = ExecutionContext(user_id="local_user")
    permission_policy = PermissionPolicy(TOOL_PERMISSIONS)
    approval_policy = ApprovalPolicy(AUTO_APPROVED_COMMANDS)
    print("Mini agent ready. Type 'exit' or 'quit' to stop.")

    while True:
        user_input = input("\nYou: ")
        if user_input.strip().lower() in ("exit", "quit"):
            break

        messages.append({"role": "user", "content": user_input})
        reply = agent_run_orchestration_loop(
            messages,
            context,
            permission_policy,
            approval_policy,
        )
        if reply is None:
            print("\nAgent run stopped.")
        else:
            print(f"\nAgent: {reply}")


if __name__ == "__main__":
    main()
