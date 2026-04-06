"""
Lead response agent powered by Claude.
Maintains conversation history per WhatsApp number and qualifies leads.
"""

import os
from typing import Optional
import anthropic

# In-memory conversation store: phone_number -> list of messages
_conversations: dict[str, list[dict]] = {}

SYSTEM_PROMPT = """You are Sofia, a friendly and professional car sales agent at Citikars — a car dealership in the USA.

About Citikars:
We help customers find their perfect vehicle — new and used cars, trucks, and SUVs. We offer competitive financing, trade-in options, and a no-pressure buying experience. Our goal is to match every customer with the right car at the right price.

Your mission in this WhatsApp conversation:
1. Greet the lead warmly and build rapport.
2. Find out what type of vehicle they are looking for (new/used, make, model, body style).
3. Gather key qualification info one question at a time:
   - Budget range (e.g. under $20k, $20k-$35k, $35k+)
   - Financing or cash purchase?
   - Do they have a trade-in?
   - Timeline — are they ready to buy now, or just browsing?
   - Their name and preferred contact time for a test drive or call with a sales advisor.
4. Offer a clear next step: schedule a test drive, send inventory links, or connect them with a sales advisor.

Behavior rules:
- Always respond in the same language the customer uses. Most leads will write in English or Spanish — adapt instantly.
- Keep messages SHORT — this is WhatsApp. 2-3 sentences max per reply.
- Never fabricate prices, APR rates, or vehicle availability. Say you will confirm with the team.
- If asked about specific stock or financing details, offer to connect them with a sales advisor or schedule a dealership visit.
- Be warm and conversational, never pushy.
- If the lead seems uninterested, close gracefully: "No worries! Feel free to reach out anytime. 🚗"
- Once you have: name + vehicle interest + budget/timeline + level of intent, append this hidden tag at the END of your reply (invisible to the customer, for our CRM):
  [LEAD_QUALIFIED: name=<name>, interest=<vehicle type/model>, budget=<range>, timeline=<now|soon|browsing>, level=<hot|warm|cold>]
"""


def _get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])



def get_conversation(phone_number: str) -> list[dict]:
    """Return the conversation history for a given phone number."""
    return _conversations.get(phone_number, [])


def clear_conversation(phone_number: str) -> None:
    """Reset conversation for a phone number (useful for testing)."""
    _conversations.pop(phone_number, None)


def extract_lead_data(response_text: str) -> Optional[dict]:
    """
    Parse the hidden [LEAD_QUALIFIED: ...] tag from Claude's response.
    Returns a dict with lead info, or None if not yet qualified.
    """
    import re

    pattern = (
        r"\[LEAD_QUALIFIED:\s*name=(.+?),\s*interest=(.+?),\s*budget=(.+?)"
        r",\s*timeline=(now|soon|browsing),\s*level=(hot|warm|cold)\]"
    )
    match = re.search(pattern, response_text, re.IGNORECASE)
    if match:
        return {
            "name": match.group(1).strip(),
            "interest": match.group(2).strip(),
            "budget": match.group(3).strip(),
            "timeline": match.group(4).strip().lower(),
            "level": match.group(5).strip().lower(),
        }
    return None


def clean_response(response_text: str) -> str:
    """Remove internal tags before sending to the customer."""
    import re

    return re.sub(
        r"\[LEAD_QUALIFIED:[^\]]*\]", "", response_text, flags=re.IGNORECASE
    ).strip()


def respond_to_lead(phone_number: str, incoming_message: str) -> tuple[str, Optional[dict]]:
    """
    Process an incoming WhatsApp message from a lead.

    Args:
        phone_number: Sender's WhatsApp number (e.g. "whatsapp:+521234567890")
        incoming_message: The text message received

    Returns:
        (reply_text, lead_data)
        - reply_text: message to send back via WhatsApp
        - lead_data: dict with qualified lead info, or None if not yet qualified
    """
    client = _get_client()

    # Retrieve or initialise conversation history
    history = _conversations.setdefault(phone_number, [])

    # Append the new user message
    history.append({"role": "user", "content": incoming_message})

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=512,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=history,
    )

    # Extract text from response
    reply_raw = next(
        (block.text for block in response.content if block.type == "text"), ""
    )

    # Parse optional lead qualification tag
    lead_data = extract_lead_data(reply_raw)
    reply_clean = clean_response(reply_raw)

    # Append assistant turn to history (store clean version for UX,
    # but keep raw for context so Claude knows what it said)
    history.append({"role": "assistant", "content": reply_raw})

    return reply_clean, lead_data
