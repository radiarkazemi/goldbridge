"""
Background task: polls sekefarshad.ir on a timer, feeds results into
the shared PriceCache. Exponential backoff with jitter on failure so a
source outage doesn't turn into a hammering retry loop.
"""
import asyncio
import random

import httpx

from app.core.config import get_settings
from app.core.logging import logger
from app.services.price_cache import cache
from app.services.session_store import load_session
from app.services.source_parser import clean_prices, extract_buy_sell

settings = get_settings()

# Prefer a saved login session (from `python login.py`) over the static
# .env values - lets you switch to real phone+code login without
# touching .env at all once that's wired up. Falls back to .env so the
# static uID/uToken approach still works in the meantime.
_session = load_session()
SOURCE_UID = (_session or {}).get("uid") or settings.source_uid_env or ""
SOURCE_UTOKEN = (_session or {}).get("utoken") or settings.source_utoken_env or ""

_AUTH_ERROR_KEYWORDS = ["توکن", "token", "session", "نشست", "احراز", "auth", "منقضی", "expired"]

# Upstream intermittently returns a 1-item truncated catalog when polled
# too aggressively. One quick retry usually recovers the full list.
_PARTIAL_RETRY_DELAY_SECONDS = 0.35
_MIN_HEALTHY_ENTRY_COUNT = 3


async def _fetch_payload(client: httpx.AsyncClient) -> dict:
    resp = await client.post(
        f"{settings.source_base_url}/prices/list.php",
        data={"all": "true", "uID": SOURCE_UID, "uToken": SOURCE_UTOKEN},
    )
    resp.raise_for_status()
    return resp.json()


async def _poll_once(client: httpx.AsyncClient) -> None:
    payload = await _fetch_payload(client)

    if not payload.get("state"):
        msg = payload.get("msg") or ""
        if any(k.lower() in msg.lower() for k in _AUTH_ERROR_KEYWORDS):
            logger.error(
                f"[poller] session looks expired/invalid ({msg}) - "
                f"run `python login.py` again to get a fresh session"
            )
        else:
            logger.warning(f"[poller] source returned state=false: {msg}")
        cache.record_failure()
        return

    new_entries = clean_prices(payload)
    # Truncated responses (common under rate pressure) - retry once before
    # merging so /prices stays as complete as possible.
    if 0 < len(new_entries) < _MIN_HEALTHY_ENTRY_COUNT:
        logger.info(
            f"[poller] source returned only {len(new_entries)} entries - "
            f"retrying once for a full catalog"
        )
        await asyncio.sleep(_PARTIAL_RETRY_DELAY_SECONDS)
        try:
            retry_payload = await _fetch_payload(client)
            if retry_payload.get("state"):
                retry_entries = clean_prices(retry_payload)
                if len(retry_entries) > len(new_entries):
                    payload = retry_payload
                    new_entries = retry_entries
        except Exception as e:
            logger.warning(f"[poller] partial-list retry failed: {e}")

    logger.info(f"[poller] source returned {len(new_entries)} price entries")
    merge_result = cache.record_entries(new_entries)
    if merge_result == "merged":
        logger.warning(
            f"[poller] merged partial catalog into cache "
            f"(got {len(new_entries)}, kept {len(cache.entries)} total)"
        )
    elif merge_result == "empty":
        logger.warning("[poller] source returned an empty prices list")

    result = extract_buy_sell(payload, settings.target_price_id)
    if result is None:
        # Partial list may omit the target id - fall back to whatever we
        # already have cached for that id rather than counting a failure.
        cached = cache.get_entry(settings.target_price_id)
        if cached and cached.get("buy") is not None and cached.get("sell") is not None:
            buy, sell = float(cached["buy"]), float(cached["sell"])
            cache.record_success(buy, sell, payload.get("lastUpdateTime") or cached.get("last_update_time"))
            logger.info(f"[poller] target id missing in this tick - kept cached buy={buy} sell={sell}")
            return
        logger.warning(f"[poller] couldn't find/parse price id={settings.target_price_id}")
        cache.record_failure()
        return

    buy, sell = result
    cache.record_success(buy, sell, payload.get("lastUpdateTime"))
    cache.sync_target_quote(settings.target_price_id, buy, sell, payload.get("lastUpdateTime"))
    logger.info(f"[poller] updated: buy={buy} sell={sell}")


def _backoff_seconds() -> float:
    if cache.consecutive_failures == 0:
        return settings.poll_seconds
    raw = settings.poll_seconds * (2 ** min(cache.consecutive_failures, 6))
    capped = min(settings.max_backoff_seconds, raw)
    return capped * (0.8 + 0.4 * random.random())  # +/-20% jitter


async def poll_loop() -> None:
    # Empty credentials still work for the public prices list on this
    # source, but a saved session/login is preferred when available.
    if not SOURCE_UID or not SOURCE_UTOKEN:
        logger.warning(
            "[poller] no BRIDGE_SOURCE_UID/UTOKEN or saved session - "
            "polling the public prices list without auth"
        )

    async with httpx.AsyncClient(timeout=10) as client:
        while True:
            try:
                await _poll_once(client)
            except Exception as e:
                # Deliberately never logs SOURCE_UID/SOURCE_UTOKEN, even on
                # error - keep it that way in any future edits here.
                logger.warning(f"[poller] poll failed: {e}")
                cache.record_failure()
                if cache.consecutive_failures == settings.max_stale_polls:
                    logger.error(
                        f"[poller] {cache.consecutive_failures} consecutive poll failures - "
                        f"marking cached prices as stale"
                    )

            await asyncio.sleep(_backoff_seconds())
