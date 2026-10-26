# Market Radar — Windows Desktop Dashboard

**Market Radar v1.2.0** is a lightweight Windows dashboard for public crypto and global-market data, with rule-based context and optional manual AI analysis. **It does not trade, connect to exchange accounts, or access wallets.**

## What's new in v1.2.0

- **Find crypto pairs instantly** by symbol, coin name, or an IDR-pair alias. Search works locally on data already loaded; typing does not call the API.
- **Quick crypto filters:** `All assets`, `Gainers`, `Losers`, and `High volume`. High volume shows the upper quartile of pairs with volume data.
- **Sortable tables:** click a column header to sort ascending; click it again to reverse. An arrow shows the current sort direction. Missing values remain at the bottom.
- **24-hour IDR volume** appears beside price and change, and the initial crypto order remains highest volume first.
- **Global-market category filter:** show all markets, commodities, FX, indices, or stocks.
- **Safer header hover/pressed colors** and a selectable compact/comfortable row density.
- **More readable market read and headlines:** clear section headings, a more conventional UI font, wrapped headlines, and source/publication-time metadata when provided by RSS.
- Existing refresh behavior, quote freshness labels, positive/negative/neutral table colors, AI settings, encrypted local API-key storage, always-on-top, and Windows startup options are retained.

## Features

- **INDODAX IDR pairs:** dynamic catalogue from the public API rather than a hard-coded coin list. The watchlist defaults to 24-hour IDR volume descending.
- **Global markets:** Gold futures, Brent/WTI crude, USD/IDR, S&P 500, Nasdaq Composite, IHSG, VIX, NVIDIA, Apple, Microsoft, and Indonesian stocks BBCA/BBRI/TLKM.
- **Rule-based market read:** crypto breadth, BTC change/range, oil/gold/index context, and a cautious entry checklist. It is an interpretation aid, not a trading signal.
- **Google News RSS:** optional feed; double-click a headline to open the source article. Publication time depends on the feed.
- **Optional OpenRouter AI:** `Ask AI (manual)` sends one snapshot only when pressed. AI is not called automatically on refresh. The default model is `openrouter/free`; model availability and quotas can change.
- **Convenience:** manual refresh, automatic refresh, clock in WIB, always-on-top, and start-with-Windows controls.

## Using the tables

### Crypto

Use **Search** to find an asset by name or symbol. The search is local and does not trigger additional network calls. Choose a quick filter next to it. `Compact rows` / `Comfortable rows` changes the height of both tables. Click any heading to sort; click the same heading again to reverse direction.

`Vol 24h IDR` is shown in compact units (`K`, `M`, `B`, `T`) so high-volume pairs fit the table. The quote timestamp is retained where the source provides one; `stale` means the quote may not reflect a current market session.

### Global markets

Select a category to narrow the 14 configured instruments. Click table headings to sort by market, last price, daily change, technicals, or quote time. Stock/futures data follows each instrument's market hours.

## Install and run

1. Install **Python 3.11 or newer** from [python.org](https://www.python.org/downloads/windows/) and ensure Tkinter is available.
2. Extract the project folder to a permanent location.
3. Double-click `Run_Market_Radar.bat`. No third-party Python packages are required.
4. If startup fails, run `Run_Market_Radar_Debug.bat` to see the error output.

## Optional AI setup

1. Create a key at [OpenRouter API Keys](https://openrouter.ai/settings/keys).
2. In the app, open **AI Settings**, paste the key, and choose a model ID if needed.
3. Save, then click **Ask AI (manual)** to analyze the current market snapshot.

The API key is **not stored in source code or this repository**. On Windows, the app encrypts a saved key with Windows DPAPI and stores it outside the project at `%APPDATA%\MarketRadar\settings.json`. This file must not be uploaded to GitHub. You can remove the saved key from the AI Settings dialog. An `OPENROUTER_API_KEY` environment variable is also supported.

Manual AI calls may use account quota. Free model routing does not guarantee capacity or speed, and a request can fail if a provider or quota is unavailable. The dashboard remains usable without AI.

## Data sources and refresh cadence

- **Crypto:** `https://indodax.com/api/pairs` and `https://indodax.com/api/summaries` from the public INDODAX API. If the pair catalogue is unavailable, the app attempts a dynamic fallback from summaries.
- **Commodities, FX, indices, and stocks:** Yahoo Finance chart endpoint (unofficial; the endpoint can change, quotes can be delayed, and requests can fail).
- **News:** Google News RSS; results can be delayed or unavailable.
- Crypto refresh: about **90 seconds**. Global-market refresh: about **5 minutes**. RSS refresh: about **15 minutes**. Quote timestamps are shown where available.

## Tests

Run the offline tests from the project directory:

```powershell
python -m unittest -v test_market_radar.py
```

The test suite covers INDODAX pair parsing/fallback, formatting, local search and quick filters, market-read structure, RSI, and encrypted settings behavior. The UI has also been smoke-tested with synthetic data in a headless Tkinter session.

## Limitations and safety

Market read and AI answers can be wrong. Verify data and sources independently; nothing here predicts a guaranteed bottom, guarantees profit, or constitutes personal financial advice. The app only reads public data. It does not log in to INDODAX, access an exchange account or wallet, place orders, or trade.

## Files

- `market_radar.py` — application source.
- `Run_Market_Radar.bat` — normal launcher.
- `Run_Market_Radar_Debug.bat` — launcher with visible errors.
- `requirements.txt` — confirms no third-party packages are required.
- `test_market_radar.py` — offline test suite.
- `market-radar-preview.png` — dashboard screenshot.

## Preview

> Preview note: this screenshot uses synthetic layout-test values; figures shown are not live market quotes.

![Market Radar v1.2.0 desktop preview](market-radar-preview.png)
