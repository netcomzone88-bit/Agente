"""
FastAPI server that receives Twilio WhatsApp webhooks and replies via Claude.

Setup:
  1. Copy .env.example to .env and fill in your credentials.
  2. pip install -r requirements.txt
  3. uvicorn main:app --reload --port 8000
  4. Expose the server (e.g. ngrok http 8000) and set the Twilio webhook URL to:
       https://<your-ngrok-url>/webhook/whatsapp
"""

import logging
import os
from typing import Annotated

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request, Response
from fastapi.responses import PlainTextResponse
from twilio.rest import Client as TwilioClient
from twilio.request_validator import RequestValidator

from agent import clear_conversation, respond_to_lead

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="Lead Agent — WhatsApp", version="1.0.0")

# ---------------------------------------------------------------------------
# Twilio helpers
# ---------------------------------------------------------------------------

def _twilio_client() -> TwilioClient:
    return TwilioClient(
        os.environ["TWILIO_ACCOUNT_SID"],
        os.environ["TWILIO_AUTH_TOKEN"],
    )


def _send_whatsapp(to: str, body: str) -> None:
    """Send a WhatsApp message via Twilio."""
    client = _twilio_client()
    msg = client.messages.create(
        from_=os.environ["TWILIO_WHATSAPP_NUMBER"],
        to=to,
        body=body,
    )
    log.info("Sent WhatsApp message SID=%s to=%s", msg.sid, to)


def _validate_twilio_request(request: Request, form_data: dict) -> bool:
    """
    Validate that the incoming request genuinely comes from Twilio.
    Skip validation in development when TWILIO_SKIP_VALIDATION=true.
    """
    if os.getenv("TWILIO_SKIP_VALIDATION", "").lower() == "true":
        return True

    validator = RequestValidator(os.environ["TWILIO_AUTH_TOKEN"])
    url = str(request.url)
    signature = request.headers.get("X-Twilio-Signature", "")
    return validator.validate(url, form_data, signature)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/webhook/whatsapp", response_class=PlainTextResponse)
async def whatsapp_webhook(
    request: Request,
    From: Annotated[str, Form()],
    Body: Annotated[str, Form()],
) -> Response:
    """
    Twilio sends a POST here every time a WhatsApp message is received.
    Twilio form fields: From, Body, plus many others (ignored here).
    """
    # Collect full form for signature validation
    form_data = dict(await request.form())

    if not _validate_twilio_request(request, form_data):
        log.warning("Invalid Twilio signature from %s", request.client.host)
        return PlainTextResponse("Forbidden", status_code=403)

    sender = From.strip()
    message = Body.strip()

    log.info("Received from=%s message=%r", sender, message)

    # Special command: reset conversation (useful during testing)
    if message.lower() in ("/reset", "reset", "reiniciar"):
        clear_conversation(sender)
        _send_whatsapp(sender, "Conversación reiniciada. ¡Hola! ¿En qué puedo ayudarte?")
        return PlainTextResponse("ok")

    try:
        reply, lead_data = respond_to_lead(sender, message)
    except Exception as exc:
        log.exception("Error generating reply for %s: %s", sender, exc)
        _send_whatsapp(
            sender,
            "Disculpa, tuve un problema técnico. Inténtalo de nuevo en un momento.",
        )
        return PlainTextResponse("error", status_code=500)

    _send_whatsapp(sender, reply)

    if lead_data:
        log.info(
            "LEAD CALIFICADO — número=%s nombre=%s necesidad=%s nivel=%s",
            sender,
            lead_data["nombre"],
            lead_data["necesidad"],
            lead_data["nivel"],
        )
        # TODO: here you can save lead_data to a CRM, database, or send
        # a Slack/email notification to your sales team.

    return PlainTextResponse("ok")


# ---------------------------------------------------------------------------
# Dev entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
