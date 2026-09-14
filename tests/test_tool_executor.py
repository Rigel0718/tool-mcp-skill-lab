import json
from types import SimpleNamespace

import pytest

from tools.tool_executor import execute_tool
from tools import (
    ToolNotFoundError,
    ToolArgumentsError, 
    ToolExecutionError,
)


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
