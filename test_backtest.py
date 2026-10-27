import unittest

from backtest import BacktestConfig, aggregate_4h, backtest_symbol, parse_closed_ohlc, rsi


class BacktestTests(unittest.TestCase):
    def test_parser_drops_open_bar_and_deduplicates(self):
        now = 10 * 3600
        rows = [
            {"Time": 7 * 3600, "Open": 100, "High": 110, "Low": 90, "Close": 105, "Volume": 2},
            {"Time": 7 * 3600, "Open": 100, "High": 112, "Low": 90, "Close": 106, "Volume": 3},
            {"Time": 9 * 3600, "Open": 100, "High": 110, "Low": 90, "Close": 105, "Volume": 2},
            {"Time": 8 * 3600, "Open": 100, "High": 90, "Low": 95, "Close": 105, "Volume": 2},
        ]
        parsed = parse_closed_ohlc(rows, now_timestamp=now)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["close"], 106)

    def test_parser_normalizes_millisecond_timestamp(self):
        row = {"time": 7 * 3600 * 1000, "open": 100, "high": 110, "low": 90, "close": 105}
        parsed = parse_closed_ohlc([row], now_timestamp=10 * 3600)
        self.assertEqual(parsed[0]["time"], 7 * 3600)

    def test_aggregate_only_complete_four_hour_groups(self):
        candles = []
        for hour in range(8):
            candles.append({"time": hour * 3600, "open": 100 + hour, "high": 110 + hour,
                            "low": 90 + hour, "close": 105 + hour, "volume": 1})
        result = aggregate_4h(candles)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["open"], 100)
        self.assertEqual(result[0]["close"], 108)
        self.assertEqual(result[0]["volume"], 4)

    def test_rsi_flat_series_is_neutral(self):
        self.assertEqual(rsi([100.0] * 20), 50.0)

    def test_rejects_too_short_history(self):
        candles = [{"time": i * 3600, "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1}
                   for i in range(99)]
        with self.assertRaisesRegex(ValueError, "need at least"):
            backtest_symbol("TEST", candles)

    def test_config_rejects_negative_capital(self):
        with self.assertRaises(ValueError):
            BacktestConfig(initial_capital_idr=0)

    def test_config_rejects_extreme_fee(self):
        with self.assertRaises(ValueError):
            BacktestConfig(fee_bps_per_side=2000)


if __name__ == "__main__":
    unittest.main()
