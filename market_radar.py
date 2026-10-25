#!/usr/bin/env python3
"""Market Radar: Windows desktop monitor using public market data only.
Crypto: official public INDODAX API. Macro: unofficial Yahoo Finance chart endpoint.
Headlines: optional Google News RSS. No trading or private credentials.
"""
from __future__ import annotations
import concurrent.futures
import json, math, os, sys, threading, time, urllib.parse, urllib.request, webbrowser
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
import tkinter as tk
from tkinter import ttk, messagebox

APP_NAME = "Market Radar"
APP_VERSION = "1.0.0"
WIB = timezone(timedelta(hours=7), name="WIB")
INDODAX_URL = "https://indodax.com/api/summaries"
INDODAX_DOCS = "https://github.com/btcid/indodax-official-api-docs"
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=3mo&interval=1d"
REFRESH_SECONDS, MACRO_REFRESH_SECONDS, NEWS_REFRESH_SECONDS = 90, 300, 900
HTTP_TIMEOUT = 12
CRYPTO_ASSETS = [("BTC", "Bitcoin"), ("ETH", "Ethereum"), ("SOL", "Solana"),
                 ("XRP", "XRP"), ("SUI", "Sui"), ("QNT", "Quant"),
                 ("ASTER", "Aster"), ("NEAR", "NEAR Protocol"), ("ALT", "AltLayer")]
MACRO_ASSETS = [
    ("GC=F", "Gold futures", "USD/oz", "commodity"),
    ("BZ=F", "Brent crude", "USD/bbl", "commodity"),
    ("CL=F", "WTI crude", "USD/bbl", "commodity"),
    ("USDIDR=X", "USD/IDR", "IDR/USD", "fx"),
    ("^GSPC", "S&P 500", "points", "index"),
    ("^IXIC", "Nasdaq Composite", "points", "index"),
    ("^JKSE", "IHSG (Jakarta)", "points", "index"),
    ("^VIX", "VIX volatility", "points", "index"),
    ("NVDA", "NVIDIA", "USD", "stock"),
    ("AAPL", "Apple", "USD", "stock"),
    ("MSFT", "Microsoft", "USD", "stock"),
    ("BBCA.JK", "Bank Central Asia", "IDR", "stock"),
    ("BBRI.JK", "Bank Rakyat Indonesia", "IDR", "stock"),
    ("TLKM.JK", "Telkom Indonesia", "IDR", "stock"),
]
COLORS = {"bg":"#0c111b", "panel":"#141d2b", "panel2":"#1b2738", "border":"#29364a",
          "text":"#e6edf7", "muted":"#93a4bb", "green":"#47d7a0", "red":"#ff737e",
          "yellow":"#f1c66d", "blue":"#77b6ff", "white":"#ffffff"}


def now_wib() -> datetime:
    return datetime.now(WIB)


def num(value: Any) -> float | None:
    try:
        if value is None or value == "": return None
        x = float(value)
        return x if math.isfinite(x) else None
    except (ValueError, TypeError, OverflowError):
        return None


def norm(s: str) -> str:
    return "".join(c for c in str(s).lower() if c.isalnum())


def find_key(mapping: dict[str, Any], target: str) -> str | None:
    target = norm(target)
    return next((k for k in mapping if norm(k) == target), None)


def fmt_idr(value: float | None) -> str:
    return "—" if value is None else "Rp" + f"{value:,.0f}".replace(",", ".")


def fmt_pct(value: float | None) -> str:
    return "—" if value is None else f"{value:+.2f}%"


def parse_epoch(value: Any) -> datetime | None:
    stamp = num(value)
    if stamp is None or stamp <= 0: return None
    if stamp > 10_000_000_000: stamp /= 1000.0
    try: return datetime.fromtimestamp(stamp, timezone.utc).astimezone(WIB)
    except (ValueError, OSError, OverflowError): return None


def age_text(dt: datetime | None) -> str:
    if not dt: return "waktu tidak tersedia"
    sec = max(0, int((now_wib() - dt).total_seconds()))
    if sec < 90: return f"{sec} dtk lalu"
    if sec < 3600: return f"{sec//60} mnt lalu"
    if sec < 86400: return f"{sec//3600} jam lalu"
    return f"{sec//86400} hari lalu"


def http_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": f"MarketRadar/{APP_VERSION}",
                                               "Accept": "application/json,text/plain,*/*"})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        if resp.status < 200 or resp.status >= 300: raise RuntimeError(f"HTTP {resp.status}")
        raw = resp.read(5_000_000)
    return json.loads(raw.decode("utf-8", errors="replace"))


def get_indodax_data() -> dict[str, dict[str, Any]]:
    payload = http_json(INDODAX_URL)
    tickers = payload.get("tickers", {}) if isinstance(payload, dict) else {}
    prices24 = payload.get("prices_24h", {}) if isinstance(payload, dict) else {}
    if not isinstance(tickers, dict): raise RuntimeError("Format respons INDODAX tidak memiliki 'tickers'.")
    output = {}
    for symbol, name in CRYPTO_ASSETS:
        tk_key = find_key(tickers, symbol.lower() + "idr")
        if tk_key is None:
            output[symbol] = {"symbol":symbol, "name":name, "available":False,
                              "error":"Pair IDR tidak ditemukan di respons INDODAX."}
            continue
        t = tickers.get(tk_key) or {}
        price, high, low = num(t.get("last")), num(t.get("high")), num(t.get("low"))
        prev_key = find_key(prices24, symbol.lower() + "idr") if isinstance(prices24, dict) else None
        prev = num(prices24.get(prev_key)) if prev_key else None
        change = (price / prev - 1) * 100 if price is not None and prev is not None and prev > 0 else None
        position = max(0, min(1, (price-low)/(high-low))) if price is not None and high is not None and low is not None and high > low else None
        output[symbol] = {"symbol":symbol,"name":name,"available":price is not None,"price":price,
                          "high":high,"low":low,"bid":num(t.get("buy")),"ask":num(t.get("sell")),
                          "volume_idr":num(t.get("vol_idr")),"change_pct":change,"previous_24h":prev,
                          "position":position,"market_time":parse_epoch(t.get("server_time")),
                          "retrieved_at":now_wib(),"source":"INDODAX public summaries API"}
    return output


def rsi14(closes: list[float], period: int = 14) -> float | None:
    if len(closes) <= period: return None
    moves = [closes[i]-closes[i-1] for i in range(1, len(closes))][-period:]
    gain = sum(max(x, 0) for x in moves) / period
    loss = sum(max(-x, 0) for x in moves) / period
    if loss == 0: return 100.0 if gain > 0 else 50.0
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def get_yahoo_quote(symbol: str, label: str, units: str, category: str) -> dict[str, Any]:
    url = YAHOO_URL.format(symbol=urllib.parse.quote(symbol, safe="^=.-"))
    payload = http_json(url)
    chart = payload.get("chart", {})
    if chart.get("error"): raise RuntimeError(str(chart["error"].get("description") or chart["error"]))
    results = chart.get("result") or []
    if not results: raise RuntimeError("Tidak ada data quote")
    result = results[0]
    meta = result.get("meta", {}) or {}
    stamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    closes = [float(x) for x in (quote.get("close") or []) if num(x) is not None]
    price = num(meta.get("regularMarketPrice"))
    if price is None and closes: price = closes[-1]
    prev = num(meta.get("previousClose")) or num(meta.get("chartPreviousClose"))
    if prev is None and len(closes) >= 2: prev = closes[-2]
    pct = (price / prev - 1) * 100 if price is not None and prev not in (None, 0) else None
    epoch = meta.get("regularMarketTime") or (stamps[-1] if stamps else None)
    return {"symbol":symbol,"name":label,"units":units,"category":category,"price":price,
            "previous_close":prev,"change_pct":pct,"market_time":parse_epoch(epoch),
            "sma20":sum(closes[-20:])/len(closes[-20:]) if closes else None,
            "rsi14":rsi14(closes),"source":"Yahoo Finance chart endpoint (unofficial)",
            "retrieved_at":now_wib(),"available":price is not None}


def get_macro_data() -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    names = {s:(n,u,c) for s,n,u,c in MACRO_ASSETS}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(get_yahoo_quote, s, n, u, c):s for s,n,u,c in MACRO_ASSETS}
        for fut in concurrent.futures.as_completed(futures):
            symbol = futures[fut]
            try: output[symbol] = fut.result()
            except Exception as exc:
                n,u,c = names[symbol]
                output[symbol] = {"symbol":symbol,"name":n,"units":u,"category":c,"available":False,"error":str(exc)}
    for s,n,u,c in MACRO_ASSETS:
        output.setdefault(s, {"symbol":s,"name":n,"units":u,"category":c,"available":False,"error":"Timeout mengambil data"})
    return output


def get_news() -> list[dict[str, Any]]:
    collected = []
    for query in ("US Iran oil Strait of Hormuz markets", "Bitcoin cryptocurrency market selloff"):
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q":query,"hl":"en-US","gl":"US","ceid":"US:en"})
        try:
            req = urllib.request.Request(url, headers={"User-Agent":f"MarketRadar/{APP_VERSION}"})
            with urllib.request.urlopen(req, timeout=8) as resp: raw = resp.read(1_000_000)
            root = ET.fromstring(raw)
            for item in root.findall("./channel/item"):
                title, link = (item.findtext("title") or "").strip(), (item.findtext("link") or "").strip()
                if title and link:
                    collected.append({"title":title,"link":link,"pubDate":item.findtext("pubDate") or "",
                                      "source":item.findtext("source") or "News"})
        except Exception: pass
    unique = {x["link"]:x for x in collected}
    return list(unique.values())[:12]


def setup_label(data: dict[str, Any]) -> tuple[str, str]:
    if not data or not data.get("available"): return "Data tidak tersedia", "neutral"
    pct, pos = data.get("change_pct"), data.get("position")
    if pct is None: return "Perubahan 24j tidak ada", "neutral"
    if pos is not None and pos <= .16 and pct <= -3: return "Dekat low; tunggu reclaim", "negative"
    if pos is not None and pos >= .82 and pct >= .5: return "Dekat high; hindari FOMO", "positive"
    if pct >= 1.5: return "Momentum positif; cek retest", "positive"
    if pct <= -3: return "Lemah; jangan tangkap jatuh", "negative"
    if -.75 <= pct <= .75: return "Konsolidasi / netral", "neutral"
    if pct > 0: return "Relatif kuat; tunggu setup", "positive"
    return "Masih terkoreksi", "negative"


def market_analysis(crypto: dict[str, dict[str, Any]], macro: dict[str, dict[str, Any]]) -> str:
    lines = ["MARKET READ · RULE-BASED, BUKAN SINYAL PASTI", "=" * 46]
    valid = [x for x in crypto.values() if x.get("available")]
    down = [x for x in valid if x.get("change_pct") is not None and x["change_pct"] < 0]
    btc = crypto.get("BTC", {})
    if valid: lines.append(f"Breadth kripto: {len(down)}/{len(valid)} aset dengan perubahan 24 jam negatif.")
    if btc.get("change_pct") is not None:
        pos = btc.get("position")
        pos_text = f"; posisi di {pos*100:.0f}% rentang low–high" if pos is not None else ""
        lines.append(f"BTC: {fmt_pct(btc['change_pct'])} dalam 24 jam{pos_text}.")

    def fresh(d: dict[str, Any]) -> bool:
        dt = d.get("market_time")
        return not dt or (now_wib() - dt).total_seconds() <= 36 * 3600
    oil, gold = macro.get("BZ=F", {}), macro.get("GC=F", {})
    nasdaq, spx, vix = macro.get("^IXIC", {}), macro.get("^GSPC", {}), macro.get("^VIX", {})
    # Do not use stale weekend/holiday quotes as if they were current-session movements.
    if not fresh(oil): oil = {}
    if not fresh(gold): gold = {}
    if not fresh(nasdaq): nasdaq = {}
    if not fresh(spx): spx = {}
    if not fresh(vix): vix = {}
    oil_pct, gold_pct = oil.get("change_pct"), gold.get("change_pct")
    nasdaq_pct, spx_pct = nasdaq.get("change_pct"), spx.get("change_pct")
    votes = 0
    if len(valid) and len(down)/len(valid) >= .65:
        votes += 1; lines.append("• Mayoritas watchlist kripto merah: tekanan jual tersebar pada aset yang tampil.")
    if oil_pct is not None and oil_pct >= 1 and ((spx_pct is not None and spx_pct < -.5) or (nasdaq_pct is not None and nasdaq_pct < -.5)):
        votes += 1; lines.append("• Minyak naik sementara indeks saham turun: kombinasi yang dapat menambah tekanan risk-off.")
    if btc.get("change_pct") is not None and btc["change_pct"] <= -2:
        votes += 1; lines.append("• BTC turun ≥2%: jangan menganggap koreksi sebagai bottom tanpa bukti pantulan.")
    if oil_pct is not None: lines.append(f"• Brent crude: {fmt_pct(oil_pct)} pada quote terakhir.")
    if gold_pct is not None: lines.append(f"• Gold futures: {fmt_pct(gold_pct)} pada quote terakhir.")
    if nasdaq_pct is not None: lines.append(f"• Nasdaq: {fmt_pct(nasdaq_pct)} pada quote terakhir.")
    if vix.get("available") and vix.get("price") is not None: lines.append(f"• VIX: {vix['price']:.2f} poin; bukan prediksi arah harga.")
    fx = macro.get("USDIDR=X", {})
    if fx.get("available") and fx.get("price") is not None and fresh(fx):
        if gold.get("available") and gold.get("price") is not None:
            grams_idr = gold["price"] * fx["price"] / 31.1034768
            lines.append(f"• Estimasi emas futures: sekitar {fmt_idr(grams_idr)}/gram ekuivalen spot (dari USD/oz × USD/IDR; bukan harga emas Antam).")
        if oil.get("available") and oil.get("price") is not None:
            lines.append(f"• Brent ekuivalen: sekitar {fmt_idr(oil['price']*fx['price'])}/barel (konversi futures USD; bukan harga BBM lokal).")
    macro_available = sum(1 for x in macro.values() if x.get("available"))
    if macro_available == 0:
        lines.append("Data komoditas/indeks belum berhasil diambil; kesimpulan makro belum tersedia.")
    elif votes >= 2:
        lines.append("\nKESIMPULAN: bias waspada / risk-off berdasarkan indikator yang tersedia; bukan prediksi tanggal bottom.")
    elif votes == 1:
        lines.append("\nKESIMPULAN: sinyal campuran dengan beberapa tanda kehati-hatian; tunggu konfirmasi.")
    else:
        lines.append("\nKESIMPULAN: data belum menunjukkan sinyal risk-off yang kuat. Tetap periksa quote dan tren.")
    lines.extend(["", "ATURAN ENTRY", "• Jangan beli hanya karena harga menyentuh low 24 jam.",
                  "• Tunggu reclaim level lalu retest yang bertahan; perubahan 24 jam saja tidak cukup.",
                  "• Stop loss tidak menjamin harga eksekusi yang sama saat volatilitas tinggi.", "",
                  "Batasan: kesimpulan berbasis aturan sederhana dari data publik; bukan ramalan AI atau nasihat finansial personal."])
    return "\n".join(lines)


class MarketRadarApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title(f"{APP_NAME} {APP_VERSION} — Global Market Dashboard")
        root.geometry("1200x730+30+25")
        root.minsize(980, 590)
        root.configure(bg=COLORS["bg"])
        root.attributes("-topmost", True)
        self.closing = False
        self.refreshing = False
        self.crypto_data: dict[str, dict[str, Any]] = {}
        self.macro_data: dict[str, dict[str, Any]] = {}
        self.news_data: list[dict[str, Any]] = []
        self.last_macro_fetch = 0.0
        self.last_news_fetch = 0.0
        self.auto_top_var = tk.BooleanVar(value=True)
        self.auto_start_var = tk.BooleanVar(value=self._autostart_path().exists())
        self.interval_var = tk.StringVar(value="90 detik")
        self._setup_style()
        self._build_ui()
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(300, self.refresh_data)
        root.after(1000, self._clock_tick)
        root.after(REFRESH_SECONDS*1000, self._auto_refresh_tick)

    def _setup_style(self) -> None:
        s = ttk.Style(self.root)
        try: s.theme_use("clam")
        except tk.TclError: pass
        s.configure("TFrame", background=COLORS["bg"])
        s.configure("TLabel", background=COLORS["bg"], foreground=COLORS["text"], font=("Segoe UI", 9))
        s.configure("Title.TLabel", background=COLORS["bg"], foreground=COLORS["text"], font=("Segoe UI Semibold", 18, "bold"))
        s.configure("Subtitle.TLabel", background=COLORS["bg"], foreground=COLORS["muted"], font=("Segoe UI", 9))
        s.configure("TButton", background=COLORS["panel2"], foreground=COLORS["text"], bordercolor=COLORS["border"], padding=(10,5), font=("Segoe UI",9))
        s.map("TButton", background=[("active", "#2a3a50")])
        s.configure("TCheckbutton", background=COLORS["bg"], foreground=COLORS["text"], font=("Segoe UI",9))
        s.map("TCheckbutton", background=[("active", COLORS["bg"])])
        s.configure("Treeview", background=COLORS["panel"], fieldbackground=COLORS["panel"], foreground=COLORS["text"], rowheight=25, borderwidth=0, font=("Segoe UI",9))
        s.configure("Treeview.Heading", background=COLORS["panel2"], foreground=COLORS["text"], font=("Segoe UI Semibold",9,"bold"), padding=(5,6), relief="flat")
        s.map("Treeview", background=[("selected", "#2b4361")], foreground=[("selected", COLORS["white"])])

    def _build_ui(self) -> None:
        header = ttk.Frame(self.root, padding=(16,12,16,8)); header.pack(fill="x")
        box = ttk.Frame(header); box.pack(side="left", fill="x", expand=True)
        ttk.Label(box, text="MARKET RADAR", style="Title.TLabel").pack(anchor="w")
        ttk.Label(box, text="Crypto · Gold · Oil · US/Indonesia markets · rule-based market read", style="Subtitle.TLabel").pack(anchor="w", pady=(2,0))
        controls = ttk.Frame(header); controls.pack(side="right", anchor="ne")
        self.update_button = ttk.Button(controls, text="↻ Update now", command=self.refresh_data)
        self.update_button.grid(row=0,column=0,padx=(0,6),pady=(0,4))
        ttk.Checkbutton(controls,text="Always on top",variable=self.auto_top_var,command=self.toggle_topmost).grid(row=0,column=1,padx=5)
        ttk.Checkbutton(controls,text="Start with Windows",variable=self.auto_start_var,command=self.toggle_autostart).grid(row=0,column=2,padx=5)
        ttk.Button(controls,text="API docs",command=lambda:webbrowser.open(INDODAX_DOCS)).grid(row=0,column=3,padx=(6,0))
        self.clock_label = ttk.Label(controls,text="WIB --:--:--",style="Subtitle.TLabel")
        self.clock_label.grid(row=1,column=0,columnspan=4,sticky="e",pady=(5,0))
        self.status_var = tk.StringVar(value="Menghubungkan ke sumber data publik…")
        tk.Label(self.root,textvariable=self.status_var,bg=COLORS["panel2"],fg=COLORS["muted"],anchor="w",padx=16,pady=6,font=("Segoe UI",9)).pack(fill="x",padx=16,pady=(0,8))

        cards=ttk.Frame(self.root,padding=(16,0,16,10)); cards.pack(fill="x")
        self.card_vars: dict[str,tk.StringVar] = {}
        for i,(key,label) in enumerate([("BTC","Bitcoin / IDR"),("ETH","Ethereum / IDR"),("GC=F","Gold futures"),("BZ=F","Brent crude")]):
            cards.columnconfigure(i,weight=1)
            frame=tk.Frame(cards,bg=COLORS["panel"],highlightbackground=COLORS["border"],highlightthickness=1)
            frame.grid(row=0,column=i,sticky="nsew",padx=(0 if i==0 else 7,0))
            tk.Label(frame,text=label.upper(),bg=COLORS["panel"],fg=COLORS["muted"],font=("Segoe UI",8,"bold")).pack(anchor="w",padx=12,pady=(9,2))
            var=tk.StringVar(value="Loading…"); self.card_vars[key]=var
            tk.Label(frame,textvariable=var,bg=COLORS["panel"],fg=COLORS["text"],font=("Segoe UI Semibold",13,"bold")).pack(anchor="w",padx=12,pady=(0,10))

        body=ttk.Frame(self.root,padding=(16,0,16,12)); body.pack(fill="both",expand=True)
        body.columnconfigure(0,weight=3,minsize=580); body.columnconfigure(1,weight=2,minsize=350); body.rowconfigure(0,weight=1)
        left=ttk.Frame(body); left.grid(row=0,column=0,sticky="nsew",padx=(0,8))
        left.columnconfigure(0,weight=1); left.rowconfigure(0,weight=3); left.rowconfigure(1,weight=2)
        p=self._make_panel(left,"CRYPTO WATCHLIST · INDODAX IDR"); p.grid(row=0,column=0,sticky="nsew",pady=(0,8))
        cols=("asset","price","change","range","setup")
        self.crypto_tree=ttk.Treeview(p,columns=cols,show="headings",height=9)
        # Keep the quote timestamp visible so cached/old prices are less likely to look live.
        cols=("asset","price","change","range","asof","setup")
        self.crypto_tree.configure(columns=cols)
        headers={"asset":"Asset","price":"Last (IDR)","change":"24h","range":"Range pos.","asof":"Quote WIB","setup":"Market read"}
        widths={"asset":100,"price":130,"change":65,"range":68,"asof":85,"setup":190}
        for c in cols:
            self.crypto_tree.heading(c,text=headers[c]); self.crypto_tree.column(c,width=widths[c],minwidth=55,stretch=(c=="setup"),anchor="w" if c in ("asset","setup") else "e")
        self._tags(self.crypto_tree)
        crypto_scroll=ttk.Scrollbar(p,orient="vertical",command=self.crypto_tree.yview); crypto_scroll.pack(side="right",fill="y",padx=(0,6),pady=(0,8))
        self.crypto_tree.configure(yscrollcommand=crypto_scroll.set); self.crypto_tree.pack(fill="both",expand=True,padx=8,pady=(0,8))
        p=self._make_panel(left,"GLOBAL MARKETS · COMMODITIES, FX, INDICES & STOCKS"); p.grid(row=1,column=0,sticky="nsew")
        cols=("asset","price","change","technicals","asof")
        self.macro_tree=ttk.Treeview(p,columns=cols,show="headings",height=9)
        headers={"asset":"Market","price":"Last","change":"Daily","technicals":"Trend / RSI","asof":"Quote time (WIB)"}
        widths={"asset":135,"price":120,"change":75,"technicals":105,"asof":130}
        for c in cols:
            self.macro_tree.heading(c,text=headers[c]); self.macro_tree.column(c,width=widths[c],minwidth=55,stretch=(c=="asset"),anchor="w" if c in ("asset","technicals","asof") else "e")
        self._tags(self.macro_tree)
        macro_scroll=ttk.Scrollbar(p,orient="vertical",command=self.macro_tree.yview); macro_scroll.pack(side="right",fill="y",padx=(0,6),pady=(0,8))
        self.macro_tree.configure(yscrollcommand=macro_scroll.set); self.macro_tree.pack(fill="both",expand=True,padx=8,pady=(0,8))

        right=ttk.Frame(body); right.grid(row=0,column=1,sticky="nsew")
        right.columnconfigure(0,weight=1); right.rowconfigure(0,weight=3); right.rowconfigure(1,weight=2)
        p=self._make_panel(right,"MARKET READ & ACTION CHECKLIST"); p.grid(row=0,column=0,sticky="nsew",pady=(0,8))
        self.analysis_text=tk.Text(p,wrap="word",bg=COLORS["panel"],fg=COLORS["text"],insertbackground=COLORS["text"],relief="flat",padx=12,pady=8,font=("Consolas",9),state="disabled",height=20)
        analysis_scroll=ttk.Scrollbar(p,orient="vertical",command=self.analysis_text.yview); analysis_scroll.pack(side="right",fill="y",padx=(0,4),pady=(0,8))
        self.analysis_text.configure(yscrollcommand=analysis_scroll.set); self.analysis_text.pack(fill="both",expand=True,padx=2,pady=(0,8))
        p=self._make_panel(right,"GLOBAL HEADLINES · DOUBLE-CLICK TO OPEN"); p.grid(row=1,column=0,sticky="nsew")
        self.news_list=tk.Listbox(p,bg=COLORS["panel"],fg=COLORS["text"],selectbackground="#2b4361",selectforeground=COLORS["white"],borderwidth=0,highlightthickness=0,activestyle="dotbox",font=("Segoe UI",9),height=7)
        news_scroll=ttk.Scrollbar(p,orient="vertical",command=self.news_list.yview); news_scroll.pack(side="right",fill="y",padx=(0,4),pady=(0,4))
        self.news_list.configure(yscrollcommand=news_scroll.set); self.news_list.pack(fill="both",expand=True,padx=8,pady=(0,4)); self.news_list.bind("<Double-Button-1>",self.open_selected_news)
        self.news_footer=ttk.Label(p,text="RSS dapat tertunda; cek tanggal dan sumber asli.",style="Subtitle.TLabel",wraplength=400)
        self.news_footer.pack(anchor="w",padx=8,pady=(0,8))
        tk.Label(self.root,text="Public data only · No trading or wallet access · Yahoo quotes are unofficial and may be delayed · Not financial advice",bg=COLORS["bg"],fg=COLORS["muted"],anchor="w",padx=16,pady=(0,8),font=("Segoe UI",8)).pack(fill="x")

    def _make_panel(self,parent:ttk.Frame,title:str)->tk.Frame:
        panel=tk.Frame(parent,bg=COLORS["panel"],highlightbackground=COLORS["border"],highlightthickness=1)
        tk.Label(panel,text=title,bg=COLORS["panel"],fg=COLORS["muted"],anchor="w",font=("Segoe UI Semibold",9,"bold")).pack(fill="x",padx=10,pady=(8,5))
        return panel

    def _tags(self,tree:ttk.Treeview)->None:
        tree.tag_configure("positive",foreground=COLORS["green"])
        tree.tag_configure("negative",foreground=COLORS["red"])
        tree.tag_configure("neutral",foreground=COLORS["text"])
        tree.tag_configure("stale",foreground=COLORS["yellow"])

    def _clock_tick(self)->None:
        if not self.closing:
            self.clock_label.configure(text=now_wib().strftime("%A, %d %b %Y · %H:%M:%S WIB"))
            self.root.after(1000,self._clock_tick)

    def _auto_refresh_tick(self)->None:
        if self.closing:return
        if not self.refreshing:self.refresh_data()
        try: interval=int(self.interval_var.get().split()[0])
        except Exception:interval=REFRESH_SECONDS
        self.root.after(max(30,interval)*1000,self._auto_refresh_tick)

    def refresh_data(self)->None:
        if self.refreshing or self.closing:return
        self.refreshing=True; self.update_button.configure(state="disabled",text="Loading…")
        self.status_var.set("Memperbarui INDODAX, komoditas, indeks, saham dan headline…")
        need_macro=(time.monotonic()-self.last_macro_fetch>=MACRO_REFRESH_SECONDS) or not self.macro_data
        need_news=(time.monotonic()-self.last_news_fetch>=NEWS_REFRESH_SECONDS)
        threading.Thread(target=self._refresh_worker,args=(need_macro,need_news),daemon=True).start()

    def _refresh_worker(self,need_macro:bool,need_news:bool)->None:
        errors=[]; crypto=None; macro=None; news=None
        try: crypto=get_indodax_data()
        except Exception as exc:errors.append(f"INDODAX: {exc}")
        if need_macro:
            try:macro=get_macro_data()
            except Exception as exc:errors.append(f"Pasar global: {exc}")
        if need_news:
            try:news=get_news()
            except Exception as exc:errors.append(f"News: {exc}")
        retrieved=now_wib()
        self.root.after(0,lambda:self._apply_refresh(crypto,macro,news,errors,retrieved,need_macro,need_news))

    def _apply_refresh(self,crypto:Any,macro:Any,news:Any,errors:list[str],retrieved:datetime,need_macro:bool,need_news:bool)->None:
        if self.closing:return
        if crypto is not None:self.crypto_data=crypto
        if macro is not None:self.macro_data=macro; self.last_macro_fetch=time.monotonic()
        if news is not None:self.news_data=news; self.last_news_fetch=time.monotonic()
        self._render_crypto();self._render_macro();self._render_cards();self._render_analysis();self._render_news()
        self.refreshing=False;self.update_button.configure(state="normal",text="↻ Update now")
        if errors:
            self.status_var.set(f"Refresh dicek {retrieved.strftime('%d %b %Y %H:%M:%S WIB')} · sebagian sumber gagal: {'; '.join(errors)[:220]} · data terakhir yang berhasil tetap ditampilkan")
        else:
            count_crypto=sum(1 for d in self.crypto_data.values() if d.get("available"));count_macro=sum(1 for d in self.macro_data.values() if d.get("available"))
            self.status_var.set(f"Refresh dicek {retrieved.strftime('%d %b %Y %H:%M:%S WIB')} · INDODAX {count_crypto}/{len(CRYPTO_ASSETS)} aset · pasar global {count_macro}/{len(MACRO_ASSETS)} quote")

    def _render_crypto(self)->None:
        for item in self.crypto_tree.get_children():self.crypto_tree.delete(item)
        for symbol,name in CRYPTO_ASSETS:
            d=self.crypto_data.get(symbol,{})
            if not d.get("available"):
                self.crypto_tree.insert("","end",iid=symbol,values=(symbol,"N/A","—","—","—",d.get("error","Tidak tersedia")),tags=("stale",));continue
            setup,tag=setup_label(d);pos=d.get("position")
            dt=d.get("market_time"); asof=dt.strftime("%H:%M:%S") if dt else "fetch time"
            if dt and (now_wib()-dt).total_seconds()>600: asof += " stale"; tag="stale"
            self.crypto_tree.insert("","end",iid=symbol,values=(f"{symbol} · {name}",fmt_idr(d.get("price")),fmt_pct(d.get("change_pct")),f"{pos*100:.0f}%" if pos is not None else "—",asof,setup),tags=(tag,))

    def _macro_price(self,d:dict[str,Any])->str:
        p=d.get("price")
        if p is None:return "N/A"
        units=d.get("units","")
        if d.get("symbol")=="USDIDR=X" or units=="IDR":return "Rp"+f"{p:,.0f}".replace(",",".")
        if units=="USD/oz":return f"${p:,.2f}/oz"
        if units=="USD/bbl":return f"${p:,.2f}/bbl"
        if units=="USD":return f"${p:,.2f}"
        if units=="points":return f"{p:,.2f}"
        return f"{p:.2f}"

    def _render_macro(self)->None:
        for item in self.macro_tree.get_children():self.macro_tree.delete(item)
        for symbol,name,units,category in MACRO_ASSETS:
            d=self.macro_data.get(symbol,{})
            if not d.get("available"):
                self.macro_tree.insert("","end",iid=symbol,values=(name,"N/A","—","—","unavailable"),tags=("stale",));continue
            dt=d.get("market_time");age=age_text(dt)
            stale=bool(dt and (now_wib()-dt).total_seconds()>36*3600)
            if stale:age+=" · stale";tag="stale"
            else:tag="positive" if (d.get("change_pct") or 0)>0 else "negative" if (d.get("change_pct") or 0)<0 else "neutral"
            rsi=d.get("rsi14");sma=d.get("sma20");technical=f"RSI {rsi:.0f}" if rsi is not None else ""
            if sma is not None and d.get("price") is not None:technical+=(" · " if technical else "")+("above SMA20" if d["price"]>=sma else "below SMA20")
            self.macro_tree.insert("","end",iid=symbol,values=(name,self._macro_price(d),fmt_pct(d.get("change_pct")),technical or "—",age),tags=(tag,))

    def _render_cards(self)->None:
        for key in ("BTC","ETH"):
            d=self.crypto_data.get(key,{})
            self.card_vars[key].set(f"{fmt_idr(d.get('price'))}   {fmt_pct(d.get('change_pct'))}" if d.get("available") else "N/A · cek koneksi")
        for key in ("GC=F","BZ=F"):
            d=self.macro_data.get(key,{})
            self.card_vars[key].set(f"${d['price']:,.2f}   {fmt_pct(d.get('change_pct'))}" if d.get("available") else "N/A · data belum tersedia")

    def _render_analysis(self)->None:
        self.analysis_text.configure(state="normal");self.analysis_text.delete("1.0","end")
        self.analysis_text.insert("1.0",market_analysis(self.crypto_data,self.macro_data))
        self.analysis_text.configure(state="disabled")

    def _render_news(self)->None:
        self.news_list.delete(0,"end")
        if not self.news_data:
            self.news_list.insert("end","Headline belum tersedia; periksa koneksi RSS.")
            self.news_footer.configure(text="Feed berita opsional. Kegagalan feed tidak memengaruhi harga market.")
            return
        for item in self.news_data[:12]:
            title=item.get("title","(tanpa judul)")
            if len(title)>125:title=title[:122]+"..."
            self.news_list.insert("end",f"{item.get('source') or 'News'} · {title}")
        self.news_footer.configure(text="Double-click untuk membuka artikel. Periksa timestamp dan sumber asli.")

    def open_selected_news(self,_event:Any=None)->None:
        sel=self.news_list.curselection()
        if sel and sel[0]<len(self.news_data):webbrowser.open(self.news_data[sel[0]].get("link",""))

    def toggle_topmost(self)->None:self.root.attributes("-topmost",bool(self.auto_top_var.get()))

    def _autostart_path(self)->Path:
        appdata=os.environ.get("APPDATA")
        if appdata:return Path(appdata)/"Microsoft"/"Windows"/"Start Menu"/"Programs"/"Startup"/"MarketRadar.vbs"
        return Path.home()/"MarketRadar.vbs"

    def toggle_autostart(self)->None:
        path=self._autostart_path()
        try:
            if self.auto_start_var.get():
                path.parent.mkdir(parents=True,exist_ok=True)
                python_exe=Path(sys.executable)
                pythonw=python_exe.with_name("pythonw.exe")
                if not pythonw.exists():pythonw=python_exe
                script=Path(__file__).resolve()
                path.write_text('Set WshShell = CreateObject("WScript.Shell")\n'+f'WshShell.Run Chr(34) & "{pythonw}" & Chr(34) & " " & Chr(34) & "{script}" & Chr(34), 0, False\n',encoding="utf-8")
                messagebox.showinfo(APP_NAME,"Auto-start aktif. Market Radar akan terbuka saat lu login ke Windows.")
            else:
                if path.exists():path.unlink()
                messagebox.showinfo(APP_NAME,"Auto-start dinonaktifkan.")
        except Exception as exc:
            self.auto_start_var.set(path.exists());messagebox.showerror(APP_NAME,f"Gagal mengubah auto-start:\n{exc}")

    def close(self)->None:
        self.closing=True
        try:self.root.destroy()
        except tk.TclError:pass


def main()->None:
    root=tk.Tk()
    MarketRadarApp(root)
    root.mainloop()

if __name__=="__main__":
    main()
