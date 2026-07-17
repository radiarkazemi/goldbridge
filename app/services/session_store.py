"""
Persists the logged-in session (uID/uToken) to a local file, ENCRYPTED
AT REST with a key that lives only in .env (BRIDGE_SESSION_KEY) - never
committed, never logged. uID/uToken are the live credentials that
authenticate as the sekefarshad.ir account this bridge polls under, so
leaving them in a plaintext file on disk is the same risk as leaving a
password in a text file.

Setup (one-time per machine):
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
Put the output in .env as BRIDGE_SESSION_KEY=... - this key is
per-machine and does NOT need to match across your two PCs; each
machine encrypts its own session.enc with its own key. It only needs
to stay the same across restarts of the same machine (so the
already-saved session.enc can still be decrypted).

If BRIDGE_SESSION_KEY is missing, session save/load is disabled and a
warning is logged - login.py will still print the uID/uToken to the
terminal so you can set them via BRIDGE_SOURCE_UID/BRIDGE_SOURCE_UTOKEN
in .env instead, but nothing is written to disk unencrypted.
"""
import json
import os

from cryptography.fernet import Fernet, InvalidToken

SESSION_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "session.enc")


def _get_fernet() -> Fernet | None:
    key = os.getenv("BRIDGE_SESSION_KEY")
    if not key:
        return None
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError):
        return None


def load_session() -> dict | None:
    fernet = _get_fernet()
    if fernet is None or not os.path.exists(SESSION_PATH):
        return None
    try:
        with open(SESSION_PATH, "rb") as f:
            encrypted = f.read()
        decrypted = fernet.decrypt(encrypted)
        data = json.loads(decrypted)
        if data.get("uid") and data.get("utoken"):
            return data
    except (InvalidToken, json.JSONDecodeError, OSError):
        # Wrong/rotated key, corrupted file, or missing - treat as "no
        # saved session" rather than crashing; poller.py falls back to
        # BRIDGE_SOURCE_UID/UTOKEN from .env in that case.
        pass
    return None


def save_session(uid: str, utoken: str, phone_number: str = "") -> bool:
    """Returns True if the session was actually written to disk
    (requires BRIDGE_SESSION_KEY to be set)."""
    fernet = _get_fernet()
    if fernet is None:
        return False
    payload = json.dumps({"uid": uid, "utoken": utoken, "phone_number": phone_number}).encode()
    encrypted = fernet.encrypt(payload)
    with open(SESSION_PATH, "wb") as f:
        f.write(encrypted)
    try:
        os.chmod(SESSION_PATH, 0o600)  # owner read/write only; no-op on Windows
    except OSError:
        pass
    return True