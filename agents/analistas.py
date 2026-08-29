#!/usr/bin/env python3
"""Jarvis — análisis de mercado multi-agente, estilo TauricResearch/TradingAgents.

Por cada activo de la watchlist ejecuta una cadena de roles (cada uno es una
llamada a `claude -p`, cada rol ve el trabajo de los anteriores):

  1. Analista técnico / cuantitativo   — lee datos + indicadores, solo hechos
  2. Analista de contexto y eventos    — catalizadores, próximo evento
  3. Investigador ALCISTA              — mejor tesis de compra
  4. Investigador BAJISTA              — rebate y construye el caso bajista
  5. Trader                            — sopesa el debate, decisión preliminar
  6. Gestor de riesgo / cartera        — veredicto FINAL en el formato del email

Al terminar todos, un rol de cartera escribe la visión de conjunto que
encabeza el informe. Todo se ensambla en el email diario "Jarvis: Mercado".

Coste: ~6 llamadas por activo + 1. Con 21 activos ≈ 127 llamadas / ejecución.

Stdlib pura. Reutiliza agents/trading.py (datos) y agents/seguimiento.py (indicadores).

Uso:
  python3 agents/analistas.py                 # watchlist completa, imprime informe
  python3 agents/analistas.py --notify        # + email + Telegram (resumen)
  python3 agents/analistas.py --only BTC ETH  # solo esos activos (para probar)
  python3 agents/analistas.py --limit 3       # solo los 3 primeros de la watchlist
"""
import os
import subprocess
import sys
import time
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "bridge"))

from trading import analyze as raw_analyze          # noqa: E402
from seguimiento import build_snapshot              # noqa: E402

WATCHLIST = os.path.join(HERE, "watchlist.txt")
VAULT_MD  = os.path.join(REPO, "vault", "outputs", "mercado.md")

CLAUDE_TIMEOUT = int(os.environ.get("JARVIS_AGENTS_TIMEOUT", "200"))

FAIL_MARKER = "fallo en la cadena de análisis"


# ── LLM ──────────────────────────────────────────────────────────────

class LLMUnavailable(RuntimeError):
    """El backend (claude -p) no está disponible: límite de sesión/uso, quota, etc."""


# Frases que claude -p emite por stdout cuando NO ha respondido de verdad.
_LIMIT_MARKERS = ("session limit", "usage limit", "hit your limit",
                  "quota", "rate limit", "resets ", "please try again later")


def ask(prompt: str) -> str:
    """Una llamada a claude -p. Reintenta ante vacío/timeout.
    Si detecta un mensaje de límite de sesión/uso, lanza LLMUnavailable
    (para abortar la corrida en vez de rellenar el informe con basura)."""
    last = ""
    for attempt in (1, 2, 3):
        try:
            r = subprocess.run(
                ["claude", "-p", "--output-format", "text"],
                input=prompt, capture_output=True, text=True, timeout=CLAUDE_TIMEOUT,
            )
            out = (r.stdout or "").strip()
            err = (r.stderr or "").strip()
        except subprocess.TimeoutExpired:
            out, err = "", "timeout"
        low = f"{out}\n{err}".lower()
        if any(m in low for m in _LIMIT_MARKERS):
            raise LLMUnavailable((out or err)[:200])
        if out:
            return out
        last = err or out
        time.sleep(3 * attempt)
    return last  # vacío o stderr no-crítico; el llamador decide


# ── Roles ────────────────────────────────────────────────────────────

FINAL_FORMAT = """- Puntuación (0-100, donde 0 = no comprar y 100 = compra asegurada): <n>
- Recomendación: <Compra fuerte | Compra floja | Neutral | Venta floja | Venta fuerte>
- Plazo: <Corto plazo | Largo plazo>
- Precio objetivo de entrada: <valor y divisa, o "no procede — ..." o "datos insuficientes para un objetivo fiable">
- Precio objetivo de salida: <valor y divisa, o "no procede" o "datos insuficientes para un objetivo fiable">
- Próximo evento relevante: <evento y fecha, o "sin evento próximo conocido">
- Justificación: <2-3 frases citando cifras concretas del análisis previo>"""

ROLES = [
    ("tecnico",
     "Eres el analista técnico y cuantitativo del equipo. Con los DATOS DE MERCADO e "
     "INDICADORES de abajo, describe en 4-6 líneas: tendencia (precio frente a SMA50 y "
     "SMA200), momentum (RSI 14 y cambios 1d/5d/20d), volumen frente a su media, y "
     "posición respecto a máximos/mínimos de 52 semanas. Solo hechos, sin recomendación."),
    ("contexto",
     "Eres el analista de contexto y eventos. Con el CONTEXTO DE NOTICIAS y la fecha de "
     "hoy, resume en 3-4 líneas los catalizadores próximos (resultados, dividendos, "
     "reuniones de bancos centrales, macro) y el riesgo de evento. Si no hay datos "
     "fiables, dilo. Cierra con una línea exacta: 'Próximo evento relevante: ...'."),
    ("alcista",
     "Eres el investigador ALCISTA. Con el análisis técnico y de contexto de abajo, "
     "construye en 4-6 líneas la tesis de compra más sólida y honesta posible. Apóyate "
     "en cifras concretas del análisis."),
    ("bajista",
     "Eres el investigador BAJISTA. Rebate la tesis alcista y construye en 4-6 líneas el "
     "caso de vender o esperar, con cifras concretas. Señala los riesgos que el alcista "
     "minimiza."),
    ("trader",
     "Eres el trader. Sopesa el debate alcista vs bajista y decide en 4-6 líneas: "
     "recomendación preliminar (compra fuerte/floja, neutral, venta floja/fuerte), plazo "
     "(corto o largo), y un rango de entrada y otro de salida con divisa. Justifica breve."),
    ("riesgo",
     "Eres el gestor de riesgo y responsable de cartera. Revisa la decisión del trader y "
     "ajústala por riesgo: liquidez y volumen, sobrecompra/sobreventa (RSI), evento "
     "próximo, y caída potencial si la tesis falla. Para instrumentos no invertibles "
     "directamente (p. ej. ^VIX, índices de volatilidad) indícalo en los precios objetivo. "
     "Emite el veredicto FINAL respondiendo EXACTAMENTE con estas 7 líneas y NADA más "
     "(sin encabezados, sin texto extra):\n\n" + FINAL_FORMAT),
]


def analyze_asset(symbol: str) -> dict:
    """Ejecuta la cadena completa de roles para un activo. Devuelve dict con el bloque final."""
    try:
        raw = raw_analyze(symbol)
    except Exception as e:
        raw = f"(sin datos de mercado: {e})"
    try:
        s = build_snapshot(symbol)
        ind = (
            f"precio {s.get('price')}, 1d {s.get('chg_1d')}, 5d {s.get('chg_5d')}, "
            f"20d {s.get('chg_20d')}, RSI14 {s.get('rsi_14')}, "
            f"SMA50 {s.get('sma_50')}, SMA200 {s.get('sma_200')}, "
            f"máx52s {s.get('high_52w')} (dist {s.get('dist_high')}%), "
            f"mín52s {s.get('low_52w')} (dist {s.get('dist_low')}%), "
            f"vol_ratio {s.get('vol_ratio')}"
        )
    except Exception as e:
        ind = f"(sin indicadores: {e})"

    today = date.today().isoformat()
    dossier = (
        f"ACTIVO: {symbol}\nFECHA: {today}\n\n"
        f"DATOS DE MERCADO / CONTEXTO DE NOTICIAS:\n{raw}\n\n"
        f"INDICADORES:\n{ind}\n"
    )

    outputs = {}
    for key, instruction in ROLES:
        prompt = (
            f"{instruction}\n\n"
            f"═══ EXPEDIENTE DEL ACTIVO ═══\n{dossier}\n"
            + ("═══ TRABAJO PREVIO DEL EQUIPO ═══\n"
               + "\n\n".join(f"[{k.upper()}]\n{v}" for k, v in outputs.items())
               if outputs else "")
        )
        out = ask(prompt)
        outputs[key] = out or "(sin salida)"
        time.sleep(0.5)

    final = outputs.get("riesgo", "").strip()
    if not final or "Puntuación" not in final:
        final = (
            "- Puntuación (0-100, donde 0 = no comprar y 100 = compra asegurada): 50\n"
            "- Recomendación: Neutral\n- Plazo: Largo plazo\n"
            "- Precio objetivo de entrada: datos insuficientes para un objetivo fiable\n"
            "- Precio objetivo de salida: datos insuficientes para un objetivo fiable\n"
            "- Próximo evento relevante: sin evento próximo conocido\n"
            f"- Justificación: {FAIL_MARKER}; lectura del trader: "
            f"{outputs.get('trader', 'n/d')[:240]}"
        )
    return {"symbol": symbol, "block": final, "debate": outputs}


# ── Watchlist ────────────────────────────────────────────────────────

def read_watchlist():
    out = []
    with open(WATCHLIST) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "tcg":
                continue
            out.append(parts[0])
    return out


# ── Ensamblado ───────────────────────────────────────────────────────

def portfolio_summary(results, today):
    blocks = "\n\n".join(f"### {r['symbol']}\n{r['block']}" for r in results)
    prompt = (
        "Eres el responsable de cartera. Abajo están los veredictos finales de "
        f"{len(results)} activos analizados hoy ({today}). Escribe 4-6 líneas de visión "
        "de conjunto: sesgo general del mercado, 2-3 mayores oportunidades (con su "
        "puntuación) y 2-3 mayores riesgos. Texto plano, sin markdown, sin repetir todos "
        "los activos.\n\n" + blocks
    )
    try:
        return ask(prompt)
    except LLMUnavailable as e:
        return f"(visión de cartera no disponible: {e})"


def assemble(results, today):
    parts = [f"# Mercado {today} — análisis multi-agente\n"]
    summary = portfolio_summary(results, today)
    if summary:
        parts.append("## Visión de cartera\n\n" + summary + "\n")
    for r in results:
        parts.append(f"### {r['symbol']}\n{r['block']}\n")
    return "\n".join(parts)


def parse_report(path):
    """Lee un mercado.md ya generado → dict ordenado {symbol: block}."""
    blocks, cur, buf = {}, None, []
    for line in open(path, encoding="utf-8").read().splitlines():
        if line.startswith("### "):
            if cur is not None:
                blocks[cur] = "\n".join(buf).strip()
            cur, buf = line[4:].strip(), []
        elif cur is not None:
            buf.append(line)
    if cur is not None:
        blocks[cur] = "\n".join(buf).strip()
    return blocks


def dispatch_report(report, today, n_assets):
    import notify as _n  # bridge/notify.py
    # Email: informe completo. Telegram: solo la visión de cartera (límite 4096).
    res = _n.dispatch(report, channels=["email"], subject=f"Jarvis: Mercado {today}")
    for ch, (ok, detail) in res.items():
        print(f"  {'✓' if ok else '✗'} {ch}: {detail}")
    tg = report.split("### ", 1)[0].strip() + \
        f"\n\n(Informe completo de {n_assets} activos en el email.)"
    res = _n.dispatch(tg, channels=["telegram"], voice_for_telegram=False)
    for ch, (ok, detail) in res.items():
        print(f"  {'✓' if ok else '✗'} {ch}: {detail}")


def save_report(report):
    os.makedirs(os.path.dirname(VAULT_MD), exist_ok=True)
    with open(VAULT_MD, "w", encoding="utf-8") as f:
        f.write(report + "\n")
    print(f"[analistas] guardado en {VAULT_MD}")


# ── Main ─────────────────────────────────────────────────────────────

def _parse_args(argv):
    opts = {"notify": "--notify" in argv, "patch": "--patch" in argv,
            "limit": None, "only": []}
    skip = set()
    for i, a in enumerate(argv):
        if i in skip or a in ("--notify", "--patch", "--only"):
            continue
        if a == "--limit":
            try:
                opts["limit"] = int(argv[i + 1]); skip.add(i + 1)
            except (ValueError, IndexError):
                pass
        elif not a.startswith("--"):
            opts["only"].append(a)
    return opts


def run_patch(opts, today):
    """Re-analiza SOLO los bloques fallidos de un mercado.md existente y reenvía."""
    if not os.path.exists(VAULT_MD):
        print(f"[analistas] no hay {VAULT_MD} que parchear"); sys.exit(1)
    blocks = parse_report(VAULT_MD)
    bad = [s for s, b in blocks.items()
           if FAIL_MARKER in b or "Puntuación (0-100" not in b
           or "no disponible" in b]
    if opts["only"]:
        bad = [s for s in bad if s in opts["only"]] or opts["only"]
    if not bad:
        print("[analistas] nada que parchear: todos los bloques están completos")
        return
    print(f"[analistas] parche {today} — re-analizando {len(bad)}: {', '.join(bad)}")
    for n, sym in enumerate(bad, 1):
        t0 = time.time()
        print(f"  [{n}/{len(bad)}] {sym} ...", flush=True)
        try:
            blocks[sym] = analyze_asset(sym)["block"]
        except LLMUnavailable as e:
            results = [{"symbol": s, "block": b} for s, b in blocks.items()]
            save_report("\n".join([f"# Mercado {today} — análisis multi-agente\n"]
                                  + [f"### {r['symbol']}\n{r['block']}\n" for r in results]))
            print(f"\n[analistas] ABORTADO en {sym}: backend LLM no disponible ({e}).")
            print(f"            Progreso guardado en {VAULT_MD} (sin Visión de cartera). "
                  "Reintenta con --patch --notify cuando se restablezca el límite.")
            sys.exit(2)
        print(f"      hecho en {time.time()-t0:.0f}s", flush=True)
        time.sleep(1.0)

    results = [{"symbol": s, "block": b} for s, b in blocks.items()]
    report = assemble(results, today)          # regenera la Visión de cartera
    save_report(report)
    if opts["notify"]:
        dispatch_report(report, today, len(results))


def run_full(opts, today):
    symbols = opts["only"] or read_watchlist()
    if opts["limit"]:
        symbols = symbols[:opts["limit"]]
    print(f"[analistas] {today} — {len(symbols)} activos, "
          f"~{len(symbols)*6+1} llamadas al LLM")

    results = []
    for n, sym in enumerate(symbols, 1):
        t0 = time.time()
        print(f"  [{n}/{len(symbols)}] {sym} ...", flush=True)
        try:
            results.append(analyze_asset(sym))
        except LLMUnavailable as e:
            partial = assemble(results, today) if results else ""
            if partial:
                save_report(partial)
            print(f"\n[analistas] ABORTADO en {sym}: backend LLM no disponible ({e}).")
            print(f"            {len(results)}/{len(symbols)} activos hechos, guardados "
                  f"en {VAULT_MD}. NO se ha enviado nada.")
            print("            Cuando se restablezca el límite:  "
                  "python3 agents/analistas.py --patch --notify")
            sys.exit(2)
        print(f"      hecho en {time.time()-t0:.0f}s", flush=True)
        time.sleep(1.0)

    report = assemble(results, today)
    save_report(report)
    if opts["notify"]:
        dispatch_report(report, today, len(results))


def main():
    opts = _parse_args(sys.argv[1:])
    today = date.today().isoformat()
    (run_patch if opts["patch"] else run_full)(opts, today)


if __name__ == "__main__":
    main()
