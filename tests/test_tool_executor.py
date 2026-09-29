import json
import logging
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


def test_execute_unknown_tool(caplog):
    tool_call = SimpleNamespace(
        name="unknown_tool", arguments='{}'
    )
    
    with caplog.at_level(logging.ERROR, logger="tools.tool_executor"):
        with pytest.raises(ToolNotFoundError):
            execute_tool(tool_call)

    assert len(caplog.records) == 1
    assert "error_type=ToolNotFoundError" in caplog.records[0].getMessage()


def test_execute_tool_with_invalid_json_arguments(caplog):
    tool_call = SimpleNamespace(
        name="list_files", 
        arguments='{"path": "some_path"'
    )
    
    with caplog.at_level(logging.ERROR, logger="tools.tool_executor"):
        with pytest.raises(ToolArgumentsError):
            execute_tool(tool_call)

    assert len(caplog.records) == 1
    assert "error_type=ToolArgumentsError" in caplog.records[0].getMessage()


def test_execute_tool_with_failure(caplog):
    tool_call = SimpleNamespace(
        name="read_file", 
        arguments=json.dumps({"path": "non_existent_file.txt"})
    )
    
    with caplog.at_level(logging.ERROR, logger="tools.tool_executor"):
        with pytest.raises(ToolExecutionError):
            execute_tool(tool_call)

    assert len(caplog.records) == 1
    assert "error_type=ToolExecutionError" in caplog.records[0].getMessage()
    assert caplog.records[0].exc_info is not None


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

def test_execute_tool_with_timeout(monkeypatch, caplog):
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
    
    with caplog.at_level(logging.ERROR, logger="tools.tool_executor"):
        with pytest.raises(ToolTimeoutError):
            execute_tool(tool_call)

    assert len(caplog.records) == 1
    assert "error_type=ToolTimeoutError" in caplog.records[0].getMessage()


# --- test for normalize reult ---
def test_execute_tool_normalizes_list_result(tmp_path):
    (tmp_path / "example.txt").touch()

    tool_call = SimpleNamespace(
        name="list_files",
        arguments=json.dumps({"path": str(tmp_path)}),
    )

    result = execute_tool(tool_call)

    assert isinstance(result, str)  # Should be a JSON string
    assert "example.txt" in result
