import asyncio
import logging
from types import SimpleNamespace

import pytest

from tools import (
    ApprovalRequiredError,
    PermissionDeniedError,
    RetryExecutor,
    ToolArgumentsError,
    ToolExecutionError,
    ToolTimeoutError,
    TransientToolError,
)


def execute_retry(executor, tool_call, operation):
    return asyncio.run(executor.execute(tool_call, operation))


def make_tool_call(name="read_file"):
    return SimpleNamespace(
        name=name,
        arguments='{"path": "secret.txt"}',
        call_id="call-1",
    )


def test_first_attempt_success_does_not_retry_or_sleep():
    calls = []
    sleeps = []
    tool_call = make_tool_call()

    result = execute_retry(RetryExecutor(sleep=sleeps.append),
        tool_call,
        lambda received: calls.append(received) or "content",
    )

    assert result == "content"
    assert calls == [tool_call]
    assert sleeps == []


@pytest.mark.parametrize("failures", [1, 2])
def test_retry_succeeds_on_first_or_second_retry(failures):
    calls = []
    sleeps = []
    tool_call = make_tool_call()

    def mock_tool(received):
        calls.append(received)
        if len(calls) <= failures:
            raise TransientToolError("temporary")
        return "content"

    result = execute_retry(
        RetryExecutor(sleep=sleeps.append), tool_call, mock_tool
    )

    assert result == "content"
    assert calls == [tool_call] * (failures + 1)
    assert sleeps == [1.0, 2.0][:failures]


def test_maximum_retries_reraises_last_error():
    errors = [
        TransientToolError("first"),
        TransientToolError("second"),
        TransientToolError("last"),
    ]
    calls = []
    sleeps = []

    def mock_tool(received):
        calls.append(received)
        raise errors[len(calls) - 1]

    with pytest.raises(TransientToolError) as caught:
        execute_retry(
            RetryExecutor(sleep=sleeps.append), make_tool_call(), mock_tool
        )

    assert caught.value is errors[-1]
    assert len(calls) == 3
    assert sleeps == [1.0, 2.0]


@pytest.mark.parametrize(
    "error",
    [
        ToolExecutionError("permanent"),
        ToolArgumentsError("invalid"),
        ToolTimeoutError("timeout"),
    ],
)
def test_non_retryable_error_is_reraised_immediately(error):
    calls = 0
    sleeps = []

    def mock_tool(received):
        nonlocal calls
        calls += 1
        raise error

    with pytest.raises(type(error)) as caught:
        execute_retry(
            RetryExecutor(sleep=sleeps.append), make_tool_call(), mock_tool
        )

    assert caught.value is error
    assert calls == 1
    assert sleeps == []


@pytest.mark.parametrize(
    "error",
    [
        PermissionDeniedError("denied"),
        ApprovalRequiredError("approval"),
    ],
)
def test_gateway_control_errors_bypass_retry_handling(error, caplog):
    calls = 0

    def mock_tool(received):
        nonlocal calls
        calls += 1
        raise error

    with caplog.at_level(logging.INFO, logger="tools.retry_executor"):
        with pytest.raises(type(error)) as caught:
            execute_retry(RetryExecutor(sleep=lambda delay: None),
                make_tool_call(),
                mock_tool,
            )

    assert caught.value is error
    assert calls == 1
    assert not caplog.records


@pytest.mark.parametrize("name", ["write_file", "run_command"])
def test_unsafe_tool_is_not_retried_for_transient_error(name):
    calls = 0

    def mock_tool(received):
        nonlocal calls
        calls += 1
        raise TransientToolError("temporary")

    with pytest.raises(TransientToolError):
        execute_retry(RetryExecutor(sleep=lambda delay: None),
            make_tool_call(name),
            mock_tool,
        )

    assert calls == 1


def test_retry_logging_contains_metadata_without_arguments(caplog):
    calls = 0
    tool_call = make_tool_call()

    def mock_tool(received):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TransientToolError("sensitive failure detail")
        return "sensitive result"

    with caplog.at_level(logging.INFO, logger="tools.retry_executor"):
        execute_retry(
            RetryExecutor(sleep=lambda delay: None), tool_call, mock_tool
        )

    messages = [record.getMessage() for record in caplog.records]
    assert any("tool retry scheduled" in message for message in messages)
    assert any("tool retry started" in message for message in messages)
    assert any("tool retry success" in message for message in messages)
    assert any("call_id=call-1" in message for message in messages)
    assert any("tool_name=read_file" in message for message in messages)
    assert any("error_type=TransientToolError" in message for message in messages)
    assert any("delay_seconds=1.0" in message for message in messages)
    assert all("secret.txt" not in message for message in messages)
    assert all("sensitive failure detail" not in message for message in messages)
    assert all("sensitive result" not in message for message in messages)


def test_final_failure_is_logged_after_retries_are_exhausted(caplog):
    with caplog.at_level(logging.INFO, logger="tools.retry_executor"):
        with pytest.raises(TransientToolError):
            execute_retry(RetryExecutor(sleep=lambda delay: None),
                make_tool_call(),
                lambda received: (_ for _ in ()).throw(
                    TransientToolError("temporary")
                ),
            )

    final_messages = [
        record.getMessage()
        for record in caplog.records
        if "final_failure" in record.getMessage()
    ]
    assert len(final_messages) == 1
    assert "attempt=3" in final_messages[0]
    assert "retry_count=2" in final_messages[0]
