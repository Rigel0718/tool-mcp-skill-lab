from collections.abc import Collection, Mapping

from context import ExecutionContext


class PermissionPolicy:
    def __init__(
        self,
        allowed_tools_by_user: Mapping[str, Collection[str]],
    ) -> None:
        self._allowed_tools_by_user = {
            user_id: frozenset(tool_names)
            for user_id, tool_names in allowed_tools_by_user.items()
        }

    def is_allowed(
        self,
        context: ExecutionContext,
        tool_name: str,
    ) -> bool:
        allowed_tools = self._allowed_tools_by_user.get(
            context.user_id,
            frozenset(),
        )
        return tool_name in allowed_tools
