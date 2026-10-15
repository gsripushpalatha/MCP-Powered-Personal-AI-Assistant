import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PROJECT_DIR = Path(__file__).resolve().parent
SERVER_FILE = PROJECT_DIR / "mcp_server.py"


async def main():
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER_FILE)],
        cwd=str(PROJECT_DIR),
    )

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            print("Connected to MCP server successfully!\n")

            result = await session.list_tools()

            print("Available MCP tools:")
            for tool in result.tools:
                print(f"- {tool.name}: {tool.description}")

            print("\nTesting calculator tool (23 + 90)...")
            calculation = await session.call_tool(
                "calculate",
                arguments={
                    "a": 23,
                    "b": 90,
                    "operation": "add",
                },
            )

            for content in calculation.content:
                if hasattr(content, "text"):
                    print("Calculator output:", content.text)

            print("\nTesting get_current_time tool...")
            time_result = await session.call_tool("get_current_time", arguments={})
            for content in time_result.content:
                if hasattr(content, "text"):
                    print("Current time output:", content.text)

            print("\nTesting run_python_code tool...")
            py_result = await session.call_tool(
                "run_python_code",
                arguments={"code": "import math\nprint(f'Primes test: {[x for x in range(2, 25) if all(x % i != 0 for i in range(2, int(math.isqrt(x)) + 1))]}')"},
            )
            for content in py_result.content:
                if hasattr(content, "text"):
                    print("Python output:", content.text)


if __name__ == "__main__":
    asyncio.run(main())
