TOOL_PERMISSIONS = {
    "local_user": {
        "list_files",
        "read_file",
        "write_file",
        "run_command",
        # Tools discovered from the PostgreSQL MCP server. Listing them here
        # grants permission; their schemas still come only from tools/list.
        "search_runs",
        "get_run",
        "get_traces",
    }
}
