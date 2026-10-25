"""Small offline smoke tests: python -m unittest test_market_radar.py"""
import time
import unittest
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

    def test_indodax_parser_and_24h_change(self):
        ts = int(time.time())
        mock_payload = {
            "tickers": {
                "btc_idr": {"last": "105", "high": "110", "low": "100", "buy": "104", "sell": "106", "server_time": ts},
                "eth_idr": {"last": "50", "high": "55", "low": "45", "server_time": ts},
            },
            "prices_24h": {"btcidr": "100", "ethidr": "52"},
        }
        with patch.object(mr, "http_json", return_value=mock_payload):
            data = mr.get_indodax_data()
        self.assertEqual(data["BTC"]["price"], 105.0)
        self.assertAlmostEqual(data["BTC"]["change_pct"], 5.0)
        self.assertEqual(data["BTC"]["position"], 0.5)
        self.assertFalse(data["SUI"]["available"])

    def test_rsi_rising_series(self):
        self.assertEqual(mr.rsi14(list(range(20))), 100.0)

if __name__ == "__main__":
    unittest.main(verbosity=2)
