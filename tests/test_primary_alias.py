"""Primary alias always mirrors the resolved tomorrow tile."""
import unittest

from app.services.price_cache import PriceCache


class PrimaryAliasTests(unittest.TestCase):
    def test_alias_mirrors_source_and_keeps_stable_id(self):
        cache = PriceCache()
        cache.entries = [
            {
                "id": 1011,
                "name": "نقدی چهارشنبه",
                "active": True,
                "base_price": 100.0,
                "profit": 7.0,
                "master_profit": 0.0,
                "farshad_commission": 7.0,
                "farshad_spread": 14.0,
                "buy": 107.0,
                "sell": 93.0,
                "related_id": 1,
                "last_update_time": "t1",
            }
        ]
        cache.sync_primary_alias(900000, 1011)
        alias = cache.get_entry(900000)
        self.assertIsNotNone(alias)
        self.assertEqual(alias["id"], 900000)
        self.assertEqual(alias["name"], "نقدی چهارشنبه")
        self.assertEqual(alias["buy"], 107.0)
        self.assertEqual(alias["sell"], 93.0)
        self.assertEqual(alias["related_id"], 1011)
        self.assertTrue(alias["active"])

    def test_alias_updates_in_place(self):
        cache = PriceCache()
        cache.entries = [
            {"id": 1011, "name": "نقدی چهارشنبه", "buy": 1.0, "sell": 2.0, "related_id": 1},
            {"id": 900000, "name": "old", "buy": 0.0, "sell": 0.0, "related_id": 1009},
        ]
        cache.sync_primary_alias(900000, 1011)
        self.assertEqual(len([e for e in cache.entries if e["id"] == 900000]), 1)
        self.assertEqual(cache.get_entry(900000)["buy"], 1.0)
        self.assertEqual(cache.get_entry(900000)["related_id"], 1011)


if __name__ == "__main__":
    unittest.main()
