#!/usr/bin/env python3
"""Cardmarket MKM API wrapper — OAuth 1.0a, stdlib only.

Credentials in agents/.env (copy agents/cardmarket.env.example):
  MKM_APP_TOKEN=...
  MKM_APP_SECRET=...
  MKM_ACCESS_TOKEN=...
  MKM_ACCESS_SECRET=...

Usage:
  python3 agents/cardmarket.py search "Ragavan"          # buscar carta (Magic por defecto)
  python3 agents/cardmarket.py search "Charizard" --game 3  # Pokémon
  python3 agents/cardmarket.py price <idProduct>         # precio guía de un producto
  python3 agents/cardmarket.py stock                     # tu stock
  python3 agents/cardmarket.py set-price <idArticle> <precio>  # cambiar precio
  python3 agents/cardmarket.py orders                    # tus pedidos recientes

Juegos: 1=Magic, 2=YuGiOh, 3=Pokémon, 5=Modern Basketball, 6=Lorcana
"""
import base64
import hashlib
import hmac
import json
import os
import random
import string
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://api.cardmarket.com/ws/v2.0"

GAME_NAMES = {1: "Magic", 2: "YuGiOh", 3: "Pokémon", 6: "Lorcana"}
CONDITION_LABELS = {
    "MT": "Mint", "NM": "Near Mint", "EX": "Excellent",
    "GD": "Good", "LP": "Light Played", "PL": "Played", "PO": "Poor",
}


# ── credentials ──────────────────────────────────────────────────────

def _load_env():
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


# ── OAuth 1.0a ───────────────────────────────────────────────────────

def _oauth_header(method: str, url: str) -> str:
    app_token     = os.environ["MKM_APP_TOKEN"]
    app_secret    = os.environ["MKM_APP_SECRET"]
    access_token  = os.environ["MKM_ACCESS_TOKEN"]
    access_secret = os.environ["MKM_ACCESS_SECRET"]

    nonce     = "".join(random.choices(string.ascii_letters + string.digits, k=32))
    timestamp = str(int(time.time()))

    oauth = {
        "oauth_consumer_key":     app_token,
        "oauth_nonce":            nonce,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp":        timestamp,
        "oauth_token":            access_token,
        "oauth_version":          "1.0",
    }

    # Query params from URL included in signature
    parsed = urllib.parse.urlparse(url)
    query  = dict(urllib.parse.parse_qsl(parsed.query))
    all_p  = {**oauth, **query}
    param_str = urllib.parse.urlencode(sorted(all_p.items()))
    clean_url = urllib.parse.urlunparse(parsed._replace(query=""))

    base_str = "&".join([
        method.upper(),
        urllib.parse.quote(clean_url, safe=""),
        urllib.parse.quote(param_str, safe=""),
    ])
    signing_key = "&".join([
        urllib.parse.quote(app_secret, safe=""),
        urllib.parse.quote(access_secret, safe=""),
    ])
    sig = hmac.new(
        signing_key.encode(), base_str.encode(), hashlib.sha1
    ).digest()
    oauth["oauth_signature"] = base64.b64encode(sig).decode()

    parts = [f'realm="{clean_url}"'] + [
        f'{k}="{urllib.parse.quote(str(v), safe="")}"'
        for k, v in sorted(oauth.items())
    ]
    return "OAuth " + ", ".join(parts)


# ── HTTP helper ──────────────────────────────────────────────────────

def _req(method: str, path: str, params: dict = None, body: dict = None):
    url = BASE_URL + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    auth = _oauth_header(method, url)
    data = json.dumps(body).encode() if body else None
    req  = urllib.request.Request(
        url, data=data,
        headers={
            "Authorization": auth,
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"MKM API {e.code}: {e.read().decode()[:400]}")


# ── public functions ─────────────────────────────────────────────────

def search(query: str, game: int = 1, only_singles: bool = True) -> str:
    """Search cards by name. Returns formatted text."""
    result = _req("GET", "/products/find", {
        "search":       query,
        "exact":        0,
        "onlysingles":  1 if only_singles else 0,
        "idGame":       game,
        "maxResults":   10,
    })
    products = result.get("product", [])
    if not isinstance(products, list):
        products = [products]
    if not products:
        return f"No se encontró '{query}' en {GAME_NAMES.get(game, game)}"

    lines = [f"🔍 Resultados para '{query}' ({GAME_NAMES.get(game, game)}):"]
    for p in products[:6]:
        pg   = p.get("priceGuide") or {}
        low  = pg.get("LOWEX") or pg.get("LOW") or "?"
        trend = pg.get("TREND") or "?"
        exp  = p.get("expansionName") or "?"
        lines.append(
            f"  [{p['idProduct']}] {p.get('enName','?')} — {exp}\n"
            f"          desde {low} € · tendencia {trend} €"
        )
    return "\n".join(lines)


def price_guide(product_id: int) -> str:
    """Get full price guide for a product ID."""
    result = _req("GET", f"/products/{product_id}")
    p  = result.get("product") or {}
    pg = p.get("priceGuide") or {}
    name = p.get("enName") or str(product_id)
    exp  = p.get("expansionName") or "?"
    lines = [f"💶 Precios de {name} ({exp}):"]
    labels = [
        ("LOW",       "Mínimo"),
        ("LOWEX",     "Mínimo Exc."),
        ("LOWFOIL",   "Mínimo Foil"),
        ("SELL",      "Venta media"),
        ("AVG",       "Media"),
        ("TREND",     "Tendencia"),
        ("TRENDFOIL", "Tend. Foil"),
    ]
    for k, label in labels:
        if k in pg and pg[k] is not None:
            lines.append(f"  {label}: {pg[k]} €")
    return "\n".join(lines)


def my_stock() -> str:
    """List your articles on sale."""
    result = _req("GET", "/stock")
    articles = result.get("article") or []
    if not isinstance(articles, list):
        articles = [articles]
    if not articles:
        return "Tu stock está vacío."
    lines = [f"📦 Tu stock ({len(articles)} artículos):"]
    for a in articles[:25]:
        name = (a.get("product") or {}).get("enName") or "?"
        cond = CONDITION_LABELS.get(a.get("condition",""), a.get("condition","?"))
        lines.append(
            f"  [{a['idArticle']}] {name} · {cond} · {a['price']} € x{a.get('count',1)}"
        )
    if len(articles) > 25:
        lines.append(f"  … y {len(articles)-25} más")
    return "\n".join(lines)


def set_price(article_id: int, price: float) -> str:
    """Update the price of one of your articles."""
    _req("PUT", "/stock", body={"article": [{"idArticle": article_id, "price": price}]})
    return f"✅ Precio actualizado: artículo {article_id} → {price:.2f} €"


def my_orders(state: str = "bought") -> str:
    """Recent orders. state: bought | sold | transit | lost | cancelled."""
    result = _req("GET", "/orders/1/2/0")  # actor=1(buyer), state=2(sent), start=0
    orders = result.get("order") or []
    if not isinstance(orders, list):
        orders = [orders]
    if not orders:
        return "No hay pedidos recientes."
    lines = [f"📬 Pedidos recientes ({len(orders)}):"]
    for o in orders[:10]:
        seller = (o.get("seller") or {}).get("username","?")
        total  = o.get("totalValue","?")
        date   = (o.get("state") or {}).get("dateSent","?")
        lines.append(f"  #{o['idOrder']} · {seller} · {total} € · {date}")
    return "\n".join(lines)


# ── CLI ──────────────────────────────────────────────────────────────

_load_env()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Cardmarket API CLI")
    sub = parser.add_subparsers(dest="cmd")

    p_search = sub.add_parser("search", help="Buscar carta")
    p_search.add_argument("query", nargs="+")
    p_search.add_argument("--game", type=int, default=1)

    p_price = sub.add_parser("price", help="Precio guía por ID")
    p_price.add_argument("id", type=int)

    sub.add_parser("stock", help="Tu stock")

    p_set = sub.add_parser("set-price", help="Cambiar precio")
    p_set.add_argument("id",    type=int)
    p_set.add_argument("price", type=float)

    sub.add_parser("orders", help="Pedidos recientes")

    args = parser.parse_args()
    if not args.cmd:
        parser.print_help(); sys.exit(1)

    try:
        if args.cmd == "search":
            print(search(" ".join(args.query), game=args.game))
        elif args.cmd == "price":
            print(price_guide(args.id))
        elif args.cmd == "stock":
            print(my_stock())
        elif args.cmd == "set-price":
            print(set_price(args.id, args.price))
        elif args.cmd == "orders":
            print(my_orders())
    except KeyError as e:
        print(f"Error: credencial no encontrada — {e}")
        print("Configura MKM_APP_TOKEN, MKM_APP_SECRET, MKM_ACCESS_TOKEN, MKM_ACCESS_SECRET en agents/.env")
        sys.exit(1)
    except RuntimeError as e:
        print(f"Error API: {e}")
        sys.exit(1)
