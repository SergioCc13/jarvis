#!/usr/bin/env python3
"""Jarvis — seguimiento diario de la watchlist. Stdlib pura, sin pip.

Diferencia con `bin/analiza`: analiza no filtra y resume TODO cada día.
`seguimiento` calcula indicadores (RSI, medias, 52 semanas, volumen), guarda
histórico en SQLite, y SOLO llama al LLM para los tickers que disparan una
señal. Los días tranquilos no gastan tokens y no molestan.

Comandos:
  python3 agents/seguimiento.py scan               # barrido, imprime tabla
  python3 agents/seguimiento.py scan --json        # + volcado JSON
  python3 agents/seguimiento.py scan --notify      # + veredicto LLM y Telegram
  python3 agents/seguimiento.py scan --notify --email    # + también por email (standalone)
  python3 agents/seguimiento.py scan --notify --always   # notifica aunque no haya señales
  python3 agents/seguimiento.py score [--days 14]  # ¿cómo se movieron los flags pasados?
  python3 agents/seguimiento.py db-path

El digest queda en vault/outputs/seguimiento.md; bin/analiza lo adjunta a su email diario.

Cron (Pi), diario, 5 min antes de bin/analiza:
  0 8 * * * cd /home/pi/jarvis && bin/seguimiento >> /tmp/jarvis-seguimiento.log 2>&1
"""
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.parse
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)          # reutiliza el fetch endurecido de trading.py
sys.path.insert(0, os.path.join(REPO, "bridge"))   # bridge/notify.py

from trading import _fetch, CRYPTO_IDS, _coingecko_id  # noqa: E402


def _get(url, tries=3):
    """_fetch de trading.py + reintento con backoff ante HTTP 429 (CoinGecko free)."""
    for i in range(tries):
        try:
            return _fetch(url)
        except RuntimeError as e:
            if "429" in str(e) and i < tries - 1:
                time.sleep(3 * (i + 1))
                continue
            raise

DB_PATH  = os.path.join(REPO, "vault", "raw", "seguimiento.db")
VAULT_MD = os.path.join(REPO, "vault", "outputs", "seguimiento.md")
WATCHLIST = os.path.join(HERE, "watchlist.txt")

# ── Umbrales (ajústalos; overridables por env JARVIS_SEG_*) ───────────

def _env_f(name, default):
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default

TH = {
    "chg_1d_abs":  _env_f("JARVIS_SEG_CHG_1D", 4.0),    # % mov. diario que dispara
    "chg_5d_abs":  _env_f("JARVIS_SEG_CHG_5D", 8.0),    # % mov. semanal
    "vol_ratio":   _env_f("JARVIS_SEG_VOL",    2.0),    # volumen hoy / media 20d
    "rsi_hot":     _env_f("JARVIS_SEG_RSI_HI", 75.0),
    "rsi_cold":    _env_f("JARVIS_SEG_RSI_LO", 25.0),
    "near_52w":    _env_f("JARVIS_SEG_52W",    2.0),    # % de distancia a máx/mín 52s
}


# ── Indicadores (funciones puras sobre listas de floats) ──────────────

def sma(values, n):
    if len(values) < n:
        return None
    return sum(values[-n:]) / n


def rsi(values, n=14):
    if len(values) < n + 1:
        return None
    deltas = [values[i + 1] - values[i] for i in range(len(values) - 1)]
    gains  = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]
    avg_g  = sum(gains[:n]) / n
    avg_l  = sum(losses[:n]) / n
    for i in range(n, len(deltas)):
        avg_g = (avg_g * (n - 1) + gains[i]) / n
        avg_l = (avg_l * (n - 1) + losses[i]) / n
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return 100.0 - 100.0 / (1.0 + rs)


def pct(a, b):
    if a is None or b in (None, 0):
        return None
    return (a - b) / b * 100.0


# ── Series de precio/volumen ─────────────────────────────────────────

def series_yahoo(symbol):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(symbol)}?interval=1d&range=1y")
    data = _get(url)
    r = data["chart"]["result"][0]
    meta = r["meta"]
    q = r.get("indicators", {}).get("quote", [{}])[0]
    closes = [c for c in (q.get("close") or []) if c is not None]
    vols   = [v for v in (q.get("volume") or []) if v is not None]
    return {
        "kind": "stock",
        "name": meta.get("longName") or meta.get("shortName") or symbol,
        "currency": meta.get("currency", "USD"),
        "closes": closes,
        "volumes": vols,
        "price": meta.get("regularMarketPrice") or (closes[-1] if closes else None),
        "high_52w": meta.get("fiftyTwoWeekHigh") or (max(closes) if closes else None),
        "low_52w":  meta.get("fiftyTwoWeekLow")  or (min(closes) if closes else None),
    }


def series_crypto(symbol):
    # una sola llamada a CoinGecko (free tier va justo de rate-limit)
    cid = _coingecko_id(symbol)
    chart = _get(f"https://api.coingecko.com/api/v3/coins/{urllib.parse.quote(cid)}"
                 f"/market_chart?vs_currency=eur&days=365")
    closes = [p[1] for p in chart.get("prices", [])]
    vols   = [v[1] for v in chart.get("total_volumes", [])]
    return {
        "kind": "crypto",
        "name": symbol.upper(),
        "currency": "EUR",
        "closes": closes,
        "volumes": vols,
        "price": closes[-1] if closes else None,
        "high_52w": max(closes) if closes else None,
        "low_52w":  min(closes) if closes else None,
    }


# ── Snapshot + detección de eventos ─────────────────────────────────

def build_snapshot(symbol):
    # cripto conocida -> CoinGecko; lo demás (acciones, ETFs, índices ^X) -> Yahoo
    if symbol.upper() in CRYPTO_IDS:
        s = series_crypto(symbol)
    else:
        s = series_yahoo(symbol)

    c = s["closes"]
    price = s["price"]
    snap = {
        "symbol": symbol,
        "asof": date.today().isoformat(),
        "name": s["name"],
        "kind": s["kind"],
        "currency": s["currency"],
        "price": price,
        "chg_1d":  pct(price, c[-2]) if len(c) >= 2 else None,
        "chg_5d":  pct(price, c[-6]) if len(c) >= 6 else None,
        "chg_20d": pct(price, c[-21]) if len(c) >= 21 else None,
        "rsi_14":  rsi(c, 14),
        "sma_50":  sma(c, 50),
        "sma_200": sma(c, 200),
        "high_52w": s["high_52w"],
        "low_52w":  s["low_52w"],
        "vol_ratio": None,
    }
    v = s["volumes"]
    if len(v) >= 21 and v[-1]:
        base = sum(v[-21:-1]) / 20
        if base:
            snap["vol_ratio"] = v[-1] / base
    if price and snap["high_52w"]:
        snap["dist_high"] = (price / snap["high_52w"] - 1) * 100
    if price and snap["low_52w"]:
        snap["dist_low"] = (price / snap["low_52w"] - 1) * 100
    return snap


def detect_events(snap, prev):
    ev = []
    d1, d5 = snap.get("chg_1d"), snap.get("chg_5d")
    if d1 is not None and abs(d1) >= TH["chg_1d_abs"]:
        ev.append(f"movimiento diario {d1:+.1f}%")
    if d5 is not None and abs(d5) >= TH["chg_5d_abs"]:
        ev.append(f"movimiento 5d {d5:+.1f}%")
    vr = snap.get("vol_ratio")
    if vr is not None and vr >= TH["vol_ratio"]:
        ev.append(f"volumen x{vr:.1f} vs media 20d")
    r = snap.get("rsi_14")
    if r is not None and r >= TH["rsi_hot"]:
        ev.append(f"RSI {r:.0f} (sobrecompra)")
    if r is not None and r <= TH["rsi_cold"]:
        ev.append(f"RSI {r:.0f} (sobreventa)")
    dh = snap.get("dist_high")
    if dh is not None and dh >= -TH["near_52w"]:
        ev.append("a menos del 2% del máximo de 52 semanas")
    dl = snap.get("dist_low")
    if dl is not None and dl <= TH["near_52w"]:
        ev.append("a menos del 2% del mínimo de 52 semanas")
    # cruce de medias vs snapshot anterior
    if prev and None not in (snap.get("sma_50"), snap.get("sma_200"),
                             prev.get("sma_50"), prev.get("sma_200")):
        now  = snap["sma_50"] - snap["sma_200"]
        was  = prev["sma_50"] - prev["sma_200"]
        if was <= 0 < now:
            ev.append("cruce alcista de medias 50/200 (golden cross)")
        elif was >= 0 > now:
            ev.append("cruce bajista de medias 50/200 (death cross)")
    return ev


# ── Almacén SQLite ─────────────────────────────────────────────────

def _db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS snapshots("
                 "symbol TEXT, asof TEXT, json TEXT, PRIMARY KEY(symbol, asof))")
    conn.execute("CREATE TABLE IF NOT EXISTS flags("
                 "symbol TEXT, asof TEXT, events TEXT, price REAL, ret REAL, "
                 "PRIMARY KEY(symbol, asof))")
    return conn


def prev_snapshot(conn, symbol, today):
    row = conn.execute("SELECT json FROM snapshots WHERE symbol=? AND asof<? "
                       "ORDER BY asof DESC LIMIT 1", (symbol, today)).fetchone()
    return json.loads(row[0]) if row else None


def save(conn, snap, events):
    conn.execute("INSERT OR REPLACE INTO snapshots VALUES (?,?,?)",
                 (snap["symbol"], snap["asof"], json.dumps(snap)))
    if events:
        conn.execute("INSERT OR REPLACE INTO flags(symbol, asof, events, price) "
                     "VALUES (?,?,?,?)",
                     (snap["symbol"], snap["asof"], "; ".join(events), snap["price"]))
    conn.commit()


# ── Watchlist ──────────────────────────────────────────────────────

def read_watchlist():
    out = []
    with open(WATCHLIST) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "tcg":
                continue  # las cartas TCG no tienen indicadores; las cubre bin/analiza
            out.append(parts[0])
    return out


# ── Veredicto LLM (una sola llamada, solo si hay señales) ───────────

def llm_digest(today, triggered):
    lines = [f"Fecha: {today}", "", "Activos de la watchlist con señales hoy:"]
    for t in triggered:
        s = t["snap"]
        def f(x, suf="%"):
            return f"{x:+.1f}{suf}" if isinstance(x, (int, float)) else "n/d"
        price_str = (f"{s['price']:.2f} {s['currency']}"
                     if isinstance(s.get("price"), (int, float)) else "n/d")
        lines.append(
            f"- {s['symbol']} ({s['name']}): {price_str} | "
            f"1d {f(s.get('chg_1d'))}, 5d {f(s.get('chg_5d'))}, 20d {f(s.get('chg_20d'))} | "
            f"RSI {s.get('rsi_14') and round(s['rsi_14'])} | "
            f"vs máx52s {f(s.get('dist_high'))}, vs mín52s {f(s.get('dist_low'))} | "
            f"SMA50 {s.get('sma_50') and round(s['sma_50'], 2)} / "
            f"SMA200 {s.get('sma_200') and round(s['sma_200'], 2)} | "
            f"vol x{s.get('vol_ratio') and round(s['vol_ratio'], 1)}")
        lines.append(f"    señales: {', '.join(t['events'])}")

    prompt = (
        "Eres un analista que hace SEGUIMIENTO de la watchlist de Sergio. "
        "NO das órdenes de compra ni de venta.\n\n"
        + "\n".join(lines)
        + "\n\nPara cada activo escribe 2-3 frases: qué ha pasado (citando los datos), "
        "y si merece que lo revise HOY o solo vigilarlo. No inventes cifras que no estén arriba. "
        "Termina con una línea de resumen general. "
        "Español, texto plano, un bullet por activo, máximo 200 palabras."
    )
    try:
        r = subprocess.run(["claude", "-p", "--output-format", "text"],
                           input=prompt, capture_output=True, text=True, timeout=150)
        body = r.stdout.strip()
    except Exception:
        body = ""
    if not body:
        body = "\n".join(f"• {t['snap']['symbol']}: {'; '.join(t['events'])}"
                         for t in triggered)
    return body


# ── Comandos ───────────────────────────────────────────────────────

def cmd_scan(argv):
    want_json   = "--json" in argv
    want_notify = "--notify" in argv
    always      = "--always" in argv
    want_email  = "--email" in argv   # además de Telegram, manda el digest por email
    today = date.today().isoformat()

    conn = _db()
    results = []
    watch = read_watchlist()
    for i, sym in enumerate(watch):
        try:
            snap = build_snapshot(sym)
        except Exception as e:
            print(f"⚠️  {sym}: {e}", file=sys.stderr)
            continue
        events = detect_events(snap, prev_snapshot(conn, sym, today))
        save(conn, snap, events)
        results.append({"snap": snap, "events": events})
        if i < len(watch) - 1:
            time.sleep(1.0)   # cortesía con Yahoo / CoinGecko free

    # tabla legible
    print(f"[seguimiento] {today}")
    hdr = f"{'SÍMBOLO':<10} {'PRECIO':>12} {'1d':>7} {'5d':>7} {'RSI':>5} {'vs52máx':>9}  SEÑALES"
    print(hdr)
    print("-" * len(hdr))
    for r in results:
        s = r["snap"]
        def g(x, w, suf=""):
            return (f"{x:{w}.1f}{suf}" if isinstance(x, (int, float)) else f"{'n/d':>{w}}")
        print(f"{s['symbol']:<10} {g(s.get('price'), 12)} "
              f"{g(s.get('chg_1d'), 6)}% {g(s.get('chg_5d'), 6)}% "
              f"{g(s.get('rsi_14'), 5)} {g(s.get('dist_high'), 8)}%  "
              f"{'; '.join(r['events']) if r['events'] else '—'}")

    if want_json:
        print("\n--- JSON ---")
        print(json.dumps(results, ensure_ascii=False, indent=2))

    if not want_notify:
        return

    triggered = [r for r in results if r["events"]]
    if triggered:
        body = llm_digest(today, triggered)
        digest = f"📊 Watchlist {today} — {len(triggered)} con señales\n\n{body}"
    else:
        digest = f"🟢 Watchlist {today} — sin novedades. Todo dentro de rango."

    print("\n--- Digest ---")
    print(digest)
    print("---")

    os.makedirs(os.path.dirname(VAULT_MD), exist_ok=True)
    with open(VAULT_MD, "w") as f:
        f.write(f"# Seguimiento {today}\n\n{digest}\n")

    if triggered or always:
        import notify  # bridge/notify.py
        chans = ["telegram"] + (["email"] if want_email else [])
        res = notify.dispatch(digest, channels=chans, voice_for_telegram=False,
                              subject=f"Jarvis: Seguimiento {today}")
        for ch, (ok, detail) in res.items():
            print(f"  {'✓' if ok else '✗'} {ch}: {detail}")
    else:
        print("  (sin señales: guardado en vault, no se notifica)")


def cmd_score(argv):
    days = 14
    if "--days" in argv:
        try:
            days = int(argv[argv.index("--days") + 1])
        except (ValueError, IndexError):
            pass
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    conn = _db()
    rows = conn.execute("SELECT symbol, asof, events, price FROM flags "
                        "WHERE asof<=? ORDER BY asof DESC LIMIT 60", (cutoff,)).fetchall()
    if not rows:
        print(f"Sin flags anteriores a {cutoff}.")
        return
    print(f"Flags de hace >= {days} días — evolución desde que se marcaron:\n")
    ok = 0
    for sym, asof, events, price in rows:
        try:
            now = build_snapshot(sym)["price"]
            ret = (now - price) / price * 100
        except Exception as e:
            print(f"  {sym:<8} {asof}  error: {e}")
            continue
        conn.execute("UPDATE flags SET ret=? WHERE symbol=? AND asof=?", (ret, sym, asof))
        flag = "↑" if ret >= 0 else "↓"
        if ret >= 0:
            ok += 1
        print(f"  {sym:<8} {asof}  {price:>10.2f} → {now:>10.2f}  {ret:+6.1f}% {flag}   [{events}]")
    conn.commit()
    print(f"\n{ok}/{len(rows)} flags con retorno positivo desde la marca "
          f"(no es rendimiento de estrategia, solo diagnóstico del filtro).")


def main():
    argv = sys.argv[1:]
    cmd = argv[0] if argv else "scan"
    if cmd == "scan":
        cmd_scan(argv[1:])
    elif cmd == "score":
        cmd_score(argv[1:])
    elif cmd == "db-path":
        print(DB_PATH)
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
