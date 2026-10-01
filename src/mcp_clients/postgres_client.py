import asyncio

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def main():
    async with streamable_http_client(
        "http://127.0.0.1:8000/mcp"
    ) as (read_stream, write_stream):
        async with ClientSession(
            read_stream,
            write_stream,
        ) as session:
            await session.initialize()

            # Tool Discovery
            tools = await session.list_tools()

            print("=== Tools ===")
            for tool in tools.tools:
                print(tool.name)

            # search_runs
            print("\n=== Runs ===")

            result = await session.call_tool(
                "search_runs",
                {
                    "limit": 10,
                },
            )

            for content in result.content:
                print(content.text)

            # get_run
            print("\n=== Run ===")

            result = await session.call_tool(
                "get_run",
                {
                    "run_id": "run-002",
                },
            )

            for content in result.content:
                print(content.text)

            # get_traces
            print("\n=== Traces ===")

            result = await session.call_tool(
                "get_traces",
                {
                    "run_id": "run-002",
                },
            )

            for content in result.content:
                print(content.text)


if __name__ == "__main__":
    asyncio.run(main())