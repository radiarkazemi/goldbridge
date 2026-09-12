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
    base_price: float | None = Field(
        None,
        description="Farshad pure mid (`price`) in Rial, BEFORE their سود commission. Farshad UI ÷10 to show Toman.",
    )
    profit: float | None = Field(
        None,
        description="Raw Farshad 'سود' field (Rial). This is the live commission they change during the day.",
    )
    master_profit: float | None = Field(
        None,
        description="Extra Farshad pad (`masterProfit`) in Rial when the card is master-handled. Usually 0.",
    )
    farshad_commission: float | None = Field(
        None,
        description="One-sided Farshad commission in Rial = profit + masterProfit. Toman = /10. buy = base_price + this, sell = base_price - this.",
    )
    farshad_spread: float | None = Field(
        None,
        description="Full Farshad on-screen spread in Rial = buy - sell = 2 × farshad_commission.",
    )
    buy: float | None = Field(None, description="Farshad on-screen customer-buy (بخرید) = base_price + farshad_commission.")
    sell: float | None = Field(None, description="Farshad on-screen customer-sell (بفروشید) = base_price - farshad_commission.")
    related_id: int | None = Field(None, description="If set, this card follows that master id (e.g. نقدی یکشنبه related_id=1). Farshad /trade shows these children, not the inactive master.")
    related_diff: float | None = Field(None, description="Offset vs the related master, in Rial.")
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
                        "id": 1013, "name": "نقدی یکشنبه", "type": 1, "ayar": 750, "item_weight": 0,
                        "active": True, "allow_buy": True, "allow_sell": True,
                        "base_price": 1042000000, "profit": 700000, "master_profit": 0,
                        "farshad_commission": 700000.0, "farshad_spread": 1400000.0,
                        "buy": 1042700000.0, "sell": 1041300000.0,
                        "related_id": 1, "related_diff": 0,
                        "min": 1, "max": 5000, "last_update_time": "2026-07-16 17:07:18",
                    }
                ],
                "source_updated_at": "2026-07-16 17:07:18",
                "stale": False,
            }
        }
    )


class PriceResponse(BaseModel):
    buy: float = Field(..., description="Farshad on-screen customer-buy (بخرید) in Rial: base_price + farshad_commission.")
    sell: float = Field(..., description="Farshad on-screen customer-sell (بفروشید) in Rial: base_price - farshad_commission.")
    name: str | None = Field(None, description="Item name. Compare this to the Farshad /trade tile — id=1 is often the master (نقد …), not the visible نقدی … card.")
    base_price: float | None = Field(None, description="Farshad pure mid in Rial (before their سود commission).")
    profit: float | None = Field(None, description="Raw Farshad 'سود' (live commission they change during the day), Rial.")
    master_profit: float | None = Field(None, description="Extra Farshad masterProfit pad in Rial.")
    farshad_commission: float | None = Field(
        None,
        description="One-sided Farshad commission in Rial (= profit + master_profit). Use this to size YOUR margin so hedges stay profitable.",
    )
    farshad_spread: float | None = Field(None, description="Full Farshad screen spread in Rial (= 2 × farshad_commission).")
    updated_at: str | None = Field(None, description="When goldbridge itself last refreshed this value (UTC ISO 8601).")
    source_updated_at: str | None = Field(None, description="Source's own last-updated timestamp.")
    stale: bool = Field(..., description="True if recent polls have been failing - treat the data with caution.")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "buy": 1040000000.0,
                "sell": 1038600000.0,
                "name": "نقدی یکشنبه",
                "base_price": 1039300000,
                "profit": 700000,
                "master_profit": 0,
                "farshad_commission": 700000.0,
                "farshad_spread": 1400000.0,
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