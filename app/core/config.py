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
    target_price_id: int = int(os.getenv("BRIDGE_TARGET_PRICE_ID", "1"))
    # Default 1s. Short/partial catalogs from sekefarshad are merged by
    # id (see price_cache.record_entries), so we can stay this fast
    # without freezing secondary cards. Going much below ~0.5s tends to
    # amplify truncated responses without buying real freshness - the
    # source's own lastUpdateTime is second-granularity.
    poll_seconds: float = float(os.getenv("BRIDGE_POLL_SECONDS", "1"))
    max_stale_polls: int = int(os.getenv("BRIDGE_MAX_STALE_POLLS", "5"))
    max_backoff_seconds: float = float(os.getenv("BRIDGE_MAX_BACKOFF_SECONDS", "60"))

    # --- Security ---
    # Any long random string; must match GOLDAPP_PRICE_API_KEY on the
    # goldapp side exactly. Blank => /price and /prices are UNAUTHENTICATED
    # (dev-only; a startup warning is logged in that case).
    api_key: str = os.getenv("BRIDGE_API_KEY", "")
    rate_limit_per_minute: int = int(os.getenv("BRIDGE_RATE_LIMIT_PER_MINUTE", "120"))

    # --- Server ---
    host: str = os.getenv("BRIDGE_HOST", "127.0.0.1")
    port: int = int(os.getenv("BRIDGE_PORT", "9100"))
    log_level: str = os.getenv("BRIDGE_LOG_LEVEL", "INFO")


@lru_cache
def get_settings() -> Settings:
    return Settings()