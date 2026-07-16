"""
Interactive login for sekefarshad.ir. Run this once (and again only if
the platform ever invalidates the saved session):

    python login.py

You'll be asked for your phone number, then the code sekefarshad.ir
texts you. On success, the session is saved to session.json and
goldbridge's main.py will pick it up automatically on its next start -
no need to touch .env's BRIDGE_SOURCE_UID/BRIDGE_SOURCE_UTOKEN by hand
again after this.

⚠️ TODO: the two endpoint calls below (REQUEST_CODE_URL /
VERIFY_CODE_URL and their payload shapes) are placeholders. They need
to be filled in with the real values once you capture them from your
browser's Network tab while logging into sekefarshad.ir/trade
yourself - see the request in chat for exactly what to capture. Until
then, running this script will fail at the first request with a clear
error rather than silently doing the wrong thing.
"""
import os
import sys

import httpx
from dotenv import load_dotenv

from session_store import save_session

load_dotenv()

SOURCE_BASE_URL = os.getenv("BRIDGE_SOURCE_BASE_URL", "https://sekefarshad.ir/server/api")

# TODO: replace with the real endpoint paths once captured from DevTools
REQUEST_CODE_URL = f"{SOURCE_BASE_URL}/auth/request-code.php"   # placeholder
VERIFY_CODE_URL = f"{SOURCE_BASE_URL}/auth/verify-code.php"     # placeholder


def request_code(phone: str):
    # TODO: confirm the real payload field name for the phone number
    # (guessing "phone" for now - replace once confirmed)
    resp = httpx.post(REQUEST_CODE_URL, data={"phone": phone}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("state"):
        raise RuntimeError(f"درخواست کد ناموفق بود: {data.get('msg')}")
    return data


def verify_code(phone: str, code: str) -> tuple[str, str]:
    # TODO: confirm the real payload field names and response shape
    # (guessing "phone"/"code" and a "uID"/"uToken" pair in the
    # response for now - replace once confirmed)
    resp = httpx.post(VERIFY_CODE_URL, data={"phone": phone, "code": code}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("state"):
        raise RuntimeError(f"تایید کد ناموفق بود: {data.get('msg')}")

    uid = data.get("uID") or data.get("data", {}).get("uID")
    utoken = data.get("uToken") or data.get("data", {}).get("uToken")
    if not uid or not utoken:
        raise RuntimeError(f"uID/uToken در پاسخ پیدا نشد: {data}")
    return str(uid), str(utoken)


def main():
    phone = input("شماره موبایل (همون شماره‌ای که در سکه فرشاد ثبت شده): ").strip()

    print("در حال ارسال کد تایید...")
    try:
        request_code(phone)
    except Exception as e:
        print(f"خطا: {e}")
        sys.exit(1)

    code = input("کدی که پیامک شد رو وارد کن: ").strip()

    print("در حال بررسی کد...")
    try:
        uid, utoken = verify_code(phone, code)
    except Exception as e:
        print(f"خطا: {e}")
        sys.exit(1)

    save_session(uid, utoken, phone_number=phone)
    print(f"ورود موفق بود. uID={uid} ذخیره شد در session.json")
    print("حالا می‌تونی goldbridge رو عادی اجرا کنی - دیگه نیازی به login دستی نیست.")


if __name__ == "__main__":
    main()