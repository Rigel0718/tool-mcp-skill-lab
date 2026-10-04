import json
import logging
from jsonschema import validate, ValidationError

from concurrent.futures import ThreadPoolExecutor, TimeoutError

from .tool_registry import TOOL_REGISTRY
from .mcp_tool_registry import MCP_TOOL_REGISTRY
from .code_tools_schemas import TOOL_SCHEMA_REGISTRY
from .tool_errors import (
    MCPToolExecutionError,
    ToolArgumentsError,
    ToolError,
    ToolExecutionError,
    ToolNotFoundError,
    ToolTimeoutError,
)


TOOL_TIMEOUT = 5  # seconds
logger = logging.getLogger(__name__)


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



def normalize_result(result):
    if isinstance(result, str):
        return result.strip()

    try: 
        return json.dumps(
            result,
            ensure_ascii=False,
        )
    except (TypeError, ValueError) as e:
        raise ToolExecutionError(
            f"Tool returned a non-serializable result: {e}"
            f"Result: {result}"
        )



def validate_tool_arguments(tool_name: str, arguments: dict, schema=None):
    if schema is None:
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



def normalize_mcp_result(result):
    content = getattr(result, "content", [])
    if getattr(result, "is_error", False):
        detail = "\n".join(
            item.text for item in content if getattr(item, "type", None) == "text"
        ) or "MCP tool returned an error"
        raise MCPToolExecutionError(detail)

    structured_content = getattr(result, "structured_content", None)
    if structured_content is not None:
        return normalize_result(structured_content)

    values = []
    for item in content:
        if getattr(item, "type", None) == "text":
            values.append(item.text)
        elif hasattr(item, "model_dump"):
            values.append(item.model_dump(by_alias=True, exclude_none=True))
        else:
            values.append(item)

    if len(values) == 1:
        return normalize_result(values[0])
    return normalize_result(values)


async def execute_tool(tool_call):
    try:
        try:
            args = json.loads(tool_call.arguments)

        except json.JSONDecodeError as e:
            raise ToolArgumentsError(
                f"Invalid arguments for tool '{tool_call.name}': {e}"
            ) from e

        tool_func = TOOL_REGISTRY.get(tool_call.name)
        mcp_registration = MCP_TOOL_REGISTRY.get(tool_call.name)
        if tool_func is None and mcp_registration is None:
            raise ToolNotFoundError(
                f"Tool not found: {tool_call.name}"
            )

        validate_tool_arguments(
            tool_call.name,
            args,
            (
                None
                if tool_func is not None
                else mcp_registration.definition.input_schema
            ),
        )

        try:
            if tool_func is not None:
                result = execute_tool_with_timeout(
                    tool_func,
                    args,
                    timeout=TOOL_TIMEOUT
                )
                return normalize_result(result)

            result = await mcp_registration.client.call_tool(
                mcp_registration.remote_name,
                args,
            )
            return normalize_mcp_result(result)

        except TimeoutError as e:
            raise ToolTimeoutError(
                f"Tool '{tool_call.name}' timed out after"
                f" {TOOL_TIMEOUT} seconds"
            ) from e

        except ToolError:
            # ToolError subtypes are an explicit contract. In particular,
            # preserve TransientToolError so RetryPolicy can identify it.
            raise

        except Exception as e:
            raise ToolExecutionError(
                f"Error occurred while executing tool '{tool_call.name}': {e}"
            ) from e

    except ToolError as error:
        logger.error(
            "tool execution error tool_name=%s error_type=%s error_message=%s",
            tool_call.name,
            type(error).__name__,
            error,
            exc_info=isinstance(error, ToolExecutionError),
        )
        raise
