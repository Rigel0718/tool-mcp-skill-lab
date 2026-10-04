import json
import os
import shlex
from collections.abc import Collection, Mapping
from typing import Any

from context import ExecutionContext

from .mcp_tool_registry import MCP_TOOL_REGISTRY, MCPToolRegistry


class ApprovalPolicy:
    def __init__(
        self,
        auto_approved_commands: Mapping[str, Collection[str] | None],
        mcp_registry: MCPToolRegistry = MCP_TOOL_REGISTRY,
    ) -> None:
        self._auto_approved_commands = {
            command: None if subcommands is None else frozenset(subcommands)
            for command, subcommands in auto_approved_commands.items()
        }
        self._mcp_registry = mcp_registry

    def requires_approval(
        self,
        context: ExecutionContext,
        tool_call,
    ) -> bool:
        # Context is part of the policy boundary even though the initial policy
        # does not yet vary by user or execution environment.
        del context

        registration = self._mcp_registry.get(tool_call.name)
        if registration is not None:
            annotations = registration.annotations
            return not (
                annotations is not None
                and annotations.read_only_hint is True
                and annotations.destructive_hint is not True
            )

        if tool_call.name in {"list_files", "read_file"}:
            return False

        arguments = self._parse_arguments(tool_call.arguments)
        if arguments is None:
            # Invalid arguments remain the Tool Executor's responsibility.
            return False

        if tool_call.name == "write_file":
            if not self._has_expected_arguments(
                arguments,
                {"path": str, "content": str},
            ):
                return False
            return self._write_requires_approval(arguments)

        if tool_call.name == "run_command":
            if not self._has_expected_arguments(
                arguments,
                {"command": str},
            ):
                return False
            return self._command_requires_approval(arguments)

        return True

    @staticmethod
    def _parse_arguments(raw_arguments: str) -> Mapping[str, Any] | None:
        try:
            arguments = json.loads(raw_arguments)
        except (json.JSONDecodeError, TypeError):
            return None

        if not isinstance(arguments, dict):
            return None
        return arguments

    @staticmethod
    def _has_expected_arguments(
        arguments: Mapping[str, Any],
        expected: Mapping[str, type],
    ) -> bool:
        return arguments.keys() == expected.keys() and all(
            isinstance(arguments[name], expected_type)
            for name, expected_type in expected.items()
        )

    @staticmethod
    def _write_requires_approval(arguments: Mapping[str, Any]) -> bool:
        try:
            return os.path.exists(arguments["path"])
        except (OSError, ValueError):
            return True

    def _command_requires_approval(
        self,
        arguments: Mapping[str, Any],
    ) -> bool:
        command = arguments["command"]

        tokens = self._tokenize_single_command(command)
        if not tokens:
            return True

        allowed_subcommands = self._auto_approved_commands.get(tokens[0])
        if tokens[0] not in self._auto_approved_commands:
            return True

        if allowed_subcommands is None:
            return False

        return len(tokens) < 2 or tokens[1] not in allowed_subcommands

    @staticmethod
    def _tokenize_single_command(command: str) -> list[str] | None:
        if "\n" in command or "\r" in command:
            return None

        try:
            lexer = shlex.shlex(
                command,
                posix=True,
                punctuation_chars=";&|<>()`",
            )
            lexer.whitespace_split = True
            lexer.commenters = ""
            tokens = list(lexer)
        except ValueError:
            return None

        shell_punctuation = frozenset(";&|<>()`")
        if any(
            token and all(character in shell_punctuation for character in token)
            for token in tokens
        ):
            return None

        # shlex separates '$(' into '$' and '('; the parenthesis check above
        # rejects command substitution without attempting full shell analysis.
        return tokens
