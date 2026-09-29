from types import SimpleNamespace

import pytest

from tools import (
    ApprovalRequiredError,
    PermissionDeniedError,
    RetryPolicy,
    ToolArgumentsError,
    ToolExecutionError,
    ToolTimeoutError,
    TransientToolError,
)


def tool_call(name):
    return SimpleNamespace(name=name)


@pytest.mark.parametrize("name", ["list_files", "read_file"])
def test_transient_error_is_retryable_for_safe_tools(name):
    policy = RetryPolicy()

    assert policy.should_retry(
        tool_call(name),
        TransientToolError("temporary"),
        retry_count=0,
    )


@pytest.mark.parametrize("name", ["write_file", "run_command", "unknown"])
def test_transient_error_is_not_retryable_for_unsafe_tools(name):
    policy = RetryPolicy()

    assert not policy.should_retry(
        tool_call(name),
        TransientToolError("temporary"),
        retry_count=0,
    )


@pytest.mark.parametrize(
    "error",
    [
        ToolArgumentsError("invalid"),
        ToolExecutionError("permanent"),
        ToolTimeoutError("unknown completion"),
        PermissionDeniedError("denied"),
        ApprovalRequiredError("approval"),
        RuntimeError("unexpected"),
    ],
)
def test_only_explicit_transient_error_is_retryable(error):
    assert not RetryPolicy().should_retry(
        tool_call("read_file"),
        error,
        retry_count=0,
    )


def test_maximum_retry_count_is_two():
    policy = RetryPolicy()
    error = TransientToolError("temporary")
    call = tool_call("read_file")

    assert policy.should_retry(call, error, retry_count=0)
    assert policy.should_retry(call, error, retry_count=1)
    assert not policy.should_retry(call, error, retry_count=2)


def test_exponential_backoff_delays_are_one_then_two_seconds():
    policy = RetryPolicy()

    assert policy.delay_seconds(0) == 1
    assert policy.delay_seconds(1) == 2


def test_write_file_can_only_be_enabled_by_explicit_policy_configuration():
    policy = RetryPolicy(
        retry_safe_tools=frozenset({"list_files", "read_file", "write_file"})
    )

    assert policy.should_retry(
        tool_call("write_file"),
        TransientToolError("temporary"),
        retry_count=0,
    )
