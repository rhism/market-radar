# Market Radar — Windows Desktop Dashboard

**Market Radar v1.4.0** is a lightweight Windows dashboard for public crypto and global-market data, with rule-based context and optional manual AI analysis. **It does not trade, connect to exchange accounts, or access wallets.**

## What's new in v1.4.0

- **CustomTkinter UI:** consistent rounded cards, buttons, entries, dropdowns, and scrollbars without hand-drawn Canvas widgets in the application code.
- **Side-to-side resize only:** one draggable divider separates the left market tables from the right analysis/news column. Individual panels no longer have top/bottom resize handles; their vertical proportions are managed by the layout.
- **Tighter typography and spacing:** title/subtitle and panel headings sit closer together, with reduced internal gaps while keeping data readable.
- **Retained data tables:** `ttk.Treeview` remains in use for sortable, centered market tables; all positive/negative/neutral/stale color semantics are preserved.
- All previous filters, sorting, row density, market analysis, news, encrypted AI settings, refresh timers, always-on-top, and Windows startup features are retained.

## Features

- **INDODAX IDR pairs:** dynamic catalogue from the public API rather than a hard-coded coin list. The watchlist defaults to 24-hour IDR volume descending.
- **Global markets:** Gold futures, Brent/WTI crude, USD/IDR, S&P 500, Nasdaq Composite, IHSG, VIX, NVIDIA, Apple, Microsoft, and Indonesian stocks BBCA/BBRI/TLKM.
- **Crypto table:** local search by symbol/name, `All assets`/`Gainers`/`Losers`/`High volume` filters, sortable columns, and compact IDR volume formatting.
- **Global-market table:** filter by commodities, FX, indices, or stocks and sort by market, last price, daily change, technicals, or quote time.
- **Rule-based market read:** crypto breadth, BTC change/range, oil/gold/index context, and a cautious entry checklist. It is an interpretation aid, not a trading signal.
- **Google News RSS:** optional feed; double-click a headline to open the source article. Publication times depend on the feed.
- **Optional OpenRouter AI:** `Ask AI (manual)` sends one snapshot only when pressed. AI is not called automatically on refresh. The default model is `openrouter/free`; model availability and quotas can change.
- **Convenience:** manual refresh, automatic refresh, clock in WIB, always-on-top, and start-with-Windows controls.

## Using the tables

### Crypto

Use the search field to find an asset by symbol or name. Search is local and does not trigger additional network calls. Choose a quick filter next to it. `Compact rows` changes the row height of both tables; click a column heading to sort, and click the same heading again to reverse direction. Missing values stay at the bottom.

`Vol 24h IDR` uses compact units (`K`, `M`, `B`, `T`) so high-volume pairs fit the table. Quote timestamps are retained where the source provides them; `stale` means a quote may not reflect a current market session.

### Global markets

Select a category to narrow the 14 configured instruments. Stock/futures data follows the relevant market hours. If columns are clipped, make the application window wider or drag the center divider to allocate more room to the table side.

## Install and run

1. Install **Python 3.11 or newer** from [python.org](https://www.python.org/downloads/windows/) and ensure Tkinter is available.
2. Extract the project folder to a permanent location.
3. Double-click `Run_Market_Radar.bat`. On first run it checks for CustomTkinter and attempts to install the dependency from `requirements.txt` if it is missing. An internet connection is required for that first installation.
4. If startup fails, run `Run_Market_Radar_Debug.bat` to see the error output.

To install the dependency manually from PowerShell in the project folder:

```powershell
py -3 -m pip install -r requirements.txt
```

## Optional AI setup

1. Create a key at [OpenRouter API Keys](https://openrouter.ai/settings/keys).
2. In the app, open **AI Settings**, paste the key, and choose a model ID if needed.
3. Save, then click **Ask AI (manual)** to analyze the current market snapshot.

The API key is **not stored in source code or this repository**. On Windows, the app encrypts a saved key with Windows DPAPI and stores it outside the project at `%APPDATA%\MarketRadar\settings.json`. This file must not be uploaded to GitHub. You can remove the saved key from the AI Settings dialog. An `OPENROUTER_API_KEY` environment variable is also supported.

Manual AI calls may use account quota. Free model routing does not guarantee capacity or speed, and requests can fail if a provider or quota is unavailable. The dashboard remains usable without AI.

## Data sources and refresh cadence

- **Crypto:** `https://indodax.com/api/pairs` and `https://indodax.com/api/summaries` from the public INDODAX API. If the pair catalogue is unavailable, the app attempts a dynamic fallback from summaries.
- **Commodities, FX, indices, and stocks:** Yahoo Finance chart endpoint (unofficial; the endpoint can change, quotes can be delayed, and requests can fail).
- **News:** Google News RSS; results can be delayed or unavailable.
- Crypto refresh: about **90 seconds**. Global-market refresh: about **5 minutes**. RSS refresh: about **15 minutes**. Quote timestamps are shown where available.

## Tests

Run the offline tests from the project directory after installing `requirements.txt`:

```powershell
python -m unittest -v test_market_radar.py
```

The test suite covers INDODAX pair parsing/fallback, formatting, local search and quick filters, market-read structure, sorting, RSI, and encrypted settings behavior.

## Limitations and safety

Market read and AI answers can be wrong. Verify data and sources independently; nothing here predicts a guaranteed bottom, guarantees profit, or constitutes personal financial advice. The dashboard only reads public data. It does not log in to INDODAX, access an exchange account or wallet, place orders, or trade.

## Files

- `market_radar.py` — application source.
- `Run_Market_Radar.bat` — normal launcher with a dependency check.
- `Run_Market_Radar_Debug.bat` — launcher with visible errors and dependency check.
- `requirements.txt` — CustomTkinter dependency.
- `test_market_radar.py` — offline tests.
