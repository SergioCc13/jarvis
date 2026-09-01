#!/usr/bin/env python3
"""Charts for the market analysis.

Two modes:
  render()        — small-multiples price sparkline grid (raw price history)
  render_scores()  — ranked bar chart of the 0-100 score bin/analiza's Claude
                     prompt asks for per ticker (the actual analysis output,
                     not just price) — this is the one bin/analiza uses.

Reuses trading.py's fetch/dispatch helpers. Colors follow the dataviz skill's
validated status palette (good/critical), used here as "up/down" or
"buy/sell", not series identity — no legend needed for single-series panels
or a single-metric bar chart.

Usage:
  python3 agents/charts.py AAPL NVDA TSLA BTC ETH SPY ^IBEX -o /tmp/mercado.png
  python3 agents/charts.py --watchlist -o /tmp/mercado.png
  echo "$SUMMARY" | python3 agents/charts.py --scores -o /tmp/mercado.png
"""
import os
import re
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trading import _fetch, _coingecko_id, CRYPTO_IDS  # noqa: E402  (reuse existing fetch/dispatch)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# Dark chart surface + status colors from the dataviz skill's validated
# palette (references/palette.md) — not the HUD's own warm palette, since
# this needs to stay validated for contrast independent of that.
SURFACE        = "#1a1a19"
TEXT_PRIMARY   = "#ffffff"
TEXT_SECONDARY = "#c3c2b7"
GOOD           = "#0ca30c"
CRITICAL       = "#d03b3b"


def _history_stock(symbol: str, days: int):
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{urllib.parse.quote(symbol)}?interval=1d&range={days}d"
    )
    data = _fetch(url)
    result = data["chart"]["result"][0]
    closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
    closes = [c for c in closes if c is not None]
    currency = result["meta"].get("currency", "USD")
    return closes, currency


def _history_crypto(symbol: str, days: int):
    cid = _coingecko_id(symbol)
    url = (
        f"https://api.coingecko.com/api/v3/coins/{urllib.parse.quote(cid)}"
        f"/market_chart?vs_currency=eur&days={days}"
    )
    data = _fetch(url)
    prices = [p[1] for p in data.get("prices", [])]
    return prices, "EUR"


def history(symbol: str, days: int = 30):
    sym = symbol.strip()
    if sym.upper() in CRYPTO_IDS:
        return _history_crypto(sym, days)
    return _history_stock(sym, days)


def render(symbols: list[str], out_path: str, days: int = 30, title: str = "Jarvis · Mercado") -> str:
    n = len(symbols)
    cols = 3 if n > 4 else (2 if n > 1 else 1)
    rows = (n + cols - 1) // cols

    fig, axes = plt.subplots(rows, cols, figsize=(4 * cols, 2.2 * rows), facecolor=SURFACE)
    fig.suptitle(title, color=TEXT_PRIMARY, fontsize=14, fontweight="bold")
    axes_flat = list(axes.flatten()) if n > 1 else [axes]

    for i, sym in enumerate(symbols):
        ax = axes_flat[i]
        ax.set_facecolor(SURFACE)
        try:
            closes, currency = history(sym, days)
        except Exception:
            closes, currency = [], ""

        if len(closes) < 2:
            ax.text(0.5, 0.5, f"{sym}\nsin datos", ha="center", va="center",
                     color=TEXT_SECONDARY, fontsize=9, transform=ax.transAxes)
            ax.set_xticks([]); ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_visible(False)
            continue

        chg = (closes[-1] - closes[0]) / closes[0] * 100
        color = GOOD if chg >= 0 else CRITICAL
        xs = range(len(closes))
        ax.plot(xs, closes, color=color, linewidth=2, solid_capstyle="round")
        ax.fill_between(xs, closes, min(closes), color=color, alpha=0.08)

        sign = "+" if chg >= 0 else ""
        ax.set_title(f"{sym}  {closes[-1]:,.2f} {currency}  ({sign}{chg:.1f}%)",
                     color=TEXT_PRIMARY, fontsize=10, loc="left", pad=6)
        ax.set_xticks([]); ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)

    for j in range(len(symbols), len(axes_flat)):
        axes_flat[j].axis("off")

    fig.patch.set_facecolor(SURFACE)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(out_path, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    return out_path


def parse_analysis(text: str) -> list[dict]:
    """Pull (ticker, score, recommendation) out of the '### TICKER' /
    '- Puntuación (...): N' / '- Recomendación: X' blocks that bin/analiza's
    prompt asks Claude to produce. Skips any ticker it can't parse cleanly
    rather than guessing a score."""
    entries = []
    ticker, score, rec = None, None, None

    def flush():
        if ticker is not None and score is not None and rec is not None:
            entries.append({"ticker": ticker, "score": score, "rec": rec})

    for line in text.splitlines():
        m = re.match(r"^#{2,3}\s+(\S+)", line.strip())
        if m:
            flush()
            ticker, score, rec = m.group(1), None, None
            continue
        m = re.search(r"Puntuaci[oó]n.*?:\s*(\d+)", line)
        if m:
            score = int(m.group(1))
            continue
        m = re.search(r"Recomendaci[oó]n:\s*(.+)", line)
        if m:
            rec = m.group(1).strip()
    flush()
    return entries


# Recommendation text -> bar color. Falls back to a neutral gray for
# anything that doesn't match one of the labels the prompt asks for.
_REC_COLORS = {
    "compra fuerte": "#0ca30c",
    "compra floja":  "#4fb84f",
    "neutral":       "#8a8a86",
    "venta floja":   "#e0716a",
    "venta fuerte":  "#d03b3b",
}


def render_scores(entries: list[dict], out_path: str, title: str = "Jarvis · Mercado — puntuación") -> str:
    entries = sorted(entries, key=lambda e: e["score"], reverse=True)
    fig, ax = plt.subplots(figsize=(7, 0.55 * len(entries) + 1), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)

    ys = range(len(entries))
    for y, e in zip(ys, entries):
        color = _REC_COLORS.get(e["rec"].strip().lower(), TEXT_SECONDARY)
        ax.barh(y, e["score"], color=color, height=0.6)
        ax.text(e["score"] + 2, y, f"{e['score']}  ·  {e['rec']}", va="center",
                 color=TEXT_PRIMARY, fontsize=9)

    ax.set_yticks(list(ys))
    ax.set_yticklabels([e["ticker"] for e in entries], color=TEXT_PRIMARY, fontsize=10)
    ax.invert_yaxis()  # highest score on top
    ax.set_xlim(0, 100)
    ax.set_xticks([0, 50, 100])
    ax.tick_params(axis="x", colors=TEXT_SECONDARY, labelsize=8)
    ax.set_title(title, color=TEXT_PRIMARY, fontsize=13, fontweight="bold", loc="left", pad=12)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.axvline(0, color=TEXT_SECONDARY, linewidth=0.6, alpha=0.4)

    fig.patch.set_facecolor(SURFACE)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    return out_path


if __name__ == "__main__":
    args = sys.argv[1:]
    out = "/tmp/jarvis-mercado.png"
    if "-o" in args:
        idx = args.index("-o")
        out = args[idx + 1]
        args = args[:idx] + args[idx + 2:]

    if "--scores" in args:
        text = sys.stdin.read()
        entries = parse_analysis(text)
        if not entries:
            print("No pude extraer ninguna puntuación del texto en stdin", file=sys.stderr)
            sys.exit(1)
        print(render_scores(entries, out))
        sys.exit(0)

    if "--watchlist" in args:
        args.remove("--watchlist")
        wl_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "watchlist.txt")
        if not os.path.exists(wl_path):
            print(f"No watchlist found at {wl_path}", file=sys.stderr)
            sys.exit(1)
        with open(wl_path) as f:
            symbols = []
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) >= 3 and parts[1] == "tcg":
                    continue  # charts.py only handles stocks/crypto, not TCG cards
                symbols.append(parts[0])
    else:
        symbols = args

    if not symbols:
        print("Uso: python3 agents/charts.py SYMBOL... [-o path.png]", file=sys.stderr)
        sys.exit(1)

    path = render(symbols, out)
    print(path)
