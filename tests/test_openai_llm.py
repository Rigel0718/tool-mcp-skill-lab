from types import SimpleNamespace

from code_agent import openai_llm


def test_tool_calls_are_requested_sequentially(monkeypatch):
    captured_request = None

    class FakeResponses:
        def create(self, **request):
            nonlocal captured_request
            captured_request = request
            return SimpleNamespace(output_text="Done")

    fake_client = SimpleNamespace(responses=FakeResponses())
    monkeypatch.setattr(openai_llm, "get_client", lambda: fake_client)

    openai_llm.call_openai_model([], tool_schemas=[{"type": "function"}])

    assert captured_request["parallel_tool_calls"] is False
