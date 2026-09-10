"""Regression tests for Farshad on-screen buy/sell derivation.

The old formula (price + priceSell / price + priceBuy) disagrees with
the Farshad app whenever priceBuy/priceSell are 0 or a different
spread than profit. These cases are captured from live list.php rows.
"""
import unittest

from app.services.source_parser import (
    clean_entry,
    extract_buy_sell,
    farshad_screen_buy_sell,
)


def _old_formula(entry: dict) -> tuple[float, float]:
    base = float(entry["price"])
    return base + float(entry.get("priceSell") or 0), base + float(entry.get("priceBuy") or 0)


class FarshadScreenQuoteTests(unittest.TestCase):
    def test_offsets_zero_uses_profit_not_flat_mid(self):
        # Live id=1012-shaped row: the common "bot idle" payload.
        entry = {
            "id": 1012,
            "name": "نقدی شنبه",
            "type": 1,
            "rate": 4.3318,
            "price": 1045200000,
            "priceBuy": 0,
            "priceSell": 0,
            "profit": 700000,
            "masterProfit": 0,
        }
        buy, sell = farshad_screen_buy_sell(entry)
        self.assertEqual((buy, sell), (1045900000.0, 1044500000.0))
        old_buy, old_sell = _old_formula(entry)
        self.assertEqual((old_buy, old_sell), (1045200000.0, 1045200000.0))
        self.assertNotEqual((buy, sell), (old_buy, old_sell))

    def test_nonzero_offsets_still_use_profit(self):
        # Live id=1014: priceBuy/priceSell are a ±500k bot offset, but
        # the app board shows ±profit (700k), not the offsets.
        entry = {
            "id": 1014,
            "name": "نقدی کارتخوان",
            "type": 1,
            "rate": 4.3318,
            "price": 1045700000,
            "priceBuy": -500000,
            "priceSell": 500000,
            "profit": 700000,
            "masterProfit": 0,
        }
        buy, sell = farshad_screen_buy_sell(entry)
        self.assertEqual((buy, sell), (1046400000.0, 1045000000.0))
        old_buy, old_sell = _old_formula(entry)
        self.assertEqual((old_buy, old_sell), (1046200000.0, 1045200000.0))
        self.assertNotEqual((buy, sell), (old_buy, old_sell))

    def test_master_profit_is_added_to_the_spread(self):
        entry = {
            "price": 1_000_000,
            "profit": 10_000,
            "masterProfit": 5_000,
        }
        self.assertEqual(
            farshad_screen_buy_sell(entry),
            (1_015_000.0, 985_000.0),
        )

    def test_missing_profit_fields_default_to_zero(self):
        self.assertEqual(
            farshad_screen_buy_sell({"price": 100}),
            (100.0, 100.0),
        )

    def test_missing_price_returns_none(self):
        self.assertIsNone(farshad_screen_buy_sell({"profit": 1}))

    def test_shakaste_gold_rounds_to_10000_rial(self):
        entry = {
            "name": "آبشده شکسته",
            "type": 1,
            "rate": 1,
            "price": 1_000_040,
            "profit": 10,
            "masterProfit": 0,
        }
        buy, sell = farshad_screen_buy_sell(entry)
        self.assertEqual(buy, 1_000_000.0)
        self.assertEqual(sell, 1_000_000.0)

    def test_shakaste_rounding_does_not_apply_to_mithqal_gold(self):
        entry = {
            "name": "آبشده شکسته",
            "type": 1,
            "rate": 4.3318,
            "price": 1_000_040,
            "profit": 10,
            "masterProfit": 0,
        }
        self.assertEqual(
            farshad_screen_buy_sell(entry),
            (1_000_050.0, 1_000_030.0),
        )

    def test_extract_buy_sell_picks_target_id(self):
        payload = {
            "prices": [
                {"id": 1, "price": 100, "profit": 1, "masterProfit": 0},
                {"id": 1012, "price": 1000, "profit": 7, "masterProfit": 0},
            ]
        }
        self.assertEqual(extract_buy_sell(payload, 1012), (1007.0, 993.0))
        self.assertIsNone(extract_buy_sell(payload, 99))

    def test_clean_entry_exposes_screen_quote(self):
        cleaned = clean_entry({
            "id": 1,
            "name": "نقد شنبه",
            "type": 1,
            "ayar": 0,
            "itemWeight": 0,
            "isActive": 1,
            "allowBuy": 1,
            "allowSell": 1,
            "price": 1045800000,
            "priceBuy": 0,
            "priceSell": 0,
            "profit": 300000,
            "masterProfit": 0,
            "min": 1,
            "max": 5000,
            "lastUpdateTime": "2026-09-10 12:12:04",
        })
        self.assertEqual(cleaned["buy"], 1046100000.0)
        self.assertEqual(cleaned["sell"], 1045500000.0)
        self.assertEqual(cleaned["base_price"], 1045800000)


if __name__ == "__main__":
    unittest.main()
