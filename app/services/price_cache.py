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

    def record_entries(self, new_entries: list[dict]) -> bool:
        """Only replaces the cached list if it's at least as complete as
        what's already cached - protects against a flaky short response
        from the source silently dropping entries. Returns True if the
        cache was updated."""
        if len(new_entries) >= len(self.entries):
            self.entries = new_entries
            return True
        return False

    def record_failure(self):
        self.consecutive_failures += 1

    def get_entry(self, entry_id: int) -> dict | None:
        return next((e for e in self.entries if e["id"] == entry_id), None)

    @property
    def is_stale(self) -> bool:
        return self.latest_buy is None or self.consecutive_failures >= settings.max_stale_polls


# Single shared instance for the whole process.
cache = PriceCache()