
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


# --------------------------------------------------
# 1. Configuration
# --------------------------------------------------

PROJECT_DIR = Path(__file__).resolve().parent
SERVER_FILE = PROJECT_DIR / "mcp_server.py"

load_dotenv(PROJECT_DIR / ".env")

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise ValueError(
        "GEMINI_API_KEY not found. Check your .env file."
    )

if not SERVER_FILE.exists():
    raise FileNotFoundError(
        f"MCP server file not found: {SERVER_FILE}"
    )

client = genai.Client(api_key=API_KEY)

MODEL_NAME = "gemini-3.5-flash-lite"


# --------------------------------------------------
# 2. Convert MCP tools to Gemini tool declarations
# --------------------------------------------------

def create_gemini_tools(mcp_tools):
    function_declarations = []

    for tool in mcp_tools:
        function_declarations.append(
            types.FunctionDeclaration(
                name=tool.name,
                description=tool.description or "",
                parameters=tool.inputSchema,
            )
        )

    return [
        types.Tool(
            function_declarations=function_declarations
        )
    ]


# --------------------------------------------------
# 3. Start MCP client and connect to server
# --------------------------------------------------

async def main():
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER_FILE)],
        cwd=str(PROJECT_DIR),
    )

    print("Starting MCP connection...")

    async with stdio_client(server_params) as (
        read_stream,
        write_stream,
    ):
        async with ClientSession(
            read_stream,
            write_stream,
        ) as session:

            await session.initialize()

            # Discover tools from the MCP server
            tool_result = await session.list_tools()
            mcp_tools = tool_result.tools

            print("\nConnected to MCP successfully!")
            print("Available tools:")

            for tool in mcp_tools:
                print(f"- {tool.name}: {tool.description}")

            # Prepare Gemini tool definitions
            gemini_tools = create_gemini_tools(mcp_tools)

            chat = client.chats.create(
                model=MODEL_NAME,
                config=types.GenerateContentConfig(
                    tools=gemini_tools,
                    system_instruction=(
                        "You are an intelligent personal AI assistant powered by Gemini and MCP. "
                        "You have access to a suite of MCP tools: "
                        "- run_python_code: execute Python for data analysis (pandas, numpy), complex math, algorithms "
                        "- calculate: math operations (add, subtract, multiply, divide, power, modulo, sqrt) "
                        "- add_note, get_notes, search_notes, delete_note: persistent note management "
                        "- web_search, fetch_web_page: live search and webpage reading "
                        "- get_current_time: current date and time "
                        "- read_sample_file, list_allowed_files: workspace file access. "
                        "Always use these tools whenever appropriate. Never invent tool results."
                    ),
                ),
            )

            print("\nPersonal AI Assistant is ready!")
            print("Type 'exit' to stop.\n")

            # ------------------------------------------
            # 4. Chat loop
            # ------------------------------------------

            while True:
                try:
                    message = input(
                        "\nYou (type 'exit' to stop): "
                    ).strip()

                    # Ignore empty messages
                    if not message:
                        continue

                    if message.lower() == "exit":
                        print("Assistant: Goodbye!")
                        break

                    # Send the user's message to Gemini
                    response = chat.send_message(message)

                    # ----------------------------------
                    # 5. Handle Gemini tool calls
                    # ----------------------------------

                    while response.function_calls:
                        function_responses = []

                        for call in response.function_calls:
                            tool_name = call.name
                            arguments = dict(call.args or {})

                            # Ensure the requested tool exists
                            allowed_tools = {
                                tool.name for tool in mcp_tools
                            }

                            if tool_name not in allowed_tools:
                                tool_output = {
                                    "error": (
                                        f"Unknown tool: {tool_name}"
                                    )
                                }
                            else:
                                print(
                                    f"\n[MCP TOOL CALLED] "
                                    f"{tool_name}"
                                )

                                try:
                                    result = await session.call_tool(
                                        tool_name,
                                        arguments=arguments,
                                    )

                                    result_text = "\n".join(
                                        item.text
                                        for item in result.content
                                        if hasattr(item, "text")
                                    )

                                    if result.isError:
                                        tool_output = {
                                            "error": result_text
                                            or "Tool execution failed."
                                        }
                                    else:
                                        tool_output = {
                                            "result": result_text
                                        }

                                except Exception as tool_error:
                                    tool_output = {
                                        "error": str(tool_error)
                                    }

                            # Return the tool result to Gemini
                            function_responses.append(
                                types.Part.from_function_response(
                                    name=tool_name,
                                    response=tool_output,
                                )
                            )

                        # Continue the same Gemini conversation
                        response = chat.send_message(
                            function_responses
                        )

                    # ----------------------------------
                    # 6. Display final assistant response
                    # ----------------------------------

                    print(
                        "\nAssistant:",
                        response.text or "(No text response)",
                    )

                except (KeyboardInterrupt, EOFError):
                    print("\nAssistant: Goodbye!")
                    break

                except Exception as error:
                    print(
                        f"\nRequest failed: {error}"
                    )


# --------------------------------------------------
# 7. Run the application
# --------------------------------------------------

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nAssistant stopped.")
    except Exception as error:
        print(f"\nApplication failed: {error}")

