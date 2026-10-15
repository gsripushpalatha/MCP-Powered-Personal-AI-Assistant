
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

from tools import calculator

# Load API key from the project's .env file
project_dir = Path(__file__).resolve().parent
load_dotenv(project_dir / ".env")

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError("GEMINI_API_KEY is missing from .env")

client = genai.Client(api_key=api_key)


def main():
    chat = client.chats.create(
        model="gemini-3.5-flash-lite",
        config=types.GenerateContentConfig(
            tools=[calculator],
            system_instruction=(
                "You are a helpful assistant. "
                "Use the calculator tool for arithmetic. "
                "Explain the result clearly."
            ),
        ),
    )

    while True:
        user_message = input("\nYou (type 'exit' to stop): ")

        if user_message.strip().lower() == "exit":
            print("Assistant: Goodbye!")
            break

        try:
            response = chat.send_message(user_message)
            print("\nAssistant:", response.text)
        except Exception as error:
            print(f"\nRequest failed: {error}")


if __name__ == "__main__":
    main()
