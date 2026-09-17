import json
import subprocess
import sys
from types import SimpleNamespace
from pathlib import Path

from code_agent import code_agent


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_main_starts_and_exits_successfully():
    result = subprocess.run(
        [sys.executable, "main.py"],
        cwd=PROJECT_ROOT,
        input="exit\n",
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Mini agent ready" in result.stdout


def test_run_agent_executes_tool_and_returns_final_text(monkeypatch):
    responses = iter(
        [
            SimpleNamespace(
                output=[
                    SimpleNamespace(
                        type="function_call",
                        name="list_files",
                        arguments=json.dumps({"path": "."}),
                        call_id="call-1",
                    )
                ],
                output_text="",
            ),
            SimpleNamespace(output=[], output_text="Done"),
        ]
    )

    monkeypatch.setattr(
        code_agent,
        "call_openai_model",
        lambda history, schemas, raw_response: next(responses),
    )
    monkeypatch.setattr(code_agent, "execute_tool", lambda tool_call: '["a.py"]')
    history = [{"role": "user", "content": "List files"}]

    assert code_agent.run_agent(history) == "Done"
    assert history[-1] == {
        "type": "function_call_output",
        "call_id": "call-1",
        "output": '["a.py"]',
    }
