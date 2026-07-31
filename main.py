"""
CLI entry point.

    python main.py add +919876543210 "Paracetamol" "500mg" "OD after breakfast"
    python main.py add-image +919876543210 ./prescription.jpg
    python main.py list [+919876543210]
    python main.py run
"""

import sys
import time

from dotenv import load_dotenv

load_dotenv()

import db
from alarm_agent import AlarmAgent
from intake_agent import (
    add_prescription,
    add_prescription_from_image,
    UnreadablePrescription,
    UnschedulableDosage,
)


def _print_result(result, parent_phone, medicine_name, dosage):
    print(f"Scheduled {medicine_name} ({dosage}) for {parent_phone}:")
    for entry in result["schedule"]:
        print(f"  {entry['alert_time_display']} - {entry['timing_label']}")
    if result["benefits"]:
        print(f"  Benefits: {result['benefits']}")
    if result["precautions"]:
        print(f"  Precautions: {result['precautions']}")


def cmd_add(args):
    if len(args) != 4:
        print("Usage: python main.py add <parent_phone> <medicine_name> <dosage> <frequency_text>")
        sys.exit(1)
    parent_phone, medicine_name, dosage, frequency_text = args
    try:
        result = add_prescription(parent_phone, medicine_name, dosage, frequency_text)
    except UnschedulableDosage as exc:
        print(f"Not scheduled: {exc}")
        sys.exit(1)
    _print_result(result, parent_phone, medicine_name, dosage)


def cmd_add_image(args):
    if len(args) != 2:
        print("Usage: python main.py add-image <parent_phone> <image_path>")
        sys.exit(1)
    parent_phone, image_path = args
    try:
        results = add_prescription_from_image(parent_phone, image_path)
    except UnreadablePrescription as exc:
        print(f"Could not read prescription image: {exc}")
        sys.exit(1)
    except UnschedulableDosage as exc:
        print(f"Not scheduled: {exc}")
        sys.exit(1)
    print(f"Found {len(results)} medicine(s) for {parent_phone}:")
    for result in results:
        if result["scheduled"]:
            _print_result(result, parent_phone, result["medicine_name"], result["dosage"])
        else:
            print(f"Skipped {result['medicine_name']} ({result['dosage']}) - as-needed, no fixed schedule")


def cmd_list(args):
    parent_phone = args[0] if args else None
    for row in db.list_schedules(parent_phone):
        status = "active" if row["active"] else "inactive"
        print(
            f"[{row['id']}] {row['parent_phone']} | {row['medicine_name']} ({row['dosage']}) "
            f"@ {row['alert_time_display']} ({row['timing_label']}) - {status}, "
            f"last_sent={row['last_sent_date']}"
        )


def cmd_run(args):
    def on_send(entry):
        print(f"Sent reminder: {entry['medicine_name']} -> {entry['parent_phone']} at {entry['alert_time_display']}")

    def on_error(entry, exc):
        print(f"Failed to send reminder for schedule {entry['id']}: {exc}")

    agent = AlarmAgent(on_send=on_send, on_error=on_error)
    agent.start()
    print("Alarm agent running. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        agent.stop()
        print("Stopped.")


COMMANDS = {"add": cmd_add, "add-image": cmd_add_image, "list": cmd_list, "run": cmd_run}


def main():
    db.init_db()
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"Usage: python main.py <{'|'.join(COMMANDS)}> ...")
        sys.exit(1)
    COMMANDS[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    main()
