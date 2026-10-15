
# Day 3: Understanding tool calling

from tools import calculator, save_note, read_notes, read_file


def assistant(user_message):
    """A simple rule-based assistant that selects tools."""

    message = user_message.lower().strip()

    if "calculate" in message or "multiply" in message:
        result = calculator(25, 17, "multiply")
        return f"The calculation result is {result}."

    elif "save a note" in message:
        note = user_message.lower().replace("save a note", "").strip()
        result = save_note(note)
        return result

    elif "show my notes" in message:
        return read_notes()

    elif "read sample.txt" in message:
        return read_file("sample.txt")

    else:
        return "I don't know which tool to use for that request yet."


# Try some requests
print("User: Calculate 25 multiplied by 17")
print("Assistant:", assistant("Calculate 25 multiplied by 17"))

print("\nUser: Show my notes")
print("Assistant:", assistant("Show my notes"))
