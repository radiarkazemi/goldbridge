"""
Pure functions that turn the raw sekefarshad.ir payload into the
shapes goldbridge exposes. No I/O, no state - kept separate from
price_cache.py so the parsing logic is independently testable.
"""


def clean_entry(entry: dict) -> dict:
    """
    Reduce one raw source entry down to the fields actually useful for
    picking a price, applying the same customer-buy/customer-sell
    derivation used in extract_buy_sell (see note there for the
    assumption behind it).
    """
    base = entry.get("price")
    price_buy_offset = entry.get("priceBuy")
    price_sell_offset = entry.get("priceSell")

    customer_buy = customer_sell = None
    if base is not None and price_buy_offset is not None and price_sell_offset is not None:
        customer_buy = float(base + price_sell_offset)
        customer_sell = float(base + price_buy_offset)

    return {
        "id": entry.get("id"),
        "name": entry.get("name"),
        "type": entry.get("type"),          # 1 = gold by gram/ayar, 2 = coin (سکه)
        "ayar": entry.get("ayar"),
        "item_weight": entry.get("itemWeight"),
        "active": bool(entry.get("isActive")),
        "allow_buy": bool(entry.get("allowBuy")),
        "allow_sell": bool(entry.get("allowSell")),
        "base_price": base,
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
    """
    Finds the target price entry and derives buy/sell.

    ASSUMPTION (verify against the real product before trusting this in
    production): the source's own "priceBuy"/"priceSell" fields are
    offsets from "price", and from the *customer's* point of view
    (matching the "بخرید"/"بفروشید" labels shown in the product's own
    UI) the mapping is:
        customer-buy  (our buy_price)  = price + priceSell
        customer-sell (our sell_price) = price + priceBuy
    This looked right against the one sample data point available at
    build time (see README.md) but has NOT been confirmed live.
    """
    entries = payload.get("prices") or []
    entry = next((p for p in entries if p.get("id") == price_id), None)
    if not entry:
        return None

    base = entry.get("price")
    price_buy_offset = entry.get("priceBuy")
    price_sell_offset = entry.get("priceSell")
    if base is None or price_buy_offset is None or price_sell_offset is None:
        return None

    customer_buy = base + price_sell_offset
    customer_sell = base + price_buy_offset
    return float(customer_buy), float(customer_sell)