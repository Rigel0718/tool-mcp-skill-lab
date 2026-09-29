import logging
import time
from collections.abc import Callable
from typing import Any

from .retry_policy import RetryPolicy
from .tool_errors import ApprovalRequiredError, PermissionDeniedError


logger = logging.getLogger(__name__)


class RetryExecutor:
    """Execute one unchanged tool call, retrying only when policy permits."""

    def __init__(
        self,
        retry_policy: RetryPolicy | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._retry_policy = retry_policy or RetryPolicy()
        self._sleep = sleep

    def execute(self, tool_call, execute_tool: Callable[[Any], str]) -> str:
        retry_count = 0

        while True:
            attempt = retry_count + 1
            try:
                result = execute_tool(tool_call)
            except (ApprovalRequiredError, PermissionDeniedError):
                # These are Gateway policy/control outcomes, not execution
                # failures. They must never participate in retry handling.
                raise
            except Exception as error:
                error_type = type(error).__name__
                call_id = getattr(tool_call, "call_id", None)

                if not self._retry_policy.should_retry(
                    tool_call,
                    error,
                    retry_count,
                ):
                    logger.info(
                        "tool retry final_failure call_id=%s tool_name=%s "
                        "attempt=%d retry_count=%d error_type=%s",
                        call_id,
                        tool_call.name,
                        attempt,
                        retry_count,
                        error_type,
                    )
                    raise

                delay = self._retry_policy.delay_seconds(retry_count)
                next_attempt = attempt + 1
                logger.info(
                    "tool retry scheduled call_id=%s tool_name=%s "
                    "attempt=%d retry_count=%d error_type=%s "
                    "delay_seconds=%s",
                    call_id,
                    tool_call.name,
                    attempt,
                    retry_count + 1,
                    error_type,
                    delay,
                )
                self._sleep(delay)
                retry_count += 1
                logger.info(
                    "tool retry started call_id=%s tool_name=%s "
                    "attempt=%d retry_count=%d",
                    call_id,
                    tool_call.name,
                    next_attempt,
                    retry_count,
                )
                continue

            if retry_count:
                logger.info(
                    "tool retry success call_id=%s tool_name=%s "
                    "attempt=%d retry_count=%d",
                    getattr(tool_call, "call_id", None),
                    tool_call.name,
                    attempt,
                    retry_count,
                )
            return result
