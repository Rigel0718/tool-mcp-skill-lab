import logging
import os
import subprocess


logger = logging.getLogger(__name__)


def list_files(path="."):
    entries = []
    for entry in os.scandir(path):
        entries.append(
            entry.name + ("/" if entry.is_dir() else "")
        )
    return "\n".join(sorted(entries)) or "No files found."


def read_file(path):
    logger.debug("reading file path=%s", path)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    logger.debug("finished reading file path=%s characters=%d", path, len(content))
    return content


def write_file(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    return f"Saved {path} ({len(content)} characters)."


def run_command(command):
    result = subprocess.run(
        command, shell=True, capture_output=True, text=True, timeout=100
    )

    output = (result.stdout + result.stderr).strip()
    return output or f"(no output, exit code {result.returncode})"
