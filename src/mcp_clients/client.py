import asyncio
import os

from mcp import Client, StdioServerParameters

server = StdioServerParameters(
    command="uv",
    args=[
        "run",
        "python",
        "-m",
        "mcp_servers.code_tools_server",
    ],
    env={
        **os.environ,
        "PYTHONPATH": "src",
    },
)

async def main():
    async with Client(server) as client:
        result = await client.list_tools()

        # for tool in result.tools:
        #     print(f"name: {tool.name}")
        #     print(f"description: {tool.description}")
        #     print(f"input_schema: {tool.input_schema}")
        #     print()

        # result =  await client.call_tool(
        #             "write_file",
        #             {"path":"./study/test.txt",
        #              "content":"HELLO"}
        #         )
        # result = await client.call_tool(
        #     "run_command",
        #         {
        #         "command": "uv run pytest tests/test_tool_executor.py -q"
        #         },
        #     )

        # # print(result.content[0].text)
        print(result,"\n")
        print(type(result))

if __name__ == "__main__":
    asyncio.run(main())
