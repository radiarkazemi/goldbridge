"""Authenticated price endpoints. Every route here requires a valid
Authorization: Bearer <BRIDGE_API_KEY> header (see app/core/security.py)."""
from fastapi import APIRouter, Depends, HTTPException

from app.core.config import get_settings
from app.core.security import rate_limit, require_api_key
from app.models.schemas import ErrorResponse, PriceResponse, PricesResponse
from app.services.price_cache import cache

router = APIRouter(dependencies=[Depends(require_api_key), Depends(rate_limit)])
settings = get_settings()

_AUTH_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Missing, malformed, or invalid API key."},
    429: {"model": ErrorResponse, "description": "Rate limit exceeded (per-IP, see BRIDGE_RATE_LIMIT_PER_MINUTE)."},
}


@router.get(
    "/prices",
    response_model=PricesResponse,
    summary="List every price entry",
    description=(
        "Returns the full cleaned list of every item the source currently "
        "reports, refreshed on each poll cycle (see BRIDGE_POLL_SECONDS). "
        "Use this to find the `id` of the item you want, then query it "
        "directly with `GET /price?id=`.\n\n"
        "Farshad's /trade board shows the **نقدی …** cards (active children "
        "with a `related_id`). `BRIDGE_TARGET_PRICE_ID=1` is usually the "
        "inactive master (e.g. نقد یکشنبه), which is a different instrument "
        "and a different `profit` than the tile you see in the Farshad app."
    ),
    responses={
        **_AUTH_RESPONSES,
        503: {"model": ErrorResponse, "description": "No prices have been fetched yet (service just started)."},
    },
)
async def get_prices():
    if not cache.entries:
        raise HTTPException(status_code=503, detail="No prices fetched yet")
    return PricesResponse(prices=cache.entries, source_updated_at=cache.source_updated_at, stale=cache.is_stale)


@router.get(
    "/price",
    response_model=PriceResponse,
    summary="Get a single buy/sell price",
    description=(
        "**Without `id`:** returns the pre-computed buy/sell for "
        "`BRIDGE_TARGET_PRICE_ID` (kept for backwards compatibility with "
        "goldapp's default price source config). Check the returned `name` — "
        "if it is the master (نقد یکشنبه) you will not match Farshad's "
        "trade-board tile (نقدی یکشنبه). Pass `?id=` of the active related "
        "card to match the app.\n\n"
        "**With `id`:** returns buy/sell for that specific item from the "
        "latest cached list - see `GET /prices` for available ids. No "
        "restart or `.env` change needed to switch items."
    ),
    responses={
        **_AUTH_RESPONSES,
        404: {"model": ErrorResponse, "description": "No price entry with the given id."},
        422: {"model": ErrorResponse, "description": "Entry exists but has no computable buy/sell (bad source data)."},
        503: {"model": ErrorResponse, "description": "No price has been fetched yet (service just started)."},
    },
)
async def get_price(id: int | None = None):
    if id is None:
        if cache.latest_buy is None:
            raise HTTPException(status_code=503, detail="No price fetched yet")
        target = cache.get_entry(settings.target_price_id) or {}
        return PriceResponse(
            buy=cache.latest_buy,
            sell=cache.latest_sell,
            name=target.get("name"),
            base_price=target.get("base_price"),
            profit=target.get("profit"),
            master_profit=target.get("master_profit"),
            farshad_commission=target.get("farshad_commission"),
            farshad_spread=target.get("farshad_spread"),
            updated_at=cache.updated_at,
            source_updated_at=cache.source_updated_at,
            stale=cache.is_stale,
        )

    entry = cache.get_entry(id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No price entry with id={id}")
    if entry["buy"] is None or entry["sell"] is None:
        raise HTTPException(status_code=422, detail=f"Price entry id={id} has no computable buy/sell")
    return PriceResponse(
        buy=entry["buy"],
        sell=entry["sell"],
        name=entry["name"],
        base_price=entry.get("base_price"),
        profit=entry.get("profit"),
        master_profit=entry.get("master_profit"),
        farshad_commission=entry.get("farshad_commission"),
        farshad_spread=entry.get("farshad_spread"),
        updated_at=cache.updated_at,
        source_updated_at=entry["last_update_time"],
        stale=cache.is_stale,
    )