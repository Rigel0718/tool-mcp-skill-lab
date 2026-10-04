from typing import Any


def mcp_tool_to_openai_schema(
    tool: Any,
    global_name: str | None = None,
) -> dict[str, Any]:
    """Adapt one MCP Tool definition directly to an OpenAI function tool."""
    schema: dict[str, Any] = {
        "type": "function",
        "name": global_name or tool.name,
        "parameters": tool.input_schema,
    }
    if tool.description is not None:
        schema["description"] = tool.description
    return schema
