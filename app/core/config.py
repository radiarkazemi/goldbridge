"""
Centralized configuration. Every env var goldbridge reads lives here -
nowhere else in the codebase should call os.getenv() directly, so
there's exactly one place to check when auditing what's configurable.
"""
import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


class Settings:
    # --- Source credentials ---
    source_base_url: str = os.getenv("BRIDGE_SOURCE_BASE_URL", "https://sekefarshad.ir/server/api")
    source_uid_env: str | None = os.getenv("BRIDGE_SOURCE_UID")
    source_utoken_env: str | None = os.getenv("BRIDGE_SOURCE_UTOKEN")

    # --- Behavior ---
    # 1 is Farshad's inactive master (نقد یکشنبه). The /trade tiles are the
    # related نقدی cards (e.g. 1013). Override to match the board.
    target_price_id: int = int(os.getenv("BRIDGE_TARGET_PRICE_ID", "1"))
    # Default 1s. Partial/truncated catalogs are applied immediately and
    # merged by id (see price_cache.record_entries); a full-catalog chase
    # only runs about every 8s, so 1s stays safe without doubling load.
    # The source's own lastUpdateTime is second-granularity anyway.
    poll_seconds: float = float(os.getenv("BRIDGE_POLL_SECONDS", "1"))
    # Brief faster cadence right after a primary quote change so the next
    # move is caught quickly, then settle back to poll_seconds.
    poll_fast_seconds: float = float(os.getenv("BRIDGE_POLL_FAST_SECONDS", "0.5"))
    poll_fast_window_seconds: float = float(os.getenv("BRIDGE_POLL_FAST_WINDOW_SECONDS", "3"))
    max_stale_polls: int = int(os.getenv("BRIDGE_MAX_STALE_POLLS", "5"))
    max_backoff_seconds: float = float(os.getenv("BRIDGE_MAX_BACKOFF_SECONDS", "60"))

    # --- Security ---
    # Any long random string; must match GOLDAPP_PRICE_API_KEY on the
    # goldapp side exactly. Blank => /price and /prices are UNAUTHENTICATED
    # (dev-only; a startup warning is logged in that case).
    api_key: str = os.getenv("BRIDGE_API_KEY", "")
    # Generous default: goldapp polling /price + /prices about every 0.5–1s
    # from 127.0.0.1 can exceed 120/min. A tight cap causes 429s and makes
    # the UI feel laggy even when the upstream poller is healthy.
    rate_limit_per_minute: int = int(os.getenv("BRIDGE_RATE_LIMIT_PER_MINUTE", "600"))

    # --- Server ---
    host: str = os.getenv("BRIDGE_HOST", "127.0.0.1")
    port: int = int(os.getenv("BRIDGE_PORT", "9100"))
    log_level: str = os.getenv("BRIDGE_LOG_LEVEL", "INFO")


@lru_cache
def get_settings() -> Settings:
    return Settings()