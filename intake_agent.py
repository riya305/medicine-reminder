"""
Agent 1: The Intake Agent (LLM-backed).

Two entry points:
- parse_dosage_schedule / add_prescription: typed medicine name + dosage + frequency text.
- parse_prescription_image / add_prescription_from_image: a photo of the prescription or
  medicine strip; Claude reads the medicine name, dosage, and frequency directly from the
  image in the same call.

Both convert dosage-frequency shorthand (OD, BD, TDS, QID, HS, SOS, meal-relative phrasing
like "after breakfast") into concrete daily alert times, then persist one row per
(parent, medicine, alert time) into the database.
"""

import base64
import json

import db
from config import MEAL_TIMES, BEFORE_MEAL_OFFSET_MINUTES
from llm import get_client

MODEL = "claude-opus-5"

SCHEDULE_ITEM_SCHEMA = {
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
}

DOSAGE_RULES = f"""Anchor times (24-hour clock), used when no single meal is named:
- breakfast: {MEAL_TIMES['breakfast']}
- lunch: {MEAL_TIMES['lunch']}
- dinner: {MEAL_TIMES['dinner']}
- bedtime: {MEAL_TIMES['bedtime']}

Shorthand meanings:
- OD / once daily -> 1 dose, at breakfast unless another meal is named
- BD / BID / twice daily / "1-0-1" -> 2 doses, at breakfast and dinner unless meals are named
- TDS / TID / thrice daily / "1-1-1" -> 3 doses, at breakfast, lunch, and dinner
- QID / QDS / four times a day -> 4 doses, at breakfast, lunch, dinner, and bedtime
- HS / at bedtime / at night -> 1 dose, at bedtime
- SOS / as needed / as required -> no fixed schedule; return an empty "schedule" array

When the text says "before" a meal, use that meal's anchor time minus {BEFORE_MEAL_OFFSET_MINUTES} \
minutes. When it says "after" a meal (or says nothing), use the anchor time as-is.

For each resulting dose time, write a short Hinglish "timing_label" a non-tech Indian parent \
would recognize, e.g. "Nashte ke baad" (after breakfast), "Nashte se pehle" (before breakfast), \
"Lunch ke baad", "Dinner ke baad", "Sone se pehle" (bedtime)."""

INFO_RULES = """Also write two short informational lines about the medicine, in simple Hinglish, \
for a non-tech Indian parent:
- "benefits": one sentence on what the medicine is generically used for.
- "precautions": one sentence on common allergic reactions or precautions to watch for, ending \
with a short nudge to confirm with the doctor or pharmacist (e.g. "Doctor/pharmacist se zaroor \
confirm karein"). Only state widely-known, generic drug-class information; do not guess at \
dosing-specific risk. If the medicine name isn't recognizable or you are not confident, return \
an empty string for both fields rather than guessing."""

SCHEDULE_SCHEMA = {
    "type": "object",
    "properties": {
        "schedule": {"type": "array", "items": SCHEDULE_ITEM_SCHEMA},
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

{DOSAGE_RULES}

{INFO_RULES}

Return only the schedule, benefits, and precautions as JSON matching the provided schema."""

MEDICINE_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "medicine_name": {
            "type": "string",
            "description": (
                "Just the drug's name (e.g. 'Paracetamol'), without a dosage-form prefix "
                "like 'Tab.', 'Cap.', or 'Syrup' -- put the form in dosage instead."
            ),
        },
        "dosage": {
            "type": "string",
            "description": "Strength and, if written, form, e.g. '500mg tablet' or '5ml syrup'.",
        },
        "schedule": {
            "type": "array",
            "items": SCHEDULE_ITEM_SCHEMA,
            "description": "Empty if this medicine's frequency is SOS/as-needed.",
        },
        "benefits": {"type": "string"},
        "precautions": {"type": "string"},
    },
    "required": ["medicine_name", "dosage", "schedule", "benefits", "precautions"],
    "additionalProperties": False,
}

PRESCRIPTION_IMAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "readable": {
            "type": "boolean",
            "description": (
                "Whether the image is clear enough to confidently read at least one medicine's "
                "name and dosage. False if handwriting, lighting, or blur make you unsure of "
                "everything on the page."
            ),
        },
        "extraction_notes": {
            "type": "string",
            "description": (
                "If readable is false, a brief note on what's unclear (e.g. 'handwriting "
                "illegible throughout'). Empty string if readable is true."
            ),
        },
        "medicines": {
            "type": "array",
            "items": MEDICINE_ITEM_SCHEMA,
            "description": (
                "One entry per medicine you can confidently read on the prescription. Skip "
                "any single medicine you aren't confident about rather than guessing -- you "
                "don't need to reject the whole image just because one line is illegible."
            ),
        },
    },
    "required": ["readable", "extraction_notes", "medicines"],
    "additionalProperties": False,
}

IMAGE_SYSTEM_PROMPT = f"""You read a photo of an Indian prescription or medicine strip/foil. A \
prescription commonly lists several medicines together -- extract every one you can confidently \
read, each as its own entry in "medicines". Never guess at a medicine name or dosage you aren't \
confident about -- getting this wrong is a real safety risk. It's fine to skip one illegible \
line while still extracting the others; you only need to reject the whole image (set "readable" \
to false, "medicines" to an empty list, and explain in "extraction_notes") if nothing on it can \
be confidently read at all.

For each medicine you do extract, apply these rules to whatever dosage-frequency shorthand you \
find (e.g. "OD", "1-0-1", "BD after food", "Q6H" for every 6 hours -> 4 doses/day at the QID \
anchor times, "SOS" for as-needed -> leave that medicine's "schedule" empty, it simply won't get \
a reminder):

{DOSAGE_RULES}

{INFO_RULES} (per medicine)

Return only JSON matching the provided schema."""

IMAGE_MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


class UnschedulableDosage(Exception):
    """Raised when the dosage text describes an as-needed dose with no fixed time."""


class UnreadablePrescription(Exception):
    """Raised when a prescription photo isn't clear enough to safely extract details from."""


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


def _detect_media_type(image_bytes):
    """Sniff the actual image format from its magic bytes -- file extensions are unreliable
    (e.g. a browser-saved WebP file renamed/exported with a .png extension)."""
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    if image_bytes.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    raise ValueError(
        f"Unrecognized image format. Supported formats: {', '.join(sorted(set(IMAGE_MEDIA_TYPES.values())))}"
    )


def parse_prescription_image(image_path):
    """Call Claude (vision) to read a prescription/medicine-strip photo and extract every
    medicine's name, dosage, schedule, and benefits/precautions in one call. Returns a list
    of medicine dicts."""
    with open(image_path, "rb") as f:
        raw = f.read()
    media_type = _detect_media_type(raw)
    image_data = base64.standard_b64encode(raw).decode("utf-8")

    client = get_client()
    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=IMAGE_SYSTEM_PROMPT,
        output_config={
            "effort": "low",
            "format": {"type": "json_schema", "schema": PRESCRIPTION_IMAGE_SCHEMA},
        },
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": image_data},
                },
                {"type": "text", "text": "Read this prescription/medicine photo and extract the details."},
            ],
        }],
    )
    text = next(block.text for block in response.content if block.type == "text")
    data = json.loads(text)
    if not data["readable"] or not data["medicines"]:
        raise UnreadablePrescription(
            data["extraction_notes"] or "Prescription image isn't clear enough to read safely."
        )
    return data["medicines"]


def add_prescription_from_image(parent_phone, image_path):
    """
    Read a prescription photo via the Intake Agent's vision call and persist one schedule
    row per resulting alert time, for every medicine found on the prescription. Medicines
    marked as-needed (SOS) are reported but not scheduled -- they have no fixed time to
    remind about. Returns a list of {"medicine_name", "dosage", "schedule", "benefits",
    "precautions", "scheduled"} dicts, one per medicine, for confirmation/logging.

    Raises UnschedulableDosage only if every medicine found is as-needed (nothing at all
    got scheduled).
    """
    medicines = parse_prescription_image(image_path)
    results = []
    for medicine in medicines:
        medicine_name = medicine["medicine_name"]
        dosage = medicine["dosage"]
        benefits = medicine["benefits"]
        precautions = medicine["precautions"]
        created = []
        for entry in medicine["schedule"]:
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
        results.append({
            "medicine_name": medicine_name,
            "dosage": dosage,
            "schedule": created,
            "benefits": benefits,
            "precautions": precautions,
            "scheduled": bool(created),
        })

    if not any(result["scheduled"] for result in results):
        names = ", ".join(r["medicine_name"] for r in results)
        raise UnschedulableDosage(f"All medicines found ({names}) are as-needed with no fixed schedule")

    return results
