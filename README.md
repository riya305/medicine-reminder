# Medicine Reminder

A two-agent system that reads a prescription's dosage shorthand (e.g. `OD after breakfast`,
`BD`), turns it into a daily schedule, and sends the parent a WhatsApp reminder over Twilio
when a dose is due.

## How it works

- **Agent 1 — Intake Agent** ([intake_agent.py](intake_agent.py)): calls Claude to parse
  freeform dosage-frequency text (`OD`, `BD`, `TDS`, `QID`, `HS`, `SOS`, meal-relative phrasing
  like "after breakfast") into concrete daily alert times, plus a short benefits/precautions
  blurb for the medicine. Saves one row per (parent phone, medicine, alert time) to SQLite.
- **Agent 2 — Background Alarm Agent** ([alarm_agent.py](alarm_agent.py)): a daemon thread that
  wakes up every 60 seconds, checks the database for any schedule matching the current clock
  time, and — if found — calls Claude to generate the reminder text and sends it via the Twilio
  WhatsApp API ([messaging.py](messaging.py)).
- **Storage** ([db.py](db.py)): a single SQLite file (`reminders.db`, created on first run).

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # then fill in your real keys below
```

`.env` needs:

| Variable | Where to get it |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic Console → API Keys |
| `TWILIO_ACCOUNT_SID` | Twilio Console dashboard |
| `TWILIO_AUTH_TOKEN` | Twilio Console dashboard |

`.env` is gitignored — never commit it.

### Twilio WhatsApp sender

`config.py` defaults `TWILIO_WHATSAPP_FROM` to Twilio's shared **WhatsApp Sandbox** number
(`whatsapp:+14155238886`), which needs no business verification — just have the recipient send
the sandbox's join code (Twilio Console → Messaging → Try it out → Send a WhatsApp message) to
that number once. For production sending outside the sandbox you'll need a Meta-approved
WhatsApp Business sender and pre-approved message templates.

## Usage

```bash
# Add a prescription — Agent 1 parses the schedule
.venv/bin/python main.py add +91XXXXXXXXXX "Paracetamol" "500mg" "OD after breakfast"

# List all schedules
.venv/bin/python main.py list [+91XXXXXXXXXX]

# Start the background alarm agent (Agent 2) — runs until Ctrl+C
.venv/bin/python main.py run
```

## Reminder format

```
🔔 REMINDER / DAWA KHANE KA SAMAY 🔔
Mummy/Papa, aapki [Dawaai ka Naam] khane ka samay ho gaya hai.
Dosage: [Dosage Amount] ([Timing Details]).

ℹ️ [Benefits, if known]
⚠️ [Precautions, if known]

Kripya dawa khakar mujhe bataiyye!
```

## Disclaimer

Benefits/precautions text is generated once at intake from the model's general knowledge of the
named medicine, not a live medical database. It's meant as a helpful nudge, not medical advice —
always confirm with a doctor or pharmacist.
