"""Offline tests for Market Radar v1.13.2 anomaly panels, history controls, and detection."""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from anomaly_radar import (
    MarketAnomalyEngine,
    calculate_depth_metrics,
    calculate_trade_metrics,
    filter_anomaly_rows,
    sort_anomaly_rows,
    filter_anomaly_history_rows,
    sort_anomaly_history_rows,
)

WIB = timezone(timedelta(hours=7))


def stamp(seconds: int) -> datetime:
    return datetime.fromtimestamp(seconds, WIB)


def payload(last: float, high: float | None = None, low: float | None = None,
            bid: float | None = None, ask: float | None = None,
            volume: float = 100_000_000.0, symbol: str = "pieverse_idr") -> dict:
    return {
        "tickers": {
            symbol: {
                "name": "Pieverse", "last": str(last), "high": str(high if high is not None else last),
                "low": str(low if low is not None else last), "buy": str(bid if bid is not None else last * .999),
                "sell": str(ask if ask is not None else last * 1.001), "vol_idr": str(volume),
            },
            "btc_usdt": {"last": "90000", "high": "91000", "low": "89000"},
        },
        "prices_24h": {"pieverseidr": str(last)},
    }


class AnomalyDetectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = MarketAnomalyEngine(Path(self.tmp.name) / "events.jsonl")
        self.lookup = {"PIEVERSE": {"pair_id": "pieverseidr", "name": "Pieverse"}}
        self.base = 1_780_000_000

    def tearDown(self):
        self.tmp.cleanup()

    def test_scans_only_idr_pairs_and_uses_pair_catalogue_metadata(self):
        rows = self.engine.update_from_payload(payload(100), self.lookup, stamp(self.base))
        self.assertEqual(rows, [])
        self.assertIn("PIEVERSE", self.engine.price_history)
        self.assertNotIn("BTC_USDT", self.engine.price_history)

    def test_extreme_24h_wick_is_detected_even_on_first_snapshot(self):
        rows = self.engine.update_from_payload(
            payload(18_500, high=8_000_000, low=17_000), self.lookup, stamp(self.base)
        )
        self.assertEqual(len(rows), 1)
        self.assertIn("24H WICK ANOMALY", rows[0]["flags"])
        self.assertEqual(rows[0]["severity"], "CRITICAL")
        self.assertGreater(rows[0]["wick_from_high_pct"], 40_000)

    def test_normal_24h_range_does_not_trigger_wick_alert(self):
        rows = self.engine.update_from_payload(
            payload(100, high=120, low=90), self.lookup, stamp(self.base)
        )
        self.assertEqual(rows, [])

    def test_rapid_five_minute_price_move_is_detected(self):
        self.engine.update_from_payload(payload(100), self.lookup, stamp(self.base))
        rows = self.engine.update_from_payload(payload(105), self.lookup, stamp(self.base + 300))
        self.assertIn("RAPID PRICE MOVE", rows[0]["flags"])
        self.assertAlmostEqual(rows[0]["change_5m_pct"], 5.0)

    def test_volume_delta_proxy_is_flagged_and_disclosed(self):
        self.engine.update_from_payload(payload(100, volume=100_000_000), self.lookup, stamp(self.base))
        rows = self.engine.update_from_payload(
            payload(100, volume=140_000_000), self.lookup, stamp(self.base + 300)
        )
        self.assertIn("VOLUME ACCELERATION", rows[0]["flags"])
        self.assertTrue(any("proxy rolling 24 jam" in item for item in rows[0]["evidence"]))

    def test_wide_spread_is_flagged_as_liquidity_risk(self):
        rows = self.engine.update_from_payload(
            payload(100, bid=98, ask=102), self.lookup, stamp(self.base)
        )
        self.assertIn("WIDE SPREAD", rows[0]["flags"])
        self.assertEqual(rows[0]["severity"], "WARNING")

    def test_event_journal_persists_and_applies_dedupe_cooldown(self):
        event_payload = payload(100, high=200, low=80)
        self.engine.update_from_payload(event_payload, self.lookup, stamp(self.base))
        self.engine.update_from_payload(event_payload, self.lookup, stamp(self.base + 30))
        self.assertEqual(len(self.engine.get_history()), 1)
        reloaded = MarketAnomalyEngine(self.engine.history_path)
        self.assertEqual(len(reloaded.get_history()), 1)
        self.assertEqual(reloaded.get_history()[0]["symbol"], "PIEVERSE")

    def test_history_records_new_anomaly_after_cooldown(self):
        event_payload = payload(100, high=200, low=80)
        self.engine.update_from_payload(event_payload, self.lookup, stamp(self.base))
        self.engine.update_from_payload(event_payload, self.lookup, stamp(self.base + 1801))
        self.assertGreaterEqual(len(self.engine.get_history()), 2)

    def test_malformed_payload_is_rejected(self):
        with self.assertRaises(ValueError):
            self.engine.update_from_payload({"wrong": {}}, self.lookup, stamp(self.base))

    def test_missing_or_nonpositive_prices_are_ignored(self):
        bad = {"tickers": {"pieverse_idr": {"last": "0"}}, "prices_24h": {}}
        self.assertEqual(self.engine.update_from_payload(bad, self.lookup, stamp(self.base)), [])

    def test_non_dict_prices_24h_is_treated_as_unavailable(self):
        bad_prices = payload(100, high=200)
        bad_prices["prices_24h"] = []
        rows = self.engine.update_from_payload(bad_prices, self.lookup, stamp(self.base))
        self.assertIn("24H WICK ANOMALY", rows[0]["flags"])
        self.assertIsNone(rows[0]["change_24h_pct"])

    def test_stale_ticker_rows_are_ignored(self):
        stale = payload(100, high=500)
        stale["tickers"]["pieverse_idr"]["server_time"] = str(self.base - 600)
        self.assertEqual(self.engine.update_from_payload(stale, self.lookup, stamp(self.base)), [])


class PublicDetailParsingTests(unittest.TestCase):
    def test_trade_metrics_count_recent_trade_notional_and_buy_ratio(self):
        now = 1_780_000_000
        trades = [
            {"date": str(now - 30), "price": "100", "amount": "2", "type": "buy"},
            {"date": str(now - 60), "price": "100", "amount": "1", "type": "sell"},
            {"date": str(now - 600), "price": "100", "amount": "99", "type": "buy"},
        ]
        result = calculate_trade_metrics(trades, now)
        self.assertEqual(result["trade_count_5m"], 2)
        self.assertEqual(result["trade_notional_5m_idr"], 300)
        self.assertAlmostEqual(result["buy_ratio_5m"], 2 / 3)

    def test_trade_metrics_accept_millisecond_timestamps(self):
        now = 1_780_000_000
        result = calculate_trade_metrics([
            {"date": str((now - 10) * 1000), "price": "20", "amount": "3", "type": "buy"}
        ], now)
        self.assertEqual(result["trade_count_5m"], 1)
        self.assertEqual(result["trade_notional_5m_idr"], 60)

    def test_depth_metrics_compute_spread_near_touch_depth_and_imbalance(self):
        depth = {
            "buy": [[99, "15"], [98.5, "5"], [95, "100"]],
            "sell": [[101, "5"], [101.5, "10"], [103, "100"]],
        }
        result = calculate_depth_metrics(depth)
        self.assertEqual(result["book_status"], "AVAILABLE")
        self.assertAlmostEqual(result["book_spread_pct"], 2.0)
        self.assertEqual(result["bid_depth_1pct_idr"], 99 * 15 + 98.5 * 5)
        self.assertEqual(result["ask_depth_1pct_idr"], 101 * 5 + 101.5 * 10)
        self.assertGreater(result["book_imbalance"], 0.5)

    def test_invalid_depth_returns_unavailable(self):
        self.assertEqual(calculate_depth_metrics(None)["book_status"], "UNAVAILABLE")
        self.assertEqual(calculate_depth_metrics({"buy": [], "sell": []})["book_status"], "INCOMPLETE")

    def test_summary_uses_exchange_pair_id_when_present(self):
        engine = self.engine_for_test()
        rows = engine.update_from_payload(payload(100, high=200), {}, stamp(1_780_000_000))
        self.assertEqual(rows[0]["pair_id"], "pieverseidr")

    @staticmethod
    def engine_for_test():
        import tempfile
        return MarketAnomalyEngine(Path(tempfile.mkdtemp()) / "events.jsonl")


class AnomalyTableHelpersTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {"symbol": "PIEVERSE", "name": "Pieverse", "severity": "CRITICAL",
             "flags": ["24H WICK ANOMALY"], "price": 18_500, "spread_pct": 1.2,
             "wick_from_high_pct": 40_000, "change_5m_pct": -3.0},
            {"symbol": "ALPHA", "name": "Alpha Token", "severity": "HIGH",
             "flags": ["RAPID PRICE MOVE", "WIDE SPREAD"], "price": 250, "spread_pct": 6.0,
             "wick_from_high_pct": None, "change_5m_pct": 17.0},
            {"symbol": "BETA", "name": "Beta", "severity": "WARNING",
             "flags": ["VOLUME ACCELERATION"], "price": 100, "spread_pct": None,
             "wick_from_high_pct": 40, "change_5m_pct": None},
        ]

    def test_search_matches_symbol_name_and_detection_text(self):
        self.assertEqual([r["symbol"] for r in filter_anomaly_rows(self.rows, "pieverse")], ["PIEVERSE"])
        self.assertEqual([r["symbol"] for r in filter_anomaly_rows(self.rows, "wide spread")], ["ALPHA"])

    def test_severity_and_detection_filters_can_be_combined(self):
        result = filter_anomaly_rows(self.rows, severity="HIGH", detection="WIDE SPREAD")
        self.assertEqual([r["symbol"] for r in result], ["ALPHA"])
        self.assertEqual(filter_anomaly_rows(self.rows, severity="CRITICAL", detection="WIDE SPREAD"), [])

    def test_default_sort_prioritises_critical_then_high_then_warning(self):
        result = sort_anomaly_rows(self.rows)
        self.assertEqual([r["symbol"] for r in result], ["PIEVERSE", "ALPHA", "BETA"])

    def test_numeric_sort_works_ascending_and_descending_with_missing_last(self):
        ascending = sort_anomaly_rows(self.rows, "price", False)
        descending = sort_anomaly_rows(self.rows, "price", True)
        self.assertEqual([r["symbol"] for r in ascending], ["BETA", "ALPHA", "PIEVERSE"])
        self.assertEqual([r["symbol"] for r in descending], ["PIEVERSE", "ALPHA", "BETA"])

    def test_missing_numeric_values_stay_at_bottom_in_both_directions(self):
        ascending = sort_anomaly_rows(self.rows, "spread", False)
        descending = sort_anomaly_rows(self.rows, "spread", True)
        self.assertEqual([r["symbol"] for r in ascending], ["PIEVERSE", "ALPHA", "BETA"])
        self.assertEqual([r["symbol"] for r in descending], ["ALPHA", "PIEVERSE", "BETA"])


class AnomalyHistoryHelpersTests(unittest.TestCase):
    def setUp(self):
        self.events = [
            {"symbol": "PIEVERSE", "name": "Pieverse", "pair_id": "pieverseidr",
             "anomaly_type": "24H WICK ANOMALY", "severity": "CRITICAL",
             "detected_at": "2026-10-31 09:01:00 WIB", "timestamp_epoch": 1_793_420_460,
             "price": 18_500, "change_5m_pct": -45.0, "wick_from_high_pct": 42_000,
             "spread_pct": 2.2, "evidence": ["High 24j ekstrem dibanding harga terakhir"]},
            {"symbol": "ALPHA", "name": "Alpha Token", "pair_id": "alphaidr",
             "anomaly_type": "WIDE SPREAD", "severity": "HIGH",
             "detected_at": "2026-10-31 09:03:00 WIB", "timestamp_epoch": 1_793_420_580,
             "price": 250, "change_5m_pct": 17.0, "wick_from_high_pct": None,
             "spread_pct": 6.0, "evidence": ["Spread bid/ask melebar"]},
            {"symbol": "BETA", "name": "Beta", "pair_id": "betaidr",
             "anomaly_type": "VOLUME ACCELERATION", "severity": "WARNING",
             "detected_at": "2026-10-31 09:02:00 WIB", "timestamp_epoch": 1_793_420_520,
             "price": 100, "change_5m_pct": None, "wick_from_high_pct": 40,
             "spread_pct": None, "evidence": ["Ticker volume proxy"]},
        ]

    def test_search_matches_pair_name_detection_and_evidence(self):
        self.assertEqual(
            [row["symbol"] for row in filter_anomaly_history_rows(self.events, "pieverse")],
            ["PIEVERSE"],
        )
        self.assertEqual(
            [row["symbol"] for row in filter_anomaly_history_rows(self.events, "ticker volume")],
            ["BETA"],
        )
        self.assertEqual(
            [row["symbol"] for row in filter_anomaly_history_rows(self.events, "alphaidr")],
            ["ALPHA"],
        )

    def test_severity_and_detection_filters_can_be_combined(self):
        result = filter_anomaly_history_rows(self.events, severity="HIGH", detection="WIDE SPREAD")
        self.assertEqual([row["symbol"] for row in result], ["ALPHA"])
        self.assertEqual(
            filter_anomaly_history_rows(self.events, severity="CRITICAL", detection="WIDE SPREAD"),
            [],
        )

    def test_severity_sort_prioritises_critical_then_high_then_warning(self):
        result = sort_anomaly_history_rows(self.events, "severity", False)
        self.assertEqual([row["symbol"] for row in result], ["PIEVERSE", "ALPHA", "BETA"])

    def test_time_sort_is_newest_first_by_default_and_oldest_first_on_reverse(self):
        newest = sort_anomaly_history_rows(self.events, "time", True)
        oldest = sort_anomaly_history_rows(self.events, "time", False)
        self.assertEqual([row["symbol"] for row in newest], ["ALPHA", "BETA", "PIEVERSE"])
        self.assertEqual([row["symbol"] for row in oldest], ["PIEVERSE", "BETA", "ALPHA"])

    def test_numeric_sort_keeps_missing_values_last_in_both_directions(self):
        ascending = sort_anomaly_history_rows(self.events, "spread", False)
        descending = sort_anomaly_history_rows(self.events, "spread", True)
        self.assertEqual([row["symbol"] for row in ascending], ["PIEVERSE", "ALPHA", "BETA"])
        self.assertEqual([row["symbol"] for row in descending], ["ALPHA", "PIEVERSE", "BETA"])

    def test_sort_supports_every_history_column(self):
        expected = {
            "asset": ["ALPHA", "BETA", "PIEVERSE"],
            "type": ["PIEVERSE", "BETA", "ALPHA"],
            "price": ["BETA", "ALPHA", "PIEVERSE"],
            "move5": ["PIEVERSE", "ALPHA", "BETA"],
            "wick": ["BETA", "PIEVERSE", "ALPHA"],
        }
        for key, symbols in expected.items():
            with self.subTest(sort_key=key):
                result = sort_anomaly_history_rows(self.events, key, False)
                self.assertEqual([row["symbol"] for row in result], symbols)

    def test_filter_does_not_mutate_source_event_list(self):
        original = list(self.events)
        filter_anomaly_history_rows(self.events, "beta")
        self.assertEqual(self.events, original)



if __name__ == "__main__":
    unittest.main(verbosity=2)
