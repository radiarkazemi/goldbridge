"""Unauthenticated by design - local liveness check only, leaks no
price data or secrets. Safe for a process monitor to hit unauthenticated."""
from fastapi import APIRouter

from app.models.schemas import HealthResponse
from app.services.price_cache import cache

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness check",
    description=(
        "Unauthenticated - no API key required. Reports whether goldbridge "
        "has fresh price data, for use by process monitors / uptime checks. "
        "Never returns price values or any secret."
    ),
)
async def health():
    return HealthResponse(
        ok=cache.latest_buy is not None and not cache.is_stale,
        last_update=cache.updated_at,
        consecutive_failures=cache.consecutive_failures,
    )