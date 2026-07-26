# Default meal/anchor times used to translate dosage shorthand (OD, BD, TDS...)
# and meal-relative phrasing ("after breakfast") into concrete clock times.
# Adjust these to match the household's actual routine.

MEAL_TIMES = {
    "breakfast": "08:00",
    "lunch": "14:00",
    "dinner": "20:00",
    "bedtime": "22:00",
}

# Minutes to shift when a dose is explicitly "before" a meal instead of "after".
BEFORE_MEAL_OFFSET_MINUTES = 30

DB_PATH = "reminders.db"

# Twilio WhatsApp sender, e.g. "whatsapp:+14155238886" (sandbox) or your approved number.
TWILIO_WHATSAPP_FROM = "whatsapp:+14155238886"

SCHEDULER_INTERVAL_SECONDS = 60
