"""
Pure functions that turn the raw sekefarshad.ir payload into the
shapes goldbridge exposes. No I/O, no state - kept separate from
price_cache.py so the parsing logic is independently testable.
"""

# Source JSON prices are Rial. 1 toman = 10 Rial.
_RIAL_PER_TOMAN = 10


def farshad_screen_buy_sell(
    base,
    price_buy_offset,
    price_sell_offset,
    profit=None,
) -> tuple[float, float] | None:
    """
    Reproduce the buy/sell Farshad shows on screen from one JSON row.

    Live offsets (when not both 0):
        بخرید  = price + priceSell
        بفروشید = price + priceBuy

    When priceBuy and priceSell are both 0, Farshad uses ``profit``:
        بخرید  = price + profit
        بفروشید = price - profit
    (Confirmed against the Farshad app UI for id=1009.)
    """
    if base is None:
        return None

    base_f = float(base)
    pb = 0.0 if price_buy_offset is None else float(price_buy_offset)
    ps = 0.0 if price_sell_offset is None else float(price_sell_offset)

    if pb == 0.0 and ps == 0.0:
        margin = 0.0 if profit is None else float(profit)
        return base_f + margin, base_f - margin

    return base_f + ps, base_f + pb


def derive_customer_buy_sell(
    base,
    price_buy_offset,
    price_sell_offset,
    profit=None,
    shop_margin_toman: float | None = None,
) -> tuple[float, float] | None:
    """
    Goldbridge pre-commission quote = Farshad on-screen quote, then
    nudge buy up / sell down by the configured shop margin (toman).
    """
    screen = farshad_screen_buy_sell(
        base, price_buy_offset, price_sell_offset, profit=profit
    )
    if screen is None:
        return None

    buy, sell = screen
    if shop_margin_toman is None:
        from app.core.config import get_settings
        shop_margin_toman = get_settings().shop_margin_toman
    margin_rial = float(shop_margin_toman) * _RIAL_PER_TOMAN
    return buy + margin_rial, sell - margin_rial


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
        profit=entry.get("profit"),
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
        profit=entry.get("profit"),
    )
