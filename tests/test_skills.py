import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from mcp.types import CallToolResult, TextContent, Tool, ToolAnnotations

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main
from code_agent import code_agent, skills
from context import ExecutionContext
from hitl import PendingApproval
from tools import ApprovalPolicy, PermissionPolicy, MCP_TOOL_REGISTRY
from tools import MCPCommunicationError, RetryExecutor, RetryPolicy
from tools.tool_executor import TOOL_REGISTRY


ROOT = Path(__file__).resolve().parents[1] / ".agents" / "skills"


def test_discovery_metadata_and_application_filtering():
    found = skills.discover_skills(ROOT)
    assert [s.name for s in found] == ["code-review"]
    assert "without modifying the code" in found[0].description
    assert "Workflow" not in found[0].description
    assert skills.discover_skills(ROOT, allowed_names=set()) == []
    assert skills.discover_skills(ROOT / "missing") == []


@pytest.mark.parametrize("header", ["no frontmatter", "---\nname: a\n",
                                        "---\nname: a\ndescription: 1\n---\n"])
def test_invalid_metadata_is_rejected(tmp_path, header):
    directory = tmp_path / "a"
    directory.mkdir()
    (directory / "SKILL.md").write_text(header)
    with pytest.raises(ValueError):
        skills.discover_skills(tmp_path)


def test_duplicate_names_are_rejected(tmp_path):
    for name in ("a", "b"):
        directory = tmp_path / name
        directory.mkdir()
        (directory / "SKILL.md").write_text("---\nname: same\ndescription: test\n---\n")
    with pytest.raises(ValueError, match="Duplicate"):
        skills.discover_skills(tmp_path)


@pytest.mark.parametrize("user_request,selection", [
    ("Explain what a Python list is", None),
    ("Review the current diff without editing files", "code-review"),
])
def test_progressive_disclosure_and_execution_context(monkeypatch, user_request, selection):
    candidates = skills.discover_skills(ROOT)
    history = [{"role": "developer", "content": main.DEVELOPER_PROMPT},
               {"role": "user", "content": user_request}]
    selection_inputs = []
    execution_inputs = []

    def select_model(messages, raw_response):
        selection_inputs.append(messages)
        return SimpleNamespace(output_text=json.dumps({"skill": selection}))

    def execute_model(messages, schemas, raw_response):
        execution_inputs.append(list(messages))
        return SimpleNamespace(output=[], output_text="Done")

    monkeypatch.setattr(skills, "call_openai_model", select_model)
    monkeypatch.setattr(code_agent, "call_openai_model", execute_model)
    assert asyncio.run(main.agent_run_orchestration_loop(
        history, ExecutionContext(user_id="user"), PermissionPolicy({}),
        ApprovalPolicy({}), candidate_skills=candidates,
    )) == "Done"
    assert "Review existing code" in str(selection_inputs)
    assert "Validate potential findings" not in str(selection_inputs)
    assert ("Validate potential findings" in str(execution_inputs)) == (selection is not None)
    assert "Authorization Boundaries" not in str(execution_inputs)
    assert "Validate potential findings" not in str(history)
    if selection:
        assert str(candidates[0].path.parent) in str(execution_inputs)


@pytest.mark.parametrize("answer", ['{"skill":"unknown"}', '[]', '{"skill":null,"extra":1}', 'not json'])
def test_selection_cannot_load_outside_candidates(monkeypatch, answer):
    monkeypatch.setattr(skills, "call_openai_model", lambda *a, **kw: SimpleNamespace(output_text=answer))
    with pytest.raises(ValueError):
        skills.select_skill([], skills.discover_skills(ROOT))


def test_no_candidates_needs_no_model(monkeypatch):
    monkeypatch.setattr(skills, "call_openai_model", lambda *a, **kw: pytest.fail("unexpected model call"))
    assert skills.select_skill([], []) is None


def test_only_selected_skill_body_is_loaded(monkeypatch, tmp_path):
    for name in ("chosen", "other"):
        directory = tmp_path / name
        directory.mkdir()
        (directory / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: routing metadata\n---\n{name} procedure"
        )
    candidates = skills.discover_skills(tmp_path)
    monkeypatch.setattr(skills, "call_openai_model", lambda messages, **kw: (
        SimpleNamespace(output_text='{"skill":"chosen"}')
    ))
    original_read = Path.read_text
    reads = []

    def read(path, **kwargs):
        reads.append(path)
        return original_read(path, **kwargs)

    monkeypatch.setattr(Path, "read_text", read)
    instructions = skills.load_skill(skills.select_skill([], candidates))
    assert "chosen procedure" in instructions
    assert "other procedure" not in instructions
    assert reads == [(tmp_path / "chosen" / "SKILL.md").resolve()]


def test_skill_reference_read_uses_local_gateway_and_permission(monkeypatch):
    skill = skills.discover_skills(ROOT)[0]
    reference = skill.path.parent / "references" / "security-review.md"
    call = SimpleNamespace(type="function_call", name="read_file",
                           arguments=json.dumps({"path": str(reference)}), call_id="ref")

    def run(allowed):
        history = [{"role": "user", "content": "Perform a security-focused code review"}]
        count = 0

        def model(messages, schemas, raw_response):
            nonlocal count
            count += 1
            assert "Validate potential findings" in str(messages)
            if count == 1:
                assert "Authorization Boundaries" not in str(messages)
                return SimpleNamespace(output=[call], output_text="")
            return SimpleNamespace(output=[], output_text="Reviewed")

        monkeypatch.setattr(code_agent, "call_openai_model", model)
        asyncio.run(code_agent.run_agent(
            history, ExecutionContext(user_id="user"),
            PermissionPolicy({"user": {"read_file"} if allowed else set()}),
            ApprovalPolicy({}), skill_instructions=skills.load_skill(skill),
        ))
        return history[-1]["output"]

    assert "Authorization Boundaries" in run(True)
    assert "not allowed" in run(False)


def test_selection_and_instructions_survive_approval_resume_once(monkeypatch):
    selections = []
    monkeypatch.setattr(skills, "call_openai_model", lambda *a, **kw: (
        selections.append(1) or SimpleNamespace(output_text='{"skill":"code-review"}')
    ))
    call = SimpleNamespace(type="function_call", name="run_command",
                           arguments='{"command":"git diff"}', call_id="diff")
    count = 0

    def model(messages, schemas, raw_response):
        nonlocal count
        count += 1
        assert "Validate potential findings" in str(messages)
        return SimpleNamespace(output=[call] if count == 1 else [], output_text="Reviewed")

    monkeypatch.setattr(code_agent, "call_openai_model", model)
    monkeypatch.setitem(TOOL_REGISTRY, "run_command", lambda command: "diff content")
    monkeypatch.setattr("builtins.input", lambda prompt: "approve")
    history = [{"role": "user", "content": "Review current changes"}]
    assert asyncio.run(main.agent_run_orchestration_loop(
        history, ExecutionContext(user_id="user"),
        PermissionPolicy({"user": {"run_command"}}), ApprovalPolicy({}),
        candidate_skills=skills.discover_skills(ROOT),
    )) == "Reviewed"
    assert selections == [1]
    assert history[-1]["output"] == "diff content"


@pytest.mark.parametrize("mode", ["retry", "denied", "approval"])
def test_selected_skill_mcp_uses_existing_policies(monkeypatch, mode):
    from code_agent.tool_discovery import discover_mcp_tools

    class Client:
        calls = 0

        async def list_tools(self):
            return SimpleNamespace(tools=[Tool(
                name="inspect", inputSchema={"type": "object"},
                annotations=ToolAnnotations(readOnlyHint=mode != "approval", idempotentHint=True),
            )])

        async def call_tool(self, name, args):
            self.calls += 1
            if self.calls == 1:
                raise MCPCommunicationError("temporary")
            return CallToolResult(content=[TextContent(type="text", text="recovered")])

    client = Client()
    MCP_TOOL_REGISTRY.clear()
    try:
        schemas = asyncio.run(discover_mcp_tools([client], namespaces=["remote"]))
        monkeypatch.setattr("tools.tool_gateway.retry_executor", RetryExecutor(
            RetryPolicy(initial_delay_seconds=0),
        ))
        call = SimpleNamespace(type="function_call", name="remote_inspect", arguments="{}", call_id="mcp")
        responses = iter([SimpleNamespace(output=[call], output_text=""),
                          SimpleNamespace(output=[], output_text="Reviewed")])

        def model(messages, received_schemas, raw_response):
            assert "Validate potential findings" in str(messages)
            assert received_schemas is schemas
            return next(responses)

        monkeypatch.setattr(code_agent, "call_openai_model", model)
        history = [{"role": "user", "content": "Review code"}]
        result = asyncio.run(code_agent.run_agent(
            history, ExecutionContext(user_id="user"),
            PermissionPolicy({"user": set() if mode == "denied" else {"remote_inspect"}}),
            ApprovalPolicy({}), schemas, skills.load_skill(skills.discover_skills(ROOT)[0]),
        ))
        if mode == "approval":
            assert isinstance(result, PendingApproval)
            assert client.calls == 0
        elif mode == "denied":
            assert "not allowed" in history[-1]["output"]
            assert client.calls == 0
        else:
            assert client.calls == 2
            assert history[-1]["output"] == "recovered"
    finally:
        MCP_TOOL_REGISTRY.clear()
