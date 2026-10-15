from mcp.server.fastmcp import FastMCP
import tools

# Create the FastMCP server instance
mcp = FastMCP("Personal AI Assistant")


@mcp.tool()
def calculate(a: float, b: float = 0.0, operation: str = "add") -> float | str:
    """Perform mathematical calculations. Operations: 'add', 'subtract', 'multiply', 'divide', 'power', 'modulo', 'sqrt'."""
    return tools.calculator(a, b, operation)


@mcp.tool()
def add_note(note: str, category: str = "general") -> str:
    """Save a note to the database with an optional category (e.g. 'work', 'study', 'reminder')."""
    return tools.save_note(note, category)


@mcp.tool()
def get_notes(category: str = "") -> str:
    """Retrieve saved notes, optionally filtered by category."""
    return tools.read_notes(category)


@mcp.tool()
def search_notes(keyword: str) -> str:
    """Search notes containing a specific keyword in their content or category."""
    return tools.search_notes(keyword)


@mcp.tool()
def delete_note(note_id: int) -> str:
    """Delete a note permanently by its integer ID."""
    return tools.delete_note(note_id)


@mcp.tool()
def web_search(query: str) -> str:
    """Search the web for real-time information, facts, current events, or documentation."""
    return tools.web_search(query)


@mcp.tool()
def fetch_web_page(url: str) -> str:
    """Fetch and read plain text content from a webpage URL."""
    return tools.fetch_web_page(url)


@mcp.tool()
def get_current_time() -> str:
    """Get the current date, time, day of the week, and timezone."""
    return tools.get_current_time()


@mcp.tool()
def read_sample_file(filename: str) -> str:
    """Read an approved text file from the project directory (e.g., 'sample.txt' or 'notes.txt')."""
    return tools.read_file(filename)


@mcp.tool()
def list_allowed_files() -> str:
    """List approved text files available in the project."""
    return tools.list_allowed_files()


@mcp.tool()
def run_python_code(code: str) -> str:
    """Execute Python code for complex math, data analysis with pandas/numpy, simulations, or algorithms. Preloaded: math, datetime, re, json, pandas as pd, numpy as np."""
    return tools.execute_python(code)


if __name__ == "__main__":
    mcp.run()
