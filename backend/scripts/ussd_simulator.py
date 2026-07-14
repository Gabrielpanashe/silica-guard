"""
Interactive USSD simulator for local testing — behaves like a real phone
dialing SilicaGuard's USSD shortcode against a locally running server.

Usage:
    cd backend
    ./venv/Scripts/python.exe scripts/ussd_simulator.py

Type a menu number and press Enter at each prompt, exactly like a phone.
The script keeps track of the accumulated `text` and sessionId for you —
that's the part that was tedious to do by hand with curl.
"""

import uuid

import requests

SERVER_URL = "http://127.0.0.1:8000/api/ussd"
SERVICE_CODE = "*384*1#"


def main():
    session_id = f"sim-{uuid.uuid4().hex[:8]}"
    phone_number = input("Simulated phone number (e.g. +263771112222): ").strip()
    if not phone_number:
        phone_number = "+263771112222"

    choices = []
    print(f"\nDialing {SERVICE_CODE} ... (sessionId={session_id})\n")

    while True:
        text = "*".join(choices)
        resp = requests.post(
            SERVER_URL,
            data={
                "sessionId": session_id,
                "phoneNumber": phone_number,
                "serviceCode": SERVICE_CODE,
                "text": text,
            },
        )
        resp.raise_for_status()
        body = resp.text

        prefix, _, message = body.partition(" ")
        print("-" * 60)
        print(message)
        print("-" * 60)

        if prefix == "END":
            print("\n[Session ended]")
            break

        choice = input("\nYour choice: ").strip()
        if not choice:
            print("(empty input not allowed on a real phone — try again)")
            continue
        choices.append(choice)


if __name__ == "__main__":
    main()
