"""
Pydantic response models. All API responses are typed - malformed or
unexpected source data gets caught here rather than silently leaking
an unexpected shape to callers. Field descriptions and example values
also drive the Swagger (/docs) schema, so keep them accurate.
"""
from pydantic import BaseModel, ConfigDict, Field


class PriceEntry(BaseModel):
    id: int = Field(..., description="Source's internal id for this item. Pass as ?id= to /price.", examples=[3])
    name: str = Field(..., description="Persian display name of the item.", examples=["سکه تمام"])
    type: int | None = Field(None, description="1 = gold by gram/ayar, 2 = coin (سکه).", examples=[2])
    ayar: int | None = Field(None, description="Gold purity (ayar/karat), where applicable.")
    item_weight: float | None = Field(None, description="Weight in grams, where applicable (e.g. coins).")
    active: bool = Field(..., description="Whether the source currently has this item active.")
    allow_buy: bool = Field(..., description="Whether the source currently allows buying this item.")
    allow_sell: bool = Field(..., description="Whether the source currently allows selling this item.")
    base_price: float | None = Field(None, description="Raw base price from the source, before buy/sell offsets.")
    buy: float | None = Field(None, description="Derived customer-buy price (see README for the offset formula).")
    sell: float | None = Field(None, description="Derived customer-sell price (see README for the offset formula).")
    min: float | None = Field(None, description="Minimum transactable quantity for this item.")
    max: float | None = Field(None, description="Maximum transactable quantity for this item.")
    last_update_time: str | None = Field(None, description="Source's own last-updated timestamp for this item.")


class PricesResponse(BaseModel):
    prices: list[PriceEntry]
    source_updated_at: str | None = Field(None, description="Source's overall last-updated timestamp.")
    stale: bool = Field(..., description="True if recent polls have been failing - treat the data with caution.")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "prices": [
                    {
                        "id": 1, "name": "نقد شنبه", "type": 1, "ayar": 750, "item_weight": 0,
                        "active": True, "allow_buy": True, "allow_sell": True,
                        "base_price": 788600000, "buy": 789250000.0, "sell": 787850000.0,
                        "min": 1, "max": 5000, "last_update_time": "2026-07-16 17:07:18",
                    }
                ],
                "source_updated_at": "2026-07-16 17:07:18",
                "stale": False,
            }
        }
    )


class PriceResponse(BaseModel):
    buy: float = Field(..., description="Customer-buy price in Rial.")
    sell: float = Field(..., description="Customer-sell price in Rial.")
    name: str | None = Field(None, description="Item name, present when queried with ?id=.")
    updated_at: str | None = Field(None, description="When goldbridge itself last refreshed this value (UTC ISO 8601).")
    source_updated_at: str | None = Field(None, description="Source's own last-updated timestamp.")
    stale: bool = Field(..., description="True if recent polls have been failing - treat the data with caution.")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "buy": 789250000.0,
                "sell": 787850000.0,
                "name": "نقد شنبه",
                "updated_at": "2026-07-17T12:00:00+00:00",
                "source_updated_at": "2026-07-16 17:07:18",
                "stale": False,
            }
        }
    )


class HealthResponse(BaseModel):
    ok: bool = Field(..., description="True if a price has been fetched and it isn't stale.")
    last_update: str | None = Field(None, description="UTC ISO 8601 timestamp of the last successful poll.")
    consecutive_failures: int = Field(..., description="Current streak of failed polls.")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"ok": True, "last_update": "2026-07-17T12:00:00+00:00", "consecutive_failures": 0}
        }
    )


class ErrorResponse(BaseModel):
    """Shape of every error response (FastAPI's default HTTPException body)."""
    detail: str = Field(..., examples=["No price fetched yet"])