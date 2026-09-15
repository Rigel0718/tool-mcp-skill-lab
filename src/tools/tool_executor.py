import json
from jsonschema import validate, ValidationError

from concurrent.futures import ThreadPoolExecutor, TimeoutError

from .tool_registry import TOOL_REGISTRY
from .code_tools_schemas import TOOL_SCHEMA_REGISTRY
from .tool_errors import ToolNotFoundError, ToolArgumentsError, ToolExecutionError, ToolTimeoutError


TOOL_TIMEOUT = 5  # seconds

def execute_tool_with_timeout(
        tool_func, 
        args, 
        timeout=TOOL_TIMEOUT
):
    executor = ThreadPoolExecutor(max_workers=1)

    future = executor.submit(
        tool_func, 
        **args,
    )

    try:
        result = future.result(timeout=timeout)
    finally:
        executor.shutdown(wait=False)

    return result

def validate_tool_arguments(tool_name: str, arguments: dict):
    schema = TOOL_SCHEMA_REGISTRY[tool_name]["parameters"]

    try:
        validate(
            instance=arguments,
            schema=schema
        )

    except ValidationError as e:
        raise ToolArgumentsError(
            f"Invalid arguments for tool '{tool_name}': {e.message}"
        )



def execute_tool(tool_call):
    try:
        args = json.loads(tool_call.arguments)

    except json.JSONDecodeError as e:
        raise ToolArgumentsError(
            f"Invalid arguments for tool '{tool_call.name}': {e}"
        )

    try:
        tool_func = TOOL_REGISTRY[tool_call.name]
    except KeyError:
        raise ToolNotFoundError(
            f"Tool not found: {tool_call.name}"
        )

    validate_tool_arguments(
        tool_call.name, 
        args,
    )

    try:
        result = execute_tool_with_timeout(
            tool_func,
            args,
            timeout=TOOL_TIMEOUT
        )

    except TimeoutError:
        raise ToolTimeoutError(
            f"Tool '{tool_call.name}' timed out after"
            f" {TOOL_TIMEOUT} seconds"
        )
    
    except Exception as e:
        raise ToolExecutionError(
            f"Error occurred while executing tool '{tool_call.name}': {e}"
        )

    return result
