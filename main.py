"""
goldbridge - a small, standalone service. Its ONLY job: poll a
third-party gold-trading platform (using credentials the platform
owner issued directly) and re-expose the current buy/sell price as a
plain local JSON endpoint.

This is intentionally NOT part of the main app's codebase - it's a
separate private service, with its own credentials, meant to be run on
its own (e.g. as its own systemd service, or even on its own small
VPS). The main app's existing generic API price source
(app/price_sources/api_source.py) can already consume this endpoint
with zero changes to the main app - see README.md.

Run: uvicorn main:app --host 127.0.0.1 --port 9100
(127.0.0.1 only - this should never be reachable from outside the
server it runs on; only the main app, running on the same machine or
over a private network, should ever talk to it.)
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime

import httpx
from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv

from session_store import load_session

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("goldbridge")

SOURCE_BASE_URL = os.getenv("BRIDGE_SOURCE_BASE_URL", "https://sekefarshad.ir/server/api")

# Prefer a saved login session (from `python login.py`) over the static
# .env values - lets you switch to real phone+code login without
# touching .env at all once that's wired up. Falls back to .env so the
# static uID/uToken approach still works in the meantime.
_session = load_session()
SOURCE_UID = (_session or {}).get("uid") or os.getenv("BRIDGE_SOURCE_UID")
SOURCE_UTOKEN = (_session or {}).get("utoken") or os.getenv("BRIDGE_SOURCE_UTOKEN")

# Which entry in the source's "prices" list to use - id=1 ("نقد شنبه")
# in the sample data you shared. Confirm this is actually the entry you
# want before relying on it; change via env if it's a different id.
TARGET_PRICE_ID = int(os.getenv("BRIDGE_TARGET_PRICE_ID", "1"))

# Deliberately conservative - this hits an endpoint authenticated as
# someone else's account. Polling too aggressively risks that account
# getting flagged/rate-limited by the platform, which would break this
# for everyone. 20s is already faster than most retail price boards
# update visually.
POLL_SECONDS = int(os.getenv("BRIDGE_POLL_SECONDS", "20"))

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(poll_loop())
    yield


app = FastAPI(title="goldbridge (private, internal use only)", lifespan=lifespan)

_latest = {"buy": None, "sell": None, "updated_at": None, "source_updated_at": None}


def extract_buy_sell(payload: dict, price_id: int) -> tuple[float, float] | None:
    """
    Finds the target price entry and derives buy/sell.

    ASSUMPTION (verify against the real product before trusting this in
    production): the source's own "priceBuy"/"priceSell" fields are
    offsets from "price", and from the *customer's* point of view
    (matching the "بخرید"/"بفروشید" labels shown in the product's own
    UI) the mapping is:
        customer-buy  (our buy_price)  = price + priceSell
        customer-sell (our sell_price) = price + priceBuy
    This looked right against the one sample data point available at
    build time (see README.md) but has NOT been confirmed live.
    """
    entries = payload.get("prices") or []
    entry = next((p for p in entries if p.get("id") == price_id), None)
    if not entry:
        return None

    base = entry.get("price")
    price_buy_offset = entry.get("priceBuy")
    price_sell_offset = entry.get("priceSell")
    if base is None or price_buy_offset is None or price_sell_offset is None:
        return None

    customer_buy = base + price_sell_offset
    customer_sell = base + price_buy_offset
    return float(customer_buy), float(customer_sell)


async def poll_loop():
    if not SOURCE_UID or not SOURCE_UTOKEN:
        logger.error("BRIDGE_SOURCE_UID / BRIDGE_SOURCE_UTOKEN not set - refusing to start polling")
        return

    async with httpx.AsyncClient(timeout=10) as client:
        while True:
            try:
                resp = await client.post(
                    f"{SOURCE_BASE_URL}/prices/list.php",
                    data={"all": "true", "uID": SOURCE_UID, "uToken": SOURCE_UTOKEN},
                )
                resp.raise_for_status()
                payload = resp.json()

                if not payload.get("state"):
                    msg = payload.get("msg") or ""
                    auth_keywords = ["توکن", "token", "session", "نشست", "احراز", "auth", "منقضی", "expired"]
                    if any(k.lower() in msg.lower() for k in auth_keywords):
                        logger.error(
                            f"[goldbridge] session looks expired/invalid ({msg}) - "
                            f"run `python login.py` again to get a fresh session"
                        )
                    else:
                        logger.warning(f"[goldbridge] source returned state=false: {msg}")
                else:
                    result = extract_buy_sell(payload, TARGET_PRICE_ID)
                    if result is None:
                        logger.warning(f"[goldbridge] couldn't find/parse price id={TARGET_PRICE_ID}")
                    else:
                        buy, sell = result
                        _latest["buy"] = buy
                        _latest["sell"] = sell
                        _latest["updated_at"] = datetime.utcnow().isoformat()
                        _latest["source_updated_at"] = payload.get("lastUpdateTime")
                        logger.info(f"[goldbridge] updated: buy={buy} sell={sell}")

            except Exception as e:
                logger.warning(f"[goldbridge] poll failed: {e}")

            await asyncio.sleep(POLL_SECONDS)


@app.get("/price")
async def get_price():
    if _latest["buy"] is None:
        raise HTTPException(status_code=503, detail="No price fetched yet")
    return _latest


@app.get("/health")
async def health():
    return {"ok": _latest["buy"] is not None, "last_update": _latest["updated_at"]}