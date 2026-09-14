import json
from types import SimpleNamespace

import pytest

from tools.tool_exacutor import exacute_tool


def test_exacute_tool_with_valid_tool_call(tmp_path):
    (tmp_path / "example.txt").touch()
    tool_call = SimpleNamespace(
        name="list_files",
        arguments=json.dumps({"path": str(tmp_path)}),
    )
    result = exacute_tool(tool_call)
    assert "example.txt" in result


def test_exacute_unknown_tool():
    tool_call = SimpleNamespace(name="unknown_tool", arguments='{}')
    with pytest.raises(ValueError, match="Tool not found: unknown_tool"):
        exacute_tool(tool_call)
