"""
Pick Farshad's "main cash" instrument for the current trading day.

Iranian gold shops post cash (نقد / نقدی) under the *delivery* weekday.
On Sunday the live main tile is نقدی دوشنبه (Monday delivery), not
yesterday's نقدی یکشنبه. So the default target is tomorrow's weekday
name in Asia/Tehran, preferring the active نقدی board card over the
inactive master and over کارتخوان variants.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Python weekday() → Persian delivery-day label used in Farshad names.
# Mon=0 … Sun=6
_WEEKDAY_FA = {
    0: "دوشنبه",
    1: "سه‌شنبه",
    2: "چهارشنبه",
    3: "پنجشنبه",
    4: "جمعه",
    5: "شنبه",
    6: "یکشنبه",
}

_TEHRAN = ZoneInfo("Asia/Tehran")


def normalize_fa_name(name: str | None) -> str:
    """Strip ZWNJ / spaces so 'سه\u200cشنبه' matches 'سه‌شنبه' / 'سه شنبه'."""
    if not name:
        return ""
    return (
        str(name)
        .replace("\u200c", "")
        .replace("\u200e", "")
        .replace("\u200f", "")
        .replace(" ", "")
        .replace("ـ", "")
    )


def name_has_weekday(name: str | None, weekday_fa: str) -> bool:
    n = normalize_fa_name(name)
    w = normalize_fa_name(weekday_fa)
    if not n or not w:
        return False
    # 'شنبه' is a suffix of 'یکشنبه' — require an exact-day match.
    if w == "شنبه":
        return "شنبه" in n and "یکشنبه" not in n
    return w in n


def tomorrow_weekday_fa(now: datetime | None = None) -> str:
    """Persian weekday label for tomorrow in Asia/Tehran."""
    local = now.astimezone(_TEHRAN) if now is not None else datetime.now(_TEHRAN)
    if local.tzinfo is None:
        local = local.replace(tzinfo=_TEHRAN)
    else:
        local = local.astimezone(_TEHRAN)
    return _WEEKDAY_FA[(local + timedelta(days=1)).weekday()]


def _is_kartkhan(entry: dict) -> bool:
    return "کارتخوان" in normalize_fa_name(entry.get("name"))


def _is_naqdi_board(entry: dict) -> bool:
    """Visible /trade 'نقدی …' tile (not the master 'نقد …')."""
    n = normalize_fa_name(entry.get("name"))
    return n.startswith("نقدی") and not _is_kartkhan(entry)


def _score_candidate(entry: dict, weekday_fa: str) -> tuple[int, int] | None:
    """Higher score wins. Second key breaks ties toward higher source ids."""
    if not name_has_weekday(entry.get("name"), weekday_fa):
        return None
    if _is_kartkhan(entry):
        return None
    if entry.get("buy") is None or entry.get("sell") is None:
        return None

    score = 0
    if _is_naqdi_board(entry):
        score += 100
    elif normalize_fa_name(entry.get("name")).startswith("نقد"):
        score += 40
    else:
        return None

    if entry.get("active"):
        score += 20

    eid = entry.get("id")
    try:
        tie = int(eid) if eid is not None else 0
    except (TypeError, ValueError):
        tie = 0
    return score, tie


def resolve_tomorrow_naqd_id(
    entries: list[dict],
    *,
    now: datetime | None = None,
    fallback_id: int | None = None,
) -> int | None:
    """Return the best Farshad id for tomorrow's main نقدی cash tile.

    Falls back to ``fallback_id`` when no weekday match exists (e.g. empty
    cache at boot, or a holiday with no matching name yet).
    """
    weekday = tomorrow_weekday_fa(now)
    best: tuple[int, int] | None = None
    best_id: int | None = None
    for entry in entries:
        scored = _score_candidate(entry, weekday)
        if scored is None:
            continue
        if best is None or scored > best:
            best = scored
            try:
                best_id = int(entry["id"])
            except (KeyError, TypeError, ValueError):
                best_id = None
    if best_id is not None:
        return best_id
    return fallback_id


def resolve_target_price_id(
    entries: list[dict],
    *,
    mode: str,
    fixed_id: int,
    now: datetime | None = None,
) -> int:
    """Resolve the effective /price target for this poll tick."""
    mode_norm = (mode or "tomorrow").strip().lower()
    if mode_norm in ("fixed", "pin", "manual"):
        return fixed_id
    resolved = resolve_tomorrow_naqd_id(entries, now=now, fallback_id=fixed_id)
    return resolved if resolved is not None else fixed_id
