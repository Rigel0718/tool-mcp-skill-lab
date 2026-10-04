import asyncio
import logging
import os
import sys
from contextlib import AsyncExitStack
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
    MCP_TOOL_REGISTRY,
)
from tools.code_tools_schemas import TOOL_SCHEMAS
from mcp_clients import MCPServerConfig, connect_mcp_servers

DEVELOPER_PROMPT = """You are a coding agent running in the user's terminal.
You can list files, read files, write files, and run shell commands.
Use your tools to complete the user's task, then briefly summarize what you did.
The working directory is the folder the user launched you from.
"""


def configure_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


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


def configured_mcp_servers() -> list[MCPServerConfig]:
    """Build application dependencies separately from discovered capabilities."""
    servers = []
    if os.getenv("CODE_MCP_ENABLED") == "1":
        from mcp_servers.code_tools_server import mcp as code_mcp_server

        servers.append(MCPServerConfig(
            name="code-tools",
            namespace="code",
            server=code_mcp_server,
            required=True,
        ))

    mcp_server_url = os.getenv("MCP_SERVER_URL")
    if mcp_server_url:
        servers.append(MCPServerConfig(
            name="postgres",
            namespace="postgres",
            server=mcp_server_url,
            required=False,
        ))
    return servers


async def agent_run_orchestration_loop(
    messages,
    context,
    permission_policy,
    approval_policy,
    tool_schemas=TOOL_SCHEMAS,
) -> str | None:
    """Orchestrate one agent run across HITL interruptions and resumes."""
    while True:
        result = await run_agent(
            messages,
            context,
            permission_policy,
            approval_policy,
            tool_schemas,
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
                output = await execute_approved_tool_via_gateway(
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


async def async_main(log_level: int = logging.INFO):
    configure_logging(log_level)
    messages = [{"role": "developer", "content": DEVELOPER_PROMPT}]
    permission_policy = PermissionPolicy(TOOL_PERMISSIONS)
    approval_policy = ApprovalPolicy(AUTO_APPROVED_COMMANDS)
    async with AsyncExitStack() as stack:
        stack.callback(MCP_TOOL_REGISTRY.clear)
        mcp_schemas = await connect_mcp_servers(
            configured_mcp_servers(), stack
        )
        tool_schemas = [*TOOL_SCHEMAS, *mcp_schemas]
        print("Mini agent ready. Type 'exit' or 'quit' to stop.")

        while True:
            user_input = input("\nYou: ")
            if user_input.strip().lower() in ("exit", "quit"):
                break

            context = ExecutionContext(user_id="local_user")
            messages.append({"role": "user", "content": user_input})
            reply = await agent_run_orchestration_loop(
                messages,
                context,
                permission_policy,
                approval_policy,
                tool_schemas,
            )
            if reply is None:
                print("\nAgent run stopped.")
            else:
                print(f"\nAgent: {reply}")


def main(log_level: int = logging.INFO):
    asyncio.run(async_main(log_level))


if __name__ == "__main__":
    main()
