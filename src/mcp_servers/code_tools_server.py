from mcp.server.mcpserver import MCPServer
from tools import code_tools

mcp = MCPServer("code-tools")

@mcp.tool()
def list_files(path: str) -> str:
    """List files and directories in the given path."""
    return code_tools.list_files(path)


@mcp.tool()
def read_file(path: str) -> str:
    """Read the contents of a file."""
    return code_tools.read_file(path)


@mcp.tool()
def write_file(path: str, content: str):
    """Write content to a file."""
    return code_tools.write_file(path,content)


@mcp.tool()
def run_command(command: str):
    """Run a shell command."""
    return code_tools.run_command(command)


if __name__ == "__main__":
    mcp.run(transport="stdio")

