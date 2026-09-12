"""
Pure functions that turn the raw sekefarshad.ir payload into the
shapes goldbridge exposes. No I/O, no state - kept separate from
price_cache.py so the parsing logic is independently testable.
"""

# Farshad's UI matches names with name.includes("شکس") (شکسته).
_SHAKASTE_MARKER = "شکس"


def _num(value, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def farshad_screen_buy_sell(entry: dict) -> tuple[float, float] | None:
    """
    Reproduce the buy/sell Farshad shows on the trade board.

    Confirmed from sekefarshad.ir's bundled UI (`mp` / `gp` / `vp` in
    `/static/js/main.4ad7f49b.js`):

        بخرید  (customer buy)  = price + profit + masterProfit
        بفروشید (customer sell) = price - profit - masterProfit

    ``priceBuy`` / ``priceSell`` are NOT used for the on-screen quote.
    They are bot live-offsets (and sometimes absolute admin-side
    snapshots). Using them is why goldbridge sometimes disagreed with
    the app:

    * when both offsets were 0, we returned a flat mid-price while the
      app still showed ``price ± profit``
    * when offsets were non-zero they were often a *different* spread
      than ``profit`` (e.g. ±500k offset vs ±700k profit)

    The app then adds a per-user ``diff`` from `/userPrices` on top of
    this board quote. This function matches the board a user with
    diff=0 sees.
    """
    if entry.get("price") is None:
        return None

    base = _num(entry.get("price"))
    profit = _num(entry.get("profit"))
    master = _num(entry.get("masterProfit"))

    buy = base + profit + master
    sell = base - profit - master

    # Same special rounding as gp/vp: nearest 10,000 Rial for شکسته gold.
    name = entry.get("name") or ""
    if (
        _num(entry.get("rate")) == 1.0
        and _num(entry.get("type")) == 1.0
        and _SHAKASTE_MARKER in name
    ):
        buy = 10000.0 * round(buy / 10000.0)
        sell = 10000.0 * round(sell / 10000.0)

    return buy, sell


def clean_entry(entry: dict) -> dict:
    """
    Reduce one raw source entry down to the fields actually useful for
    picking a price, applying the same customer-buy/customer-sell
    derivation used in extract_buy_sell.
    """
    result = farshad_screen_buy_sell(entry)
    customer_buy = customer_sell = None
    if result is not None:
        customer_buy, customer_sell = result

    related_id = entry.get("relatedId") or 0
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
        "profit": entry.get("profit"),
        "buy": customer_buy,
        "sell": customer_sell,
        "related_id": related_id if related_id else None,
        "related_diff": entry.get("relatedDiff") or 0,
        "min": entry.get("min"),
        "max": entry.get("max"),
        "last_update_time": entry.get("lastUpdateTime"),
    }


def clean_prices(payload: dict) -> list[dict]:
    entries = payload.get("prices") or []
    return [clean_entry(e) for e in entries]


def extract_buy_sell(payload: dict, price_id: int) -> tuple[float, float] | None:
    """Finds the target price entry and derives the Farshad on-screen buy/sell."""
    entries = payload.get("prices") or []
    entry = next((p for p in entries if p.get("id") == price_id), None)
    if not entry:
        return None
    return farshad_screen_buy_sell(entry)


def active_related_board_cards(entries: list[dict], master_id: int) -> list[dict]:
    """Farshad trade-board tiles that follow a master id via ``relatedId``.

    Master rows like id=1 "نقد یکشنبه" are often inactive. The visible
    /trade cards are the "نقدی …" children (related_id = master, isActive=1).
    """
    related = []
    for entry in entries:
        if entry.get("related_id") != master_id:
            continue
        if not entry.get("active"):
            continue
        related.append(entry)
    return related
