
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai

# Load .env from this project's directory
project_dir = Path(__file__).resolve().parent
load_dotenv(project_dir / ".env")

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError(
        "API key not found. Check your project's .env file."
    )

client = genai.Client(api_key=api_key)

response = client.models.generate_content(
    model="gemini-3.5-flash-lite",
    contents="Reply with: Gemini connection successful."
)

print(response.text)
