"""
Background task: polls sekefarshad.ir on a timer, feeds results into
the shared PriceCache. Exponential backoff with jitter on failure so a
source outage doesn't turn into a hammering retry loop.

Primary (id=target) freshness is the priority: every successful tick is
applied immediately. Full-catalog retries for secondary cards never
block applying the primary quote from the first response.
"""
import asyncio
import random
import time

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

# How often (wall-clock) we insist on chasing a full catalog. Short
# responses from sekefarshad are common under load and usually contain
# the primary instrument - we merge those immediately for speed and
# only occasionally retry for completeness of secondary cards.
_FULL_CATALOG_REFRESH_SECONDS = 8.0
_MIN_HEALTHY_ENTRY_COUNT = 3


async def _fetch_payload(client: httpx.AsyncClient) -> dict:
    resp = await client.post(
        f"{settings.source_base_url}/prices/list.php",
        data={"all": "true", "uID": SOURCE_UID, "uToken": SOURCE_UTOKEN},
    )
    resp.raise_for_status()
    return resp.json()


def _apply_tick(payload: dict, new_entries: list[dict]) -> bool:
    """Merge catalog + update primary quote. Returns True if buy/sell changed."""
    merge_result = cache.record_entries(new_entries)
    if merge_result == "merged":
        logger.debug(
            f"[poller] merged partial catalog (got {len(new_entries)}, "
            f"kept {len(cache.entries)} total)"
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
            cache.record_success(
                buy, sell, payload.get("lastUpdateTime") or cached.get("last_update_time")
            )
            return False
        logger.warning(f"[poller] couldn't find/parse price id={settings.target_price_id}")
        cache.record_failure()
        return False

    buy, sell = result
    changed = buy != cache.latest_buy or sell != cache.latest_sell
    cache.record_success(buy, sell, payload.get("lastUpdateTime"))
    cache.sync_target_quote(settings.target_price_id, buy, sell, payload.get("lastUpdateTime"))
    if changed:
        logger.info(
            f"[poller] updated: buy={buy} sell={sell} "
            f"(entries={len(cache.entries)}, tick={len(new_entries)})"
        )
    return changed


async def _poll_once(client: httpx.AsyncClient, *, force_full_retry: bool = False) -> bool:
    """One upstream poll. Returns True if the primary quote changed."""
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
        return False

    new_entries = clean_prices(payload)

    # Apply the first response immediately so id=1 never waits on a
    # full-catalog chase. Secondary completeness is best-effort after.
    changed = _apply_tick(payload, new_entries)

    if (
        force_full_retry
        and 0 < len(new_entries) < _MIN_HEALTHY_ENTRY_COUNT
        and len(cache.entries) >= _MIN_HEALTHY_ENTRY_COUNT
    ):
        await asyncio.sleep(0.25)
        try:
            retry_payload = await _fetch_payload(client)
            if retry_payload.get("state"):
                retry_entries = clean_prices(retry_payload)
                if len(retry_entries) > len(new_entries):
                    logger.info(
                        f"[poller] full-catalog refresh recovered {len(retry_entries)} entries"
                    )
                    # Merge longer catalog; may also refresh primary if present.
                    if _apply_tick(retry_payload, retry_entries):
                        changed = True
        except Exception as e:
            logger.warning(f"[poller] full-catalog refresh failed: {e}")

    return changed


def _backoff_seconds(base_interval: float) -> float:
    if cache.consecutive_failures == 0:
        return base_interval
    raw = base_interval * (2 ** min(cache.consecutive_failures, 6))
    capped = min(settings.max_backoff_seconds, raw)
    return capped * (0.8 + 0.4 * random.random())  # +/-20% jitter


def _interval_after_tick(*, changed: bool, fast_until: float, now: float) -> tuple[float, float]:
    """Pick next sleep base; extend a short fast window when price moves."""
    if changed:
        fast_until = now + settings.poll_fast_window_seconds
    if now < fast_until:
        return min(settings.poll_seconds, settings.poll_fast_seconds), fast_until
    return settings.poll_seconds, fast_until


async def poll_loop() -> None:
    # Empty credentials still work for the public prices list on this
    # source, but a saved session/login is preferred when available.
    if not SOURCE_UID or not SOURCE_UTOKEN:
        logger.warning(
            "[poller] no BRIDGE_SOURCE_UID/UTOKEN or saved session - "
            "polling the public prices list without auth"
        )

    last_full_refresh = 0.0
    fast_until = 0.0
    # Fail hung connects quickly; keep enough read budget for the source.
    timeout = httpx.Timeout(connect=2.0, read=5.0, write=5.0, pool=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        while True:
            started = time.monotonic()
            force_full = (started - last_full_refresh) >= _FULL_CATALOG_REFRESH_SECONDS
            changed = False
            try:
                changed = await _poll_once(client, force_full_retry=force_full)
                if force_full:
                    last_full_refresh = time.monotonic()
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

            now = time.monotonic()
            base_interval, fast_until = _interval_after_tick(
                changed=changed, fast_until=fast_until, now=now
            )
            # Account for request time so the effective interval stays
            # close to the chosen poll period instead of (poll + RTT).
            elapsed = now - started
            await asyncio.sleep(max(0.0, _backoff_seconds(base_interval) - elapsed))
