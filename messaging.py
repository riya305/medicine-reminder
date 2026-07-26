"""
Agent 2 support: LLM-generated WhatsApp reminder text, sent via the Twilio API.
"""

import json
import os

from twilio.rest import Client

from config import TWILIO_WHATSAPP_FROM
from llm import get_client

MODEL = "claude-opus-5"

MESSAGE_SCHEMA = {
    "type": "object",
    "properties": {"message": {"type": "string"}},
    "required": ["message"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """You write a WhatsApp medicine reminder for an Indian parent, filling in the \
bracketed placeholders in the template below with the given medicine name, dosage, and timing. \
Keep the emoji, wording, and line breaks exactly as shown outside the placeholders.

Template:
\U0001F514 REMINDER / DAWA KHANE KA SAMAY \U0001F514
Mummy/Papa, aapki [Dawaai ka Naam] khane ka samay ho gaya hai.
Dosage: [Dosage Amount] ([Timing Details]).

Kripya dawa khakar mujhe bataiyye!

If a "Benefits" line and/or a "Precautions" line are given below, append them after the Dosage \
line and before the closing "Kripya dawa khakar mujhe bataiyye!" line, each on its own line, \
prefixed with ℹ️ for benefits and ⚠️ for precautions. If either is missing or \
empty, omit that line entirely rather than inventing one.

Return only the finished message as JSON matching the provided schema."""


def generate_reminder_message(medicine_name, dosage, timing_label, benefits="", precautions=""):
    user_content = (
        f"Dawaai ka Naam: {medicine_name}\n"
        f"Dosage Amount: {dosage}\n"
        f"Timing Details: {timing_label}\n"
        f"Benefits: {benefits}\n"
        f"Precautions: {precautions}"
    )
    client = get_client()
    response = client.messages.create(
        model=MODEL,
        max_tokens=512,
        system=SYSTEM_PROMPT,
        output_config={
            "effort": "low",
            "format": {"type": "json_schema", "schema": MESSAGE_SCHEMA},
        },
        messages=[{"role": "user", "content": user_content}],
    )
    text = next(block.text for block in response.content if block.type == "text")
    return json.loads(text)["message"]


def _get_twilio_client():
    account_sid = os.environ["TWILIO_ACCOUNT_SID"]
    auth_token = os.environ["TWILIO_AUTH_TOKEN"]
    return Client(account_sid, auth_token)


def send_whatsapp_reminder(parent_phone, medicine_name, dosage, timing_label, benefits="", precautions=""):
    """Generate the reminder via Claude and send it to parent_phone (E.164) via Twilio WhatsApp."""
    body = generate_reminder_message(medicine_name, dosage, timing_label, benefits, precautions)
    client = _get_twilio_client()
    return client.messages.create(
        from_=TWILIO_WHATSAPP_FROM,
        to=f"whatsapp:{parent_phone}",
        body=body,
    )
