LIST_FILES_SCHEMA = {
    "type": "function",
    "name": "list_files",
    "description": "List files and directories in a given path.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "The path to list files from. "
                    "Use '.' for the current directory."
                ),
            }
        },
        "required": ["path"],
        "additionalProperties": False,
    },
    "strict": True,
}

READ_FILE_SCHEMA = {
    "type": "function",
    "name": "read_file",
    "description": "Read the contents of a file.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "The path of the file to read.",
            }
        },
        "required": ["path"],
        "additionalProperties": False,
    },
    "strict": True,
}


WRITE_FILE_SCHEMA = {
    "type": "function",
    "name": "write_file",
    "description": "Write content to a file.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "The path of the file to write to.",
            },
            "content": {
                "type": "string",
                "description": "The content to write to the file.",
            },
        },
        "required": ["path", "content"],
        "additionalProperties": False,
    },
    "strict": True,
}

RUN_COMMAND_SCHEMA = {
    "type": "function",
    "name": "run_command",
    "description": "Run a shell command.",
    "parameters": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to run.",
            }
        },
        "required": ["command"],
        "additionalProperties": False,
    },
    "strict": True,
}