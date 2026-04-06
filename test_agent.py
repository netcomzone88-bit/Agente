"""
Local test — chat with Sofia directly in the terminal.
No Twilio needed. Just set ANTHROPIC_API_KEY in your .env

Run:
  python test_agent.py
"""

import os
import sys
from pathlib import Path

# Load .env if present
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

if not os.environ.get("ANTHROPIC_API_KEY"):
    print("ERROR: ANTHROPIC_API_KEY is not set.")
    print("Create a .env file with:  ANTHROPIC_API_KEY=sk-ant-...")
    sys.exit(1)

from agent import clear_conversation, respond_to_lead

TEST_NUMBER = "whatsapp:+10000000000"
print("=" * 55)
print("  Citikars — Sofia (WhatsApp Lead Agent) — LOCAL TEST")
print("=" * 55)
print('Type your message and press Enter. Type "quit" to exit.')
print('Type "reset" to start a new conversation.\n')

while True:
    try:
        user_input = input("You: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nBye!")
        break

    if not user_input:
        continue

    if user_input.lower() == "quit":
        print("Bye!")
        break

    if user_input.lower() == "reset":
        clear_conversation(TEST_NUMBER)
        print("--- Conversation reset ---\n")
        continue

    print("Sofia: ", end="", flush=True)
    reply, lead_data = respond_to_lead(TEST_NUMBER, user_input)
    print(reply)

    if lead_data:
        print()
        print("━" * 40)
        print("🚗  LEAD QUALIFIED")
        print(f"   Name:     {lead_data['name']}")
        print(f"   Interest: {lead_data['interest']}")
        print(f"   Budget:   {lead_data['budget']}")
        print(f"   Timeline: {lead_data['timeline']}")
        print(f"   Level:    {lead_data['level'].upper()}")
        print("━" * 40)

    print()
