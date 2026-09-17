import json
from typing import Any

from tools import ToolError, execute_tool
from tools import TOOL_SCHEMAS
from tools import execute_tools_via_gateway
from context import ExecutionContext

from .openai_llm import call_openai_model


MAX_TOOL_ROUNDS = 20
test_context = ExecutionContext(user_id="local_user")


def run_agent(
    history: list[Any],
    tool_schemas: list[dict[str, Any]] = TOOL_SCHEMAS,
) -> str:
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
                result = execute_tools_via_gateway(tool_call)
            except ToolError as e:
                # Returning tool failures lets the model recover or explain them.
                result = f"Tool error: {e}"

            history.append({
                "type": "function_call_output",
                "call_id": tool_call.call_id,
                "output": result,
            })

    raise RuntimeError(f"Agent exceeded {MAX_TOOL_ROUNDS} tool rounds")
