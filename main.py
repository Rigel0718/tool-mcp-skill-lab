import sys
from pathlib import Path

# Keep this file directly runnable from a source checkout.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from code_agent import run_agent

DEVELOPER_PROMPT = """You are a coding agent running in the user's terminal.
You can list files, read files, write files, and run shell commands.
Use your tools to complete the user's task, then briefly summarize what you did.
The working directory is the folder the user launched you from.
"""


def main():
    messages = [{"role": "developer", "content": DEVELOPER_PROMPT}]
    print("Mini agent ready. Type 'exit' or 'quit' to stop.")

    while True:
        user_input = input("\nYou: ")
        if user_input.strip().lower() in ("exit", "quit"):
            break

        messages.append({"role": "user", "content": user_input})
        reply = run_agent(messages)
        print(f"\nAgent: {reply}")


if __name__ == "__main__":
    main()
