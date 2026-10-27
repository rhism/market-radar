#!/usr/bin/env python3
"""Offline, long-only research backtest for Market Radar v1.9.1.

This is deliberately separate from market_radar.py. It does not change the app or
place orders. Historical OHLC cannot reconstruct historical bid/ask spread, so
results are a technical-strategy proxy, not an exact replay of live app signals.
"""
from __future__ import annotations

import argparse
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

OHLC_URL = "https://indodax.com/tradingview/history_v2"
BAR_SECONDS = 3600
FOUR_HOURS = 4 * BAR_SECONDS
MIN_CANDLES = 100
DEFAULT_SYMBOLS = ("BTC", "ETH", "SOL", "XRP", "SUI", "QNT", "ASTER", "ALT")


@dataclass(frozen=True)
class BacktestConfig:
    initial_capital_idr: float = 10_000_000.0
    fee_bps_per_side: float = 30.0
    slippage_bps_per_side: float = 10.0
    min_estimated_turnover_24h_idr: float = 500_000_000.0
    require_btc_filter: bool = True

    def __post_init__(self) -> None:
        if self.initial_capital_idr <= 0:
            raise ValueError("Initial capital must be positive.")
        if not 0 <= self.fee_bps_per_side <= 1000:
            raise ValueError("Fee bps must be between 0 and 1000.")
        if not 0 <= self.slippage_bps_per_side <= 1000:
            raise ValueError("Slippage bps must be between 0 and 1000.")
        if self.min_estimated_turnover_24h_idr < 0:
            raise ValueError("Turnover threshold cannot be negative.")


def parse_closed_ohlc(payload: Any, now_timestamp: int | None = None) -> list[dict[str, float | int]]:
    """Parse documented Indodax history rows, dedupe timestamps, discard open bars."""
    now_ts = int(time.time() if now_timestamp is None else now_timestamp)
    if not isinstance(payload, list):
        raise ValueError("Unexpected Indodax OHLC payload; expected a list.")
    candles: dict[int, dict[str, float | int]] = {}
    for row in payload:
        if not isinstance(row, dict):
            continue
        try:
            raw_ts = float(row.get("Time", row.get("time", row.get("t"))))
            if raw_ts > 10_000_000_000:
                raw_ts /= 1000
            ts = int(raw_ts)
            o = float(row.get("Open", row.get("open", row.get("o"))))
            h = float(row.get("High", row.get("high", row.get("h"))))
            low = float(row.get("Low", row.get("low", row.get("l"))))
            close = float(row.get("Close", row.get("close", row.get("c"))))
            volume = max(0.0, float(row.get("Volume", row.get("volume", row.get("v", 0))) or 0))
        except (TypeError, ValueError, OverflowError):
            continue
        if ts <= 0 or ts + BAR_SECONDS > now_ts:
            continue
        if min(o, h, low, close) <= 0 or h < max(o, close, low) or low > min(o, close, h):
            continue
        candles[ts] = {"time": ts, "open": o, "high": h, "low": low, "close": close, "volume": volume}
    return [candles[ts] for ts in sorted(candles)]


def fetch_history(symbol: str, days: int = 90, now_timestamp: int | None = None,
                  timeout: float = 15.0) -> list[dict[str, float | int]]:
    """Fetch hourly history in 14-day chunks, merge and dedupe closed candles."""
    symbol = "".join(ch for ch in symbol.upper() if ch.isalnum())
    if not symbol or days < 1 or days > 730:
        raise ValueError("Use a valid symbol and a history window from 1 to 730 days.")
    end = int(time.time() if now_timestamp is None else now_timestamp)
    start = end - days * 86400
    merged: dict[int, dict[str, float | int]] = {}
    chunk_seconds = 14 * 86400
    cursor = start
    while cursor < end:
        chunk_end = min(end, cursor + chunk_seconds)
        query = urllib.parse.urlencode({"from": cursor, "to": chunk_end, "symbol": symbol + "IDR", "tf": "60"})
        request = urllib.request.Request(
            OHLC_URL + "?" + query,
            headers={"User-Agent": "MarketRadar-Backtest/1.0", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read(8_000_000).decode("utf-8", errors="replace"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Indodax OHLC fetch failed for {symbol}: {exc}") from None
        if isinstance(payload, dict) and str(payload.get("s", "")).lower() == "no_data":
            payload = []
        rows = parse_closed_ohlc(payload, now_timestamp=end)
        for candle in rows:
            ts = int(candle["time"])
            if start <= ts < end:
                merged[ts] = candle
        cursor = chunk_end
        time.sleep(0.05)
    return [merged[ts] for ts in sorted(merged)]


def ema(values: list[float], period: int) -> float | None:
    if period < 1 or len(values) < period:
        return None
    current = sum(values[:period]) / period
    alpha = 2 / (period + 1)
    for value in values[period:]:
        current = alpha * value + (1 - alpha) * current
    return current


def rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) <= period:
        return None
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0 if avg_gain else 50.0
    return 100 - 100 / (1 + avg_gain / avg_loss)


def aggregate_4h(candles: list[dict[str, Any]]) -> list[dict[str, float | int]]:
    groups: dict[int, list[dict[str, Any]]] = {}
    for candle in candles:
        ts = int(candle["time"])
        bucket = ts // FOUR_HOURS * FOUR_HOURS
        groups.setdefault(bucket, []).append(candle)
    output = []
    for bucket, group in sorted(groups.items()):
        group = sorted(group, key=lambda item: int(item["time"]))
        if [int(item["time"]) for item in group] != [bucket + i * BAR_SECONDS for i in range(4)]:
            continue
        output.append({"time": bucket, "open": float(group[0]["open"]),
                       "high": max(float(x["high"]) for x in group),
                       "low": min(float(x["low"]) for x in group),
                       "close": float(group[-1]["close"]),
                       "volume": sum(float(x.get("volume") or 0) for x in group)})
    return output


def signal_at(candles: list[dict[str, Any]], index: int,
              btc_candles: list[dict[str, Any]] | None = None,
              config: BacktestConfig | None = None) -> str:
    """Evaluate only information available at this candle's close; execute next bar open."""
    cfg = config or BacktestConfig()
    history = candles[:index + 1]
    four = aggregate_4h(history)
    if len(history) < 35 or len(four) < 22:
        return "WAIT"
    closes = [float(c["close"]) for c in history]
    closes4 = [float(c["close"]) for c in four]
    ema9, ema21 = ema(closes, 9), ema(closes, 21)
    ema9_4, ema21_4 = ema(closes4, 9), ema(closes4, 21)
    last = history[-1]
    close = float(last["close"])
    trend1 = "BULLISH" if ema9 is not None and ema21 is not None and close > ema9 > ema21 else (
        "BEARISH" if ema9 is not None and ema21 is not None and close < ema9 < ema21 else "MIXED")
    last4 = four[-1]
    close4 = float(last4["close"])
    trend4 = "BULLISH" if ema9_4 is not None and ema21_4 is not None and close4 > ema9_4 > ema21_4 else (
        "BEARISH" if ema9_4 is not None and ema21_4 is not None and close4 < ema9_4 < ema21_4 else "MIXED")
    rsi1 = rsi(closes, 14)
    trs = []
    for j, candle in enumerate(history):
        previous = float(history[j - 1]["close"]) if j else float(candle["close"])
        trs.append(max(float(candle["high"]) - float(candle["low"]),
                       abs(float(candle["high"]) - previous), abs(float(candle["low"]) - previous)))
    atr = sum(trs[-14:]) / 14 if len(trs) >= 14 else None
    ema_extension = (close - ema21) / atr if atr and atr > 0 and ema21 is not None else None
    prior_volumes = [float(c.get("volume") or 0) for c in history[-21:-1]]
    avg_volume = sum(prior_volumes) / len(prior_volumes) if prior_volumes else 0
    vol_ratio = float(last.get("volume") or 0) / avg_volume if avg_volume > 0 else None
    # OHLC volume is the exchange's chart volume. Estimate IDR turnover only; spread
    # history is unavailable, so the live spread gate cannot be reproduced here.
    turnover_24h = sum(float(c.get("volume") or 0) * float(c["close"]) for c in history[-24:])
    if turnover_24h < cfg.min_estimated_turnover_24h_idr:
        return "WAIT"
    if cfg.require_btc_filter and btc_candles is not None and candles is not btc_candles:
        btc_index = min(index, len(btc_candles) - 1)
        btc_history = btc_candles[:btc_index + 1]
        btc4 = aggregate_4h(btc_history)
        if len(btc_history) < 35 or len(btc4) < 22:
            return "WAIT"
        btc_closes4 = [float(c["close"]) for c in btc4]
        b9, b21 = ema(btc_closes4, 9), ema(btc_closes4, 21)
        btc_last = float(btc4[-1]["close"])
        btc_trend = "BULLISH" if b9 is not None and b21 is not None and btc_last > b9 > b21 else (
            "BEARISH" if b9 is not None and b21 is not None and btc_last < b9 < b21 else "MIXED")
        if btc_trend not in {"BULLISH", "MIXED"}:
            return "WAIT"
    buy = (trend1 == "BULLISH" and trend4 == "BULLISH" and close > (ema21 or math.inf)
           and rsi1 is not None and 52 <= rsi1 <= 68
           and vol_ratio is not None and vol_ratio >= 1.2
           and ema_extension is not None and 0 <= ema_extension <= 1.8)
    sell = (trend1 == "BEARISH" and trend4 == "BEARISH" and close < (ema21 or -math.inf)
            and rsi1 is not None and rsi1 <= 42
            and vol_ratio is not None and vol_ratio >= 1.2)
    if buy:
        return "BUY"
    if sell:
        return "SELL"
    return "WAIT"


def backtest_symbol(symbol: str, candles: list[dict[str, Any]], config: BacktestConfig | None = None,
                    btc_candles: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """One-position-at-a-time long-only simulation; signal at close, fill next open."""
    cfg = config or BacktestConfig()
    candles = sorted(candles, key=lambda item: int(item["time"]))
    if len(candles) < MIN_CANDLES:
        raise ValueError(f"{symbol}: only {len(candles)} candles; need at least {MIN_CANDLES}.")
    fee = cfg.fee_bps_per_side / 10_000
    slip = cfg.slippage_bps_per_side / 10_000
    cash = cfg.initial_capital_idr
    quantity = 0.0
    entry_price = 0.0
    entry_time = 0
    entry_cash = 0.0
    trades: list[dict[str, Any]] = []
    equity_curve: list[float] = [cash]
    for i in range(len(candles) - 1):
        signal = signal_at(candles, i, btc_candles=btc_candles, config=cfg)
        next_bar = candles[i + 1]
        if quantity == 0 and signal == "BUY":
            fill = float(next_bar["open"]) * (1 + slip)
            quantity = cash * (1 - fee) / fill
            entry_price, entry_time, entry_cash = fill, int(next_bar["time"]), cash
            cash = 0.0
        elif quantity > 0 and signal == "SELL":
            fill = float(next_bar["open"]) * (1 - slip)
            proceeds = quantity * fill * (1 - fee)
            pnl = proceeds - entry_cash
            trades.append({"symbol": symbol, "entry_time": entry_time, "exit_time": int(next_bar["time"]),
                           "entry_price": round(entry_price, 8), "exit_price": round(fill, 8),
                           "pnl_idr": round(pnl, 2), "return_pct": round(pnl / entry_cash * 100, 4),
                           "exit_reason": "SELL signal"})
            cash, quantity = proceeds, 0.0
        mark = cash if quantity == 0 else quantity * float(next_bar["close"])
        equity_curve.append(mark)
    if quantity > 0:
        last = candles[-1]
        fill = float(last["close"]) * (1 - slip)
        proceeds = quantity * fill * (1 - fee)
        pnl = proceeds - entry_cash
        trades.append({"symbol": symbol, "entry_time": entry_time, "exit_time": int(last["time"]),
                       "entry_price": round(entry_price, 8), "exit_price": round(fill, 8),
                       "pnl_idr": round(pnl, 2), "return_pct": round(pnl / entry_cash * 100, 4),
                       "exit_reason": "End of data (forced close)"})
        cash, quantity = proceeds, 0.0
        equity_curve.append(cash)
    total_pnl = cash - cfg.initial_capital_idr
    wins = [t for t in trades if t["pnl_idr"] > 0]
    losses = [t for t in trades if t["pnl_idr"] < 0]
    gross_profit = sum(t["pnl_idr"] for t in wins)
    gross_loss = abs(sum(t["pnl_idr"] for t in losses))
    peak = -math.inf
    max_drawdown = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - value) / peak)
    return {
        "symbol": symbol, "candles": len(candles),
        "start_utc": datetime.fromtimestamp(int(candles[0]["time"]), timezone.utc).isoformat(),
        "end_utc": datetime.fromtimestamp(int(candles[-1]["time"]), timezone.utc).isoformat(),
        "initial_capital_idr": round(cfg.initial_capital_idr, 2),
        "final_equity_idr": round(cash, 2), "net_profit_idr": round(total_pnl, 2),
        "net_return_pct": round(total_pnl / cfg.initial_capital_idr * 100, 4),
        "trades": len(trades), "win_rate_pct": round(len(wins) / len(trades) * 100, 2) if trades else 0.0,
        "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss else (None if not gross_profit else "infinite"),
        "max_drawdown_pct": round(max_drawdown * 100, 4), "fee_bps_per_side": cfg.fee_bps_per_side,
        "slippage_bps_per_side": cfg.slippage_bps_per_side,
        "limitations": ["Technical-rule proxy, not an exact replay of live signals.",
                        "Historical bid/ask spread is unavailable and therefore not simulated.",
                        "24h IDR turnover is estimated from candle volume times close; validate volume units.",
                        "Results are historical and do not predict future returns."],
        "trade_log": trades,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Market Radar historical OHLC backtest (research only).")
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS), help="Comma-separated IDR-pair symbols.")
    parser.add_argument("--days", type=int, default=90, help="History window, 1-730 days (default: 90).")
    parser.add_argument("--capital", type=float, default=10_000_000, help="Starting IDR per asset.")
    parser.add_argument("--fee-bps", type=float, default=30, help="Estimated fee per side in basis points.")
    parser.add_argument("--slippage-bps", type=float, default=10, help="Estimated slippage per side in basis points.")
    parser.add_argument("--output", default="backtest_results.json", help="Output JSON path.")
    args = parser.parse_args()
    cfg = BacktestConfig(args.capital, args.fee_bps, args.slippage_bps)
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    all_candles: dict[str, list[dict[str, Any]]] = {}
    errors: dict[str, str] = {}
    for symbol in symbols:
        try:
            candles = fetch_history(symbol, args.days)
            if len(candles) < MIN_CANDLES:
                errors[symbol] = f"Insufficient history: {len(candles)} candles."
            else:
                all_candles[symbol] = candles
        except Exception as exc:
            errors[symbol] = str(exc)
    btc = all_candles.get("BTC")
    results = []
    for symbol, candles in all_candles.items():
        try:
            results.append(backtest_symbol(symbol, candles, cfg, btc_candles=btc if symbol != "BTC" else None))
        except Exception as exc:
            errors[symbol] = str(exc)
    report = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "history_days_requested": args.days,
              "config": asdict(cfg), "results": results, "errors": errors,
              "warning": "Research only. Do not use as a live trading recommendation."}
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
    print(json.dumps({"output": args.output, "symbols_completed": len(results), "errors": errors,
                      "summary": [{k: r[k] for k in ("symbol", "candles", "net_profit_idr", "net_return_pct",
                                                       "trades", "win_rate_pct", "profit_factor", "max_drawdown_pct")}
                                  for r in results]}, indent=2, ensure_ascii=False))
    return 0 if results else 1


if __name__ == "__main__":
    raise SystemExit(main())
