# Market Radar — Windows Desktop Dashboard

**Market Radar v1.9.1** is a lightweight Windows dashboard for public crypto and global-market data, with rule-based context and optional manual AI analysis. **It does not trade, connect to exchange accounts, or access wallets.**

## What's new in v1.9.1
- **Cleaner Entry / Exit Analyst output:** concise signal counts, compact per-asset lines, no duplicate AI table, and focused detail on up to three assets. Trading rules are unchanged.

- **Rule-based intraday signal engine:** Entry / Exit Analyst fetches closed INDODAX 1-hour OHLC candles for a bounded candidate list and derives 4-hour candles only from four consecutive, complete 1-hour bars.
- **Direct signal labels:** `BUY NOW`, `SELL / EXIT NOW`, `WAIT`, or `NO SIGNAL` are computed by app code—not invented by the AI. The engine checks 1h/4h EMA trend, 1h RSI, last-hour volume versus the preceding 20 candles, ATR extension, current ticker-versus-last-close divergence, 24h IDR volume, bid/ask spread, quote/candle freshness, and BTC 4h trend as a filter for altcoin buys.
- **Conservative data gates:** a direct action is withheld when candle history is insufficient/stale, quote time is stale, bid/ask is missing, daily IDR volume is below Rp500,000,000, or spread exceeds 0.75%. These initial thresholds are explicit heuristics and have not been backtested; they are not calibrated probabilities or guarantees.
- **Asset-specific news pulse:** when Entry / Exit Analyst is clicked, the app tries to retrieve up to three recent Google News RSS headlines for up to five candidates. Headlines are only event clues, not verified fundamentals; missing/noisy headlines do not prove that a coin has no material risk.
- **AI role clarified:** the deterministic signal engine is the source of the direct signal. The AI explains checks and risk and must not upgrade `WAIT`/`NO SIGNAL` to `BUY NOW`. No automated trading or exchange-account access is added.

## What's new in v1.7.0

- **Header navigation:** `MARKET RADAR` opens page one; `MARKET INSIGHT` sits beside it and opens page two. Both use the same large, bold typography and remain outside the data panels.
- **Resizable side-by-side panels:** both pages use a draggable divider between their left and right panels. Resize it to give the crypto table, global markets, market read, or headlines more horizontal space.
- **More table room:** page one shows the crypto watchlist beside global markets; page two shows the market read/action checklist beside global headlines. Status, summary cards, and controls remain visible when switching pages.
- **Retained CustomTkinter UI:** rounded cards, buttons, entries, dropdowns, and scrollbars remain, with native `ttk.Treeview` tables for sorting and color semantics.
- **Action guide:** the Market Insight page now briefly defines every action label and clarifies that TP Watch does not mean selling the entire holding.

## What's new in v1.7.1

- **RSS diagnostics:** Global Headlines now exposes a short Google News RSS status/error instead of silently hiding all failures.
- **More resilient RSS parsing:** uses a browser-like User-Agent and handles RSS/Atom-style element naming more defensively.
- **Faster retry after an empty feed:** retries after about 60 seconds when no headlines loaded, while successful feeds keep the 15-minute refresh interval. `Update now` remains available.

## What's new in v1.8.4

- **Purpose-specific free-model fallback:** replaced the random `openrouter/free` fallback with explicit general-purpose models `nvidia/nemotron-3-ultra-550b-a55b:free` and `nvidia/nemotron-3.5-lightning:free`. The generic router can select specialist models (including content-safety classifiers) that do not produce market analysis.
- **Rejects safety-classifier output:** responses such as `User Safety: safe` are no longer displayed as successful market analysis. For the default Gemma model, the app retries once through the explicit general-purpose fallback chain; if the result remains unsuitable, it shows a diagnostic error.

## What's new in v1.8.3

- **Initial free-model fallback (superseded in v1.8.4):** the default Gemma request used `openrouter/free` as fallback. Because that router can select specialist models, v1.8.4 replaces it with a fixed list of general-purpose free models.
- **Gemma reasoning-budget fix:** the default Gemma request disables optional reasoning for the concise dashboard response, and Entry / Exit Analyst gets a larger output budget. If Gemma still returns HTTP 200 with `finish_reason: length` but no visible answer, the app retries using the fixed general-purpose fallback chain. Empty-response diagnostics include available finish/usage metadata. Custom model IDs are not silently changed.

## What's new in v1.8.1

- **Legacy model-setting migration:** old settings that contain the former default `openrouter/free` without a settings version are migrated to `google/gemma-4-31b-it:free`. A model choice explicitly saved with the current settings version remains unchanged.
- **Better OpenRouter error diagnostics:** HTTP errors surface provider metadata/raw detail when available, plus `Retry-After` and request ID headers. No client-side retry loop is added.

## What's new in v1.8.0

- **Two distinct AI analyst modes:** `Market Analyst` summarizes the supplied crypto/global-market snapshot and recent RSS headlines; `Entry / Exit Analyst` reviews a small, liquid watchlist using the existing rule labels and 24-hour reference levels.
- **Specific default model:** uses `google/gemma-4-31b-it:free` through OpenRouter instead of the generic `openrouter/free` router. In v1.8.0, pre-existing model settings were preserved as-is; v1.8.1 adds the migration for old unversioned settings that still contain that previous default.
- **Clearer AI setup:** AI Settings links directly to the selected model page and explains that a user-provided OpenRouter API key is required. No API key is included in the app or repository.
- **Conservative entry/exit output:** the AI may only use supplied market numbers or calculate the midpoint of the stated 24-hour range. It must describe low/high values as references—not proven stop-loss or guaranteed take-profit levels—and acknowledge when data is missing.

## Features

- **INDODAX IDR pairs:** dynamic catalogue from the public API rather than a hard-coded coin list. The watchlist defaults to 24-hour IDR volume descending.
- **Global markets:** Gold futures, Brent/WTI crude, USD/IDR, S&P 500, Nasdaq Composite, IHSG, VIX, NVIDIA, Apple, Microsoft, and Indonesian stocks BBCA/BBRI/TLKM.
- **Crypto table:** local search by symbol/name, `All assets`/`Gainers`/`Losers`/`High volume` filters, sortable columns, and compact IDR volume formatting.
- **Global-market table:** filter by commodities, FX, indices, or stocks and sort by market, last price, daily change, technicals, or quote time.
- **Rule-based market read:** crypto breadth, BTC change/range, oil/gold/index context, and a cautious entry/exit checklist with per-asset action labels. It is an interpretation aid, not a trading signal.
- **Google News RSS:** optional feed; double-click a headline to open the source article. Publication times depend on the feed.
- **Optional OpenRouter AI:** separate `Market Analyst` and `Entry / Exit Analyst` buttons run only when pressed. AI is not called automatically on refresh. Default model: `google/gemma-4-31b-it:free`; availability and quotas can change.
- **Convenience:** manual refresh, automatic refresh, clock in WIB, optional always-on-top, and start-with-Windows controls. A desktop-shortcut helper and app icon are included.

## Action labels in plain language

These are watch labels based on a small set of 24-hour quote/range rules—not guaranteed buy/sell calls. The app does not know your entry price, quantity, or risk limit.

- **BUY WATCH / SELL REVIEW:** legacy dashboard labels based on 24-hour quotes, not direct trading calls. The dedicated v1.9.0 Entry / Exit signal block uses separate candle-confirmed rules.
- **BUY NOW:** all explicit engine gates passed on closed 1h candles and derived 4h trend, with liquidity/spread and BTC-regime checks. This is an unbacktested rules-based alert, not a guarantee or personalized instruction.
- **SELL / EXIT NOW:** bearish 1h and 4h trend plus RSI and volume confirmation passed the engine. The app does not know whether you own the asset or your cost basis; consider this a market-condition alert, not a personalized order.
- **WAIT:** not all buy/sell criteria are satisfied.
- **NO SIGNAL:** candle/quote freshness, history, bid/ask, volume, or spread data is insufficient for a direct signal.
- **NO BUY:** avoid opening a new position while price is falling hard near the 24-hour low.
- **WAIT / RISK:** momentum is negative; wait for stabilization and check risk if already holding.
- **HOLD / WAIT:** movement is relatively flat; no clear setup.
- **WAIT:** insufficient 24-hour change data to classify.
- **STALE / WAIT:** quote is too old to trust for a fresh decision.
- **NO DATA:** quote unavailable; no usable action signal.

**Entry vs. exit:** `BUY WATCH` is only a *possible entry to investigate*. `TP WATCH` and `SELL REVIEW` are *exit/position-review prompts*, not sell commands. Stop-loss is not personalized or automatically triggered by the app; set it before entering and follow your own risk rules.

## Using the tables

### Crypto

Use the search field to find an asset by symbol or name. Search is local and does not trigger additional network calls. Choose a quick filter next to it. `Compact rows` changes the row height of both tables; click a column heading to sort, and click the same heading again to reverse direction. Missing values stay at the bottom.

`Vol 24h IDR` uses compact units (`K`, `M`, `B`, `T`) so high-volume pairs fit the table. Low-priced assets retain decimal precision (for example, a price below Rp1 will not be rounded to `Rp0`). Quote timestamps are retained where the source provides them; stale quotes are marked and receive a non-actionable status. Select an asset row to view its conditional entry/exit references.

### Global markets

Select a category to narrow the 14 configured instruments. Stock/futures quotes generally move during the relevant exchange session and may look unchanged outside market hours, on holidays, or when Yahoo Finance has delayed/stale data. The app uses Yahoo Finance’s unofficial chart endpoint; it does not poll every instrument tick-by-tick. The crypto and global-market tables are side by side on page one. Drag the divider between panels to choose their widths. Use the horizontal scrollbar inside a table if a narrow display clips some columns.

## Install and run

1. Install **Python 3.11 or newer** from [python.org](https://www.python.org/downloads/windows/) and ensure Tkinter is available.
2. Extract the project folder to a permanent location.
3. Double-click `Run_Market_Radar.bat`. On first run it checks for CustomTkinter and attempts to install the dependency from `requirements.txt` if it is missing. An internet connection is required for that first installation.
4. To create a desktop shortcut with the app icon, keep the project in its permanent folder and double-click `Create_Desktop_Shortcut.bat`. The shortcut will point to that folder, so do not move the project afterward.
5. If startup fails, run `Run_Market_Radar_Debug.bat` to see the error output.

To install the dependency manually from PowerShell in the project folder:

```powershell
py -3 -m pip install -r requirements.txt
```

## Optional AI setup

1. Create a key at [OpenRouter API Keys](https://openrouter.ai/settings/keys). OpenRouter is the access platform; the model selected inside it is the AI used by Market Radar.
2. In the app, open **AI Settings** and paste your key. The default model is [Google Gemma 4 31B Instruct (free)](https://openrouter.ai/google/gemma-4-31b-it:free); the model ID is `google/gemma-4-31b-it:free`. The free tier is rate-limited and provider availability can change.
3. Save, then click **Market Analyst** for broader market context or **Entry / Exit Analyst** for conditional crypto setup reviews. Both use the same configured model but different instructions. They run only when clicked, never on every price refresh.

The API key is **not stored in source code or this repository**. On Windows, the app encrypts a saved key with Windows DPAPI and stores it outside the project at `%APPDATA%\MarketRadar\settings.json`. This file must not be uploaded to GitHub. You can remove the saved key from the AI Settings dialog. An `OPENROUTER_API_KEY` environment variable is also supported.

Manual AI calls consume the model/provider's available quota. Free access does not guarantee capacity, speed, or uninterrupted availability. API key, selected model ID, and returned model are shown/managed in AI Settings and the result window. The dashboard remains usable without AI.

## Data sources and refresh cadence

- **Crypto quotes:** `https://indodax.com/api/pairs` and `https://indodax.com/api/summaries` from the public INDODAX API.
- **Entry/exit technical candles:** INDODAX's documented public chart-history endpoint `/tradingview/history_v2` is requested only when Entry / Exit Analyst is clicked; up to 14 pairs are checked. The API documentation is in the [official INDODAX API repository](https://github.com/btcid/indodax-official-api-docs/blob/master/Public-RestAPI.md).
- **Commodities, FX, indices, and stocks:** Yahoo Finance chart endpoint (unofficial; the endpoint can change, quotes can be delayed, and requests can fail).
- **News:** Global Google News RSS for the dashboard; on-demand coin-name search for up to five Entry / Exit candidates. Results can be delayed, ambiguous, or unavailable.
- Crypto refresh: about **90 seconds**. Global-market refresh: about **5 minutes**. RSS refresh: about **15 minutes**. These run automatically; `Update now` remains available for a manual refresh. Macro values can remain unchanged if the underlying market is closed or the source has not published a new quote. Quote timestamps are shown where available.

## Tests

Run the offline tests from the project directory after installing `requirements.txt`:

```powershell
python -m unittest -v test_market_radar.py test_ai_modes.py
```

The tests cover legacy AI model-setting migration and OpenRouter HTTP error diagnostics, INDODAX pair parsing, OHLC normalization and unfinished-candle rejection, 4h aggregation, EMA/RSI/ATR metric calculation, direct BUY/SELL signal gates, liquidity and BTC regime filtering, asset-news snapshot fields, IDR formatting, old action labels, stale-quote handling, local search and filters, sorting, and AI analyst snapshot/prompts.

## Limitations and safety

Market read and AI answers can be wrong. Verify data and sources independently; nothing here predicts a guaranteed bottom, guarantees profit, or constitutes personal financial advice. `BUY WATCH`, `TP WATCH`, and `SELL REVIEW` are conditional labels, not instructions to place orders. Entry/midpoint, low and high references are calculated from the last reported 24-hour range, not validated by candle, volume-profile, or portfolio data. The dashboard only reads public data. It does not log in to INDODAX, access an exchange account or wallet, place orders, or trade.

## Files

- `market_radar.py` — application source.
- `Market_Radar.ico` — Windows/app icon.
- `Create_Desktop_Shortcut.bat` / `Create_Desktop_Shortcut.ps1` — creates a desktop shortcut to the project launcher.
- `Run_Market_Radar.bat` — normal launcher with a dependency check.
- `Run_Market_Radar_Debug.bat` — launcher with visible errors and dependency check.
- `requirements.txt` — CustomTkinter dependency.
- `test_market_radar.py` — offline tests.

## Preview

> Preview note: this screenshot uses synthetic layout-test values; figures shown are not live market quotes.

![Market Radar desktop preview](market-radar-preview.png)


## Historical backtest (research tool, separate from the app)

A standalone offline/online research script is available as `backtest.py`. It does **not** modify or run inside the desktop app, and does not place orders. It downloads closed 1-hour OHLC history from INDODAX in bounded 14-day chunks, evaluates the technical rules using only candles available at each signal close, and simulates fills at the **next candle open**. This avoids entering at the same close that created the signal.

From PowerShell in the project directory:

```powershell
python backtest.py --days 90 --symbols BTC,ETH,SOL,XRP,SUI,QNT,ASTER,ALT --fee-bps 30 --slippage-bps 10 --output backtest_results.json
```

The default starting capital is Rp10,000,000 **per asset**. Fee and slippage values are configurable estimates in basis points per side (30 bps = 0.30%; 10 bps = 0.10%). Check the fee schedule for your own account and rerun with realistic assumptions. The JSON report includes net profit after modeled costs, win rate, profit factor, maximum drawdown, and individual trades per asset. The default history window is 90 days; the script accepts 1–730 days, subject to what INDODAX actually returns. It records per-symbol data errors instead of silently treating missing history as a successful result.

**Important limitations before interpreting the report:**
- Historical bid/ask spread and the app's live quote-freshness checks cannot be reconstructed from OHLC alone; the live spread gate is therefore not reproduced.
- The 24-hour IDR turnover gate is estimated from candle volume × close. Confirm the volume units from returned data before trusting this filter.
- The script is a transparent technical-rule proxy, not a perfect replay of every live-app condition. Do not use its results as a promise or prediction of future profit.
- A backtest with too few trades, a short period, or one market regime is weak evidence. Inspect per-asset trade logs and test different periods/cost assumptions before considering changes to live BUY/SELL rules.

Run the existing application tests and the new backtest tests without launching the GUI:

```powershell
python -m unittest -v test_market_radar.py test_ai_modes.py test_backtest.py
```
