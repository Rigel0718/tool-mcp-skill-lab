import json
from types import SimpleNamespace

from tools import execute_tools_via_gateway
from context import ExecutionContext

def test_execute_tools_via_gateway(tmp_path):
    test_context = ExecutionContext(user_id="test_user")
    (tmp_path / "example.txt").touch()

    test_tool_call = SimpleNamespace(
        type="function_call",
        name="list_files",
        arguments=json.dumps({"path": str(tmp_path)}),
        call_id="call-1",
    )

    result = execute_tools_via_gateway(test_tool_call, test_context)

    assert result == "example.txt"
