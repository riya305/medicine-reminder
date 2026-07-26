"""
Agent 2 support: deterministic WhatsApp reminder text, sent via the Twilio API.

Every value here (medicine name, dosage, timing, benefits, precautions) is already known
from the Intake Agent's schedule row, so building the message is plain template-filling --
no LLM call needed at fire time.
"""

import os

from twilio.rest import Client

from config import TWILIO_WHATSAPP_FROM

TEMPLATE = (
    "\U0001F514 REMINDER / DAWA KHANE KA SAMAY \U0001F514\n"
    "Mummy/Papa, aapki {medicine_name} khane ka samay ho gaya hai.\n"
    "Dosage: {dosage} ({timing_label}).\n"
    "{info_block}"
    "Kripya dawa khakar mujhe bataiyye!"
)


def format_reminder(medicine_name, dosage, timing_label, benefits="", precautions=""):
    info_lines = []
    if benefits:
        info_lines.append(f"ℹ️ {benefits}")
    if precautions:
        info_lines.append(f"⚠️ {precautions}")
    info_block = "\n" + "\n".join(info_lines) + "\n\n" if info_lines else "\n"

    return TEMPLATE.format(
        medicine_name=medicine_name,
        dosage=dosage,
        timing_label=timing_label,
        info_block=info_block,
    )


def _get_twilio_client():
    account_sid = os.environ["TWILIO_ACCOUNT_SID"]
    auth_token = os.environ["TWILIO_AUTH_TOKEN"]
    return Client(account_sid, auth_token)


def send_whatsapp_reminder(parent_phone, medicine_name, dosage, timing_label, benefits="", precautions=""):
    """Format the reminder and send it to parent_phone (E.164) via Twilio WhatsApp."""
    body = format_reminder(medicine_name, dosage, timing_label, benefits, precautions)
    client = _get_twilio_client()
    return client.messages.create(
        from_=TWILIO_WHATSAPP_FROM,
        to=f"whatsapp:{parent_phone}",
        body=body,
    )
