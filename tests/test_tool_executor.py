import json
from types import SimpleNamespace

import time
import pytest

from tools.tool_executor import execute_tool
from tools import (
    ToolNotFoundError,
    ToolArgumentsError, 
    ToolExecutionError,
    ToolTimeoutError,
)

from tools.tool_registry import TOOL_REGISTRY
from tools.code_tools_schemas import TOOL_SCHEMA_REGISTRY


def test_execute_tool_with_valid_tool_call(tmp_path):
    (tmp_path / "example.txt").touch()
    tool_call = SimpleNamespace(
        name="list_files",
        arguments=json.dumps({"path": str(tmp_path)}),
    )
    result = execute_tool(tool_call)
    assert "example.txt" in result


def test_execute_unknown_tool():
    tool_call = SimpleNamespace(
        name="unknown_tool", arguments='{}'
    )
    
    with pytest.raises(ToolNotFoundError):
        execute_tool(tool_call)


def test_execute_tool_with_invalid_json_arguments():
    tool_call = SimpleNamespace(
        name="list_files", 
        arguments='{"path": "some_path"'
    )
    
    with pytest.raises(ToolArgumentsError):
        execute_tool(tool_call)


def test_execute_tool_with_failure():
    tool_call = SimpleNamespace(
        name="read_file", 
        arguments=json.dumps({"path": "non_existent_file.txt"})
    )
    
    with pytest.raises(ToolExecutionError):
        execute_tool(tool_call)


#------ validate_tool_arguments tests -----
def test_execute_tool_with_missing_required_argument():
    tool_call = SimpleNamespace(
        name="list_files", 
        arguments=json.dumps({}),
    )
    
    with pytest.raises(ToolArgumentsError):
        execute_tool(tool_call)


def test_execute_tool_with_invalid_argument_type():
    tool_call = SimpleNamespace(
        name="list_files", 
        arguments=json.dumps({"path": 123}),
    )
    
    with pytest.raises(ToolArgumentsError):
        execute_tool(tool_call)


# --- test for tool timeout ---

def test_execute_tool_with_timeout(monkeypatch):
    def slow_tool():
        time.sleep(10)  # Simulate long-running tool
        return "done"        


    monkeypatch.setitem(
        TOOL_REGISTRY, 
        "slow_tool", 
        slow_tool,
    )

    monkeypatch.setitem(
        TOOL_SCHEMA_REGISTRY, 
        "slow_tool", 
        {
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
            "strict": True,
        }
    )

    monkeypatch.setattr(
        "tools.tool_executor.TOOL_TIMEOUT",
        0.1,  # Set a very short timeout for testing
    )
    
    tool_call = SimpleNamespace(
        name="slow_tool", 
        arguments=json.dumps({})
    )
    
    with pytest.raises(ToolTimeoutError):
        execute_tool(tool_call)


# --- test for normalize reult ---
def test_execute_tool_normalizes_list_result(tmp_path):
    (tmp_path / "example.txt").touch()

    tool_call = SimpleNamespace(
        name="list_files",
        arguments=json.dumps({"path": str(tmp_path)}),
    )

    result = execute_tool(tool_call)

    assert isinstance(result, str)  # Should be a JSON string

    parsed_result = json.loads(result)
    assert "example.txt" in parsed_result