import json

from tool_registry import TOOL_REGISTRY

def exacute_tool(tool_call):
    try:
        args = json.loads(tool_call)

    except json.JSONDecodeError as e:
        raise ValueError(
            f"Invalid arguments for tool '{tool_call.name}': {e}"
        )

    try:
        tool_func = TOOL_REGISTRY[tool_call.name]
    except KeyError:
        raise ValueError(
            f"Tool not found: {tool_call.name}"
        )


    try:
        result = tool_func(**args)

    except TypeError as e:
            raise ValueError(
                f"Invalid arguments for tool '{tool_call.name}': {e}"
            )
    
    except Exception as e:
        raise RuntimeError(
            f"Error occurred while executing tool '{tool_call.name}': {e}"
        )

    return result