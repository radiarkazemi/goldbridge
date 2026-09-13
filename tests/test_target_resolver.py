"""Tests for tomorrow's Farshad نقدی target selection."""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.source_parser import clean_prices
from app.services.target_resolver import (
    name_has_weekday,
    normalize_fa_name,
    resolve_target_price_id,
    resolve_tomorrow_naqd_id,
    tomorrow_weekday_fa,
)

_TEHRAN = ZoneInfo("Asia/Tehran")


class WeekdayNameTests(unittest.TestCase):
    def test_normalize_strips_zwnj(self):
        self.assertEqual(normalize_fa_name("نقدی سه\u200cشنبه"), "نقدیسهشنبه")

    def test_shanbeh_does_not_match_yekshanbeh(self):
        self.assertTrue(name_has_weekday("نقدی شنبه", "شنبه"))
        self.assertFalse(name_has_weekday("نقدی یکشنبه", "شنبه"))
        self.assertTrue(name_has_weekday("نقدی یکشنبه", "یکشنبه"))


class TomorrowNaqdResolverTests(unittest.TestCase):
    payload = {
        "prices": [
            {
                "id": 1,
                "name": "نقد دوشنبه",
                "isActive": 0,
                "price": 1019600000,
                "profit": 300000,
                "masterProfit": 0,
            },
            {
                "id": 1013,
                "name": "نقدی یکشنبه",
                "isActive": 0,
                "price": 1019600000,
                "profit": 700000,
                "masterProfit": 0,
                "relatedId": 1,
            },
            {
                "id": 1009,
                "name": "نقدی دوشنبه",
                "isActive": 1,
                "price": 1027800000,
                "profit": 600000,
                "masterProfit": 0,
                "relatedId": 1,
            },
            {
                "id": 1014,
                "name": "نقدی کارتخوان",
                "isActive": 1,
                "price": 1028300000,
                "profit": 600000,
                "masterProfit": 0,
                "relatedId": 1009,
            },
            {
                "id": 1010,
                "name": "نقدی سه‌شنبه",
                "isActive": 1,
                "price": 1030800000,
                "profit": 700000,
                "masterProfit": 0,
                "relatedId": 7,
            },
        ]
    }

    def setUp(self):
        self.entries = clean_prices(self.payload)

    def test_sunday_picks_doshanbeh_board_not_yekshanbeh(self):
        # Sunday 2026-09-13 afternoon Tehran → tomorrow = دوشنبه
        now = datetime(2026, 9, 13, 16, 0, tzinfo=_TEHRAN)
        self.assertEqual(tomorrow_weekday_fa(now), "دوشنبه")
        self.assertEqual(resolve_tomorrow_naqd_id(self.entries, now=now), 1009)

    def test_ignores_kartkhan_variant(self):
        now = datetime(2026, 9, 13, 16, 0, tzinfo=_TEHRAN)
        self.assertEqual(resolve_tomorrow_naqd_id(self.entries, now=now), 1009)

    def test_prefers_active_naqdi_over_inactive_master(self):
        now = datetime(2026, 9, 13, 16, 0, tzinfo=_TEHRAN)
        # Master id=1 is also named دوشنبه but inactive / smaller سود.
        self.assertEqual(resolve_tomorrow_naqd_id(self.entries, now=now), 1009)

    def test_monday_picks_seshanbeh(self):
        now = datetime(2026, 9, 14, 10, 0, tzinfo=_TEHRAN)  # Monday
        self.assertEqual(tomorrow_weekday_fa(now), "سه‌شنبه")
        self.assertEqual(resolve_tomorrow_naqd_id(self.entries, now=now), 1010)

    def test_fallback_when_no_match(self):
        now = datetime(2026, 9, 17, 10, 0, tzinfo=_TEHRAN)  # Thursday → جمعه
        self.assertEqual(tomorrow_weekday_fa(now), "جمعه")
        self.assertEqual(
            resolve_tomorrow_naqd_id(self.entries, now=now, fallback_id=1009),
            1009,
        )

    def test_mode_fixed_pins_id(self):
        now = datetime(2026, 9, 13, 16, 0, tzinfo=_TEHRAN)
        self.assertEqual(
            resolve_target_price_id(
                self.entries, mode="fixed", fixed_id=1013, now=now
            ),
            1013,
        )

    def test_mode_tomorrow_overrides_stale_pin(self):
        now = datetime(2026, 9, 13, 16, 0, tzinfo=_TEHRAN)
        self.assertEqual(
            resolve_target_price_id(
                self.entries, mode="tomorrow", fixed_id=1013, now=now
            ),
            1009,
        )


if __name__ == "__main__":
    unittest.main()
