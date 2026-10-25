"""Offline tests: python -m unittest -v test_market_radar.py"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import market_radar as mr


class HelpersTest(unittest.TestCase):
    def test_pair_key_normalisation(self):
        self.assertEqual(mr.find_key({"btc_idr": 1}, "BTCIDR"), "btc_idr")

    def test_percent_format(self):
        self.assertEqual(mr.fmt_pct(1.236), "+1.24%")
        self.assertEqual(mr.fmt_pct(-1.236), "-1.24%")

    def test_reclaim_warning_when_near_low(self):
        label, tag = mr.setup_label({"available": True, "change_pct": -4.2, "position": 0.08})
        self.assertIn("tunggu reclaim", label)
        self.assertEqual(tag, "negative")

    def test_dynamic_pair_catalogue_includes_all_idr_pairs_and_excludes_cross_pairs(self):
        pairs = [
            {"id": "btcidr", "symbol": "BTCIDR", "base_currency": "idr", "traded_currency": "btc", "traded_currency_unit": "BTC", "ticker_id": "btc_idr"},
            {"id": "ethidr", "symbol": "ETHIDR", "base_currency": "idr", "traded_currency": "eth", "traded_currency_unit": "ETH", "ticker_id": "eth_idr"},
            {"id": "arbidr", "symbol": "ARBIDR", "base_currency": "idr", "traded_currency": "arb", "traded_currency_unit": "ARB", "ticker_id": "arb_idr"},
            {"id": "ethbtc", "symbol": "ETHBTC", "base_currency": "btc", "traded_currency": "eth", "traded_currency_unit": "ETH", "ticker_id": "eth_btc"},
        ]
        summaries = {
            "tickers": {
                "btc_idr": {"name": "Bitcoin", "last": "105", "high": "110", "low": "100", "buy": "104", "sell": "106", "vol_idr": "5000"},
                "eth_idr": {"name": "Ethereum", "last": "50", "high": "55", "low": "45", "vol_idr": "3000"},
                "arb_idr": {"name": "Arbitrum", "last": "25", "high": "30", "low": "20", "vol_idr": "1000"},
            },
            "prices_24h": {"btcidr": "100", "ethidr": "52", "arbidr": "20"},
        }
        with patch.object(mr, "http_json", side_effect=[pairs, summaries]):
            data = mr.get_indodax_data()
        self.assertEqual(set(data), {"BTC", "ETH", "ARB"})
        self.assertNotIn("ETHBTC", data)
        self.assertEqual(data["BTC"]["price"], 105.0)
        self.assertAlmostEqual(data["BTC"]["change_pct"], 5.0)
        self.assertEqual(data["BTC"]["position"], 0.5)
        self.assertEqual(data["ARB"]["name"], "Arbitrum")
        self.assertEqual({symbol for symbol, _ in mr.CRYPTO_ASSETS}, {"BTC", "ETH", "ARB"})

    def test_dynamic_summary_fallback_when_pair_catalogue_fails(self):
        summaries = {
            "tickers": {
                "btc_idr": {"name": "Bitcoin", "last": "105", "high": "110", "low": "100"},
                "ten_idr": {"name": "Ten", "last": "2", "high": "3", "low": "1"},
                "eth_btc": {"name": "Ethereum/BTC", "last": "1"},
            },
            "prices_24h": {"btcidr": "100"},
        }
        with patch.object(mr, "http_json", side_effect=[RuntimeError("catalogue unavailable"), summaries]):
            data = mr.get_indodax_data()
        self.assertEqual(set(data), {"BTC", "TEN"})
        self.assertNotIn("ETH", data)

    def test_rsi_rising_series(self):
        self.assertEqual(mr.rsi14(list(range(20))), 100.0)

    def test_saved_api_key_is_encrypted_not_plaintext(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            def fake_dpapi(data, protect):
                return b"encrypted:" + data if protect else data.removeprefix(b"encrypted:")
            with patch.object(mr, "ai_settings_path", return_value=path), \
                 patch.object(mr, "_dpapi", side_effect=fake_dpapi), \
                 patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}):
                mr.save_ai_settings("openrouter/free", api_key="sk-or-example-sensitive-key")
                saved = path.read_text(encoding="utf-8")
                self.assertNotIn("sk-or-example-sensitive-key", saved)
                self.assertIn("api_key_protected", json.loads(saved))
                model, key = mr.load_ai_settings()
                self.assertEqual(model, "openrouter/free")
                self.assertEqual(key, "sk-or-example-sensitive-key")


if __name__ == "__main__":
    unittest.main(verbosity=2)
