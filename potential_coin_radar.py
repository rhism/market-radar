"""Source-grounded research helpers for Market Radar's Potential Coin Radar.

This module deliberately does not import market_radar.py so the source-matching
and data-normalization logic can be tested without loading the desktop UI.
CoinPaprika's keyless tier requires personal/non-commercial use and attribution.
"""
from __future__ import annotations

import concurrent.futures
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

COINPAPRIKA_BASE_URL = "https://api.coinpaprika.com/v1"
COINPAPRIKA_CREDIT = "Powered by CoinPaprika"
DEFILLAMA_PROTOCOLS_URL = "https://api.llama.fi/protocols"
DEFILLAMA_REVENUE_URL = "https://api.llama.fi/overview/fees?excludeTotalDataChart=true&excludeTotalDataChartBreakdown=true&dataType=dailyRevenue"
POTENTIAL_RADAR_SCAN_LIMIT = 36
POTENTIAL_RADAR_PROFILE_LIMIT = 8
POTENTIAL_RADAR_GITHUB_LIMIT = 3
POTENTIAL_RADAR_NEWS_LIMIT = 5

_CACHE_LOCK = threading.Lock()
_CACHE: dict[str, Any] = {
    "coinpaprika_at": 0.0,
    "coinpaprika_data": None,
    "coinpaprika_error": None,
    "defillama_at": 0.0,
    "defillama_data": None,
    "defillama_error": None,
    "defillama_fees_at": 0.0,
    "defillama_fees_data": None,
    "defillama_fees_error": None,
}


def research_http_json(
    url: str,
    timeout: float = 10.0,
    max_bytes: int = 15_000_000,
    api_kind: str = "research",
) -> Any:
    """Read bounded JSON from a documented public research endpoint."""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "MarketRadar/1.12.0 (personal research dashboard)",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(max_bytes + 1)
            if len(raw) > max_bytes:
                raise RuntimeError(f"Respons {api_kind} melampaui batas ukuran {max_bytes} byte.")
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(f"HTTP {response.status}")
        return json.loads(raw.decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} dari {api_kind}") from None
    except (TimeoutError, urllib.error.URLError) as exc:
        raise RuntimeError(f"Koneksi {api_kind} gagal: {str(exc)[:120]}") from None
    except json.JSONDecodeError:
        raise RuntimeError(f"Respons {api_kind} bukan JSON valid.") from None


def clear_research_cache() -> None:
    """Test helper: reset provider index cache without making network requests."""
    with _CACHE_LOCK:
        _CACHE.update({
            "coinpaprika_at": 0.0,
            "coinpaprika_data": None,
            "coinpaprika_error": None,
            "defillama_at": 0.0,
            "defillama_data": None,
            "defillama_error": None,
            "defillama_fees_at": 0.0,
            "defillama_fees_data": None,
            "defillama_fees_error": None,
        })


def _get_cached_index(
    provider: str, url: str, ttl_seconds: int = 900, list_key: str | None = None,
) -> tuple[list[dict[str, Any]] | None, str | None]:
    key = {
        "CoinPaprika": "coinpaprika",
        "DeFiLlama": "defillama",
        "DeFiLlama daily revenue": "defillama_fees",
    }.get(provider)
    if key is None:
        raise ValueError(f"Provider cache tidak dikenal: {provider}")
    with _CACHE_LOCK:
        now_mono = time.monotonic()
        cached = _CACHE.get(f"{key}_data")
        cached_error = _CACHE.get(f"{key}_error")
        fetched_at = float(_CACHE.get(f"{key}_at") or 0.0)
        if cached is not None and now_mono - fetched_at < ttl_seconds:
            return cached, None
        if cached is None and cached_error and now_mono - fetched_at < 60:
            return None, str(cached_error)
        try:
            payload = research_http_json(url, timeout=14, max_bytes=25_000_000, api_kind=provider)
            if list_key is not None:
                if not isinstance(payload, dict):
                    raise RuntimeError(f"Format ringkasan {provider} tidak valid.")
                payload = payload.get(list_key)
            if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
                raise RuntimeError(f"Format indeks {provider} tidak valid.")
            _CACHE[f"{key}_at"] = now_mono
            _CACHE[f"{key}_error"] = None
            _CACHE[f"{key}_data"] = payload
            return payload, None
        except Exception as exc:
            _CACHE[f"{key}_at"] = now_mono
            _CACHE[f"{key}_error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
            return None, str(_CACHE[f"{key}_error"])


def fetch_coinpaprika_coin_index() -> tuple[list[dict[str, Any]] | None, str | None]:
    return _get_cached_index("CoinPaprika", f"{COINPAPRIKA_BASE_URL}/coins")


def fetch_defillama_protocol_index() -> tuple[list[dict[str, Any]] | None, str | None]:
    return _get_cached_index("DeFiLlama", DEFILLAMA_PROTOCOLS_URL)


def fetch_defillama_revenue_index() -> tuple[list[dict[str, Any]] | None, str | None]:
    """Fetch the free dailyRevenue overview so several projects share one bounded request."""
    return _get_cached_index(
        "DeFiLlama daily revenue", DEFILLAMA_REVENUE_URL, list_key="protocols",
    )

def _normalise_name(value: Any) -> str:
    return "".join(char for char in str(value or "").lower() if char.isalnum())


def match_coinpaprika_asset(
    symbol: str,
    name: str,
    coin_index: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, str]:
    """Only resolve a profile when both symbol and normalized name match exactly."""
    symbol_key = str(symbol or "").strip().upper()
    name_key = _normalise_name(name)
    symbol_matches = [
        item for item in coin_index
        if str(item.get("symbol") or "").strip().upper() == symbol_key
        and item.get("id")
        and item.get("is_active") is not False
    ]
    exact = [item for item in symbol_matches if _normalise_name(item.get("name")) == name_key]
    if len(exact) == 1:
        return exact[0], "EXACT_SYMBOL_AND_NAME"
    if len(exact) > 1:
        return None, "AMBIGUOUS_EXACT_MATCH"
    if len(symbol_matches) > 1:
        return None, "AMBIGUOUS_SYMBOL"
    if len(symbol_matches) == 1:
        return None, "NAME_MISMATCH_REQUIRES_REVIEW"
    return None, "NOT_FOUND"


def _link_list(value: Any) -> list[str]:
    candidates: list[str] = []
    if isinstance(value, str):
        candidates.append(value)
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                candidates.append(item)
            elif isinstance(item, dict):
                link = item.get("url") or item.get("link")
                if isinstance(link, str):
                    candidates.append(link)
    output: list[str] = []
    for candidate in candidates:
        candidate = candidate.strip()
        parsed = urllib.parse.urlparse(candidate)
        if parsed.scheme in {"http", "https"} and parsed.netloc and candidate not in output:
            output.append(candidate[:500])
    return output[:8]


def github_repo_from_url(url: str) -> tuple[str, str] | None:
    """Accept a GitHub owner/repository path only when supplied by the coin profile."""
    parsed = urllib.parse.urlparse(str(url or ""))
    if parsed.netloc.lower() not in {"github.com", "www.github.com"}:
        return None
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2 or parts[0].lower() in {
        "topics", "orgs", "features", "settings", "marketplace", "search", "collections",
    }:
        return None
    owner, repo = parts[0], parts[1].removesuffix(".git")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", owner) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", repo):
        return None
    return owner, repo


def fetch_github_repo_metadata(url: str) -> dict[str, Any]:
    parsed = github_repo_from_url(url)
    if not parsed:
        return {"status": "UNAVAILABLE", "reason": "Tautan repository tidak valid."}
    owner, repo = parsed
    api_url = f"https://api.github.com/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}"
    try:
        data = research_http_json(api_url, timeout=8, max_bytes=1_000_000, api_kind="GitHub repository metadata")
        if not isinstance(data, dict) or data.get("message") == "Not Found":
            return {"status": "UNAVAILABLE", "url": url, "reason": "Repository publik tidak ditemukan."}
        return {
            "status": "AVAILABLE",
            "repository": str(data.get("full_name") or f"{owner}/{repo}")[:180],
            "url": str(data.get("html_url") or url)[:500],
            "description": str(data.get("description") or "")[:500],
            "stars": int(data.get("stargazers_count") or 0),
            "forks": int(data.get("forks_count") or 0),
            "open_issues": int(data.get("open_issues_count") or 0),
            "created_at": str(data.get("created_at") or "")[:40],
            "last_push_at": str(data.get("pushed_at") or "")[:40],
            "source_api_url": api_url,
            "interpretation_limit": "Stars, forks, dan waktu push bukan bukti kualitas, keamanan, atau bahwa repository mewakili produk utama.",
        }
    except Exception as exc:
        return {"status": "UNAVAILABLE", "url": url, "reason": f"GitHub tidak dapat diperiksa: {type(exc).__name__}: {str(exc)[:100]}"}


def extract_coinpaprika_profile(profile: dict[str, Any], coin_id: str) -> dict[str, Any]:
    links = profile.get("links") if isinstance(profile.get("links"), dict) else {}
    extended = profile.get("links_extended") if isinstance(profile.get("links_extended"), list) else []
    websites = _link_list(links.get("website"))
    whitepapers = _link_list(links.get("whitepaper"))
    source_urls: list[str] = []
    for candidate in _link_list(links.get("source_code")):
        if github_repo_from_url(candidate) and candidate not in source_urls:
            source_urls.append(candidate)
    for item in extended:
        if not isinstance(item, dict):
            continue
        candidate = str(item.get("url") or "").strip()
        link_type = str(item.get("type") or "").lower()
        if link_type in {"github", "source_code", "source-code"} and github_repo_from_url(candidate) and candidate not in source_urls:
            source_urls.append(candidate)
    team_rows = profile.get("team") if isinstance(profile.get("team"), list) else []
    team: list[dict[str, str]] = []
    for person in team_rows[:12]:
        if isinstance(person, dict) and str(person.get("name") or "").strip():
            team.append({
                "name": str(person.get("name") or "").strip()[:120],
                "position": str(person.get("position") or "").strip()[:100],
                "id": str(person.get("id") or "")[:120],
            })
    tag_rows = profile.get("tags") if isinstance(profile.get("tags"), list) else []
    tags = [str(item.get("name") or item.get("id") or "")[:80] for item in tag_rows[:12] if isinstance(item, dict)]
    return {
        "status": "PROFILE_AVAILABLE",
        "provider": "CoinPaprika",
        "coin_id": coin_id,
        "profile_name": str(profile.get("name") or "")[:180],
        "profile_symbol": str(profile.get("symbol") or "").upper()[:30],
        "rank": profile.get("rank") if isinstance(profile.get("rank"), int) else None,
        "asset_type": str(profile.get("type") or "")[:40],
        "description": str(profile.get("description") or "").strip()[:1000],
        "started_at": str(profile.get("started_at") or "")[:40],
        "open_source": profile.get("open_source") if isinstance(profile.get("open_source"), bool) else None,
        "proof_type": str(profile.get("proof_type") or "")[:100],
        "hash_algorithm": str(profile.get("hash_algorithm") or "")[:100],
        "tags": [tag for tag in tags if tag],
        "team_listed_by_provider": team,
        "team_verification_note": "Nama/role adalah data katalog; identitas dan jabatan belum diverifikasi independen.",
        "website_links_from_profile": websites,
        "whitepaper_urls": whitepapers,
        "github_urls": source_urls[:8],
        "profile_url": f"https://coinpaprika.com/coin/{urllib.parse.quote(coin_id)}/",
        "source_api_url": f"{COINPAPRIKA_BASE_URL}/coins/{urllib.parse.quote(coin_id)}",
        "revenue_or_company_financials": "NOT_PROVIDED_BY_THIS_PROFILE",
        "token_unlocks": "NOT_CHECKED_IN_THIS_FIRST_ITERATION",
        "audit_status": "NOT_VERIFIED_IN_THIS_FIRST_ITERATION",
    }


def match_defillama_protocol(symbol: str, name: str, protocols: list[dict[str, Any]]) -> dict[str, Any] | None:
    symbol_key, name_key = str(symbol or "").strip().upper(), _normalise_name(name)
    exact = [
        item for item in protocols
        if str(item.get("symbol") or "").strip().upper() == symbol_key
        and _normalise_name(item.get("name")) == name_key
    ]
    if len(exact) != 1:
        return None
    item = exact[0]
    chains = item.get("chains") if isinstance(item.get("chains"), list) else []
    return {
        "status": "EXACT_MATCH",
        "name": str(item.get("name") or "")[:180],
        "symbol": str(item.get("symbol") or "").upper()[:30],
        "category": str(item.get("category") or "")[:100],
        "chains": [str(chain)[:80] for chain in chains[:20]],
        "tvl_usd": _finite_number(item.get("tvl")),
        "tvl_change_1d_pct": _finite_number(item.get("change_1d")),
        "tvl_change_7d_pct": _finite_number(item.get("change_7d")),
        "source_url": DEFILLAMA_PROTOCOLS_URL,
        "interpretation_limit": "TVL adalah nilai dana yang tercatat dalam protokol, bukan pendapatan, laba perusahaan, atau nilai pasar token.",
    }


def match_defillama_revenue(symbol: str, name: str, revenue_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Match daily protocol revenue only when symbol and normalized name are both unique and exact."""
    symbol_key, name_key = str(symbol or "").strip().upper(), _normalise_name(name)
    exact = [
        item for item in revenue_rows
        if str(item.get("symbol") or "").strip().upper() == symbol_key
        and _normalise_name(item.get("name") or item.get("displayName")) == name_key
    ]
    if len(exact) != 1:
        return None
    item = exact[0]
    return {
        "status": "EXACT_MATCH",
        "name": str(item.get("name") or item.get("displayName") or "")[:180],
        "symbol": str(item.get("symbol") or "").upper()[:30],
        "protocol_revenue_usd_24h": _finite_number(item.get("total24h")),
        "protocol_revenue_usd_7d": _finite_number(item.get("total7d")),
        "protocol_revenue_change_1d_pct": _finite_number(item.get("change_1d")),
        "methodology_url": str(item.get("methodologyURL") or "")[:500],
        "source_url": DEFILLAMA_REVENUE_URL,
        "interpretation_limit": "Daily revenue menurut metodologi DeFiLlama untuk protokol yang dicocokkan; bukan laporan keuangan perusahaan, laba bersih, pendapatan tim, atau pendapatan pemegang token. Cakupan protokol dapat berbeda.",
    }


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
        if number != number or number in {float("inf"), float("-inf")}:
            return None
        return number
    except (TypeError, ValueError, OverflowError):
        return None


def _candidate_priority(row: dict[str, Any]) -> tuple[int, int, float]:
    analysis = row.get("technical_analysis") if isinstance(row.get("technical_analysis"), dict) else {}
    setup = analysis.get("potential_setup") if isinstance(analysis.get("potential_setup"), dict) else {}
    label = str(setup.get("label") or "")
    signal = str(analysis.get("signal") or "NO SIGNAL")
    plan = analysis.get("trade_plan") if isinstance(analysis.get("trade_plan"), dict) else {}
    plan_status = str(plan.get("status") or "")
    rank = (
        5 if signal == "SELL / EXIT NOW" else
        0 if label == "EARLY REVERSAL WATCH" else
        1 if label == "BASE FORMING WATCH" else
        2 if label == "PULLBACK WATCH" else
        3 if signal == "BUY NOW" else
        4 if signal == "WAIT" and plan_status not in {"MISSED_ENTRY", "SKIP_HIGH_RISK"} else 6
    )
    return rank, -int(_finite_number(setup.get("score")) or 0), -(_finite_number(row.get("volume_idr")) or 0)


def enrich_fundamental_research(crypto: dict[str, dict[str, Any]], limit: int = POTENTIAL_RADAR_PROFILE_LIMIT) -> tuple[dict[str, dict[str, Any]], str]:
    """Attach top-candidate profiles, team/product links and limited public repository metrics."""
    enriched = {symbol: dict(row) for symbol, row in crypto.items()}
    technical_rows = []
    for symbol, row in enriched.items():
        analysis = row.get("technical_analysis")
        if not isinstance(analysis, dict):
            continue
        setup = analysis.get("potential_setup") if isinstance(analysis.get("potential_setup"), dict) else {}
        if setup.get("label") == "DATA / RISK GATE":
            continue
        technical_rows.append((symbol, row))
    technical_rows.sort(key=lambda item: _candidate_priority(item[1]))
    targets = technical_rows[:max(0, min(int(limit), POTENTIAL_RADAR_PROFILE_LIMIT))]
    if not targets:
        return enriched, "Belum ada hasil candle untuk diperkaya dengan riset proyek."

    coin_index, coin_error = fetch_coinpaprika_coin_index()
    protocols, defi_error = fetch_defillama_protocol_index()
    revenue_rows, revenue_error = fetch_defillama_revenue_index()
    matched = 0
    profile_tasks: list[tuple[str, str, str, str]] = []

    for symbol, row in targets:
        asset_name = str(row.get("name") or symbol)
        defi_match = match_defillama_protocol(symbol, asset_name, protocols) if protocols is not None else None
        revenue_match = match_defillama_revenue(symbol, asset_name, revenue_rows) if revenue_rows is not None else None
        base: dict[str, Any] = {
            "provider": "CoinPaprika",
            "matched_symbol": symbol,
            "matched_name": asset_name,
            "defillama": defi_match,
            "defillama_status": "EXACT_MATCH" if defi_match else ("NOT_MATCHED" if protocols is not None else "SOURCE_UNAVAILABLE"),
            "defillama_error": str(defi_error or "")[:120] if protocols is None else None,
            "defillama_data_source": DEFILLAMA_PROTOCOLS_URL,
            "defillama_daily_revenue": revenue_match,
            "defillama_revenue_status": "EXACT_MATCH" if revenue_match else ("NOT_MATCHED" if revenue_rows is not None else "SOURCE_UNAVAILABLE"),
            "defillama_revenue_error": str(revenue_error or "")[:120] if revenue_rows is None else None,
            "defillama_revenue_data_source": DEFILLAMA_REVENUE_URL,
        }
        if coin_index is None:
            base.update({
                "status": "SOURCE_UNAVAILABLE",
                "note": "Profil CoinPaprika belum bisa diperiksa karena indeks sumber tidak tersedia; jangan menyimpulkan kualitas proyek dari data kosong.",
                "error": str(coin_error or "Index unavailable")[:160],
                "source_url": "https://coinpaprika.com/",
            })
            enriched[symbol]["fundamental_research"] = base
            continue

        coin, match_status = match_coinpaprika_asset(symbol, asset_name, coin_index)
        if coin is None:
            base.update({
                "status": match_status,
                "note": "Tidak ada profil unik dengan simbol dan nama yang cocok persis; aplikasi tidak menebak proyek berdasarkan ticker saja.",
                "source_url": "https://coinpaprika.com/",
                "coin_list_source_url": f"{COINPAPRIKA_BASE_URL}/coins",
            })
            enriched[symbol]["fundamental_research"] = base
            continue

        coin_id = str(coin.get("id") or "")
        coin_name = str(coin.get("name") or "")
        coin_symbol = str(coin.get("symbol") or "").upper()
        base.update({
            "status": "MATCHED_PROFILE_PENDING",
            "coin_id": coin_id,
            "matched_name": coin_name[:180],
            "matched_symbol": coin_symbol[:30],
            "match_method": "EXACT_SYMBOL_AND_NORMALIZED_NAME",
            "source_url": f"https://coinpaprika.com/coin/{urllib.parse.quote(coin_id)}/",
            "coin_list_source_url": f"{COINPAPRIKA_BASE_URL}/coins",
            "coin_list_rank": coin.get("rank") if isinstance(coin.get("rank"), int) else None,
        })
        enriched[symbol]["fundamental_research"] = base
        profile_tasks.append((symbol, coin_id, coin_name, coin_symbol))
        matched += 1

    def fetch_profile(task: tuple[str, str, str, str]) -> tuple[str, dict[str, Any] | None, str | None]:
        asset_symbol, coin_id, expected_name, expected_symbol = task
        if not coin_id or not re.fullmatch(r"[A-Za-z0-9_-]{2,120}", coin_id):
            return asset_symbol, None, "Coin ID tidak valid."
        url = f"{COINPAPRIKA_BASE_URL}/coins/{urllib.parse.quote(coin_id)}"
        try:
            profile = research_http_json(url, timeout=8, max_bytes=2_000_000, api_kind="CoinPaprika coin profile")
            if not isinstance(profile, dict):
                raise RuntimeError("Format profil tidak valid.")
            if (str(profile.get("symbol") or "").upper() != expected_symbol
                    or _normalise_name(profile.get("name")) != _normalise_name(expected_name)):
                raise RuntimeError("Profil tidak cocok dengan indeks; hasil ditolak.")
            return asset_symbol, profile, None
        except Exception as exc:
            return asset_symbol, None, f"{type(exc).__name__}: {str(exc)[:130]}"

    if profile_tasks:
        jobs: dict[concurrent.futures.Future, str] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(profile_tasks))) as pool:
            for task in profile_tasks:
                jobs[pool.submit(fetch_profile, task)] = task[0]
            for future in concurrent.futures.as_completed(jobs):
                symbol, profile, error = future.result()
                research = enriched[symbol].get("fundamental_research") or {}
                if profile is None:
                    research["status"] = "PROFILE_UNAVAILABLE"
                    research["profile_error"] = error
                    research["note"] = "Katalog cocok, tetapi profil detail tidak tersedia; data tim/produk yang hilang tidak disimpulkan."
                else:
                    research.update(extract_coinpaprika_profile(profile, str(research.get("coin_id") or "")))
                    research["provider"] = "CoinPaprika"
                    research["status"] = "PROFILE_AVAILABLE"
                enriched[symbol]["fundamental_research"] = research

    # Inspect only a few source-code repositories explicitly linked from matched profiles.
    repo_targets: list[tuple[str, str]] = []
    for symbol, _row in targets:
        research = enriched[symbol].get("fundamental_research") or {}
        repo_urls = research.get("github_urls") if isinstance(research.get("github_urls"), list) else []
        for repo_url in repo_urls:
            if github_repo_from_url(repo_url) and not any(existing_url == repo_url for _, existing_url in repo_targets):
                repo_targets.append((symbol, repo_url))
                if len(repo_targets) >= POTENTIAL_RADAR_GITHUB_LIMIT:
                    break
        if len(repo_targets) >= POTENTIAL_RADAR_GITHUB_LIMIT:
            break
    if repo_targets:
        repo_jobs: dict[concurrent.futures.Future, tuple[str, str]] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(3, len(repo_targets))) as pool:
            for symbol, repo_url in repo_targets:
                repo_jobs[pool.submit(fetch_github_repo_metadata, repo_url)] = (symbol, repo_url)
            for future in concurrent.futures.as_completed(repo_jobs):
                symbol, _repo_url = repo_jobs[future]
                research = enriched[symbol].get("fundamental_research") or {}
                research.setdefault("github_repositories", []).append(future.result())
                enriched[symbol]["fundamental_research"] = research

    profiled = sum(1 for symbol, _row in targets if (enriched[symbol].get("fundamental_research") or {}).get("status") == "PROFILE_AVAILABLE")
    defi_matches = sum(1 for symbol, _row in targets if (enriched[symbol].get("fundamental_research") or {}).get("defillama_status") == "EXACT_MATCH")
    status = f"CoinPaprika: {matched} exact match, {profiled} profil detail tersedia dari {len(targets)} kandidat; DeFiLlama TVL exact-match pada {defi_matches} proyek."
    if coin_index is None:
        status += f" Indeks CoinPaprika tidak tersedia ({str(coin_error or 'error')[:90]})."
    if protocols is None:
        status += f" Indeks DeFiLlama TVL tidak tersedia ({str(defi_error or 'error')[:90]})."
    if revenue_rows is None:
        status += f" Indeks dailyRevenue DeFiLlama tidak tersedia ({str(revenue_error or 'error')[:90]})."
    revenue_matches = sum(1 for symbol, _row in targets if (enriched[symbol].get("fundamental_research") or {}).get("defillama_revenue_status") == "EXACT_MATCH")
    status += f" DeFiLlama dailyRevenue exact-match pada {revenue_matches} protokol."
    status += " CoinPaprika: personal/nonkomersial, wajib atribusi. Metadata tim/proyek bukan verifikasi independen."
    return enriched, status


def candidate_priority(row: dict[str, Any]) -> tuple[int, int, float]:
    analysis = row.get("technical_analysis") if isinstance(row.get("technical_analysis"), dict) else {}
    setup = analysis.get("potential_setup") if isinstance(analysis.get("potential_setup"), dict) else {}
    label = str(setup.get("label") or "")
    signal = str(analysis.get("signal") or "NO SIGNAL")
    plan = analysis.get("trade_plan") if isinstance(analysis.get("trade_plan"), dict) else {}
    status = str(plan.get("status") or "")
    rank = (5 if signal == "SELL / EXIT NOW" else
            0 if label == "EARLY REVERSAL WATCH" else
            1 if label == "BASE FORMING WATCH" else
            2 if label == "PULLBACK WATCH" else
            3 if signal == "BUY NOW" else
            4 if signal == "WAIT" and status not in {"MISSED_ENTRY", "SKIP_HIGH_RISK"} else 6)
    return rank, -int(_finite_number(setup.get("score")) or 0), -(_finite_number(row.get("volume_idr")) or 0)


def _format_idr(value: Any) -> str:
    number = _finite_number(value)
    if number is None:
        return "—"
    if abs(number) >= 1000:
        return "Rp" + f"{number:,.0f}".replace(",", ".")
    decimals = 2 if abs(number) >= 1 else 6
    return "Rp" + f"{number:,.{decimals}f}".replace(",", "<G>").replace(".", ",").replace("<G>", ".").rstrip("0").rstrip(",")


def _format_volume(value: Any) -> str:
    number = _finite_number(value)
    if number is None:
        return "—"
    for threshold, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if number >= threshold:
            return f"Rp{number / threshold:.2f}{suffix}"
    return f"Rp{number:,.0f}".replace(",", ".")


def _display_plan_status(value: Any) -> str:
    status = str(value or "NO_PLAN")
    labels = {
        "CONDITIONAL": "Menunggu konfirmasi candle 1 jam",
        "MISSED_ENTRY": "Trigger entry sudah lewat — jangan mengejar harga",
        "SKIP_HIGH_RISK": "Lewati — risiko terlalu tinggi",
        "BLOCKED_RISK_GATE": "Pantau saja — gerbang data/risiko belum lolos",
        "NO_PLAN": "Belum tersedia rencana harga yang valid",
        "NO_SETUP": "Belum ada setup yang memenuhi syarat",
    }
    return labels.get(status, status.replace("_", " ").title())


def _display_profile_status(value: Any) -> str:
    status = str(value or "NOT_CHECKED")
    labels = {
        "PROFILE_AVAILABLE": "Profil proyek ditemukan",
        "NOT_FOUND": "Profil proyek tidak ditemukan",
        "AMBIGUOUS_MATCH": "Pencocokan proyek ambigu — tidak ditebak",
        "NOT_CHECKED": "Belum diperiksa",
        "FETCH_ERROR": "Sumber profil gagal diakses",
    }
    return labels.get(status, status.replace("_", " ").title())


def format_potential_radar_summary(crypto: dict[str, dict[str, Any]], status_lines: list[str] | None = None) -> str:
    """Create a readable, source-grounded scan overview before the detailed AI report.

    Keep this section focused on scan coverage, setup counts, and compact candidate
    evidence. The AI's following section provides deeper project research so the same
    team/site/repository paragraphs are not duplicated twice.
    """
    rows = [(symbol, row) for symbol, row in crypto.items() if isinstance(row.get("technical_analysis"), dict)]
    rows.sort(key=lambda item: candidate_priority(item[1]))
    labels = [str(((row.get("technical_analysis") or {}).get("potential_setup") or {}).get("label") or "NO DATA") for _, row in rows]
    labels_to_count = ("EARLY REVERSAL WATCH", "BASE FORMING WATCH", "PULLBACK WATCH", "NO EARLY SETUP", "DATA / RISK GATE")
    counts = {label: labels.count(label) for label in labels_to_count}
    readable_counts = {
        "EARLY REVERSAL WATCH": "reversal awal",
        "BASE FORMING WATCH": "pembentukan dasar",
        "PULLBACK WATCH": "pullback",
        "NO EARLY SETUP": "belum ada setup awal",
        "DATA / RISK GATE": "data/gerbang risiko",
    }
    lines = [
        "POTENTIAL COIN RADAR · RINGKASAN PEMINDAIAN",
        "",
        "CAKUPAN PEMINDAIAN",
        f"• Candle 1 jam dianalisis: {len(rows)} pair IDR",
        "• Distribusi setup: " + "  |  ".join(f"{readable_counts[key]}: {counts[key]}" for key in labels_to_count),
    ]
    if status_lines:
        lines.append("• Status pengambilan data:")
        for status_line in status_lines:
            if not status_line:
                continue
            # Provider status strings often contain several independent facts;
            # display each fact as its own short wrapped bullet.
            parts = [part.strip() for part in re.split(r"(?<=[;.!?])\s+", str(status_line).strip()) if part.strip()]
            lines.extend("  – " + part[:240] for part in parts)
    lines.extend([
        "",
        "KANDIDAT UNTUK DITINJAU",
        "Urutan di bawah adalah prioritas pemeriksaan, bukan probabilitas harga naik atau sinyal beli.",
    ])
    if not rows:
        lines.append("Belum ada kandidat dengan hasil analisis candle yang bisa ditampilkan.")
    for index, (symbol, row) in enumerate(rows[:8], start=1):
        analysis = row.get("technical_analysis") or {}
        setup = analysis.get("potential_setup") or {}
        metrics = analysis.get("metrics") or {}
        research = row.get("fundamental_research") or {}
        plan = analysis.get("trade_plan") or {}
        rsi = _finite_number(metrics.get("rsi14_1h"))
        rsi_text = f"{rsi:.1f}".replace(".", ",") if rsi is not None else "—"
        price_text = _format_idr(row.get("price"))
        volume_text = _format_volume(row.get("volume_idr"))
        score = int(_finite_number(setup.get("score")) or 0)
        max_score = int(_finite_number(setup.get("max_score")) or 8)
        setup_label = str(setup.get("label") or "NO DATA").replace("_", " ")
        lines.extend([
            "",
            f"{index:02d}  {symbol}  ·  {setup_label}",
            f"     Bukti teknikal: {score}/{max_score}  |  Harga: {price_text}  |  RSI 1j: {rsi_text}  |  Volume 24j: {volume_text}",
            f"     Rencana entry: {_display_plan_status(plan.get('status'))}",
            f"     Riset proyek: {_display_profile_status(research.get('status'))}",
        ])
        evidence = [str(item).strip() for item in (setup.get("evidence") or [])[:4] if str(item).strip()]
        if evidence:
            lines.append("     Bukti candle:")
            lines.extend("       • " + item[:180] for item in evidence)

        # Preserve the source evidence for all eight shortlisted scan rows, even
        # when the AI's detailed narrative chooses only five. Every item is clearly
        # attributed and missing values are rendered as unavailable, never as None.
        if research.get("status") == "PROFILE_AVAILABLE":
            desc = " ".join(str(research.get("description") or "").split())
            if desc:
                lines.append("     Ringkasan katalog: " + desc[:320] + ("…" if len(desc) > 320 else ""))
            team = research.get("team_listed_by_provider") or []
            if team:
                names = ", ".join(
                    f"{person.get('name')} ({person.get('position') or 'peran tidak disebutkan'})"
                    for person in team[:3] if isinstance(person, dict) and person.get("name")
                )
                if names:
                    lines.append("     Tim menurut katalog CoinPaprika (belum diverifikasi independen): " + names)
            websites = research.get("website_links_from_profile") or []
            if websites:
                lines.append("     Situs resmi yang dicantumkan: " + str(websites[0])[:280])
            whitepapers = research.get("whitepaper_urls") or []
            if whitepapers:
                lines.append("     Whitepaper: " + str(whitepapers[0])[:280])
            tags = research.get("tags") or []
            if tags:
                lines.append("     Kategori katalog: " + ", ".join(str(tag) for tag in tags[:4]))
            repos = research.get("github_repositories") or []
            available_repos = [repo for repo in repos if isinstance(repo, dict) and repo.get("status") == "AVAILABLE"]
            if available_repos:
                repo = available_repos[0]
                pushed = str(repo.get("last_push_at") or "belum tersedia")
                lines.append(
                    f"     GitHub: {repo.get('repository') or 'repo publik'}  |  stars {repo.get('stars', '—')}  |  update terakhir {pushed}  |  {repo.get('url') or ''}"
                )
            elif research.get("github_urls"):
                lines.append("     GitHub dari profil (metadata repo belum diperiksa pada scan ini): " + str(research.get("github_urls")[0])[:280])
            elif research.get("open_source") is False:
                lines.append("     Kode sumber publik: tidak tercantum di profil; tidak berarti pasti tidak ada.")
        elif research.get("status") == "NOT_FOUND":
            lines.append("     Riset proyek: tidak ditemukan profil CoinPaprika yang cocok secara unik; proyek tidak ditebak dari ticker saja.")
        elif research.get("status") in {"SOURCE_UNAVAILABLE", "FETCH_ERROR"}:
            lines.append("     Riset proyek: sumber tidak tersedia saat pemindaian; bukan bukti bahwa proyek tidak valid.")

        defi = research.get("defillama") or {}
        if research.get("defillama_status") == "EXACT_MATCH" or defi.get("status") == "EXACT_MATCH":
            tvl = _finite_number(defi.get("tvl_usd"))
            change_1d = _finite_number(defi.get("tvl_change_1d_pct"))
            change_7d = _finite_number(defi.get("tvl_change_7d_pct"))
            if tvl is None:
                lines.append("     DeFiLlama TVL: proyek cocok, tetapi angka TVL belum tersedia.")
            else:
                tvl_text = f"USD {tvl:,.0f}".replace(",", ".")
                c1_text = f"{change_1d:+.2f}%".replace(".", ",") if change_1d is not None else "belum tersedia"
                c7_text = f"{change_7d:+.2f}%".replace(".", ",") if change_7d is not None else "belum tersedia"
                lines.append(f"     DeFiLlama TVL: {tvl_text}  |  perubahan 1 hari/7 hari: {c1_text} / {c7_text}")
        elif research.get("defillama_status") == "NOT_MATCHED":
            lines.append("     DeFiLlama TVL: tidak ada pencocokan nama+simbol yang tepat.")

        revenue = research.get("defillama_daily_revenue") or {}
        if research.get("defillama_revenue_status") == "EXACT_MATCH" or revenue.get("status") == "EXACT_MATCH":
            daily_revenue = _finite_number(revenue.get("protocol_revenue_usd_24h"))
            weekly_revenue = _finite_number(revenue.get("protocol_revenue_usd_7d"))
            daily_text = f"USD {daily_revenue:,.0f}".replace(",", ".") if daily_revenue is not None else "belum tersedia"
            weekly_text = f"USD {weekly_revenue:,.0f}".replace(",", ".") if weekly_revenue is not None else "belum tersedia"
            lines.append(f"     DeFiLlama dailyRevenue protokol: 24 jam {daily_text}  |  7 hari {weekly_text}; bukan laporan keuangan perusahaan.")
        elif research.get("defillama_revenue_status") == "NOT_MATCHED":
            lines.append("     DeFiLlama dailyRevenue: tidak ada pencocokan nama+simbol yang tepat.")

        lines.extend([
            "     Sumber profil: " + str(research.get("profile_url") or research.get("source_url") or "https://coinpaprika.com/"),
        ])
        asset_news = row.get("asset_news") or []
        news_items = [item for item in asset_news if isinstance(item, dict) and item.get("title")]
        if news_items:
            lines.append("     Headline (petunjuk, bukan verifikasi katalis):")
            for item in news_items[:2]:
                news_line = f"{str(item.get('title'))[:220]} — {str(item.get('source') or 'RSS')}"
                if item.get("link"):
                    news_line += " — " + str(item.get("link"))[:260]
                lines.append("       • " + news_line)

    lines.extend([
        "",
        "CARA MEMBACA HASIL",
        "• Reversal/base-forming watch berarti pantau; bukan perintah beli.",
        "• MISSED_ENTRY berarti trigger lama sudah lewat. Tunggu setup baru; jangan mengejar harga.",
        "• Harga entry/TP/invalidasi hanya boleh dipakai jika rencana candle valid dan syaratnya terpenuhi.",
        "• Metadata proyek/tim berasal dari katalog publik, bukan verifikasi independen. Data yang tidak ditemukan tidak boleh diasumsikan.",
        "",
        "SUMBER DAN BATASAN",
        f"• Atribusi: {COINPAPRIKA_CREDIT}.",
        "• Tier CoinPaprika ini untuk penggunaan personal/nonkomersial; penggunaan komersial memerlukan izin yang sesuai.",
        "• Scan terbatas pada kandidat yang diprioritaskan; urutan heuristik bukan probabilitas profit. Level teknikal belum tervalidasi dengan backtest walk-forward.",
    ])
    return "\n".join(lines)


def enrich_potential_coin_radar_data(
    crypto: dict[str, dict[str, Any]],
    technical_enricher: Callable[..., tuple[dict[str, dict[str, Any]], str]],
    news_fetcher: Callable[..., dict[str, list[dict[str, str]]]],
) -> tuple[dict[str, dict[str, Any]], str]:
    """Run a bounded technical scan, add project research for leading candidates, then attach headlines."""
    enriched, technical_status = technical_enricher(crypto, limit=POTENTIAL_RADAR_SCAN_LIMIT)
    enriched, research_status = enrich_fundamental_research(enriched, limit=POTENTIAL_RADAR_PROFILE_LIMIT)
    asset_news = news_fetcher(enriched, max_assets=POTENTIAL_RADAR_NEWS_LIMIT)
    for symbol, headlines in asset_news.items():
        if symbol in enriched:
            enriched[symbol]["asset_news"] = headlines
    summary = format_potential_radar_summary(enriched, [
        technical_status,
        research_status,
        f"Headline RSS dicoba sampai {POTENTIAL_RADAR_NEWS_LIMIT} aset; headline adalah petunjuk, bukan verifikasi katalis.",
    ])
    return enriched, summary
