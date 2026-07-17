"""
Interactive login for sekefarshad.ir. Run this once (and again only if
the platform ever invalidates the saved session):

    python login.py

You'll be asked for your phone number, then the code sekefarshad.ir
texts you. On success, the session is saved ENCRYPTED to session.enc
(requires BRIDGE_SESSION_KEY in .env - see app/services/session_store.py
for one-time setup) and goldbridge picks it up automatically on its
next start - no need to touch .env's BRIDGE_SOURCE_UID/BRIDGE_SOURCE_UTOKEN
by hand again after this.

⚠️ Both endpoints are now wired to the real API (captured 2026-07-17
from DevTools). uID = the logged-in user's numeric id (user.id in the
response), uToken = the session token string (token in the response) -
these are what every other goldbridge/goldapp request then sends back
as uID/uToken to prove the session is valid.
"""
import os
import platform
import sys

import httpx
from dotenv import load_dotenv

from app.services.session_store import save_session

load_dotenv()

SOURCE_BASE_URL = os.getenv("BRIDGE_SOURCE_BASE_URL", "https://sekefarshad.ir/server/api")

REQUEST_CODE_URL = f"{SOURCE_BASE_URL}/users/loginRequest.php"
VERIFY_CODE_URL = f"{SOURCE_BASE_URL}/users/LoginSms.php"

# Static per-storefront values captured alongside the request - not
# secrets, just identify which store/customer this login is for.
# Override via .env if these ever change.
STORE_NAME = os.getenv("BRIDGE_STORE_NAME", "Farshad Gold")
CUSTOMER_ID = os.getenv("BRIDGE_CUSTOMER_ID", "155")
SMS_URL_DOMAIN = os.getenv("BRIDGE_SMS_URL_DOMAIN", "gold999.ir")

# Reported alongside LoginSms.php in the captured request - a browser
# UA string and device fields. Kept generic/truthful for this script
# (not spoofing a real browser) rather than copying a captured UA verbatim.
_UA = f"goldbridge-login-script/1.0 (Python {platform.python_version()}; {platform.system()})"


def request_code(phone: str):
    """
    Confirmed shape (from DevTools capture):
      POST /users/loginRequest.php
      payload: mobile, storeName, customerId, SMS_URL, uID=0, uToken=""
      Note: the API can return HTTP 401 even for ordinary "wrong number"
      responses, with a normal {state, msg, data} JSON body - so we
      read the body regardless of status code instead of raise_for_status().
    """
    resp = httpx.post(
        REQUEST_CODE_URL,
        data={
            "mobile": phone,
            "storeName": STORE_NAME,
            "customerId": CUSTOMER_ID,
            "SMS_URL": SMS_URL_DOMAIN,
            "uID": "0",
            "uToken": "",
        },
        timeout=10,
    )
    data = resp.json()
    if not data.get("state"):
        raise RuntimeError(f"درخواست کد ناموفق بود: {data.get('msg')}")
    return data


def verify_code(phone: str, code: str) -> tuple[str, str]:
    """
    Confirmed shape (from DevTools capture):
      POST /users/LoginSms.php
      payload: mobile, code, token="", deviceType="browser", ua,
               browserName, mobileVendor="none", mobileModel="none",
               osName, osVersion, uID=0, uToken=""
      response: {state, msg, data, user: {id, ...}, token: "<session token>"}
      -> our uID  = response.user.id
         our uToken = response.token
    """
    resp = httpx.post(
        VERIFY_CODE_URL,
        data={
            "mobile": phone,
            "code": code,
            "token": "",
            "deviceType": "browser",
            "ua": _UA,
            "browserName": "goldbridge-login-script",
            "mobileVendor": "none",
            "mobileModel": "none",
            "osName": platform.system(),
            "osVersion": platform.release(),
            "uID": "0",
            "uToken": "",
        },
        timeout=10,
    )
    data = resp.json()
    if not data.get("state"):
        raise RuntimeError(f"تایید کد ناموفق بود: {data.get('msg')}")

    uid = (data.get("user") or {}).get("id")
    utoken = data.get("token")
    if not uid or not utoken:
        raise RuntimeError(f"uID/uToken در پاسخ پیدا نشد: {data}")
    return str(uid), str(utoken)


def main():
    if not os.getenv("BRIDGE_SESSION_KEY"):
        print(
            "⚠️  BRIDGE_SESSION_KEY تنظیم نشده - session رمزنگاری‌شده ذخیره نمی‌شه.\n"
            "   برای ساختنش:\n"
            '   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"\n'
            "   و نتیجه رو در .env به عنوان BRIDGE_SESSION_KEY قرار بده، بعد دوباره اجرا کن.\n"
        )
        sys.exit(1)

    phone = os.getenv("BRIDGE_LOGIN_PHONE")
    if phone:
        print(f"شماره موبایل از .env خونده شد (BRIDGE_LOGIN_PHONE).")
    else:
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

    saved = save_session(uid, utoken, phone_number=phone)
    if saved:
        print(f"ورود موفق بود. session رمزنگاری‌شده در session.enc ذخیره شد.")
        print("حالا می‌تونی goldbridge رو عادی اجرا کنی - دیگه نیازی به login دستی نیست.")
    else:
        print(f"ورود موفق بود اما ذخیره روی دیسک انجام نشد (BRIDGE_SESSION_KEY تنظیم نشده).")
        print(f"uID={uid}\nuToken={utoken}")
        print("این مقادیر رو دستی در BRIDGE_SOURCE_UID / BRIDGE_SOURCE_UTOKEN در .env قرار بده.")


if __name__ == "__main__":
    main()