"""
Agent 1: The Intake Agent (LLM-backed).

Calls Claude to parse freeform prescription dosage-frequency shorthand (OD, BD, TDS,
QID, HS, SOS, plus meal-relative phrasing like "after breakfast") into concrete daily
alert times, then persists one row per (parent, medicine, alert time) into the database.
"""

import json

import db
from config import MEAL_TIMES, BEFORE_MEAL_OFFSET_MINUTES
from llm import get_client

MODEL = "claude-opus-5"

SCHEDULE_SCHEMA = {
    "type": "object",
    "properties": {
        "schedule": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "alert_time_24": {
                        "type": "string",
                        "description": "24-hour clock time, HH:MM",
                    },
                    "alert_time_display": {
                        "type": "string",
                        "description": "12-hour clock time with AM/PM, e.g. '08:00 AM'",
                    },
                    "timing_label": {
                        "type": "string",
                        "description": "Short Hinglish label, e.g. 'Nashte ke baad'",
                    },
                },
                "required": ["alert_time_24", "alert_time_display", "timing_label"],
                "additionalProperties": False,
            },
        },
        "benefits": {
            "type": "string",
            "description": (
                "One short Hinglish sentence on what this medicine is generically used for. "
                "Empty string if the medicine name isn't recognizable."
            ),
        },
        "precautions": {
            "type": "string",
            "description": (
                "One short Hinglish sentence on common allergic reactions or precautions to "
                "watch for with this medicine, ending with a nudge to confirm with the doctor "
                "or pharmacist. Empty string if the medicine name isn't recognizable."
            ),
        },
    },
    "required": ["schedule", "benefits", "precautions"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = f"""You convert Indian prescription dosage-frequency shorthand into concrete \
daily WhatsApp reminder times for a parent's medicine schedule.

Anchor times (24-hour clock), used when no single meal is named:
- breakfast: {MEAL_TIMES['breakfast']}
- lunch: {MEAL_TIMES['lunch']}
- dinner: {MEAL_TIMES['dinner']}
- bedtime: {MEAL_TIMES['bedtime']}

Shorthand meanings:
- OD / once daily -> 1 dose, at breakfast unless another meal is named
- BD / BID / twice daily -> 2 doses, at breakfast and dinner unless meals are named
- TDS / TID / thrice daily -> 3 doses, at breakfast, lunch, and dinner
- QID / QDS / four times a day -> 4 doses, at breakfast, lunch, dinner, and bedtime
- HS / at bedtime / at night -> 1 dose, at bedtime
- SOS / as needed / as required -> no fixed schedule; return an empty "schedule" array

When the text says "before" a meal, use that meal's anchor time minus {BEFORE_MEAL_OFFSET_MINUTES} \
minutes. When it says "after" a meal (or says nothing), use the anchor time as-is.

For each resulting dose time, write a short Hinglish "timing_label" a non-tech Indian parent \
would recognize, e.g. "Nashte ke baad" (after breakfast), "Nashte se pehle" (before breakfast), \
"Lunch ke baad", "Dinner ke baad", "Sone se pehle" (bedtime).

Also write two short informational lines about the named medicine, in simple Hinglish, for a \
non-tech Indian parent:
- "benefits": one sentence on what the medicine is generically used for.
- "precautions": one sentence on common allergic reactions or precautions to watch for, ending \
with a short nudge to confirm with the doctor or pharmacist (e.g. "Doctor/pharmacist se zaroor \
confirm karein"). Only state widely-known, generic drug-class information; do not guess at \
dosing-specific risk. If the medicine name isn't recognizable or you are not confident, return \
an empty string for both fields rather than guessing.

Return only the schedule, benefits, and precautions as JSON matching the provided schema."""


class UnschedulableDosage(Exception):
    """Raised when the dosage text describes an as-needed dose with no fixed time."""


def parse_dosage_schedule(medicine_name, frequency_text):
    """Call Claude to turn e.g. 'OD after breakfast' or 'BD' into concrete alert-time entries,
    plus a short benefits/precautions blurb for the named medicine."""
    client = get_client()
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        output_config={
            "effort": "low",
            "format": {"type": "json_schema", "schema": SCHEDULE_SCHEMA},
        },
        messages=[{
            "role": "user",
            "content": f"Medicine name: {medicine_name!r}\nDosage frequency text: {frequency_text!r}",
        }],
    )
    text = next(block.text for block in response.content if block.type == "text")
    data = json.loads(text)
    if not data["schedule"]:
        raise UnschedulableDosage(f"'{frequency_text}' is an as-needed dose with no fixed schedule")
    return data


def add_prescription(parent_phone, medicine_name, dosage, frequency_text):
    """
    Parse the dosage frequency via the Intake Agent and persist one schedule row per
    resulting alert time. Returns {"schedule": [...], "benefits": str, "precautions": str}
    for confirmation/logging.
    """
    data = parse_dosage_schedule(medicine_name, frequency_text)
    benefits = data["benefits"]
    precautions = data["precautions"]
    created = []
    for entry in data["schedule"]:
        db.insert_schedule(
            parent_phone=parent_phone,
            medicine_name=medicine_name,
            dosage=dosage,
            timing_label=entry["timing_label"],
            alert_time_24=entry["alert_time_24"],
            alert_time_display=entry["alert_time_display"],
            benefits=benefits,
            precautions=precautions,
        )
        created.append(entry)
    return {"schedule": created, "benefits": benefits, "precautions": precautions}
