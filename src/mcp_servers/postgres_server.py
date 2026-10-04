from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from postgres import queries


mcp = MCPServer("postgres")
READ_ONLY_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def search_runs(
    status: str | None = None,
    limit: int = 10,
):
    """Search agent runs."""
    return queries.search_runs(status=status, limit=limit)


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def get_run(run_id: str):
    """Get an agent run by ID."""
    return queries.get_run(run_id)


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def get_traces(run_id: str):
    """Get traces for an agent run."""
    return queries.get_traces(run_id)



if __name__ == "__main__":
    mcp.run(transport="streamable-http")
