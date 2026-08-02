"""
Pure functions that turn the raw sekefarshad.ir payload into the
shapes goldbridge exposes. No I/O, no state - kept separate from
price_cache.py so the parsing logic is independently testable.
"""


def derive_customer_buy_sell(
    base,
    price_buy_offset,
    price_sell_offset,
    *,
    price_diff=None,
    profit_diff=None,
) -> tuple[float, float] | None:
    """
    Derive customer-facing buy/sell (Rial) from one source row.

    When live offsets are present (priceBuy / priceSell not both 0):
        customer-buy  = price + priceSell
        customer-sell = price + priceBuy

    When both offsets are 0, sekefarshad still shows a two-sided quote
    from the configured diffs (before any app-side commission):
        margin        = (profitDiff + priceDiff) * 10
        customer-buy  = price + margin
        customer-sell = price - margin
    """
    if base is None:
        return None

    base_f = float(base)
    pb = 0.0 if price_buy_offset is None else float(price_buy_offset)
    ps = 0.0 if price_sell_offset is None else float(price_sell_offset)

    if pb == 0.0 and ps == 0.0:
        pdiff = 0.0 if price_diff is None else float(price_diff)
        prof_diff = 0.0 if profit_diff is None else float(profit_diff)
        margin = (prof_diff + pdiff) * 10.0
        return base_f + margin, base_f - margin

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
        price_diff=entry.get("priceDiff"),
        profit_diff=entry.get("profitDiff"),
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
        price_diff=entry.get("priceDiff"),
        profit_diff=entry.get("profitDiff"),
    )
