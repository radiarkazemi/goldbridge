"""
Pure functions that turn the raw sekefarshad.ir payload into the
shapes goldbridge exposes. No I/O, no state - kept separate from
price_cache.py so the parsing logic is independently testable.
"""


def derive_customer_buy_sell(
    base,
    price_buy_offset,
    price_sell_offset,
    profit=None,
) -> tuple[float, float] | None:
    """
    Derive customer-facing buy/sell (Rial) from one source row.

    Live trading rows usually set priceBuy/priceSell as offsets from
    ``price`` (priceBuy is often negative). From the customer's point
    of view (بخرید / بفروشید):
        customer-buy  = price + priceSell
        customer-sell = price + priceBuy

    When the source clears both offsets to 0 (common when the bot is
    idle / inactive), those fields no longer carry the spread - the
    configured ``profit`` margin does. Fall back to:
        customer-buy  = price + profit
        customer-sell = price - profit

    If offsets and profit are all zero/missing, buy == sell == price.
    """
    if base is None:
        return None

    base_f = float(base)
    pb = 0.0 if price_buy_offset is None else float(price_buy_offset)
    ps = 0.0 if price_sell_offset is None else float(price_sell_offset)

    if pb == 0.0 and ps == 0.0:
        margin = 0.0 if profit is None else float(profit)
        if margin != 0.0:
            return base_f + margin, base_f - margin
        return base_f, base_f

    return base_f + ps, base_f + pb


def clean_entry(entry: dict) -> dict:
    """
    Reduce one raw source entry down to the fields actually useful for
    picking a price, applying the same customer-buy/customer-sell
    derivation used in extract_buy_sell.
    """
    result = derive_customer_buy_sell(
        entry.get("price"),
        entry.get("priceBuy"),
        entry.get("priceSell"),
        entry.get("profit"),
    )
    customer_buy = customer_sell = None
    if result is not None:
        customer_buy, customer_sell = result

    return {
        "id": entry.get("id"),
        "name": entry.get("name"),
        "type": entry.get("type"),          # 1 = gold by gram/ayar, 2 = coin (سکه)
        "ayar": entry.get("ayar"),
        "item_weight": entry.get("itemWeight"),
        "active": bool(entry.get("isActive")),
        "allow_buy": bool(entry.get("allowBuy")),
        "allow_sell": bool(entry.get("allowSell")),
        "base_price": entry.get("price"),
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
    """Finds the target price entry and derives buy/sell."""
    entries = payload.get("prices") or []
    entry = next((p for p in entries if p.get("id") == price_id), None)
    if not entry:
        return None
    return derive_customer_buy_sell(
        entry.get("price"),
        entry.get("priceBuy"),
        entry.get("priceSell"),
        entry.get("profit"),
    )
