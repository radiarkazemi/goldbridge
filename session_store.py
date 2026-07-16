"""
Persists the logged-in session (uID/uToken) to a local JSON file, so
goldbridge doesn't need to re-login every time it restarts. Only the
login itself (see login.py) requires a human to read the SMS code off
their phone - once logged in, the resulting session is reused
indefinitely until the platform itself invalidates it.
"""
import json
import os

SESSION_PATH = os.path.join(os.path.dirname(__file__), "session.json")


def load_session() -> dict | None:
    if not os.path.exists(SESSION_PATH):
        return None
    try:
        with open(SESSION_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("uid") and data.get("utoken"):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return None


def save_session(uid: str, utoken: str, phone_number: str = ""):
    data = {"uid": uid, "utoken": utoken, "phone_number": phone_number}
    with open(SESSION_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def clear_session():
    if os.path.exists(SESSION_PATH):
        os.remove(SESSION_PATH)