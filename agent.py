"""
Lead response agent powered by Claude.
Maintains conversation history per WhatsApp number and qualifies leads.
"""

import os
from typing import Optional
import anthropic

# In-memory conversation store: phone_number -> list of messages
_conversations: dict[str, list[dict]] = {}

SYSTEM_PROMPT = """Eres {agent_name}, un agente de ventas de {business_name}.

Sobre la empresa:
{business_description}

Tu objetivo es:
1. Saludar al lead de forma amigable y profesional.
2. Identificar qué necesita (producto, servicio, información, soporte).
3. Recopilar datos clave: nombre, empresa (si aplica), necesidad principal.
4. Calificar el lead: ¿tiene presupuesto? ¿es el decisor? ¿cuál es su urgencia?
5. Ofrecer el siguiente paso concreto: demo, llamada, envío de propuesta, etc.

Reglas de comportamiento:
- Responde siempre en el idioma del lead (español por defecto).
- Sé conciso: mensajes de WhatsApp cortos, máximo 3-4 oraciones por turno.
- Nunca inventes precios ni compromisos que no puedas cumplir.
- Si el lead hace preguntas muy técnicas o pide cotización exacta, agenda una llamada con el equipo.
- Si el lead no parece interesado, despídete cordialmente y ofrece quedar disponible para el futuro.
- Cuando tengas nombre + necesidad + nivel de interés, escribe al final de tu respuesta la etiqueta:
  [LEAD_CALIFICADO: nombre=<nombre>, necesidad=<descripción breve>, nivel=<alto|medio|bajo>]
  Esta etiqueta es invisible para el lead; es para el sistema interno.
"""


def _get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def _build_system_prompt() -> str:
    return SYSTEM_PROMPT.format(
        agent_name=os.getenv("AGENT_NAME", "Sofia"),
        business_name=os.getenv("BUSINESS_NAME", "Nuestra Empresa"),
        business_description=os.getenv(
            "BUSINESS_DESCRIPTION",
            "Empresa especializada en soluciones tecnológicas para empresas.",
        ),
    )


def get_conversation(phone_number: str) -> list[dict]:
    """Return the conversation history for a given phone number."""
    return _conversations.get(phone_number, [])


def clear_conversation(phone_number: str) -> None:
    """Reset conversation for a phone number (useful for testing)."""
    _conversations.pop(phone_number, None)


def extract_lead_data(response_text: str) -> Optional[dict]:
    """
    Parse the hidden [LEAD_CALIFICADO: ...] tag from Claude's response.
    Returns a dict with lead info, or None if not present yet.
    """
    import re

    pattern = r"\[LEAD_CALIFICADO:\s*nombre=(.+?),\s*necesidad=(.+?),\s*nivel=(alto|medio|bajo)\]"
    match = re.search(pattern, response_text, re.IGNORECASE)
    if match:
        return {
            "nombre": match.group(1).strip(),
            "necesidad": match.group(2).strip(),
            "nivel": match.group(3).strip().lower(),
        }
    return None


def clean_response(response_text: str) -> str:
    """Remove internal tags before sending to the user."""
    import re

    return re.sub(
        r"\[LEAD_CALIFICADO:[^\]]*\]", "", response_text, flags=re.IGNORECASE
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
        system=_build_system_prompt(),
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
