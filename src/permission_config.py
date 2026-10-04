TOOL_PERMISSIONS = {
    "local_user": {
        "list_files",
        "read_file",
        "write_file",
        "run_command",
        # Global MCP identities grant application permission; schemas and
        # remote names still come only from tools/list discovery.
        "code_list_files",
        "code_read_file",
        "code_write_file",
        "code_run_command",
        "postgres_search_runs",
        "postgres_get_run",
        "postgres_get_traces",
    }
}
