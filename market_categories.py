"""Locally curated category mapping for INDODAX IDR watchlist assets.

The documented INDODAX /api/pairs response does not expose category membership.
This module therefore keeps an explicit, reviewable symbol map instead of
pretending that categories are supplied by the ticker API. Unmapped symbols
remain visible under the dedicated "Unmapped" filter.

A symbol may belong to more than one category when its project serves multiple
roles. Add new symbols only after checking the project's primary use case.
"""
from __future__ import annotations

from collections.abc import Iterable

CATEGORY_ASSETS: dict[str, tuple[str, ...]] = {
    "AI & Big Data": (
        "AGIX", "AIOZ", "ARKM", "FET", "GRT", "IO", "NMR", "OCEAN",
        "RENDER", "SAPIEN", "SKYAI", "TAO", "UAI", "VIRTUAL", "WLD",
    ),
    "Layer 1&2": (
        "ADA", "ALGO", "APT", "ARB", "ATOM", "AVAX", "BCH", "BTC",
        "DOT", "EOS", "ETH", "HBAR", "HYPE", "ICP", "KAS", "KAVA",
        "LTC", "MANTA", "METIS", "NEAR", "OP", "POL", "SEI", "SOL",
        "STRK", "SUI", "TON", "TRX", "XLM", "XRP", "XTZ", "ZIL", "ZK",
    ),
    "Meme": (
        "BABYDOGE", "BOME", "BONK", "BRETT", "CAT", "DOGE", "FARTCOIN",
        "FLOKI", "JELLYJELLY", "MEME", "MOODENG", "NEIRO", "PEPE",
        "PIPPIN", "POPCAT", "SHIB", "TURBO", "VINE", "WIF",
    ),
    "RWA": ("CFG", "ONDO", "PAXG", "POLYX", "XAUT"),
    "GameFi": (
        "AXS", "BEAT", "ENJ", "GALA", "GMT", "ILV", "IMX", "MAGIC",
        "PORTAL", "RON", "SUPER", "YGG",
    ),
    "Governance/DAO": (
        "AAVE", "BAL", "COMP", "CRV", "CVX", "DYDX", "ENS", "LDO",
        "MKR", "SKY", "UNI", "YFI",
    ),
    "Blockchain Service": (
        "ANKR", "API3", "AR", "BAND", "FIL", "GRT", "HNT", "HOT",
        "LINK", "QNT", "STORJ",
    ),
    "CEX/DEX": (
        "1INCH", "ASTER", "BNB", "CAKE", "CRO", "DODO", "DYDX", "GT",
        "HYPE", "JUP", "KCS", "OKB", "RAY", "SUSHI", "UNI",
    ),
    "NFT": ("APE", "BLUR", "CHZ", "ENJ", "IMX", "PENGU", "RARE", "RARI"),
    "DeFi": (
        "1INCH", "AAVE", "BAL", "CAKE", "COMP", "CRV", "CVX", "DODO",
        "DYDX", "ENA", "GMX", "JTO", "JUP", "KERNEL", "KNC", "LDO",
        "MKR", "PENDLE", "RAY", "RUNE", "SKY", "SNX", "SUSHI", "UNI",
        "VELVET", "YFI",
    ),
    "Metaverse": ("APE", "MANA", "SAND"),
    "Stable Coin": ("DAI", "FDUSD", "IDRT", "PAXG", "TUSD", "USDC", "USDE", "USDT", "XAUT"),
    "Tokenized Stocks": (),
}

# The menu follows the current INDODAX market-category names where applicable.
# "New Coin", "Favorites", and "IDR Markets" are intentionally omitted:
# the desktop table already contains IDR pairs, has no favorites list, and the
# documented public pair catalogue does not provide an authoritative listing date.
INDODAX_CATEGORY_OPTIONS: tuple[str, ...] = (
    "All categories",
    "AI & Big Data",
    "Layer 1&2",
    "Meme",
    "RWA",
    "GameFi",
    "Governance/DAO",
    "Blockchain Service",
    "CEX/DEX",
    "Tokenized Stocks",
    "NFT",
    "DeFi",
    "Metaverse",
    "Stable Coin",
    "Unmapped",
)

_SYMBOL_CATEGORIES: dict[str, set[str]] = {}
for _category, _symbols in CATEGORY_ASSETS.items():
    for _symbol in _symbols:
        _SYMBOL_CATEGORIES.setdefault(_symbol.upper(), set()).add(_category)


def categories_for_symbol(symbol: str) -> tuple[str, ...]:
    """Return the curated categories for a symbol, or ('Unmapped',)."""
    key = str(symbol or "").strip().upper()
    categories = _SYMBOL_CATEGORIES.get(key)
    if not categories:
        return ("Unmapped",)
    return tuple(category for category in INDODAX_CATEGORY_OPTIONS if category in categories)


def filter_assets_by_category(
    assets: Iterable[tuple[str, str]], category: str = "All categories",
) -> list[tuple[str, str]]:
    """Filter (symbol, name) pairs without changing order or mutating input."""
    rows = list(assets)
    selected = str(category or "All categories").strip().casefold()
    if selected in {"", "all categories"}:
        return rows
    if selected not in {item.casefold() for item in INDODAX_CATEGORY_OPTIONS}:
        return []
    if selected == "unmapped":
        return [row for row in rows if categories_for_symbol(row[0]) == ("Unmapped",)]
    return [row for row in rows if selected in {item.casefold() for item in categories_for_symbol(row[0])}]
