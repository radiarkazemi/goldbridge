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

# Deliberately conservative by default - this hits an endpoint authenticated
# as someone else's account. Polling too aggressively risks that account
# getting flagged/rate-limited by the platform. Set to 2s to match the
# source's own update cadence; override via BRIDGE_POLL_SECONDS if it
# starts getting rate-limited or flagged.
POLL_SECONDS = int(os.getenv("BRIDGE_POLL_SECONDS", "2"))

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(poll_loop())
    yield


app = FastAPI(title="goldbridge (private, internal use only)", lifespan=lifespan)

_latest = {"buy": None, "sell": None, "updated_at": None, "source_updated_at": None}
_latest_list: list[dict] = []


def clean_entry(entry: dict) -> dict:
    """
    Reduce one raw source entry down to the fields actually useful for
    picking a price, applying the same customer-buy/customer-sell
    derivation used in extract_buy_sell (see note there for the
    assumption behind it).
    """
    base = entry.get("price")
    price_buy_offset = entry.get("priceBuy")
    price_sell_offset = entry.get("priceSell")

    customer_buy = customer_sell = None
    if base is not None and price_buy_offset is not None and price_sell_offset is not None:
        customer_buy = float(base + price_sell_offset)
        customer_sell = float(base + price_buy_offset)

    return {
        "id": entry.get("id"),
        "name": entry.get("name"),
        "type": entry.get("type"),          # 1 = gold by gram/ayar, 2 = coin (سکه)
        "ayar": entry.get("ayar"),
        "item_weight": entry.get("itemWeight"),
        "active": bool(entry.get("isActive")),
        "allow_buy": bool(entry.get("allowBuy")),
        "allow_sell": bool(entry.get("allowSell")),
        "base_price": base,
        "buy": customer_buy,
        "sell": customer_sell,
        "min": entry.get("min"),
        "max": entry.get("max"),
        "last_update_time": entry.get("lastUpdateTime"),
    }


def clean_prices(payload: dict) -> list[dict]:
    entries = payload.get("prices") or []
    return [clean_entry(e) for e in entries]


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
                    global _latest_list
                    new_list = clean_prices(payload)
                    logger.info(f"[goldbridge] source returned {len(new_list)} price entries")
                    if len(new_list) >= len(_latest_list):
                        _latest_list = new_list
                    else:
                        logger.warning(
                            f"[goldbridge] source returned fewer entries than cached "
                            f"({len(new_list)} < {len(_latest_list)}) - keeping previous list"
                        )

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


@app.get("/prices")
async def get_prices():
    """
    Full cleaned list of every price entry from the source, refreshed
    every poll cycle. Use this to see what's available and pick an id
    to pass to /price?id=.
    """
    if not _latest_list:
        raise HTTPException(status_code=503, detail="No prices fetched yet")
    return {"prices": _latest_list, "source_updated_at": _latest["source_updated_at"]}


@app.get("/price")
async def get_price(id: int | None = None):
    """
    Default (no ?id=): the pre-computed buy/sell for BRIDGE_TARGET_PRICE_ID
    (kept for backwards compatibility with the main app's price source).

    With ?id=N: buy/sell computed on the fly for that entry from the
    latest cached list - lets you pick any item without restarting
    goldbridge or touching .env.
    """
    if id is None:
        if _latest["buy"] is None:
            raise HTTPException(status_code=503, detail="No price fetched yet")
        return _latest

    entry = next((p for p in _latest_list if p["id"] == id), None)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No price entry with id={id}")
    if entry["buy"] is None or entry["sell"] is None:
        raise HTTPException(status_code=422, detail=f"Price entry id={id} has no computable buy/sell")
    return {
        "buy": entry["buy"],
        "sell": entry["sell"],
        "name": entry["name"],
        "updated_at": _latest["updated_at"],
        "source_updated_at": entry["last_update_time"],
    }


@app.get("/health")
async def health():
    return {"ok": _latest["buy"] is not None, "last_update": _latest["updated_at"]}