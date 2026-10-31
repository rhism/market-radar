#!/usr/bin/env python3
"""Replay INDODAX 1-minute OHLC candles through Market Radar's anomaly rules.

This is a diagnostic utility, not a predictor. OHLC replay can approximate
close-based price alerts and rolling 24h wick alerts, but cannot reconstruct
30-second ticker snapshots, individual trades, spreads, or historical order books.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from anomaly_radar import MarketAnomalyEngine

BASE_URL = "https://indodax.com"
OHLC_URL = BASE_URL + "/tradingview/history_v2"
HTTP_TIMEOUT = 15
CHUNK_SECONDS = 6 * 60 * 60
WIB = ZoneInfo("Asia/Jakarta")


def _finite(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _epoch(value: Any) -> int | None:
    number = _finite(value)
    if number is None or number <= 0:
        return None
    if number > 10_000_000_000:
        number /= 1000.0
    return int(number)


def parse_local_datetime(value: str) -> datetime:
    """Parse ISO/date-time text; naive input is interpreted as Asia/Jakarta."""
    try:
        parsed = datetime.fromisoformat(value.strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Format tanggal/waktu tidak valid: {value!r}. Gunakan YYYY-MM-DD HH:MM.") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=WIB)
    return parsed.astimezone(WIB)


def parse_ohlc_payload(payload: Any) -> list[dict[str, float | int]]:
    """Normalize documented Indodax list candles or TradingView UDF arrays."""
    rows: Any = payload
    if isinstance(payload, dict):
        status = str(payload.get("s") or "").lower()
        if status == "no_data":
            return []
        if status == "ok" and all(key in payload for key in ("t", "o", "h", "l", "c")):
            count = min(len(payload.get(key) or []) for key in ("t", "o", "h", "l", "c"))
            volumes = payload.get("v") or []
            rows = [
                {
                    "Time": payload["t"][index], "Open": payload["o"][index],
                    "High": payload["h"][index], "Low": payload["l"][index],
                    "Close": payload["c"][index],
                    "Volume": volumes[index] if index < len(volumes) else 0,
                }
                for index in range(count)
            ]
        else:
            raise ValueError("Format OHLC dari Indodax tidak dikenali.")
    if not isinstance(rows, list):
        raise ValueError("Respons OHLC harus berupa daftar candle.")

    output: dict[int, dict[str, float | int]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        stamp = _epoch(row.get("Time", row.get("time", row.get("timestamp", row.get("t")))))
        open_price = _finite(row.get("Open", row.get("open", row.get("o"))))
        high = _finite(row.get("High", row.get("high", row.get("h"))))
        low = _finite(row.get("Low", row.get("low", row.get("l"))))
        close = _finite(row.get("Close", row.get("close", row.get("c"))))
        volume = _finite(row.get("Volume", row.get("volume", row.get("v"))))
        if stamp is None or None in (open_price, high, low, close):
            continue
        if min(open_price, high, low, close) <= 0:
            continue
        if high < max(open_price, close, low) or low > min(open_price, close, high):
            continue
        output[stamp] = {
            "time": stamp, "open": open_price, "high": high,
            "low": low, "close": close, "volume": max(0.0, volume or 0.0),
        }
    return [output[key] for key in sorted(output)]


def _request_candles(symbol: str, start_epoch: int, end_epoch: int) -> list[dict[str, float | int]]:
    query = urllib.parse.urlencode({
        "from": int(start_epoch), "to": int(end_epoch), "symbol": symbol, "tf": "1",
    })
    request = urllib.request.Request(
        OHLC_URL + "?" + query,
        headers={"User-Agent": "MarketRadar-AnomalyReplay/1.0", "Accept": "application/json"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f"Indodax OHLC HTTP {response.status}")
        raw = response.read(5_000_000)
    try:
        payload = json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("Respons OHLC Indodax bukan JSON valid.") from exc
    return parse_ohlc_payload(payload)


def fetch_historical_candles(
    symbol: str,
    start: datetime,
    end: datetime,
    warmup_hours: int = 24,
) -> list[dict[str, float | int]]:
    """Fetch one-minute candles in six-hour chunks with an earlier warm-up window."""
    symbol = re.sub(r"[^A-Za-z0-9]", "", str(symbol or "")).upper()
    if not re.fullmatch(r"[A-Z0-9]{2,28}IDR", symbol):
        raise ValueError("Symbol harus berupa pair IDR, contoh PIEVERSEIDR.")
    start_wib = start.astimezone(WIB) if start.tzinfo else start.replace(tzinfo=WIB)
    end_wib = end.astimezone(WIB) if end.tzinfo else end.replace(tzinfo=WIB)
    if end_wib <= start_wib:
        raise ValueError("Waktu akhir harus lebih besar daripada waktu mulai.")
    if warmup_hours < 0 or warmup_hours > 168:
        raise ValueError("Warm-up harus antara 0 sampai 168 jam.")

    start_epoch = int(start_wib.timestamp()) - warmup_hours * 3600 - 60
    end_epoch = int(end_wib.timestamp())
    chunks: list[dict[str, float | int]] = []
    cursor = start_epoch
    while cursor < end_epoch:
        chunk_end = min(cursor + CHUNK_SECONDS, end_epoch)
        chunks.extend(_request_candles(symbol, cursor, chunk_end))
        cursor = chunk_end
    unique = {int(row["time"]): row for row in chunks}
    return [unique[key] for key in sorted(unique)]


def replay_candles(
    candles: Iterable[dict[str, Any]],
    symbol: str,
    start: datetime,
    end: datetime,
    *,
    warmup_hours: int = 24,
    engine: MarketAnomalyEngine | None = None,
    candle_minutes: int = 1,
) -> dict[str, Any]:
    """Run closed 1m candle snapshots through the exact existing anomaly engine."""
    symbol = re.sub(r"[^A-Za-z0-9]", "", str(symbol or "")).upper()
    if not re.fullmatch(r"[A-Z0-9]{2,28}IDR", symbol):
        raise ValueError("Symbol harus berupa pair IDR, contoh PIEVERSEIDR.")
    if candle_minutes != 1:
        raise ValueError("Replay saat ini hanya mendukung candle 1 menit agar sesuai ambang rapid-move scanner.")
    start_wib = start.astimezone(WIB) if start.tzinfo else start.replace(tzinfo=WIB)
    end_wib = end.astimezone(WIB) if end.tzinfo else end.replace(tzinfo=WIB)
    if end_wib <= start_wib:
        raise ValueError("Waktu akhir harus lebih besar daripada waktu mulai.")
    if warmup_hours < 0 or warmup_hours > 168:
        raise ValueError("Warm-up harus antara 0 sampai 168 jam.")

    normalized = parse_ohlc_payload(list(candles))
    if not normalized:
        raise ValueError("Tidak ada candle OHLC valid untuk diputar ulang.")

    start_epoch = int(start_wib.timestamp())
    end_epoch = int(end_wib.timestamp())
    warmup_epoch = start_epoch - warmup_hours * 3600
    usable = [row for row in normalized if warmup_epoch - 60 <= int(row["time"]) < end_epoch]
    replay_rows = [row for row in usable if start_epoch <= int(row["time"]) < end_epoch]
    if not replay_rows:
        raise ValueError("Tidak ada candle pada rentang waktu replay yang diminta.")

    owned_engine = engine is None
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    if engine is None:
        temp_dir = tempfile.TemporaryDirectory(prefix="market_radar_anomaly_replay_")
        engine = MarketAnomalyEngine(Path(temp_dir.name) / "replay_events.jsonl")

    pair_id = symbol.lower()
    alerts: list[dict[str, Any]] = []
    first_rapid: dict[str, Any] | None = None
    first_wick: dict[str, Any] | None = None
    first_any: dict[str, Any] | None = None
    peak_high = 0.0
    last_close: float | None = None

    try:
        for index, candle in enumerate(usable):
            candle_open = int(candle["time"])
            candle_close = candle_open + 60
            if candle_close > end_epoch:
                continue
            current_time = datetime.fromtimestamp(candle_close, WIB)
            window_start = candle_close - 24 * 3600
            window = [
                item for item in usable
                if window_start <= int(item["time"]) + 60 <= candle_close
            ]
            if not window:
                continue
            high_24h = max(float(item["high"]) for item in window)
            low_24h = min(float(item["low"]) for item in window)
            peak_high = max(peak_high, float(candle["high"]))
            prior = [
                item for item in usable
                if int(item["time"]) + 60 <= window_start
            ]
            previous_price = float(prior[-1]["close"]) if prior else None
            close = float(candle["close"])
            payload = {
                "tickers": {
                    pair_id: {
                        "name": symbol.removesuffix("IDR"),
                        "last": str(close), "high": str(high_24h), "low": str(low_24h),
                        "buy": None, "sell": None, "vol_idr": None,
                        "server_time": str(candle_close),
                    }
                },
                "prices_24h": {pair_id: str(previous_price)} if previous_price else {},
            }
            rows = engine.update_from_payload(payload, now=current_time)
            last_close = close
            if candle_open < start_epoch:
                continue
            peak_high = max(peak_high, float(candle["high"]))
            if not rows:
                continue

            for row in rows:
                item = dict(row)
                item["candle_open_at"] = datetime.fromtimestamp(candle_open, WIB).isoformat()
                item["detected_at"] = current_time.isoformat()
                item["detection_timing"] = "CANDLE_CLOSE_REACTION"
                item["replay_data"] = "INDODAX_1M_OHLC_PROXY"
                alerts.append(item)
                if first_any is None:
                    first_any = item
                flags = set(item.get("flags") or [])
                if first_rapid is None and "RAPID PRICE MOVE" in flags:
                    first_rapid = item
                if first_wick is None and "24H WICK ANOMALY" in flags:
                    first_wick = item
    finally:
        # The temporary event journal is intentionally discarded after replay.
        if owned_engine and temp_dir is not None:
            temp_dir.cleanup()

    severity_rank = {"CRITICAL": 0, "HIGH": 1, "WARNING": 2, "INFO": 3}
    max_severity = min(
        (str(item.get("severity") or "INFO") for item in alerts),
        key=lambda level: severity_rank.get(level, 9),
        default=None,
    )
    report = {
        "symbol": symbol,
        "timeframe": "1m",
        "timezone": "Asia/Jakarta (WIB)",
        "replay_start": start_wib.isoformat(),
        "replay_end": end_wib.isoformat(),
        "warmup_hours": warmup_hours,
        "candles_in_replay": len(replay_rows),
        "candles_with_alerts": len({item["candle_open_at"] for item in alerts}),
        "alert_rows": len(alerts),
        "max_severity": max_severity,
        "first_anomaly_at": first_any.get("detected_at") if first_any else None,
        "first_rapid_move_at": first_rapid.get("detected_at") if first_rapid else None,
        "first_wick_anomaly_at": first_wick.get("detected_at") if first_wick else None,
        "first_detection_timing": first_any.get("detection_timing") if first_any else None,
        "highest_candle_high_idr": peak_high,
        "last_replay_close_idr": last_close,
        "alerts": alerts,
        "limitations": [
            "Replay memakai OHLC 1 menit; alarm hanya dapat dicatat pada penutupan candle, bukan sebelum lonjakan dimulai.",
            "Tidak merekonstruksi snapshot ticker live 30 detik yang dipakai aplikasi.",
            "Spread, trades 5 menit, bid depth, dan ask depth tidak diuji karena tidak tersedia dari OHLC.",
            "Volume candle tidak dipakai sebagai pengganti vol_idr ticker; keduanya bukan metrik yang identik.",
            "Hasil ini menguji ambang deteksi yang ada, bukan kemampuan memprediksi lonjakan.",
        ],
        "interpretation": (
            "Jika alarm muncul pada candle yang memuat lonjakan, scanner bereaksi setelah/ketika candle itu selesai; "
            "itu bukan bukti bahwa sistem memberi peringatan sebelum spike."
        ),
    }
    return report


def _summary_text(report: dict[str, Any]) -> str:
    lines = [
        f"ANOMALY REPLAY · {report['symbol']}",
        f"Rentang: {report['replay_start']} sampai {report['replay_end']}",
        f"Candle replay: {report['candles_in_replay']} · candle dengan alert: {report['candles_with_alerts']}",
        f"Alert pertama: {report['first_anomaly_at'] or 'tidak ada'}",
        f"Rapid move pertama: {report['first_rapid_move_at'] or 'tidak ada'}",
        f"Wick anomaly pertama: {report['first_wick_anomaly_at'] or 'tidak ada'}",
        f"Severity tertinggi: {report['max_severity'] or 'tidak ada'}",
        "",
        "INTERPRETASI",
        str(report["interpretation"]),
        "",
        "BATASAN",
    ]
    lines.extend(f"- {item}" for item in report["limitations"])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Replay aturan Anomaly Radar pada candle 1 menit historis Indodax. Input waktu tanpa zona dianggap WIB."
    )
    parser.add_argument("--symbol", default="PIEVERSEIDR", help="Pair IDR, contoh PIEVERSEIDR")
    parser.add_argument("--start", required=True, help='Waktu mulai WIB, contoh "2026-10-31 06:00"')
    parser.add_argument("--end", required=True, help='Waktu akhir WIB, contoh "2026-10-31 11:00"')
    parser.add_argument("--warmup-hours", type=int, default=24, help="Data pemanasan rolling high 24 jam (default 24)")
    parser.add_argument("--output", default="", help="Lokasi JSON hasil replay (opsional)")
    args = parser.parse_args(argv)

    try:
        start = parse_local_datetime(args.start)
        end = parse_local_datetime(args.end)
        candles = fetch_historical_candles(args.symbol, start, end, args.warmup_hours)
        report = replay_candles(candles, args.symbol, start, end, warmup_hours=args.warmup_hours)
        print(_summary_text(report))
        output = args.output.strip() or f"anomaly_replay_{args.symbol.upper()}_{start:%Y%m%d_%H%M}.json"
        Path(output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nFile laporan: {Path(output).resolve()}")
        return 0
    except Exception as exc:
        print(f"Anomaly Replay gagal: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
