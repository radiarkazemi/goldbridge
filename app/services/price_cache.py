"""
The single in-memory source of truth for "what's the latest price
data we have". Isolated in its own module (rather than living as
module-level globals in main.py or the poller) so both the poller
(writer) and the routers (readers) import the same object without
circular imports, and so it's the one place to swap for a shared
store (e.g. Redis) if goldbridge is ever run with multiple workers.
"""
from datetime import datetime, timezone

from app.core.config import get_settings

settings = get_settings()


class PriceCache:
    def __init__(self):
        self.latest_buy: float | None = None
        self.latest_sell: float | None = None
        self.updated_at: str | None = None
        self.source_updated_at: str | None = None
        self.entries: list[dict] = []
        self.consecutive_failures: int = 0

    def record_success(self, buy: float, sell: float, source_updated_at: str | None):
        self.latest_buy = buy
        self.latest_sell = sell
        self.updated_at = datetime.now(timezone.utc).isoformat()
        self.source_updated_at = source_updated_at
        self.consecutive_failures = 0

    def record_entries(self, new_entries: list[dict]) -> str:
        """Apply a cleaned source list into the cache.

        The upstream API sometimes rate-limits / truncates and returns
        only 1 entry instead of the full catalog. Blindly replacing the
        cache with that short list (or refusing to update at all) leaves
        secondary cards stale. Strategy:
          - empty -> no-op ("empty")
          - first fill OR full/equal-length list -> replace ("replaced")
          - shorter partial list -> merge by id, keeping other cards ("merged")

        Returns one of: "empty" | "replaced" | "merged".
        """
        if not new_entries:
            return "empty"

        if not self.entries or len(new_entries) >= len(self.entries):
            self.entries = list(new_entries)
            return "replaced"

        by_id = {e["id"]: dict(e) for e in self.entries if e.get("id") is not None}
        for e in new_entries:
            eid = e.get("id")
            if eid is None:
                continue
            by_id[eid] = dict(e)

        ordered: list[dict] = []
        seen: set = set()
        for e in self.entries:
            eid = e.get("id")
            if eid in by_id and eid not in seen:
                ordered.append(by_id[eid])
                seen.add(eid)
        for e in new_entries:
            eid = e.get("id")
            if eid is not None and eid not in seen:
                ordered.append(dict(e))
                seen.add(eid)

        self.entries = ordered
        return "merged"

    def sync_target_quote(self, price_id: int, buy: float, sell: float, source_updated_at: str | None):
        """Keep the matching /prices row in sync with /price's target quote
        even when the source only returned that one row this tick."""
        for entry in self.entries:
            if entry.get("id") == price_id:
                entry["buy"] = buy
                entry["sell"] = sell
                if source_updated_at:
                    entry["last_update_time"] = source_updated_at
                return
        # Target not in list yet (boot / never saw a full catalog) - add a
        # minimal row so /prices isn't empty of the primary instrument.
        self.entries.append({
            "id": price_id,
            "name": None,
            "type": None,
            "ayar": None,
            "item_weight": None,
            "active": True,
            "allow_buy": True,
            "allow_sell": True,
            "base_price": None,
            "profit": None,
            "master_profit": None,
            "farshad_commission": None,
            "farshad_spread": None,
            "buy": buy,
            "sell": sell,
            "related_id": None,
            "related_diff": None,
            "min": None,
            "max": None,
            "last_update_time": source_updated_at,
        })

    def record_failure(self):
        self.consecutive_failures += 1

    def get_entry(self, entry_id: int) -> dict | None:
        return next((e for e in self.entries if e["id"] == entry_id), None)

    @property
    def is_stale(self) -> bool:
        return self.latest_buy is None or self.consecutive_failures >= settings.max_stale_polls


# Single shared instance for the whole process.
cache = PriceCache()
