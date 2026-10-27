"""Offline regression tests for Market Radar's two OpenRouter analyst modes.
Run with: python -m unittest -v test_ai_modes.py
"""
import json
import os
import io
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import market_radar as mr


class AiModesTest(unittest.TestCase):
    def setUp(self):
        self.crypto = {
            "BTC": {
                "symbol": "BTC", "name": "Bitcoin", "available": True,
                "price": 100.0, "change_pct": 2.0, "low": 80.0, "high": 120.0,
                "volume_idr": 9000.0, "position": 0.5,
                "market_time": None, "retrieved_at": mr.now_wib(),
            },
            "ETH": {
                "symbol": "ETH", "name": "Ethereum", "available": True,
                "price": 90.0, "change_pct": -3.5, "low": 80.0, "high": 110.0,
                "volume_idr": 6000.0, "position": 1 / 3,
                "market_time": None, "retrieved_at": mr.now_wib(),
            },
        }
        self.macro = {
            "^GSPC": {
                "symbol": "^GSPC", "name": "S&P 500", "category": "index",
                "units": "points", "available": True, "price": 5000,
                "change_pct": -0.7, "market_time": None, "retrieved_at": mr.now_wib(),
            },
            "GC=F": {"symbol": "GC=F", "name": "Gold futures", "available": False, "error": "timeout"},
        }
        self.news = [{
            "title": "Markets fell today", "source": "Example News",
            "pubDate": "Tue, 27 Oct 2026 09:00:00 GMT", "link": "https://example.com",
        }]

    def test_default_model_is_a_specific_free_model(self):
        self.assertEqual(mr.DEFAULT_AI_MODEL, "google/gemma-4-31b-it:free")
        self.assertEqual(mr.APP_VERSION, "1.9.1")

    def test_legacy_default_router_is_migrated_to_gemma(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            # v1.7.1 and the first v1.8.0 Gemma patch saved no settings_version.
            path.write_text(json.dumps({"model": "openrouter/free"}), encoding="utf-8")
            with patch.object(mr, "ai_settings_path", return_value=path), patch.dict(
                os.environ, {"OPENROUTER_MODEL": "", "OPENROUTER_API_KEY": ""}
            ):
                self.assertEqual(mr.load_ai_settings()[0], mr.DEFAULT_AI_MODEL)

    def test_explicitly_saved_model_id_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text(json.dumps({"settings_version": mr.AI_SETTINGS_VERSION,
                                        "model": "openrouter/free"}), encoding="utf-8")
            with patch.object(mr, "ai_settings_path", return_value=path), patch.dict(
                os.environ, {"OPENROUTER_MODEL": "", "OPENROUTER_API_KEY": ""}
            ):
                # An explicitly saved current-version model choice is preserved.
                self.assertEqual(mr.load_ai_settings()[0], "openrouter/free")

    def test_market_snapshot_contains_breadth_macro_and_headlines(self):
        snapshot = mr.build_ai_snapshot(self.crypto, self.macro, self.news, "market")
        self.assertEqual(snapshot["analysis_type"], "market")
        self.assertEqual(snapshot["crypto_pairs_available"], 2)
        self.assertEqual(snapshot["crypto_breadth"], {
            "up_24h": 1, "down_24h": 1, "unchanged_or_missing_change": 0,
        })
        self.assertEqual(snapshot["recent_headlines"][0]["source"], "Example News")
        self.assertFalse(next(row for row in snapshot["global_markets"] if row["symbol"] == "GC=F")["available"])

    def test_entry_exit_snapshot_contains_existing_action_and_reference_levels(self):
        snapshot = mr.build_ai_snapshot(self.crypto, self.macro, self.news, "entry_exit")
        btc = next(row for row in snapshot["crypto_top_by_idr_volume"] if row["symbol"] == "BTC")
        self.assertEqual(btc["rule_action"], "BUY WATCH")
        self.assertEqual(btc["reference_levels_24h_idr"], {
            "low": 80.0, "midpoint": 100.0, "high": 120.0,
        })

    def test_analyst_prompts_are_separate_and_include_risk_limits(self):
        _, market_prompt, market_tokens = mr._ai_prompts("market")
        _, entry_prompt, entry_tokens = mr._ai_prompts("entry_exit")
        self.assertIn("MARKET ANALYST", market_prompt)
        self.assertIn("ENTRY & EXIT ANALYST", entry_prompt)
        self.assertIn("not proven stop-loss/take-profit", entry_prompt)
        self.assertIn("Do NOT create another table", entry_prompt)
        self.assertIn("Maximum about 250 words", entry_prompt)
        self.assertGreater(entry_tokens, market_tokens)
        with self.assertRaises(ValueError):
            mr.build_ai_snapshot(self.crypto, self.macro, [], "unknown")

    def test_openrouter_request_uses_selected_model_and_analyst_mode(self):
        fake_response = MagicMock()
        fake_response.read.return_value = json.dumps({
            "model": mr.DEFAULT_AI_MODEL,
            "choices": [{"message": {"content": "Analisis uji."}}],
        }).encode("utf-8")
        fake_response.__enter__.return_value = fake_response
        with patch.object(mr.urllib.request, "urlopen", return_value=fake_response) as open_url:
            answer, actual_model = mr.get_openrouter_analysis(
                "secret-test-key", mr.DEFAULT_AI_MODEL, self.crypto, self.macro,
                analysis_type="entry_exit", news=self.news,
            )
        self.assertEqual(answer, "Analisis uji.")
        self.assertEqual(actual_model, mr.DEFAULT_AI_MODEL)
        request = open_url.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["model"], mr.DEFAULT_AI_MODEL)
        self.assertEqual(payload["models"], mr.DEFAULT_AI_FALLBACK_MODELS)
        self.assertEqual(payload["reasoning"], {"enabled": False})
        self.assertGreaterEqual(payload["max_tokens"], 1200)
        self.assertLessEqual(payload["max_tokens"], 1600)
        self.assertIn("ENTRY & EXIT ANALYST", payload["messages"][0]["content"])
        self.assertNotIn("secret-test-key", request.data.decode("utf-8"))


    def test_empty_length_response_retries_through_fixed_general_purpose_model(self):
        primary = MagicMock()
        primary.read.return_value = json.dumps({
            "model": mr.DEFAULT_AI_MODEL,
            "choices": [{"message": {"content": ""}, "finish_reason": "length",
                          "native_finish_reason": "length"}],
            "usage": {"completion_tokens": 2200,
                      "completion_tokens_details": {"reasoning_tokens": 2180}},
        }).encode("utf-8")
        primary.__enter__.return_value = primary
        fallback = MagicMock()
        fallback.read.return_value = json.dumps({
            "model": "example/free-model",
            "choices": [{"message": {"content": "Entry/exit fallback berhasil."}, "finish_reason": "stop"}],
        }).encode("utf-8")
        fallback.__enter__.return_value = fallback
        with patch.object(mr.urllib.request, "urlopen", side_effect=[primary, fallback]) as open_url:
            answer, actual_model = mr.get_openrouter_analysis(
                "secret-test-key", mr.DEFAULT_AI_MODEL, self.crypto, self.macro,
                analysis_type="entry_exit", news=self.news,
            )
        self.assertEqual(answer, "Entry/exit fallback berhasil.")
        self.assertEqual(actual_model, "example/free-model")
        self.assertEqual(open_url.call_count, 2)
        retry_payload = json.loads(open_url.call_args_list[1].args[0].data.decode("utf-8"))
        self.assertEqual(retry_payload["model"], mr.DEFAULT_AI_FALLBACK_MODEL)
        self.assertEqual(retry_payload["models"], [mr.SECONDARY_AI_FALLBACK_MODEL])
        self.assertEqual(retry_payload["reasoning"], {"enabled": False})
        self.assertNotEqual(retry_payload["model"], "openrouter/free")

    def test_empty_response_reports_usage_metadata(self):
        primary = MagicMock()
        primary.read.return_value = json.dumps({
            "model": "example/custom-model",
            "choices": [{"message": {"content": ""}, "finish_reason": "length",
                          "native_finish_reason": "max_tokens"}],
            "usage": {"completion_tokens": 1400,
                      "completion_tokens_details": {"reasoning_tokens": 1397}},
        }).encode("utf-8")
        primary.__enter__.return_value = primary
        with patch.object(mr.urllib.request, "urlopen", return_value=primary):
            with self.assertRaises(RuntimeError) as caught:
                mr.get_openrouter_analysis(
                    "secret-test-key", "example/custom-model", self.crypto, self.macro,
                    analysis_type="market", news=self.news,
                )
        message = str(caught.exception)
        self.assertIn("finish_reason: length", message)
        self.assertIn("native_finish_reason: max_tokens", message)
        self.assertIn("completion_tokens: 1400", message)
        self.assertIn("reasoning_tokens: 1397", message)

    def test_safety_classifier_answer_is_retried_with_general_purpose_model(self):
        classifier = MagicMock()
        classifier.read.return_value = json.dumps({
            "model": "nvidia/nemotron-3.5-content-safety:free",
            "choices": [{"message": {"content": "User Safety: safe"}, "finish_reason": "stop"}],
        }).encode("utf-8")
        classifier.__enter__.return_value = classifier
        fallback = MagicMock()
        fallback.read.return_value = json.dumps({
            "model": mr.DEFAULT_AI_FALLBACK_MODEL,
            "choices": [{"message": {"content": "BTC: tunggu konfirmasi retest."}, "finish_reason": "stop"}],
        }).encode("utf-8")
        fallback.__enter__.return_value = fallback
        with patch.object(mr.urllib.request, "urlopen", side_effect=[classifier, fallback]) as open_url:
            answer, actual_model = mr.get_openrouter_analysis(
                "secret-test-key", mr.DEFAULT_AI_MODEL, self.crypto, self.macro,
                analysis_type="entry_exit", news=self.news,
            )
        self.assertEqual(answer, "BTC: tunggu konfirmasi retest.")
        self.assertEqual(actual_model, mr.DEFAULT_AI_FALLBACK_MODEL)
        self.assertEqual(open_url.call_count, 2)
        retry_payload = json.loads(open_url.call_args_list[1].args[0].data.decode("utf-8"))
        self.assertEqual(retry_payload["model"], mr.DEFAULT_AI_FALLBACK_MODEL)
        self.assertEqual(retry_payload["models"], [mr.SECONDARY_AI_FALLBACK_MODEL])

    def test_safety_classifier_answer_is_not_accepted_even_after_retry(self):
        classifier = MagicMock()
        classifier.read.return_value = json.dumps({
            "model": "nvidia/nemotron-3.5-content-safety:free",
            "choices": [{"message": {"content": "User Safety: safe"}, "finish_reason": "stop"}],
        }).encode("utf-8")
        classifier.__enter__.return_value = classifier
        second_classifier = MagicMock()
        second_classifier.read.return_value = json.dumps({
            "model": "nvidia/nemotron-3.5-content-safety:free",
            "choices": [{"message": {"content": "User Safety: safe"}, "finish_reason": "stop"}],
        }).encode("utf-8")
        second_classifier.__enter__.return_value = second_classifier
        with patch.object(mr.urllib.request, "urlopen", side_effect=[classifier, second_classifier]):
            with self.assertRaisesRegex(RuntimeError, "klasifikasi keselamatan, bukan analisis pasar"):
                mr.get_openrouter_analysis(
                    "secret-test-key", mr.DEFAULT_AI_MODEL, self.crypto, self.macro,
                    analysis_type="entry_exit", news=self.news,
                )

    def test_custom_model_does_not_get_implicit_free_router_fallback(self):
        custom_model = "google/gemma-4-31b-it"
        fake_response = MagicMock()
        fake_response.read.return_value = json.dumps({
            "model": custom_model,
            "choices": [{"message": {"content": "Analisis uji."}}],
        }).encode("utf-8")
        fake_response.__enter__.return_value = fake_response
        with patch.object(mr.urllib.request, "urlopen", return_value=fake_response) as open_url:
            mr.get_openrouter_analysis(
                "secret-test-key", custom_model, self.crypto, self.macro,
                analysis_type="market", news=self.news,
            )
        payload = json.loads(open_url.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(payload["model"], custom_model)
        self.assertNotIn("models", payload)

    def test_market_analyst_request_contains_headlines_and_market_role(self):
        fake_response = MagicMock()
        fake_response.read.return_value = json.dumps({
            "model": mr.DEFAULT_AI_MODEL,
            "choices": [{"message": {"content": "Ringkasan pasar uji."}}],
        }).encode("utf-8")
        fake_response.__enter__.return_value = fake_response
        with patch.object(mr.urllib.request, "urlopen", return_value=fake_response) as open_url:
            answer, _actual_model = mr.get_openrouter_analysis(
                "secret-test-key", mr.DEFAULT_AI_MODEL, self.crypto, self.macro,
                analysis_type="market", news=self.news,
            )
        self.assertEqual(answer, "Ringkasan pasar uji.")
        payload = json.loads(open_url.call_args.args[0].data.decode("utf-8"))
        self.assertIn("MARKET ANALYST", payload["messages"][0]["content"])
        self.assertIn("Markets fell today", payload["messages"][1]["content"])

    def test_http_429_diagnostics_include_provider_metadata_and_retry_after(self):
        error_payload = {
            "error": {
                "code": 429,
                "message": "Provider returned error",
                "metadata": {"provider_name": "Test Provider", "raw": "upstream overloaded"},
            }
        }
        headers = {"Retry-After": "7", "x-request-id": "req-test-123"}
        exc = mr.urllib.error.HTTPError(
            mr.OPENROUTER_URL, 429, "Too Many Requests", headers,
            io.BytesIO(json.dumps(error_payload).encode("utf-8")),
        )
        with patch.object(mr.urllib.request, "urlopen", side_effect=exc):
            with self.assertRaises(RuntimeError) as caught:
                mr.get_openrouter_analysis(
                    "secret-test-key", mr.DEFAULT_AI_MODEL, self.crypto, self.macro,
                    analysis_type="market", news=self.news,
                )
        message = str(caught.exception)
        self.assertIn("provider=Test Provider", message)
        self.assertIn("provider_detail=upstream overloaded", message)
        self.assertIn("Retry-After=7", message)
        self.assertIn("request_id=req-test-123", message)
        self.assertNotIn("secret-test-key", message)

    def test_missing_api_key_is_a_clear_error(self):
        with self.assertRaisesRegex(RuntimeError, "API key belum diatur"):
            mr.get_openrouter_analysis("", mr.DEFAULT_AI_MODEL, self.crypto, self.macro)

    def test_ohlc_parser_discards_unfinished_bars_and_normalizes_milliseconds(self):
        now_ts = 1_800_000_000
        payload = [
            {"Time": (now_ts - 7200) * 1000, "Open": 10, "High": 12, "Low": 9, "Close": 11, "Volume": "100"},
            {"Time": (now_ts - 3600) * 1000, "Open": 11, "High": 13, "Low": 10, "Close": 12, "Volume": "120"},
            {"Time": now_ts, "Open": 12, "High": 14, "Low": 11, "Close": 13, "Volume": "130"},
        ]
        parsed = mr.parse_indodax_ohlc(payload, 60, now_timestamp=now_ts)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["time"], now_ts - 7200)
        self.assertEqual(parsed[1]["close"], 12.0)

    def test_ohlc_parser_handles_no_data_and_rejects_bad_candle(self):
        self.assertEqual(mr.parse_indodax_ohlc({"s": "no_data"}, 60, now_timestamp=100_000), [])
        parsed = mr.parse_indodax_ohlc([
            {"Time": 90_000, "Open": 10, "High": 8, "Low": 9, "Close": 10, "Volume": 1},
        ], 60, now_timestamp=100_000)
        self.assertEqual(parsed, [])

    def test_indodax_ohlc_fetch_uses_pair_symbol_and_closed_bar_history(self):
        now_ts = 1_800_000_000
        body = json.dumps([
            {"Time": now_ts - 7200, "Open": 10, "High": 12, "Low": 9, "Close": 11, "Volume": "100"},
            {"Time": now_ts - 3600, "Open": 11, "High": 13, "Low": 10, "Close": 12, "Volume": "120"},
        ]).encode("utf-8")
        fake_response = MagicMock()
        fake_response.read.return_value = body
        fake_response.__enter__.return_value = fake_response
        with patch.object(mr.time, "time", return_value=now_ts), patch.object(mr.urllib.request, "urlopen", return_value=fake_response) as open_url:
            candles = mr.fetch_indodax_ohlc({"symbol": "BTC", "ohlc_symbol": "BTCIDR"}, 60, 5)
        self.assertEqual(len(candles), 2)
        request = open_url.call_args.args[0]
        self.assertIn("symbol=BTCIDR", request.full_url)
        self.assertIn("tf=60", request.full_url)
        self.assertIn("tradingview/history_v2", request.full_url)

    def test_hourly_to_four_hour_aggregation_requires_four_consecutive_candles(self):
        candles = []
        for i in range(9):
            candles.append({"time": i * 3600, "open": 100 + i, "high": 102 + i,
                            "low": 99 + i, "close": 101 + i, "volume": 10})
        aggregated = mr.aggregate_hourly_to_4h_candles(candles) if hasattr(mr, "aggregate_hourly_to_4h_candles") else mr.aggregate_hourly_to_4h(candles)
        self.assertEqual(len(aggregated), 2)
        self.assertEqual(aggregated[0]["open"], 100)
        self.assertEqual(aggregated[0]["close"], 104)
        self.assertEqual(aggregated[0]["high"], 105)
        self.assertEqual(aggregated[0]["volume"], 40)

    def test_signal_summary_is_compact_and_does_not_repeat_asset_news(self):
        sample = {
            "XRP": {
                "name": "XRP", "volume_idr": 900_000_000,
                "technical_analysis": {
                    "signal": "BUY NOW", "spread_pct": 0.004,
                    "metrics": {"rsi14_1h": 54.2, "volume_ratio_1h": 4.9,
                                "trend_1h": "BULLISH", "trend_4h": "BULLISH"},
                },
                "asset_news": [{"title": "A long unrelated headline"}],
            },
            "BTC": {
                "name": "Bitcoin", "volume_idr": 800_000_000,
                "technical_analysis": {
                    "signal": "WAIT", "spread_pct": 0.06,
                    "metrics": {"rsi14_1h": 49.1, "volume_ratio_1h": 2.27,
                                "trend_1h": "MIXED", "trend_4h": "MIXED"},
                    "reasons": ["Belum semua syarat sinyal terpenuhi."],
                },
            },
        }
        result = mr.format_signal_summary(sample, "OHLC selesai; Asset-news RSS dicoba untuk 5 aset")
        self.assertIn("BUY NOW: 1", result)
        self.assertIn("WAIT: 1", result)
        self.assertIn("XRP", result)
        self.assertNotIn("A long unrelated headline", result)
        self.assertNotIn("| Symbol |", result)

    def test_technical_metrics_calculate_trends_and_indicators(self):
        now_ts = int(mr.time.time())
        start = ((now_ts // 3600) - 130) * 3600
        candles = []
        close = 100.0
        changes = [0.35, 0.25, -0.18, 0.30, -0.12, 0.22, -0.10]
        for i in range(125):
            open_price = close
            close = close + changes[i % len(changes)]
            candles.append({"time": start + i * 3600, "open": open_price,
                            "high": max(open_price, close) + 0.2,
                            "low": min(open_price, close) - 0.2,
                            "close": close, "volume": 100 + (i % 5) * 2})
        # Last bar should already be closed for the current epoch.
        metrics = mr.technical_metrics(candles, now_timestamp=start + 126 * 3600)
        self.assertTrue(metrics["available"])
        self.assertEqual(metrics["candles_1h"], 125)
        self.assertGreaterEqual(metrics["candles_4h"], 22)
        self.assertIn(metrics["trend_1h"], {"BULLISH", "BEARISH", "MIXED"})
        self.assertIsNotNone(metrics["rsi14_1h"])
        self.assertIsNotNone(metrics["atr14_1h"])

    def test_trade_signal_requires_all_buy_checks_and_live_liquidity(self):
        now = mr.now_wib()
        row = {"symbol": "ETH", "price": 100.0, "bid": 99.9, "ask": 100.1,
               "volume_idr": 2_000_000_000, "retrieved_at": now, "market_time": now}
        metrics = {"available": True, "bar_age_minutes": 20, "trend_1h": "BULLISH", "trend_4h": "BULLISH",
                   "rsi14_1h": 58.0, "volume_ratio_1h": 1.5, "extension_atr_1h": 1.2,
                   "last_close_idr": 100.0, "ema21_1h": 98.0, "atr14_1h": 2.0, "atr_pct_1h": 2.0}
        signal = mr.evaluate_trade_signal(row, metrics, now=now)
        self.assertEqual(signal["signal"], "BUY NOW")
        # A bearish BTC 4h regime must suppress an altcoin buy setup.
        self.assertEqual(mr.evaluate_trade_signal(row, metrics, btc_bearish=True, now=now)["signal"], "WAIT")
        # Missing/small liquidity data cannot produce a direct buy/sell action.
        thin = dict(row, volume_idr=100_000_000)
        self.assertEqual(mr.evaluate_trade_signal(thin, metrics, now=now)["signal"], "NO SIGNAL")

    def test_trade_signal_waits_when_live_quote_diverges_from_last_closed_candle(self):
        now = mr.now_wib()
        row = {"symbol": "ETH", "price": 105.0, "bid": 104.9, "ask": 105.1,
               "volume_idr": 2_000_000_000, "retrieved_at": now, "market_time": now}
        metrics = {"available": True, "bar_age_minutes": 20, "trend_1h": "BULLISH", "trend_4h": "BULLISH",
                   "rsi14_1h": 58.0, "volume_ratio_1h": 1.5, "extension_atr_1h": 1.2,
                   "last_close_idr": 100.0, "ema21_1h": 98.0, "atr14_1h": 1.0, "atr_pct_1h": 1.0}
        result = mr.evaluate_trade_signal(row, metrics, now=now)
        self.assertEqual(result["signal"], "WAIT")
        self.assertEqual(result["state"], "quote_candle_divergence")

    def test_trade_signal_requires_bearish_confirmation_before_sell_now(self):
        now = mr.now_wib()
        row = {"symbol": "ETH", "price": 100.0, "bid": 99.9, "ask": 100.1,
               "volume_idr": 2_000_000_000, "retrieved_at": now, "market_time": now}
        metrics = {"available": True, "bar_age_minutes": 20, "trend_1h": "BEARISH", "trend_4h": "BEARISH",
                   "rsi14_1h": 38.0, "volume_ratio_1h": 1.6, "extension_atr_1h": -0.6,
                   "last_close_idr": 100.0, "ema21_1h": 102.0, "atr14_1h": 2.0, "atr_pct_1h": 2.0}
        self.assertEqual(mr.evaluate_trade_signal(row, metrics, now=now)["signal"], "SELL / EXIT NOW")

    def test_entry_exit_snapshot_passes_engine_signal_and_asset_news_to_ai(self):
        crypto = {"BTC": dict(self.crypto["BTC"], technical_analysis={
            "signal": "WAIT", "state": "no_complete_setup", "reasons": ["RSI di luar rentang"],
            "metrics": {"trend_1h": "MIXED", "trend_4h": "BULLISH", "rsi14_1h": 49.0},
        }, asset_news=[{"symbol": "BTC", "title": "Bitcoin network update", "source": "Example", "published_at": "today"}])}
        snapshot = mr.build_ai_snapshot(crypto, self.macro, self.news, "entry_exit")
        btc = snapshot["crypto_top_by_idr_volume"][0]
        self.assertEqual(btc["technical_signal"]["signal"], "WAIT")
        self.assertEqual(btc["asset_news"][0]["title"], "Bitcoin network update")
        self.assertIn("not calibrated win probabilities", snapshot["technical_signal_method"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
