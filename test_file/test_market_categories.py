import unittest

from market_categories import (
    INDODAX_CATEGORY_OPTIONS,
    categories_for_symbol,
    filter_assets_by_category,
)


class MarketCategoriesTest(unittest.TestCase):
    def setUp(self):
        self.assets = [
            ("BTC", "Bitcoin"),
            ("PEPE", "Pepe"),
            ("RENDER", "Render"),
            ("PAXG", "PAX Gold"),
            ("UNI", "Uniswap"),
            ("NEWCOIN", "New Coin"),
        ]

    def test_menu_contains_requested_indodax_categories(self):
        for category in ("AI & Big Data", "Layer 1&2", "Meme", "DeFi", "RWA"):
            self.assertIn(category, INDODAX_CATEGORY_OPTIONS)

    def test_all_categories_preserves_every_asset_and_order(self):
        self.assertEqual(filter_assets_by_category(self.assets), self.assets)

    def test_category_filter_returns_matching_assets(self):
        self.assertEqual(filter_assets_by_category(self.assets, "Meme"), [("PEPE", "Pepe")])
        self.assertEqual(filter_assets_by_category(self.assets, "AI & Big Data"), [("RENDER", "Render")])

    def test_asset_can_belong_to_multiple_categories(self):
        self.assertEqual(categories_for_symbol("UNI"), ("Governance/DAO", "CEX/DEX", "DeFi"))

    def test_symbol_matching_is_case_insensitive(self):
        self.assertEqual(categories_for_symbol("pEpe"), ("Meme",))

    def test_unmapped_assets_are_not_mislabelled_as_others(self):
        self.assertEqual(categories_for_symbol("NEWCOIN"), ("Unmapped",))
        self.assertEqual(filter_assets_by_category(self.assets, "Unmapped"), [("NEWCOIN", "New Coin")])

    def test_unknown_category_returns_no_rows(self):
        self.assertEqual(filter_assets_by_category(self.assets, "Not a category"), [])

    def test_input_collection_is_not_modified(self):
        original = list(self.assets)
        filter_assets_by_category(self.assets, "Meme")
        self.assertEqual(self.assets, original)


if __name__ == "__main__":
    unittest.main()
