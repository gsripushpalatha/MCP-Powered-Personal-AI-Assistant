# ⚡ MCP-Powered Personal AI Assistant

An advanced, personal AI assistant built with **Google Gemini 2.0 / 3.5**, the **Model Context Protocol (MCP)**, and **Streamlit**. Designed to match commercial AI assistant capabilities (ChatGPT, Gemini) while running **100% on free-tier APIs and local tools**.

---

## ✨ Features

- **⚡ Token Streaming UX**: Real-time word streaming with dynamic response generation.
- **💭 Thinking / Reasoning Trace**: Expandable reasoning trace blocks showing the model's internal chain-of-thought before tool execution.
- **🛠️ 11 Local MCP Tools**:
  - 🐍 `run_python_code`: Sandboxed Python Code Interpreter (supports `pandas`, `numpy`, data analysis, and math algorithms) running in an isolated child subprocess.
  - 🧮 `calculate`: Arithmetic, exponentiation (`power`), modulo, square root.
  - 📝 `add_note`: Persistent note storage categorized in SQLite.
  - 📚 `get_notes`: List saved notes with optional category filter.
  - 🔍 `search_notes`: Keyword search across saved notes.
  - 🗑️ `delete_note`: Delete note by ID.
  - 🌐 `web_search`: Real-time web search via DuckDuckGo.
  - 📖 `fetch_web_page`: Extract and read plain text from any webpage.
  - ⏰ `get_current_time`: Precise current local timestamp and day of week.
  - 📄 `read_sample_file`: Inspect allowed local workspace files safely.
  - 📁 `list_allowed_files`: Directory listing of approved workspace assets.
- **💾 Multi-Session SQLite History**:
  - Sidebar chat threads grouped by date (`Today`, `Yesterday`, `Previous 7 Days`, `Older`).
  - Automatic concise title generation powered by Gemini (e.g., *"Quantum Computing Research"*).
  - Search across all conversation titles and message transcripts in real time.
  - URL query parameter sync (`?conv=...`) preserves active conversation across page reloads.
- **📥 One-Click Dual Export**:
  - **Markdown (`.md`)**: Full formatted transcript with timestamps, role badges, thinking callouts, and collapsible tool logs.
  - **PDF (`.pdf`)**: Formatted document with page numbering, user/assistant chat cards, thinking process, and tool tags via `fpdf2`.
- **🔄 Message Action Bar**:
  - `👍` / `👎` Feedback tracking.
  - `🔄 Regenerate` response.
  - `✏️ Edit Prompt` for user turns.
  - `📋 Copy Markdown` with syntax highlighting.
- **📎 Multimodal Vision**: Upload images (PNG, JPG, WEBP) or PDFs for Gemini inspection.
- **🛡️ Free-Tier Quota Resilience**: Model selector with `gemini-3.5-flash-lite` (default, high quota), `gemini-2.0-flash`, `gemini-1.5-flash`, `gemini-2.5-flash`, and `gemini-2.5-pro`.

---

## 🚀 Quick Start

### 1. Clone the repository
```bash
git clone <your-repo-url>
cd mcp-ai-assistant
```

### 2. Set up virtual environment
```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure your API key
Create a `.env` file in the project root:
```env
GEMINI_API_KEY=your_gemini_api_key_here
```
*(Get a free API key at [Google AI Studio](https://aistudio.google.com/)).*

### 5. Launch the application
```bash
streamlit run app.py
```
Open [http://localhost:8501](http://localhost:8501) in your browser.

---

## 🏗️ Architecture

```
mcp-ai-assistant/
├── app.py              # Main Streamlit UI, streaming engine, session management
├── chat_db.py          # SQLite database schema (conversations & chat_messages)
├── tools.py            # Local tool implementations & SQLite notes database
├── mcp_server.py       # FastMCP server exposing 11 tools over stdio
├── gemini_mcp.py       # Async Gemini function calling loop with MCP integration
├── requirements.txt    # Python dependencies
├── .env.example        # Environment variable template
└── .gitignore          # Ignores .venv, .env, *.db, and cache
```

---

## 🔒 Security & Privacy
- API keys and local databases (`notes.db`, `chat_history.db`) are excluded via `.gitignore`.
- Python code execution runs in an isolated child process with timeout protection and command filtering.
