import asyncio
import base64
import datetime
import importlib
import json
import os
from pathlib import Path
import re
import socket
import sys
import time

# Windows Python 3.10 asyncio proactor connection reset patch (WinError 10054)
if sys.platform == "win32":
    try:
        from asyncio.proactor_events import _ProactorBasePipeTransport

        def _clean_call_connection_lost(self, exc):
            try:
                if hasattr(self, "_protocol") and self._protocol:
                    self._protocol.connection_lost(exc)
            finally:
                if hasattr(self, "_sock") and self._sock:
                    if hasattr(self._sock, "shutdown"):
                        try:
                            self._sock.shutdown(socket.SHUT_RDWR)
                        except (ConnectionResetError, OSError):
                            pass
                    if hasattr(self._sock, "close"):
                        try:
                            self._sock.close()
                        except (ConnectionResetError, OSError):
                            pass
                    self._sock = None
                server = getattr(self, "_server", None)
                if server is not None:
                    try:
                        server._detach()
                    except Exception:
                        pass
                    self._server = None

        _ProactorBasePipeTransport._call_connection_lost = _clean_call_connection_lost
    except Exception:
        pass

import chat_db
importlib.reload(chat_db)
from dotenv import load_dotenv
from google import genai
from google.genai import types
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import streamlit as st
from tools import get_notes_data

# --------------------------------------------------
# 1. Page Configuration & Custom CSS
# --------------------------------------------------

PROJECT_DIR = Path(__file__).resolve().parent
SERVER_FILE = PROJECT_DIR / "mcp_server.py"

load_dotenv(PROJECT_DIR / ".env")
API_KEY = os.getenv("GEMINI_API_KEY")

st.set_page_config(
    page_title="MCP AI Assistant",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .main .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
        max-width: 1080px;
    }
    .tool-chip {
        display: inline-block;
        background: #f1f5f9;
        color: #334155;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 0.82rem;
        margin-right: 6px;
        margin-bottom: 6px;
        font-weight: 500;
        border: 1px solid #e2e8f0;
    }
    .tool-badge-success {
        color: #16a34a;
        font-weight: 600;
    }
    .tool-badge-error {
        color: #dc2626;
        font-weight: 600;
    }
    .group-header {
        font-size: 0.78rem;
        font-weight: 700;
        text-transform: uppercase;
        color: #94a3b8;
        letter-spacing: 0.05em;
        margin-top: 12px;
        margin-bottom: 4px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

if not API_KEY:
    st.error("⚠️ `GEMINI_API_KEY` was not found. Please set it in your `.env` file.")
    st.stop()

if not SERVER_FILE.exists():
    st.error(f"⚠️ MCP server file not found at: `{SERVER_FILE}`")
    st.stop()

client = genai.Client(api_key=API_KEY)


# --------------------------------------------------
# 2. Conversation State Management & Persistence
# --------------------------------------------------

conversations = chat_db.list_conversations()
if not conversations:
    new_id = chat_db.create_conversation("New Chat")
    st.session_state.current_conv_id = new_id
    conversations = chat_db.list_conversations()

# URL query parameter persistence across browser refresh
url_conv_id = st.query_params.get("conv")
if url_conv_id and any(c.get("id") == url_conv_id for c in conversations):
    st.session_state.current_conv_id = url_conv_id
elif "current_conv_id" not in st.session_state or not any(
    c.get("id") == st.session_state.current_conv_id for c in conversations
):
    st.session_state.current_conv_id = (
        conversations[0].get("id") if conversations else chat_db.create_conversation("New Chat")
    )

# Keep query parameter synced with active thread
st.query_params["conv"] = st.session_state.current_conv_id


# --------------------------------------------------
# 3. Helpers: Thinking, Smart Title & Dual Export (MD & PDF)
# --------------------------------------------------

def extract_thought_and_answer(raw_text: str):
    """Extract <thought> reasoning and clean response text."""
    thought_match = re.search(r"<thought>(.*?)</thought>", raw_text, re.DOTALL | re.IGNORECASE)
    if thought_match:
        thought = thought_match.group(1).strip()
        cleaned = re.sub(r"<thought>.*?</thought>", "", raw_text, flags=re.DOTALL | re.IGNORECASE).strip()
        return thought, cleaned
    return None, raw_text.strip()


def generate_ai_title(prompt: str, model_name: str) -> str:
    """Generate a 3-5 word concise topic title using Gemini with resilient fallback."""
    models_to_try = [model_name, "gemini-3.5-flash-lite", "gemini-2.0-flash", "gemini-1.5-flash"]
    seen = set()
    for m in models_to_try:
        if m in seen:
            continue
        seen.add(m)
        try:
            res = client.models.generate_content(
                model=m,
                contents=(
                    f"Generate a concise 3 to 5 word topic title summarizing this user prompt: '{prompt[:250]}'. "
                    "For example: 'Quantum Computing Research', 'Monthly Sales Analysis', 'Study MCP Architecture'. "
                    "Output ONLY the concise title, no quotes, no period, no conversational text."
                ),
            )
            cleaned = res.text.strip().replace('"', '').replace("'", "").replace("*", "").strip()
            if cleaned:
                return cleaned[:40]
        except Exception:
            continue
    first_line = prompt.strip().split("\n")[0].strip()
    return first_line[:32] if first_line else "New Chat"


def build_markdown_export(conv_title: str, messages: list) -> str:
    """Generate a clean GitHub Flavored Markdown transcript of the conversation."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"# ⚡ {conv_title}",
        f"*Exported on: {timestamp}*",
        "",
        "---",
        "",
    ]
    for msg in messages:
        role = "### 👤 User" if msg["role"] == "user" else "### 🤖 Assistant"
        created = f" *({msg.get('created_at', '')})*" if msg.get("created_at") else ""
        lines.append(f"{role}{created}\n")
        if msg.get("thought"):
            lines.append(f"> **💭 Thinking Process:**\n> {msg['thought']}\n")
        lines.append(f"{msg['content']}\n")

        if msg.get("tools"):
            lines.append("<details>\n<summary>🛠️ Tools Executed</summary>\n")
            for t in msg["tools"]:
                lines.append(f"- **{t['name']}**")
                if t.get("arguments"):
                    lines.append(f"  - Arguments: `{json.dumps(t['arguments'])}`")
                lines.append(f"  - Output:\n```text\n{t.get('output', '')}\n```")
            lines.append("</details>\n")
        lines.append("---\n")
    return "\n".join(lines)


def clean_pdf_text(text: str) -> str:
    """Sanitize unicode text for standard PDF Latin-1 fonts."""
    if not text:
        return ""
    replacements = {
        "\u2014": "-", "\u2013": "-", "\u201c": '"', "\u201d": '"',
        "\u2018": "'", "\u2019": "'", "\u2026": "...", "\u2022": "*",
        "⚡": "", "💭": "", "🛠️": "", "👤": "", "🤖": "", "👍": "", "👎": "",
        "🐍": "", "🧮": "", "📝": "", "📚": "", "🔍": "", "🗑️": "", "🌐": "", "⏰": "",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return "".join(c if ord(c) <= 255 else "?" for c in text)


def generate_chat_pdf(conv_title: str, messages: list) -> bytes:
    """Generate a formatted PDF document of the conversation using fpdf2."""
    from fpdf import FPDF

    class ChatPDF(FPDF):
        def header(self):
            self.set_font("helvetica", "B", 10)
            self.set_text_color(100, 116, 139)
            self.cell(self.epw, 8, "MCP-Powered Personal AI Assistant - Chat Transcript", border=0, new_x="LMARGIN", new_y="NEXT")
            self.ln(4)

        def footer(self):
            self.set_y(-15)
            self.set_font("helvetica", "I", 8)
            self.set_text_color(150, 150, 150)
            self.cell(self.epw, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    pdf = ChatPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    epw = pdf.epw

    # Title & Header
    pdf.set_font("helvetica", "B", 16)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(epw, 10, clean_pdf_text(conv_title), new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("helvetica", "I", 9)
    pdf.set_text_color(100, 116, 139)
    now_str = datetime.datetime.now().strftime("%B %d, %Y at %I:%M %p")
    pdf.cell(epw, 6, f"Exported: {now_str}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    for msg in messages:
        role = "User" if msg["role"] == "user" else "Assistant"
        time_str = msg.get("created_at", "")

        pdf.set_font("helvetica", "B", 10)
        if role == "User":
            pdf.set_fill_color(241, 245, 249)
            pdf.set_text_color(15, 23, 42)
            label = f"  User ({time_str})" if time_str else "  User"
            pdf.cell(epw, 7, clean_pdf_text(label), fill=True, new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.set_fill_color(238, 242, 255)
            pdf.set_text_color(55, 48, 163)
            label = f"  Assistant ({time_str})" if time_str else "  Assistant"
            pdf.cell(epw, 7, clean_pdf_text(label), fill=True, new_x="LMARGIN", new_y="NEXT")

        pdf.ln(2)

        # Thinking trace
        if msg.get("thought"):
            pdf.set_font("helvetica", "I", 8)
            pdf.set_text_color(100, 116, 139)
            pdf.multi_cell(epw, 4, clean_pdf_text(f"Thinking: {msg['thought']}"))
            pdf.ln(2)

        # Message body
        pdf.set_font("helvetica", "", 9.5)
        pdf.set_text_color(30, 41, 59)
        pdf.multi_cell(epw, 5, clean_pdf_text(msg["content"]))

        # Tools executed
        if msg.get("tools"):
            pdf.ln(1)
            pdf.set_font("helvetica", "I", 8)
            pdf.set_text_color(120, 120, 120)
            tools_str = ", ".join(t["name"] for t in msg["tools"])
            pdf.cell(epw, 5, clean_pdf_text(f"[MCP Tools: {tools_str}]"), new_x="LMARGIN", new_y="NEXT")

        pdf.ln(4)

    return bytes(pdf.output())


# --------------------------------------------------
# 4. Sidebar: Search, Date-Grouped Chats, Settings & Tools
# --------------------------------------------------

with st.sidebar:
    st.markdown("### ⚡ MCP AI Assistant")
    st.caption("Gemini + Model Context Protocol")

    if st.button("➕ New Chat", use_container_width=True, type="primary"):
        new_id = chat_db.create_conversation("New Chat")
        st.session_state.current_conv_id = new_id
        st.query_params["conv"] = new_id
        st.rerun()

    # Search conversations
    st.markdown("#### 💬 Conversations")
    search_kw = st.text_input("🔍 Search chats", "", placeholder="Search keywords...", key="search_kw_sidebar")

    def render_conv_item(conv):
        col_chat, col_del = st.columns([0.82, 0.18])
        cid = conv.get("id", "")
        ctitle = conv.get("title", "Untitled")
        is_active = cid == st.session_state.current_conv_id
        label = f"● {ctitle}" if is_active else ctitle

        with col_chat:
            if st.button(
                label,
                key=f"conv_{cid}",
                use_container_width=True,
                type="secondary" if not is_active else "primary",
            ):
                st.session_state.current_conv_id = cid
                st.query_params["conv"] = cid
                st.rerun()

        with col_del:
            if st.button("🗑️", key=f"del_{cid}", help="Delete chat"):
                if cid:
                    chat_db.delete_conversation(cid)
                remaining = chat_db.list_conversations()
                if remaining:
                    st.session_state.current_conv_id = remaining[0].get("id", "")
                    st.query_params["conv"] = remaining[0].get("id", "")
                else:
                    new_c = chat_db.create_conversation("New Chat")
                    st.session_state.current_conv_id = new_c
                    st.query_params["conv"] = new_c
                st.rerun()

    if search_kw.strip():
        search_results = chat_db.search_conversations(search_kw.strip())
        st.caption(f"Found {len(search_results)} matching thread(s):")
        for conv in search_results:
            render_conv_item(conv)
    else:
        # Date-Grouped Sidebar Threads: Today, Yesterday, Previous 7 Days, Older
        grouped = chat_db.group_conversations_by_date(conversations)
        for group_name, group_list in grouped.items():
            st.markdown(f"<div class='group-header'>📅 {group_name}</div>", unsafe_allow_html=True)
            for conv in group_list:
                render_conv_item(conv)

    st.divider()

    # Model & Persona Selection
    st.subheader("⚙️ Settings")
    model_options = {
        "gemini-3.5-flash-lite": "Gemini 3.5 Flash Lite (High Free Quota)",
        "gemini-2.0-flash": "Gemini 2.0 Flash (Fast & Multimodal)",
        "gemini-1.5-flash": "Gemini 1.5 Flash (Reliable & High Quota)",
        "gemini-2.5-flash": "Gemini 2.5 Flash (Experimental - 20/day limit)",
        "gemini-2.5-pro": "Gemini 2.5 Pro (Deep Reasoning)",
    }
    selected_model = st.selectbox(
        "Model",
        options=list(model_options.keys()),
        format_func=lambda k: model_options[k],
        index=0,
    )

    persona = st.selectbox(
        "Persona",
        [
            "Helpful Assistant (Friendly & Contextual)",
            "Concise Specialist (Direct & Minimalist)",
            "Technical Analyst (Deep & Thorough)",
        ],
        index=0,
    )

    temperature = st.slider(
        "Temperature",
        min_value=0.0,
        max_value=1.0,
        value=0.2,
        step=0.05,
        help="Lower values yield more deterministic tool execution.",
    )

    st.divider()

    # Local Notes Database Viewer
    st.subheader("📚 Notes Database")
    notes_list = get_notes_data()
    if notes_list:
        st.caption(f"{len(notes_list)} note(s) in `notes.db`:")
        with st.expander("👁️ View saved notes", expanded=False):
            for n in notes_list:
                st.markdown(f"**#{n.get('id', '')}** `[{n.get('category', 'general')}]` *{n.get('created_at', '')}*")
                st.write(n.get("content", ""))
                st.divider()
    else:
        st.info("No notes saved yet.")

    # MCP Tool Catalog
    with st.expander("🛠️ Active MCP Tools (11)", expanded=False):
        st.markdown(
            """
            - 🐍 **run_python_code**: Execute Python scripts (pandas, numpy, math)
            - 🧮 **calculate**: `add`, `subtract`, `multiply`, `divide`, `power`, `modulo`, `sqrt`
            - 📝 **add_note**: Save note with category in SQLite
            - 📚 **get_notes**: Read notes, optional category filter
            - 🔍 **search_notes**: Search notes by keyword
            - 🗑️ **delete_note**: Delete note by ID
            - 🌐 **web_search**: Real-time web search via DuckDuckGo
            - 📖 **fetch_web_page**: Read webpage plain text
            - ⏰ **get_current_time**: Current date, time, and day
            - 📄 **read_sample_file**: Read approved workspace files
            - 📁 **list_allowed_files**: List accessible local files
            """
        )


# --------------------------------------------------
# 5. MCP Agent Core Execution
# --------------------------------------------------

def build_system_instruction(persona_name: str) -> str:
    persona_notes = {
        "Helpful Assistant (Friendly & Contextual)": (
            "You are a friendly, highly capable personal AI assistant. "
            "Explain tool results clearly and contextually."
        ),
        "Concise Specialist (Direct & Minimalist)": (
            "You are an efficient, concise assistant. Provide direct answers "
            "with minimum fluff, letting tool results speak for themselves."
        ),
        "Technical Analyst (Deep & Thorough)": (
            "You are a precise technical analyst. Explain calculations, "
            "source observations, and technical details accurately."
        ),
    }

    return (
        f"{persona_notes.get(persona_name, '')} "
        "You have direct access to local tools through the Model Context Protocol (MCP).\n"
        "Guidelines:\n"
        "1. First, inside <thought>...</thought> tags, briefly explain your reasoning plan: what the user is asking, which tools (if any) you will call, and why.\n"
        "2. For calculations or math, call 'calculate'. For data analysis, simulations, statistics, or algorithms, ALWAYS call 'run_python_code'.\n"
        "3. To take notes, search notes, view notes, or delete notes, ALWAYS use the note tools.\n"
        "4. For questions about current events, news, or outside facts, use 'web_search'.\n"
        "5. To read links or webpages provided by the user, use 'fetch_web_page'.\n"
        "6. For the current date or time, ALWAYS call 'get_current_time'.\n"
        "7. If the user attaches an image or document, inspect it thoroughly and use tools as needed.\n"
        "8. Never fabricate tool outputs; summarize exactly what tools return."
    )


async def process_message_async(
    user_message: str,
    previous_messages: list,
    model_name: str,
    temperature: float,
    persona_name: str,
    file_bytes: bytes = None,
    mime_type: str = None,
):
    venv_py = PROJECT_DIR / ".venv" / "Scripts" / "python.exe"
    python_exe = str(venv_py) if venv_py.exists() else sys.executable

    server_params = StdioServerParameters(
        command=python_exe,
        args=[str(SERVER_FILE)],
        cwd=str(PROJECT_DIR),
    )

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            tool_result = await session.list_tools()
            mcp_tools = tool_result.tools

            declarations = [
                types.FunctionDeclaration(
                    name=tool.name,
                    description=tool.description or "",
                    parameters=tool.inputSchema,
                )
                for tool in mcp_tools
            ]

            gemini_tools = [types.Tool(function_declarations=declarations)]

            # Build native multi-turn history
            history = []
            for msg in previous_messages:
                role = "user" if msg["role"] == "user" else "model"
                history.append(
                    types.Content(
                        role=role,
                        parts=[types.Part.from_text(text=msg["content"])],
                    )
                )

            chat = client.chats.create(
                model=model_name,
                history=history,
                config=types.GenerateContentConfig(
                    tools=gemini_tools,
                    system_instruction=build_system_instruction(persona_name),
                    temperature=temperature,
                ),
            )

            prompt_parts = [types.Part.from_text(text=user_message)]
            if file_bytes and mime_type:
                prompt_parts.append(
                    types.Part.from_bytes(data=file_bytes, mime_type=mime_type)
                )

            response = chat.send_message(prompt_parts)

            tools_executed = []
            allowed_names = {t.name for t in mcp_tools}

            # Tool calling loop
            while response.function_calls:
                function_responses = []

                for call in response.function_calls:
                    tool_name = call.name
                    arguments = dict(call.args or {})

                    if tool_name not in allowed_names:
                        tool_output = {"error": f"Tool '{tool_name}' is not allowed."}
                        is_error = True
                        result_text = "Tool not allowed."
                    else:
                        try:
                            result = await session.call_tool(tool_name, arguments=arguments)

                            result_text = "\n".join(
                                item.text
                                for item in result.content
                                if hasattr(item, "text")
                            )

                            is_error = getattr(result, "isError", False)
                            if is_error:
                                tool_output = {"error": result_text or "Tool execution failed."}
                            else:
                                tool_output = {"result": result_text}

                        except Exception as tool_err:
                            is_error = True
                            result_text = str(tool_err)
                            tool_output = {"error": result_text}

                    tools_executed.append(
                        {
                            "name": tool_name,
                            "arguments": arguments,
                            "output": result_text,
                            "is_error": is_error,
                        }
                    )

                    function_responses.append(
                        types.Part.from_function_response(
                            name=tool_name,
                            response=tool_output,
                        )
                    )

                response = chat.send_message(function_responses)

            answer = response.text or "I completed the request."
            return answer, tools_executed


# --------------------------------------------------
# 6. UI Helpers: Rendering & Streaming
# --------------------------------------------------

TOOL_ICONS = {
    "run_python_code": "🐍",
    "calculate": "🧮",
    "add_note": "📝",
    "get_notes": "📚",
    "search_notes": "🔍",
    "delete_note": "🗑️",
    "web_search": "🌐",
    "fetch_web_page": "📖",
    "get_current_time": "⏰",
    "read_sample_file": "📄",
    "list_allowed_files": "📁",
}


def render_tool_execution(tools):
    if not tools:
        return

    chips = []
    for t in tools:
        icon = TOOL_ICONS.get(t["name"], "🛠️")
        chips.append(f"{icon} `{t['name']}`")
    st.markdown(
        f"<div style='margin-bottom: 8px;'>{' '.join(chips)}</div>",
        unsafe_allow_html=True,
    )

    with st.expander(
        f"🛠️ MCP Tool Execution ({len(tools)} call{'s' if len(tools)>1 else ''})",
        expanded=False,
    ):
        for idx, t in enumerate(tools):
            icon = TOOL_ICONS.get(t["name"], "🛠️")
            status_badge = (
                "<span class='tool-badge-error'>❌ Error</span>"
                if t.get("is_error")
                else "<span class='tool-badge-success'>✅ Success</span>"
            )
            st.markdown(
                f"**{idx + 1}. {icon} `{t['name']}`** — {status_badge}",
                unsafe_allow_html=True,
            )

            # Rich rendering for Python Code Interpreter
            if t["name"] == "run_python_code" and "code" in t.get("arguments", {}):
                st.caption("🐍 Executed Python Code:")
                st.code(t["arguments"]["code"], language="python")
                st.caption("Output / Result:")
                st.code(t.get("output", ""), language="text")
            else:
                if t.get("arguments"):
                    st.caption("Arguments:")
                    st.json(t["arguments"])
                st.caption("Tool Result:")
                st.code(t.get("output", ""), language="text")

            if idx < len(tools) - 1:
                st.divider()


def stream_text_generator(full_text: str):
    """Smooth token-like word streamer for natural UI typing effect."""
    words = full_text.split(" ")
    for i, word in enumerate(words):
        yield word + (" " if i < len(words) - 1 else "")
        time.sleep(0.012)


# --------------------------------------------------
# 7. Main Chat Area
# --------------------------------------------------

# Check if a prompt regeneration was requested
if "regen_user_prompt" in st.session_state and st.session_state.regen_user_prompt:
    prompt_to_send = st.session_state.pop("regen_user_prompt")
else:
    prompt_to_send = None

# Active Conversation Header
current_conv = next(
    (c for c in conversations if c.get("id") == st.session_state.current_conv_id),
    None,
)
current_title = current_conv.get("title", "Chat") if current_conv else "Chat"

col_head, col_act = st.columns([0.65, 0.35])
with col_head:
    st.markdown(f"### ⚡ {current_title}")

# Load messages for active conversation from SQLite
messages = chat_db.get_conversation_messages(st.session_state.current_conv_id)

with col_act:
    col_export, col_rename = st.columns([0.55, 0.45])
    with col_export:
        if messages:
            with st.popover("📥 Export", use_container_width=True):
                st.markdown("##### Export Conversation")
                md_content = build_markdown_export(current_title, messages)
                safe_filename = re.sub(r"[^\w\-_\. ]", "_", current_title).strip() or "chat"
                st.download_button(
                    label="📄 Markdown (.md)",
                    data=md_content,
                    file_name=f"{safe_filename}.md",
                    mime="text/markdown",
                    use_container_width=True,
                )
                try:
                    pdf_bytes = generate_chat_pdf(current_title, messages)
                    st.download_button(
                        label="📕 PDF Document (.pdf)",
                        data=pdf_bytes,
                        file_name=f"{safe_filename}.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                    )
                except Exception as e:
                    st.caption(f"PDF export note: {e}")
    with col_rename:
        with st.popover("✏️ Rename", use_container_width=True):
            new_title_input = st.text_input("New conversation title:", value=current_title)
            if st.button("Save", key="save_title_btn"):
                if new_title_input.strip():
                    chat_db.update_conversation_title(
                        st.session_state.current_conv_id, new_title_input.strip()
                    )
                    st.rerun()

# Render conversation history with message actions
for idx, msg in enumerate(messages):
    msg_id = msg.get("id", idx)
    role = msg.get("role", "user")
    content = msg.get("content", "")

    with st.chat_message(role):
        # Collapsible Thinking Trace
        if msg.get("thought"):
            with st.expander("💭 Thinking Process", expanded=False):
                st.markdown(f"*{msg['thought']}*")

        if msg.get("image_b64"):
            st.image(msg["image_b64"], width=280)

        if role == "assistant" and msg.get("tools"):
            render_tool_execution(msg["tools"])

        st.markdown(content)

        # Message Actions Toolbar for Assistant Responses
        if role == "assistant":
            is_latest_turn = idx == len(messages) - 1
            col_a, col_b, col_c, col_d = st.columns([0.16, 0.16, 0.28, 0.40])

            with col_a:
                is_pos = msg.get("feedback") == "positive"
                btn_pos = "👍" if not is_pos else "👍✓"
                if st.button(btn_pos, key=f"pos_{msg_id}_{idx}", help="Helpful response"):
                    if isinstance(msg_id, int):
                        chat_db.set_message_feedback(msg_id, "positive")
                    st.rerun()

            with col_b:
                is_neg = msg.get("feedback") == "negative"
                btn_neg = "👎" if not is_neg else "👎✓"
                if st.button(btn_neg, key=f"neg_{msg_id}_{idx}", help="Needs improvement"):
                    if isinstance(msg_id, int):
                        chat_db.set_message_feedback(msg_id, "negative")
                    st.rerun()

            with col_c:
                if is_latest_turn:
                    if st.button("🔄 Regenerate", key=f"regen_{msg_id}_{idx}", help="Regenerate this answer"):
                        last_user = next((m for m in reversed(messages[:idx]) if m.get("role") == "user"), None)
                        if last_user:
                            chat_db.delete_last_assistant_message(st.session_state.current_conv_id)
                            st.session_state.regen_user_prompt = last_user.get("content", "")
                            st.rerun()

            with col_d:
                with st.popover("📋 Copy Markdown", use_container_width=False):
                    st.caption("Click the copy icon on the top right:")
                    st.code(content, language="markdown")

        elif role == "user":
            is_latest_user = idx == len(messages) - 2 or idx == len(messages) - 1
            if is_latest_user:
                with st.popover("✏️ Edit Prompt", use_container_width=False):
                    edited_prompt = st.text_area("Edit your prompt:", value=content, key=f"edit_area_{msg_id}_{idx}")
                    if st.button("Resend Edited Prompt", key=f"edit_btn_{msg_id}_{idx}"):
                        if edited_prompt.strip():
                            chat_db.delete_last_turn(st.session_state.current_conv_id)
                            st.session_state.regen_user_prompt = edited_prompt.strip()
                            st.rerun()


# Starter Prompts on Empty Chat
if len(messages) == 0 and not prompt_to_send:
    st.markdown("#### 💡 Quick Starters")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🐍 Python: Sum primes < 100", use_container_width=True):
            prompt_to_send = "Use Python to calculate the sum of all prime numbers less than 100."
        if st.button("⏰ What's the current date & time?", use_container_width=True):
            prompt_to_send = "What is the current date and time?"
    with col2:
        if st.button("📊 Python: Monthly Sales DataFrame", use_container_width=True):
            prompt_to_send = "Write a python script using pandas to simulate 12 months of sales, compute total revenue, average, and the highest month."
        if st.button("📝 Save note: Study MCP", use_container_width=True):
            prompt_to_send = "Save a note in category 'study' saying: Study MCP architecture and tool integration"
    with col3:
        if st.button("🌐 Search latest AI agent news", use_container_width=True):
            prompt_to_send = "Search the web for the latest updates on AI agents and MCP"
        if st.button("📚 Show all my saved notes", use_container_width=True):
            prompt_to_send = "Show all my saved notes"


# --------------------------------------------------
# 8. Attachment & Chat Input
# --------------------------------------------------

with st.expander("📎 Attach Image or PDF (Gemini Multimodal Vision)", expanded=False):
    uploaded_file = st.file_uploader(
        "Upload image (PNG, JPG, WEBP) or PDF for Gemini to inspect:",
        type=["png", "jpg", "jpeg", "webp", "pdf"],
        key="chat_file_uploader",
    )
    if uploaded_file:
        st.caption(f"✅ Ready to send: **{uploaded_file.name}** ({uploaded_file.type})")
        if uploaded_file.type.startswith("image/"):
            st.image(uploaded_file, width=200)

chat_input = st.chat_input("Ask a question, run Python, upload an image, or request a tool...")

if chat_input and chat_input.strip():
    prompt_to_send = chat_input.strip()

if prompt_to_send:
    user_prompt = prompt_to_send

    # Process file attachment if present
    file_bytes = None
    file_mime = None
    image_b64 = None

    if uploaded_file:
        file_bytes = uploaded_file.getvalue()
        file_mime = uploaded_file.type
        if file_mime.startswith("image/"):
            b64_data = base64.b64encode(file_bytes).decode("utf-8")
            image_b64 = f"data:{file_mime};base64,{b64_data}"

    # Auto-generate smart concise title via Gemini on first prompt
    if len(messages) == 0 and current_title == "New Chat":
        smart_title = generate_ai_title(user_prompt, selected_model)
        chat_db.update_conversation_title(st.session_state.current_conv_id, smart_title)

    # 1. Save and display user message
    chat_db.add_message(
        conv_id=st.session_state.current_conv_id,
        role="user",
        content=user_prompt,
        image_b64=image_b64,
    )

    with st.chat_message("user"):
        if image_b64:
            st.image(image_b64, width=280)
        st.markdown(user_prompt)

    # 2. Query Gemini with MCP tools
    with st.chat_message("assistant"):
        with st.spinner("Connecting to MCP & reasoning with Gemini..."):
            try:
                answer, tools_used = asyncio.run(
                    process_message_async(
                        user_message=user_prompt,
                        previous_messages=messages,
                        model_name=selected_model,
                        temperature=temperature,
                        persona_name=persona,
                        file_bytes=file_bytes,
                        mime_type=file_mime,
                    )
                )

                # Parse reasoning/thinking vs clean answer
                thought_trace, clean_answer = extract_thought_and_answer(answer)

                if thought_trace:
                    with st.expander("💭 Thinking Process", expanded=True):
                        st.markdown(f"*{thought_trace}*")

                # Show tool execution cards if tools were invoked
                if tools_used:
                    render_tool_execution(tools_used)

                # Stream response dynamically for ChatGPT/Gemini-like experience
                st.write_stream(stream_text_generator(clean_answer))

                # Save assistant response to SQLite database
                chat_db.add_message(
                    conv_id=st.session_state.current_conv_id,
                    role="assistant",
                    content=clean_answer,
                    tools=tools_used,
                    thought=thought_trace,
                )

                st.rerun()

            except Exception as error:
                err_str = str(error)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    st.warning(
                        "⚠️ **Daily Free Quota Exceeded for this specific model**\n\n"
                        "Google AI Studio applies daily request limits per model on the free tier.\n\n"
                        "👉 **Immediate Fix**: Switch the **Model** dropdown in the left sidebar to **Gemini 3.5 Flash Lite** or **Gemini 2.0 Flash** to continue chatting immediately!"
                    )
                else:
                    def extract_all_exceptions(exc):
                        if hasattr(exc, "exceptions") and exc.exceptions:
                            for s in exc.exceptions:
                                yield from extract_all_exceptions(s)
                        else:
                            yield exc

                    all_errors = list(extract_all_exceptions(error))
                    if all_errors:
                        err_msg = "\n".join(f"• {type(e).__name__}: {e}" for e in all_errors)
                        st.error(f"Execution Error:\n{err_msg}")
                    else:
                        st.error(f"Execution Error: {error}")
