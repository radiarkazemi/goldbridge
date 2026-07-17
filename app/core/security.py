"""
FastAPI dependencies for auth and rate limiting. Kept separate from
routers so the security policy is auditable in one file and reusable
across every router that needs it.
"""
import hmac
import time

from fastapi import Header, HTTPException, Request

from app.core.config import get_settings
from app.core.logging import logger

settings = get_settings()

# Per-IP sliding-window rate limit state. In-memory, so it resets on
# restart and is per-process - fine for this single-process internal
# service; swap for a shared store (e.g. Redis) if goldbridge is ever
# run with multiple workers or instances.
_rate_limit_buckets: dict[str, list[float]] = {}


def require_api_key(authorization: str | None = Header(default=None)) -> None:
    """
    Validates `Authorization: Bearer <key>` with a constant-time
    comparison (hmac.compare_digest) to avoid leaking key correctness
    via response-time side channels.

    No-ops if BRIDGE_API_KEY isn't configured (local dev without a key
    still works), but a warning is logged once at startup in that case
    - see app/main.py.
    """
    if not settings.api_key:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(token, settings.api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")


def rate_limit(request: Request) -> None:
    """Simple in-memory sliding-window limiter, keyed by client IP."""
    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    window_start = now - 60
    bucket = _rate_limit_buckets.setdefault(client_ip, [])
    bucket[:] = [t for t in bucket if t > window_start]
    if len(bucket) >= settings.rate_limit_per_minute:
        logger.warning(f"[security] rate limit exceeded for {client_ip}")
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    bucket.append(now)


def warn_if_unprotected() -> None:
    if not settings.api_key:
        logger.warning(
            "[security] BRIDGE_API_KEY is not set - /price and /prices are "
            "UNAUTHENTICATED. Set BRIDGE_API_KEY in .env before exposing this "
            "beyond a trusted local dev machine."
        )