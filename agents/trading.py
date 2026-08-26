#!/usr/bin/env python3
"""Jarvis market data collector — stdlib only, no pip required.

Sources:
  Stocks / ETFs / Indices → Yahoo Finance (free, no key)
  Crypto                  → CoinGecko (free, no key)
  TCG cards               → agents/scraper.py

Usage:
  python3 agents/trading.py AAPL BTC SPY
  python3 agents/trading.py ^IBEX ^GSPC ETH
  python3 agents/trading.py --watchlist           # reads agents/watchlist.txt
"""
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

HEADERS = {"User-Agent": "Mozilla/5.0 (Jarvis/1.0)", "Accept": "application/json"}

CRYPTO_IDS = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "XRP": "ripple",
    "ADA": "cardano", "DOGE": "dogecoin", "BNB": "binancecoin", "AVAX": "avalanche-2",
    "MATIC": "matic-network", "DOT": "polkadot", "LINK": "chainlink",
    "UNI": "uniswap", "LTC": "litecoin", "BCH": "bitcoin-cash",
    "SHIB": "shiba-inu", "TRX": "tron", "TON": "the-open-network",
    "ATOM": "cosmos", "XLM": "stellar", "FIL": "filecoin",
}


# ── HTTP ──────────────────────────────────────────────────────────────

def _fetch(url: str, timeout=12, as_json=True):
    req = urllib.request.Request(url, headers=HEADERS)
    last_err = None
    for verified in (True, False):
        ctx = ssl.create_default_context()
        if not verified:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                raw = resp.read()
                return json.loads(raw) if as_json else raw.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"HTTP {e.code}")
        except urllib.error.URLError as e:
            if not verified:
                raise RuntimeError(str(e))
            last_err = e
    raise RuntimeError(str(last_err))


# ── Yahoo Finance ─────────────────────────────────────────────────────

def _yfinance(symbol: str) -> dict:
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{urllib.parse.quote(symbol)}?interval=1d&range=5d"
    )
    data = _fetch(url)
    result = data["chart"]["result"][0]
    meta   = result["meta"]
    closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
    closes = [c for c in closes if c is not None]
    return {
        "name":     meta.get("longName") or meta.get("shortName") or symbol,
        "currency": meta.get("currency", "USD"),
        "price":    meta.get("regularMarketPrice") or (closes[-1] if closes else None),
        "prev":     meta.get("chartPreviousClose") or (closes[-2] if len(closes) >= 2 else None),
        "week_open": closes[0] if closes else None,
        "volume":   meta.get("regularMarketVolume"),
    }


def stock(symbol: str) -> str:
    try:
        d = _yfinance(symbol)
    except (RuntimeError, KeyError, IndexError) as e:
        return f"⚠️  {symbol}: error obteniendo datos ({e})"

    price    = d["price"]
    prev     = d["prev"]
    wk_open  = d["week_open"]
    currency = d["currency"]

    lines = [f"📈 {symbol} — {d['name']}"]
    if price is not None:
        lines.append(f"  Precio: {price:.2f} {currency}")
    if price and prev:
        chg = (price - prev) / prev * 100
        sign = "+" if chg >= 0 else ""
        lines.append(f"  Hoy:    {prev:.2f} → {price:.2f} ({sign}{chg:.2f}%)")
    if price and wk_open and wk_open != prev:
        wk_chg = (price - wk_open) / wk_open * 100
        sign   = "+" if wk_chg >= 0 else ""
        lines.append(f"  Semana: {wk_open:.2f} → {price:.2f} ({sign}{wk_chg:.2f}%)")
    if d.get("volume"):
        vol = d["volume"]
        lines.append(f"  Volumen: {vol/1e6:.1f}M" if vol > 1e6 else f"  Volumen: {vol:,}")
    return "\n".join(lines)


# ── CoinGecko ─────────────────────────────────────────────────────────

def _coingecko_id(symbol: str) -> str:
    sid = symbol.upper()
    if sid in CRYPTO_IDS:
        return CRYPTO_IDS[sid]
    # Search by symbol
    try:
        data = _fetch(f"https://api.coingecko.com/api/v3/search?query={urllib.parse.quote(sid)}")
        coins = data.get("coins", [])
        for c in coins:
            if c.get("symbol", "").upper() == sid:
                return c["id"]
        if coins:
            return coins[0]["id"]
    except RuntimeError:
        pass
    return sid.lower()


def crypto(symbol: str) -> str:
    cid = _coingecko_id(symbol)
    try:
        url = (
            f"https://api.coingecko.com/api/v3/coins/markets"
            f"?vs_currency=eur&ids={urllib.parse.quote(cid)}"
            f"&price_change_percentage=24h,7d&sparkline=false"
        )
        coins = _fetch(url)
        if not coins:
            return f"⚠️  {symbol}: no encontrado en CoinGecko (id={cid})"
        c = coins[0]
    except RuntimeError as e:
        return f"⚠️  {symbol}: {e}"

    price   = c.get("current_price")
    chg_24h = c.get("price_change_percentage_24h")
    chg_7d  = c.get("price_change_percentage_7d_in_currency")
    high    = c.get("high_24h")
    low     = c.get("low_24h")
    mcap    = c.get("market_cap")

    lines = [f"🪙 {symbol.upper()} — {c.get('name', symbol)}"]
    if price is not None:
        lines.append(f"  Precio: {price:,.4f} EUR")
    if chg_24h is not None:
        s = "+" if chg_24h >= 0 else ""
        lines.append(f"  24h:    {s}{chg_24h:.2f}%")
    if chg_7d is not None:
        s = "+" if chg_7d >= 0 else ""
        lines.append(f"  7d:     {s}{chg_7d:.2f}%")
    if high and low:
        lines.append(f"  Rango:  {low:,.4f} – {high:,.4f} EUR")
    if mcap:
        lines.append(f"  Market cap: {mcap/1e9:.2f}B EUR")
    return "\n".join(lines)


# ── TCG cards ─────────────────────────────────────────────────────────

def tcg(name: str, game: str = "magic") -> str:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    scraper    = os.path.join(script_dir, "scraper.py")
    import subprocess
    result = subprocess.run(
        [sys.executable, scraper, game, name],
        capture_output=True, text=True, timeout=30
    )
    out = result.stdout.strip() or result.stderr.strip()
    return out or f"⚠️  No se encontró '{name}' ({game})"


# ── News (DuckDuckGo) ─────────────────────────────────────────────────

def _news(query: str) -> str:
    url = (
        f"https://api.duckduckgo.com/?q={urllib.parse.quote(query + ' noticias precio')}"
        f"&format=json&no_html=1&skip_disambig=1"
    )
    try:
        data = _fetch(url)
        parts = []
        if data.get("AbstractText"):
            parts.append(data["AbstractText"][:200])
        for t in data.get("RelatedTopics", [])[:2]:
            if isinstance(t, dict) and t.get("Text"):
                parts.append(t["Text"][:120])
        return " | ".join(parts) if parts else ""
    except RuntimeError:
        return ""


# ── Asset dispatcher ──────────────────────────────────────────────────

def analyze(symbol: str, tcg_game: str = "") -> str:
    sym = symbol.strip()
    if not sym:
        return ""

    if tcg_game:
        return tcg(sym, tcg_game)

    if sym.upper() in CRYPTO_IDS:
        result = crypto(sym)
    else:
        # Try to detect if it's a known crypto not in our table
        result = stock(sym)

    news = _news(sym)
    if news:
        result += f"\n  Contexto: {news[:180]}"
    return result


# ── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]

    if not args:
        print(__doc__)
        sys.exit(1)

    # --watchlist mode
    if "--watchlist" in args:
        wl_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "watchlist.txt")
        if not os.path.exists(wl_path):
            print(f"No watchlist found at {wl_path}")
            sys.exit(1)
        with open(wl_path) as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        assets = []
        for line in lines:
            parts = line.split()
            if len(parts) >= 3 and parts[1] == "tcg":
                assets.append((parts[0], parts[2]))
            else:
                assets.append((parts[0], ""))
    else:
        # Parse positional args: symbol [--tcg GAME symbol ...]
        assets = []
        i = 0
        while i < len(args):
            if args[i] == "--tcg" and i + 2 < len(args):
                game = args[i + 1]
                name = args[i + 2]
                assets.append((name, game))
                i += 3
            else:
                assets.append((args[i], ""))
                i += 1

    blocks = []
    for sym, game in assets:
        blocks.append(analyze(sym, tcg_game=game))

    print("\n\n".join(b for b in blocks if b))
