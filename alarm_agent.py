"""
Agent 2: The Background Alarm Agent.

A background thread that wakes up every SCHEDULER_INTERVAL_SECONDS, checks the
database for any medicine schedules matching the current clock time, and fires
a WhatsApp reminder for each match via Twilio.
"""

import threading
import time
from datetime import datetime

import db
import messaging
from config import SCHEDULER_INTERVAL_SECONDS


class AlarmAgent:
    def __init__(self, interval_seconds=SCHEDULER_INTERVAL_SECONDS, on_send=None, on_error=None):
        self.interval_seconds = interval_seconds
        self.on_send = on_send or (lambda entry: None)
        self.on_error = on_error or (lambda entry, exc: None)
        self._stop_event = threading.Event()
        self._thread = None

    def _tick(self):
        now = datetime.now()
        current_time_24 = now.strftime("%H:%M")
        today = now.strftime("%Y-%m-%d")

        for entry in db.get_due_schedules(current_time_24, today):
            try:
                messaging.send_whatsapp_reminder(
                    parent_phone=entry["parent_phone"],
                    medicine_name=entry["medicine_name"],
                    dosage=entry["dosage"],
                    timing_label=entry["timing_label"],
                    benefits=entry["benefits"],
                    precautions=entry["precautions"],
                )
                db.mark_sent(entry["id"], today)
                self.on_send(entry)
            except Exception as exc:
                self.on_error(entry, exc)

    def _run(self):
        while not self._stop_event.is_set():
            self._tick()
            self._stop_event.wait(self.interval_seconds)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="alarm-agent", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=self.interval_seconds + 5)
