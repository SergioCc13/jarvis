#!/usr/bin/env python3
"""Jarvis scraper — precios de cartas, ofertas de trabajo, cualquier web.

Cartas:
  python3 agents/scraper.py magic "Ragavan"
  python3 agents/scraper.py pokemon "Charizard"
  python3 agents/scraper.py yugioh "Dark Magician"

Trabajo:
  python3 agents/scraper.py jobs "desarrollador python"
  python3 agents/scraper.py jobs "diseñador UX" --lugar "Barcelona"
  python3 agents/scraper.py jobs "data scientist" --lugar "remoto"

General:
  python3 agents/scraper.py url "https://cualquier-web.com"
  python3 agents/scraper.py search "cualquier consulta"
"""
import html.parser
import json
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

HEADERS = {
    "User-Agent": "Jarvis/1.0 (personal assistant; contact via GitHub)",
    "Accept": "application/json",
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


# ── Magic — Scryfall ─────────────────────────────────────────────────

def magic(query: str) -> str:
    """Search Magic cards via Scryfall. Includes Cardmarket EUR prices."""
    # Try exact match first, then fuzzy
    for endpoint in ("named?exact=", "named?fuzzy="):
        try:
            url = f"https://api.scryfall.com/cards/{endpoint}{urllib.parse.quote(query)}"
            card = _fetch(url)
            return _fmt_scryfall(card)
        except RuntimeError:
            pass

    # Full text search (returns list)
    try:
        url = f"https://api.scryfall.com/cards/search?q={urllib.parse.quote(query)}&order=usd"
        data = _fetch(url)
        cards = data.get("data", [])[:5]
        if not cards:
            return f"No se encontró '{query}' en Scryfall"
        lines = [f"🃏 Resultados Magic para '{query}':"]
        for c in cards:
            lines.append(_fmt_scryfall_short(c))
        return "\n".join(lines)
    except RuntimeError as e:
        return f"Error buscando '{query}': {e}"


def _fmt_scryfall(card: dict) -> str:
    name   = card.get("name", "?")
    set_   = card.get("set_name", "?")
    rarity = card.get("rarity", "?")
    prices = card.get("prices", {})
    lines  = [f"🃏 {name} — {set_} ({rarity})"]

    if prices.get("eur"):
        lines.append(f"  Cardmarket:     {prices['eur']} €")
    if prices.get("eur_foil"):
        lines.append(f"  CM Foil:        {prices['eur_foil']} €")
    if prices.get("usd"):
        lines.append(f"  TCGPlayer (USD):{prices['usd']} $")

    uri = card.get("scryfall_uri") or card.get("uri", "")
    if uri:
        lines.append(f"  🔗 {uri}")
    return "\n".join(lines)


def _fmt_scryfall_short(card: dict) -> str:
    prices = card.get("prices", {})
    eur = prices.get("eur") or "?"
    return f"  • {card.get('name','?')} ({card.get('set_name','?')}) — {eur} €"


# ── Pokémon — pokemontcg.io ──────────────────────────────────────────

def pokemon(query: str) -> str:
    """Search Pokémon cards. Free API, no key needed for basic use."""
    url = f"https://api.pokemontcg.io/v2/cards?q=name:{urllib.parse.quote(query)}&pageSize=5"
    try:
        data = _fetch(url)
    except RuntimeError as e:
        # Fallback: DuckDuckGo search for prices
        return (
            f"API Pokémon no disponible ({e}).\n"
            + ddg_search(f"precio {query} Pokemon card cardmarket")
        )

    cards = data.get("data", [])
    if not cards:
        return f"No se encontró '{query}' en Pokémon TCG"

    lines = [f"🎴 Pokémon — '{query}':"]
    for c in cards:
        name   = c.get("name", "?")
        set_   = (c.get("set") or {}).get("name", "?")
        rarity = c.get("rarity", "?")
        prices = (c.get("tcgplayer") or {}).get("prices", {})

        price_str = ""
        for variant, p in prices.items():
            mid = p.get("mid") or p.get("market")
            if mid:
                price_str = f"{mid:.2f} $ ({variant})"
                break

        lines.append(f"  • {name} — {set_} ({rarity})" + (f" · {price_str}" if price_str else ""))
    return "\n".join(lines)


# ── YuGiOh — ygoprodeck ──────────────────────────────────────────────

def yugioh(query: str) -> str:
    """Search YuGiOh cards via ygoprodeck free API."""
    url = f"https://db.ygoprodeck.com/api/v7/cardinfo.php?fname={urllib.parse.quote(query)}&num=5&offset=0"
    try:
        data = _fetch(url)
    except RuntimeError as e:
        return f"Error buscando YuGiOh '{query}': {e}"

    cards = data.get("data", [])
    if not cards:
        return f"No se encontró '{query}' en YuGiOh"

    lines = [f"👹 YuGiOh — '{query}':"]
    for c in cards:
        name  = c.get("name", "?")
        ctype = c.get("type", "?")
        sets  = c.get("card_sets", [])
        price = None
        if sets:
            price = sets[0].get("set_price")
        lines.append(f"  • {name} ({ctype})" + (f" · desde {price} $" if price else ""))
    return "\n".join(lines)


# ── Generic URL text extractor ────────────────────────────────────────

class _StripHTML(html.parser.HTMLParser):
    SKIP = {"script", "style", "nav", "footer", "head", "noscript", "svg", "aside"}

    def __init__(self):
        super().__init__()
        self._buf = []
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._depth += 1
        if tag in {"p", "div", "h1", "h2", "h3", "li", "br", "tr"}:
            if self._buf and self._buf[-1] != "\n":
                self._buf.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._depth:
            self._depth -= 1

    def handle_data(self, data):
        if not self._depth:
            t = data.strip()
            if t:
                self._buf.append(t + " ")

    def result(self, max_chars=4000):
        raw = "".join(self._buf)
        raw = re.sub(r" {2,}", " ", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw[:max_chars].strip()


def url_text(url: str, max_chars=4000) -> str:
    """Extract clean readable text from any URL."""
    try:
        html_raw = _fetch(url, as_json=False)
    except RuntimeError as e:
        return f"Error al acceder a {url}: {e}"
    parser = _StripHTML()
    parser.feed(html_raw)
    return parser.result(max_chars) or "(sin contenido útil)"


# ── DuckDuckGo search ─────────────────────────────────────────────────

def ddg_search(query: str) -> str:
    """Search via DuckDuckGo Instant Answer API."""
    url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&no_html=1&skip_disambig=1"
    try:
        data = _fetch(url)
    except RuntimeError as e:
        return f"Error de búsqueda: {e}"

    parts = []
    if data.get("AbstractText"):
        parts.append(data["AbstractText"])
    if data.get("Answer"):
        parts.append(data["Answer"])
    for t in data.get("RelatedTopics", [])[:3]:
        if isinstance(t, dict) and t.get("Text"):
            parts.append(f"• {t['Text']}")
    return "\n".join(parts) if parts else f"Sin resultados para: {query}"


# ── Job search ───────────────────────────────────────────────────────

def _parse_indeed(html_text: str) -> list[dict]:
    """Extract job listings from Indeed HTML."""
    jobs = []
    titles   = re.findall(r'data-testid="job-snippet"[^>]*>.*?<h2[^>]*><a[^>]*>(.*?)</a>', html_text, re.S)
    companies = re.findall(r'data-testid="company-name"[^>]*>(.*?)</(?:span|div|a)>', html_text, re.S)
    locations = re.findall(r'data-testid="text-location"[^>]*>(.*?)</div>', html_text, re.S)

    # Fallback: generic pattern
    if not titles:
        titles   = re.findall(r'class="jobTitle[^"]*"[^>]*>.*?<span[^>]*>(.*?)</span>', html_text, re.S)
        companies = re.findall(r'class="companyName"[^>]*>(.*?)</(?:span|a)>', html_text, re.S)
        locations = re.findall(r'class="companyLocation"[^>]*>(.*?)</div>', html_text, re.S)

    for i, title in enumerate(titles[:8]):
        title = re.sub(r'<[^>]+>', '', title).strip()
        company = re.sub(r'<[^>]+>', '', companies[i]).strip() if i < len(companies) else "?"
        location = re.sub(r'<[^>]+>', '', locations[i]).strip() if i < len(locations) else "?"
        if title:
            jobs.append({"title": title, "company": company, "location": location, "source": "Indeed"})
    return jobs


def _parse_infojobs(html_text: str) -> list[dict]:
    """Extract job listings from Infojobs HTML."""
    # Infojobs has structured cards
    jobs = []
    blocks = re.findall(
        r'<div[^>]+class="[^"]*ij-OfferCardContent[^"]*"[^>]*>(.*?)</div>\s*</div>',
        html_text, re.S
    )
    if not blocks:
        # Try h2 links (offer titles)
        titles    = re.findall(r'<h2[^>]*>\s*<a[^>]*>(.*?)</a>', html_text, re.S)
        companies = re.findall(r'<span[^>]*itemprop="name"[^>]*>(.*?)</span>', html_text, re.S)
        locations = re.findall(r'<li[^>]*class="[^"]*location[^"]*"[^>]*>(.*?)</li>', html_text, re.S)
        for i, title in enumerate(titles[:8]):
            title = re.sub(r'<[^>]+>', '', title).strip()
            company = re.sub(r'<[^>]+>', '', companies[i]).strip() if i < len(companies) else "?"
            location = re.sub(r'<[^>]+>', '', locations[i]).strip() if i < len(locations) else "?"
            if title and len(title) > 3:
                jobs.append({"title": title, "company": company, "location": location, "source": "Infojobs"})
    return jobs


def _remotive_jobs(query: str, limit=6) -> list[dict]:
    """Remotive.com — free API for remote tech jobs, no auth needed."""
    url = f"https://remotive.com/api/remote-jobs?search={urllib.parse.quote(query)}&limit={limit}"
    data = _fetch(url)
    results = []
    for j in (data.get("jobs") or [])[:limit]:
        results.append({
            "title":    j.get("title", "?"),
            "company":  j.get("company_name", "?"),
            "location": j.get("candidate_required_location") or "remoto",
            "url":      j.get("url", ""),
            "source":   "Remotive",
        })
    return results


def jobs(query: str, lugar: str = "España") -> str:
    """Search job listings: scrape Indeed/Infojobs + Remotive free API."""
    results = []
    indeed_url = (
        f"https://es.indeed.com/jobs?"
        f"q={urllib.parse.quote(query)}&l={urllib.parse.quote(lugar)}&lang=es"
    )
    ij_url = (
        f"https://www.infojobs.net/jobsearch/search-results/list.xhtml?"
        f"keyword={urllib.parse.quote(query)}"
    )

    # ── Indeed España ────────────────────────────────────────────────
    try:
        html = _fetch(indeed_url, as_json=False)
        results.extend(_parse_indeed(html))
    except RuntimeError:
        pass

    # ── Infojobs ─────────────────────────────────────────────────────
    if len(results) < 4:
        try:
            html = _fetch(ij_url, as_json=False)
            results.extend(_parse_infojobs(html))
        except RuntimeError:
            pass

    # ── Remotive (free API, remote jobs) ─────────────────────────────
    remote_results = []
    try:
        remote_results = _remotive_jobs(query)
    except RuntimeError:
        pass

    # Build output
    lines = [f"💼 Ofertas: '{query}'" + (f" en {lugar}" if lugar != "España" else "")]

    seen = set()
    if results:
        lines.append(f"\n📍 Presencial / Híbrido ({len(results)} encontradas):")
        for j in results:
            key = j["title"].lower()[:30]
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"  • {j['title']} — {j['company']} ({j['location']}) [{j['source']}]")
    else:
        lines.append("\n📍 Presencial: scraping bloqueado — usa los enlaces directos abajo")

    if remote_results:
        lines.append(f"\n🌍 Remoto ({len(remote_results)} en Remotive):")
        for j in remote_results:
            key = j["title"].lower()[:30]
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"  • {j['title']} — {j['company']} ({j['location']})")
            if j.get("url"):
                lines.append(f"    🔗 {j['url']}")

    lines.append(f"\n🔗 Indeed: {indeed_url}")
    lines.append(f"🔗 Infojobs: {ij_url}")
    lines.append(f"🔗 LinkedIn: https://www.linkedin.com/jobs/search/?keywords={urllib.parse.quote(query)}&location={urllib.parse.quote(lugar)}")
    return "\n".join(lines)


# ── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    cmd   = sys.argv[1].lower()

    # Parse --lugar for jobs command
    lugar = "España"
    rest_args = sys.argv[2:]
    if "--lugar" in rest_args:
        idx = rest_args.index("--lugar")
        if idx + 1 < len(rest_args):
            lugar = rest_args[idx + 1]
            rest_args = rest_args[:idx] + rest_args[idx + 2:]
    arg = " ".join(rest_args)

    try:
        if cmd == "magic":
            print(magic(arg))
        elif cmd == "pokemon":
            print(pokemon(arg))
        elif cmd == "yugioh":
            print(yugioh(arg))
        elif cmd == "url":
            print(url_text(sys.argv[2]))
        elif cmd == "search":
            print(ddg_search(arg))
        elif cmd == "jobs":
            print(jobs(arg, lugar=lugar))
        else:
            print(f"Comando desconocido: {cmd}")
            print("Usa: magic | pokemon | yugioh | url | search | jobs")
            sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
