from tools.code_tools import read_file, write_file, list_files, run_command


TOOL_REGISTRY = {
    "list_files": list_files,
    "read_file": read_file,
    "write_file": write_file,
    "run_command": run_command, 
}
