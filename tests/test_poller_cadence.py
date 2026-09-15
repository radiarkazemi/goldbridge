"""Poller cadence helpers – keep 1s polling safe under truncated catalogs."""
import unittest

from app.core.config import get_settings
from app.services.poller import _backoff_seconds, _interval_after_tick


class PollerCadenceTests(unittest.TestCase):
    def test_default_poll_is_one_second(self):
        settings = get_settings()
        self.assertEqual(settings.poll_seconds, 1.0)
        self.assertLessEqual(settings.poll_fast_seconds, settings.poll_seconds)

    def test_interval_bursts_after_price_change(self):
        settings = get_settings()
        base, until = _interval_after_tick(changed=True, fast_until=0.0, now=100.0)
        self.assertEqual(base, settings.poll_fast_seconds)
        self.assertEqual(until, 100.0 + settings.poll_fast_window_seconds)

        still_fast, _ = _interval_after_tick(changed=False, fast_until=until, now=100.5)
        self.assertEqual(still_fast, settings.poll_fast_seconds)

        settled, _ = _interval_after_tick(changed=False, fast_until=until, now=200.0)
        self.assertEqual(settled, settings.poll_seconds)

    def test_backoff_without_failures_is_base_interval(self):
        from app.services.price_cache import cache

        cache.consecutive_failures = 0
        self.assertEqual(_backoff_seconds(1.0), 1.0)


if __name__ == "__main__":
    unittest.main()
