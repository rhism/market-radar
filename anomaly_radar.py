"""INDODAX all-IDR-pair anomaly scanner using public market data only.

The scanner records local ticker snapshots and detects unusual 24h wicks,
rapid price moves, ticker-volume acceleration, and wide spreads. For the small
set of active anomalies it periodically checks public trades and order-book
quotes. It never reads account data or submits orders.
"""
from __future__ import annotations

import json
import math
import os
import re
import time
import urllib.parse
import urllib.request
from collections import defaultdict, deque
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

APP_VERSION = "1.13.1"
BASE_URL = "https://indodax.com"
SUMMARY_URL = BASE_URL + "/api/summaries"
SCAN_INTERVAL_SECONDS = 30
HTTP_TIMEOUT = 8
MAX_HISTORY_POINTS = 40
MAX_EVENT_ROWS = 500
DETAIL_FETCH_COOLDOWN_SECONDS = 180
EVENT_LOG_COOLDOWN_SECONDS = 1800
WIB = timezone(timedelta(hours=7), name="WIB")


def finite_number(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _normalise(value: Any) -> str:
    return "".join(char for char in str(value or "").lower() if char.isalnum())


def _symbol_from_pair(pair_id: Any) -> str | None:
    value = _normalise(pair_id)
    if not value.endswith("idr") or len(value) <= 3:
        return None
    return value[:-3].upper()


def _epoch_seconds(value: Any) -> float | None:
    timestamp = finite_number(value)
    if timestamp is None or timestamp <= 0:
        return None
    return timestamp / 1000.0 if timestamp > 10_000_000_000 else timestamp


def _default_history_path() -> Path:
    root = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    base = Path(root) if root else Path.home() / ".local" / "share"
    return base / "MarketRadar" / "anomaly_events.jsonl"


def _request_json(url: str) -> Any:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": f"MarketRadar/{APP_VERSION}", "Accept": "application/json"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f"HTTP {response.status}")
        payload = response.read(3_000_000)
    return json.loads(payload.decode("utf-8", errors="replace"))


def filter_anomaly_rows(
    rows: list[dict[str, Any]],
    query: str = "",
    severity: str = "All severities",
    detection: str = "All detections",
) -> list[dict[str, Any]]:
    """Filter active anomaly rows by a free-text query, severity, and detection flag."""
    needle = _normalise(query)
    severity_key = str(severity or "All severities").strip().upper()
    detection_key = str(detection or "All detections").strip().upper()
    output: list[dict[str, Any]] = []
    for row in rows:
        if severity_key not in {"", "ALL", "ALL SEVERITIES"} and str(row.get("severity") or "").upper() != severity_key:
            continue
        flags = [str(item).upper() for item in (row.get("flags") or [])]
        if detection_key not in {"", "ALL", "ALL DETECTIONS"} and detection_key not in flags:
            continue
        haystack = _normalise(" ".join([
            str(row.get("symbol") or ""), str(row.get("name") or ""),
            str(row.get("pair_id") or ""), " ".join(flags),
            " ".join(str(item) for item in (row.get("evidence") or [])),
        ]))
        if needle and needle not in haystack:
            continue
        output.append(row)
    return output


def sort_anomaly_rows(
    rows: list[dict[str, Any]], sort_key: str = "severity", reverse: bool = False,
) -> list[dict[str, Any]]:
    """Sort anomaly rows while keeping missing values at the bottom in either direction."""
    severity_rank = {"CRITICAL": 0, "HIGH": 1, "WARNING": 2, "INFO": 3}

    def value(row: dict[str, Any]) -> Any:
        if sort_key == "asset":
            return _normalise(f"{row.get('symbol') or ''} {row.get('name') or ''}")
        if sort_key == "severity":
            return severity_rank.get(str(row.get("severity") or "").upper())
        if sort_key == "flags":
            return " · ".join(str(item) for item in (row.get("flags") or [])).casefold()
        if sort_key == "price":
            return finite_number(row.get("price"))
        if sort_key == "move1":
            return finite_number(row.get("change_1m_pct"))
        if sort_key == "move5":
            return finite_number(row.get("change_5m_pct"))
        if sort_key == "wick":
            return finite_number(row.get("wick_from_high_pct"))
        if sort_key == "spread":
            return finite_number(row.get("spread_pct"))
        if sort_key == "vol24":
            return finite_number(row.get("volume_24h_idr"))
        if sort_key == "trades":
            return finite_number(row.get("trade_count_5m"))
        if sort_key == "book":
            return finite_number(row.get("bid_depth_1pct_idr"))
        return None

    available = [row for row in rows if value(row) is not None]
    missing = [row for row in rows if value(row) is None]
    available.sort(key=value, reverse=bool(reverse))
    return available + missing


def calculate_trade_metrics(trades: Any, now_timestamp: float | None = None) -> dict[str, Any]:
    """Summarise recent public prints; API timestamps may be seconds or ms."""
    now_value = time.time() if now_timestamp is None else float(now_timestamp)
    recent: list[tuple[float, float, float, str]] = []
    if isinstance(trades, list):
        for trade in trades:
            if not isinstance(trade, dict):
                continue
            stamp = _epoch_seconds(trade.get("date", trade.get("timestamp", trade.get("time"))))
            price = finite_number(trade.get("price"))
            amount = finite_number(trade.get("amount"))
            if stamp is None or price is None or amount is None or price <= 0 or amount <= 0:
                continue
            if 0 <= now_value - stamp <= 300:
                recent.append((stamp, price, amount, str(trade.get("type") or "").lower()))
    buy_value = sum(price * amount for _, price, amount, side in recent if side == "buy")
    sell_value = sum(price * amount for _, price, amount, side in recent if side == "sell")
    total = buy_value + sell_value
    return {
        "trade_count_5m": len(recent),
        "trade_notional_5m_idr": sum(price * amount for _, price, amount, _ in recent),
        "buy_notional_5m_idr": buy_value,
        "sell_notional_5m_idr": sell_value,
        "buy_ratio_5m": buy_value / total if total > 0 else None,
        "largest_trade_5m_idr": max((price * amount for _, price, amount, _ in recent), default=0.0),
    }


def calculate_depth_metrics(depth: Any) -> dict[str, Any]:
    """Compute spread and near-touch IDR depth from the public order book."""
    if not isinstance(depth, dict):
        return {"book_status": "UNAVAILABLE"}

    def levels(side: Any) -> list[tuple[float, float]]:
        output: list[tuple[float, float]] = []
        if not isinstance(side, list):
            return output
        for item in side:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            price, amount = finite_number(item[0]), finite_number(item[1])
            if price is not None and amount is not None and price > 0 and amount > 0:
                output.append((price, amount))
        return output

    bids = sorted(levels(depth.get("buy")), key=lambda item: item[0], reverse=True)
    asks = sorted(levels(depth.get("sell")), key=lambda item: item[0])
    if not bids or not asks:
        return {"book_status": "INCOMPLETE"}
    best_bid, best_ask = bids[0][0], asks[0][0]
    mid = (best_bid + best_ask) / 2
    spread_pct = (best_ask - best_bid) / mid * 100 if mid > 0 else None
    bid_depth = sum(price * amount for price, amount in bids if price >= best_bid * 0.99)
    ask_depth = sum(price * amount for price, amount in asks if price <= best_ask * 1.01)
    total_depth = bid_depth + ask_depth
    return {
        "book_status": "AVAILABLE",
        "book_bid": best_bid,
        "book_ask": best_ask,
        "book_spread_pct": spread_pct,
        "bid_depth_1pct_idr": bid_depth,
        "ask_depth_1pct_idr": ask_depth,
        "book_imbalance": bid_depth / total_depth if total_depth > 0 else None,
    }


class MarketAnomalyEngine:
    """Rolling market-wide anomaly detector with a small local event journal."""

    def __init__(self, history_path: str | Path | None = None) -> None:
        self.history_path = Path(history_path) if history_path else _default_history_path()
        self.price_history: dict[str, deque[dict[str, float | None]]] = defaultdict(
            lambda: deque(maxlen=MAX_HISTORY_POINTS)
        )
        self.active_alerts: list[dict[str, Any]] = []
        self.event_history = self._load_event_history()
        self._last_logged: dict[str, float] = {}
        for event in self.event_history:
            key = f"{event.get('symbol')}|{event.get('anomaly_type')}"
            stamp = _epoch_seconds(event.get("timestamp_epoch"))
            if stamp is not None:
                self._last_logged[key] = max(self._last_logged.get(key, 0.0), stamp)
        self._last_detail_fetch: dict[str, float] = {}
        self.last_scan_at: datetime | None = None
        self.last_error: str | None = None

    @staticmethod
    def fetch_summary_payload() -> Any:
        """Fetch one all-pairs public ticker summary (no private key required)."""
        return _request_json(SUMMARY_URL)

    def _load_event_history(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        try:
            with self.history_path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        item = json.loads(line)
                        if isinstance(item, dict) and item.get("symbol"):
                            events.append(item)
                    except (json.JSONDecodeError, TypeError):
                        continue
        except (OSError, UnicodeError):
            pass
        return events[-MAX_EVENT_ROWS:]

    def _record_event(self, row: dict[str, Any], anomaly_type: str, now_value: float) -> None:
        key = f"{row['symbol']}|{anomaly_type}"
        previous = self._last_logged.get(key, 0.0)
        if now_value - previous < EVENT_LOG_COOLDOWN_SECONDS:
            return
        self._last_logged[key] = now_value
        event = {
            "timestamp_epoch": now_value,
            "detected_at": datetime.fromtimestamp(now_value, WIB).strftime("%Y-%m-%d %H:%M:%S WIB"),
            "symbol": row.get("symbol"),
            "name": row.get("name"),
            "pair_id": row.get("pair_id"),
            "anomaly_type": anomaly_type,
            "severity": row.get("severity"),
            "price": row.get("price"),
            "change_1m_pct": row.get("change_1m_pct"),
            "change_5m_pct": row.get("change_5m_pct"),
            "change_15m_pct": row.get("change_15m_pct"),
            "wick_from_high_pct": row.get("wick_from_high_pct"),
            "spread_pct": row.get("spread_pct"),
            "volume_24h_idr": row.get("volume_24h_idr"),
            "evidence": row.get("evidence", []),
        }
        self.event_history.append(event)
        self.event_history = self.event_history[-MAX_EVENT_ROWS:]
        try:
            self.history_path.parent.mkdir(parents=True, exist_ok=True)
            with self.history_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n")
            # Keep the local journal bounded over long-running desktop sessions.
            if self.history_path.stat().st_size > 1_000_000:
                lines = self.history_path.read_text(encoding="utf-8").splitlines()[-MAX_EVENT_ROWS:]
                self.history_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        except (OSError, TypeError, ValueError):
            # A read-only profile must not stop the live scan.
            pass

    @staticmethod
    def _window_value(points: deque, now_value: float, seconds: int) -> float | None:
        target = now_value - seconds
        tolerance = max(35.0, seconds * 0.18)
        eligible = [point for point in points if point["timestamp"] <= target + 10]
        if not eligible:
            return None
        point = max(eligible, key=lambda item: item["timestamp"])
        if target - point["timestamp"] > tolerance:
            return None
        value = finite_number(point.get("price"))
        return value if value is not None and value > 0 else None

    @staticmethod
    def _severity(flags: list[str], wick_pct: float | None, rapid_move: float | None, spread_pct: float | None) -> str:
        if wick_pct is not None and wick_pct >= 1000:
            return "CRITICAL"
        if wick_pct is not None and wick_pct >= 200:
            return "HIGH"
        if rapid_move is not None and abs(rapid_move) >= 15:
            return "HIGH"
        if spread_pct is not None and spread_pct >= 5:
            return "HIGH"
        if flags:
            return "WARNING"
        return "INFO"

    def update_from_payload(
        self,
        payload: Any,
        pair_lookup: dict[str, dict[str, Any]] | None = None,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Consume one /api/summaries response and return current anomaly rows."""
        if not isinstance(payload, dict) or not isinstance(payload.get("tickers"), dict):
            raise ValueError("Respons summaries INDODAX tidak berisi objek 'tickers'.")
        now_dt = now or datetime.now(WIB)
        now_value = now_dt.timestamp()
        lookup = pair_lookup or {}
        prices_24h = payload.get("prices_24h")
        if not isinstance(prices_24h, dict):
            prices_24h = {}
        current_alerts: list[dict[str, Any]] = []

        for ticker_key, ticker in payload["tickers"].items():
            if not isinstance(ticker, dict):
                continue
            symbol = _symbol_from_pair(ticker_key)
            if not symbol:
                continue  # Ignore BTC/USDT and other non-IDR pairs.
            meta = lookup.get(symbol, {}) if isinstance(lookup, dict) else {}
            pair_id = str(meta.get("pair_id") or (symbol.lower() + "idr"))
            if not re.fullmatch(r"[A-Za-z0-9_-]{3,40}", pair_id):
                pair_id = symbol.lower() + "idr"
            name = str(ticker.get("name") or meta.get("name") or symbol)
            price = finite_number(ticker.get("last"))
            if price is None or price <= 0:
                continue
            high = finite_number(ticker.get("high"))
            low = finite_number(ticker.get("low"))
            bid = finite_number(ticker.get("buy"))
            ask = finite_number(ticker.get("sell"))
            volume = finite_number(ticker.get("vol_idr"))
            exchange_time = _epoch_seconds(ticker.get("server_time"))
            quote_age = max(0.0, now_value - exchange_time) if exchange_time is not None else None
            # Ignore stale ticker rows; stale highs can otherwise look like fresh anomalies.
            if quote_age is not None and quote_age > 300:
                continue
            previous_price = finite_number(prices_24h.get(_normalise(ticker_key)))
            if previous_price is None:
                previous_price = finite_number(prices_24h.get(_normalise(ticker_key).replace("_", "")))
            change_24h = (price / previous_price - 1) * 100 if previous_price and previous_price > 0 else None
            spread_pct = ((ask - bid) / ((ask + bid) / 2) * 100) if bid and ask and bid > 0 and ask >= bid else None

            points = self.price_history[symbol]
            points.append({"timestamp": now_value, "price": price, "volume": volume})
            old_1m = self._window_value(points, now_value, 60)
            old_5m = self._window_value(points, now_value, 300)
            old_15m = self._window_value(points, now_value, 900)
            move_1m = (price / old_1m - 1) * 100 if old_1m else None
            move_5m = (price / old_5m - 1) * 100 if old_5m else None
            move_15m = (price / old_15m - 1) * 100 if old_15m else None
            volume_5m = None
            if len(points) >= 2 and points[0].get("volume") is not None:
                candidate = self._window_value(points, now_value, 300)
                old_point = next((point for point in reversed(points) if point["timestamp"] <= now_value - 300 + 10), None)
                if (old_point and now_value - old_point["timestamp"] <= 355
                        and old_point.get("volume") is not None and volume is not None):
                    delta = volume - float(old_point["volume"])
                    volume_5m = delta if delta >= 0 else None

            wick_pct = (high / price - 1) * 100 if high is not None and high >= price * 1.25 else None
            rapid_candidates = [value for value in (move_1m, move_5m, move_15m) if value is not None]
            rapid_move = max(rapid_candidates, key=abs) if rapid_candidates else None
            flags: list[str] = []
            evidence: list[str] = []

            if wick_pct is not None and wick_pct >= 25:
                flags.append("24H WICK ANOMALY")
                evidence.append(f"High 24j {high:,.8g} vs last {price:,.8g} ({wick_pct:+.1f}% dari harga terakhir).")
            if ((move_1m is not None and abs(move_1m) >= 2.0)
                    or (move_5m is not None and abs(move_5m) >= 4.0)
                    or (move_15m is not None and abs(move_15m) >= 8.0)):
                flags.append("RAPID PRICE MOVE")
                window_text = f"1m {move_1m:+.2f}%" if move_1m is not None else "1m n/a"
                window_text += f" · 5m {move_5m:+.2f}%" if move_5m is not None else " · 5m n/a"
                window_text += f" · 15m {move_15m:+.2f}%" if move_15m is not None else " · 15m n/a"
                evidence.append("Perubahan harga snapshot: " + window_text + ".")
            if spread_pct is not None and spread_pct >= 2.5:
                flags.append("WIDE SPREAD")
                evidence.append(f"Spread bid/ask sekitar {spread_pct:.2f}%.")
            if volume_5m is not None and volume_5m >= 20_000_000:
                flags.append("VOLUME ACCELERATION")
                evidence.append(f"Kenaikan ticker vol_idr 5m sekitar Rp{volume_5m:,.0f}; proxy rolling 24 jam, bukan hitungan trade terverifikasi.")

            if not flags:
                continue
            severity = self._severity(flags, wick_pct, rapid_move, spread_pct)
            row = {
                "symbol": symbol, "name": name, "pair_id": pair_id,
                "severity": severity, "flags": flags, "evidence": evidence,
                "price": price, "high_24h": high, "low_24h": low,
                "change_24h_pct": change_24h,
                "change_1m_pct": move_1m, "change_5m_pct": move_5m, "change_15m_pct": move_15m,
                "wick_from_high_pct": wick_pct, "spread_pct": spread_pct,
                "volume_24h_idr": volume, "volume_delta_5m_idr": volume_5m,
                "trade_count_5m": None, "trade_notional_5m_idr": None,
                "buy_ratio_5m": None, "bid_depth_1pct_idr": None,
                "ask_depth_1pct_idr": None, "book_imbalance": None,
                "quote_at": now_dt.strftime("%Y-%m-%d %H:%M:%S WIB"),
                "quote_age_seconds": quote_age,
                "timestamp_epoch": now_value,
            }
            for anomaly_type in flags:
                self._record_event(row, anomaly_type, now_value)
            current_alerts.append(row)

        severity_rank = {"CRITICAL": 0, "HIGH": 1, "WARNING": 2, "INFO": 3}
        current_alerts.sort(key=lambda item: (severity_rank.get(item["severity"], 9),
                                              -(item.get("wick_from_high_pct") or 0),
                                              -abs(item.get("change_5m_pct") or 0),
                                              -float(item.get("volume_24h_idr") or 0)))
        self.active_alerts = current_alerts
        self.last_scan_at = now_dt
        self.last_error = None
        return current_alerts

    def enrich_active_alerts(self, max_pairs: int = 3, now_timestamp: float | None = None) -> None:
        """Check public recent trades and depth for a few active anomalies only."""
        now_value = time.time() if now_timestamp is None else float(now_timestamp)
        enriched = 0
        for row in self.active_alerts:
            symbol = str(row.get("symbol") or "")
            if not symbol or enriched >= max_pairs:
                break
            if now_value - self._last_detail_fetch.get(symbol, 0.0) < DETAIL_FETCH_COOLDOWN_SECONDS:
                continue
            self._last_detail_fetch[symbol] = now_value
            pair_id = urllib.parse.quote(str(row.get("pair_id") or ""), safe="_-")
            if not pair_id:
                continue
            enriched += 1
            try:
                trades = _request_json(f"{BASE_URL}/api/trades/{pair_id}")
                row.update(calculate_trade_metrics(trades, now_value))
            except Exception as exc:
                row["trades_error"] = f"{type(exc).__name__}: {str(exc)[:100]}"
            try:
                depth = _request_json(f"{BASE_URL}/api/depth/{pair_id}")
                row.update(calculate_depth_metrics(depth))
            except Exception as exc:
                row["book_status"] = "ERROR"
                row["book_error"] = f"{type(exc).__name__}: {str(exc)[:100]}"

    def get_history(self, limit: int = 200) -> list[dict[str, Any]]:
        return list(reversed(self.event_history[-max(1, min(limit, MAX_EVENT_ROWS)):]))

    def status_text(self) -> str:
        if self.last_error:
            return f"Anomaly scan gagal: {self.last_error}"
        stamp = self.last_scan_at.strftime("%H:%M:%S WIB") if self.last_scan_at else "belum ada scan"
        return f"Anomaly scan {stamp} · {len(self.active_alerts)} pair terdeteksi · interval {SCAN_INTERVAL_SECONDS} detik"
