#!/usr/bin/env python3
"""Real dates for the market analysis: next Fed (FOMC) meeting + a company's
next earnings/dividend date. Stdlib only.

FOMC 2026 schedule is fixed/official (published in advance by the Fed) — not
looked up live, just hardcoded with its source. Re-check
https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm each year.

Company dates come from Yahoo Finance's quoteSummary endpoint, which (unlike
the plain chart endpoint trading.py uses) requires a cookie + crumb handshake.
"""
import datetime
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request

HEADERS = {"User-Agent": "Mozilla/5.0 (Jarvis/1.0)"}

# Source: https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
# (fetched 2026-08-29). Each meeting's decision lands on the second date.
FOMC_2026 = [
    ("2026-01-27", "2026-01-28"),
    ("2026-03-17", "2026-03-18"),
    ("2026-04-28", "2026-04-29"),
    ("2026-06-16", "2026-06-17"),
    ("2026-07-28", "2026-07-29"),
    ("2026-09-15", "2026-09-16"),
    ("2026-10-27", "2026-10-28"),
    ("2026-12-08", "2026-12-09"),
]


def next_fomc_meeting(today: datetime.date | None = None) -> str:
    """Return a human-readable line about the next FOMC meeting, or '' if the
    hardcoded schedule doesn't cover this date (e.g. a future year)."""
    today = today or datetime.date.today()
    for start, end in FOMC_2026:
        end_d = datetime.date.fromisoformat(end)
        if end_d >= today:
            days = (end_d - today).days
            when = "hoy/mañana" if days <= 1 else f"en {days} días"
            return f"Próxima reunión de la Fed (FOMC): {start} a {end} ({when})"
    return ""


def _yahoo_session():
    """Yahoo's quoteSummary endpoint requires a cookie + crumb (unlike the
    plain chart endpoint) — do that handshake once per run."""
    ctx = ssl.create_default_context()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(),
        urllib.request.HTTPSHandler(context=ctx),
    )
    try:
        opener.open(urllib.request.Request("https://fc.yahoo.com", headers=HEADERS), timeout=8)
    except urllib.error.HTTPError:
        pass  # this endpoint 404s but still sets the cookie we need — only the cookie matters
    req = urllib.request.Request("https://query2.finance.yahoo.com/v1/test/getcrumb", headers=HEADERS)
    crumb = opener.open(req, timeout=8).read().decode().strip()
    return opener, crumb


def company_dates(symbol: str) -> str:
    """Return a human-readable line with the next earnings date (+ ex-dividend
    date if known) for a stock symbol, or '' if unavailable (crypto, index,
    Yahoo blocked us, etc.) — never guesses."""
    try:
        opener, crumb = _yahoo_session()
        url = (
            f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/"
            f"{urllib.parse.quote(symbol)}?modules=calendarEvents&crumb={urllib.parse.quote(crumb)}"
        )
        req = urllib.request.Request(url, headers=HEADERS)
        data = json.loads(opener.open(req, timeout=8).read())
        events = data["quoteSummary"]["result"][0]["calendarEvents"]
    except (urllib.error.URLError, KeyError, IndexError, TypeError, ValueError, OSError):
        return ""

    parts = []
    earnings = events.get("earnings", {}).get("earningsDate") or []
    if earnings:
        parts.append(f"próximos resultados: {earnings[0]['fmt']}")
    ex_div = events.get("exDividendDate", {}).get("fmt")
    if ex_div:
        parts.append(f"ex-dividendo: {ex_div}")

    return f"{symbol}: " + ", ".join(parts) if parts else ""


if __name__ == "__main__":
    import sys
    print(next_fomc_meeting())
    for sym in sys.argv[1:]:
        line = company_dates(sym)
        if line:
            print(line)
