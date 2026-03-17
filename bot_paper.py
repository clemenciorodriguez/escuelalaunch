"""
bot_paper.py
Detecta tokens nuevos con coinTradeTime futuro,
espera el timestamp exacto, consulta el precio real
y registra una compra ficticia en data/portfolio.json.

Corre despues de scraper.py en el workflow de GitHub Actions.
"""

import json
import ssl
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

BUY_USDT      = 5.0
INITIAL_USDT  = 100.0
DATA_URL      = "https://www.binance.com/bapi/apex/v1/friendly/apex/web/launchpool/holder/project"
PRICE_URL     = "https://api.binance.com/api/v3/ticker/price?symbol={}"
PORTFOLIO_FILE = Path("data/portfolio.json")
SEEN_FILE      = Path("data/seen_listings.json")

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode    = ssl.CERT_NONE

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Content-Type":    "application/json",
    "Accept":          "application/json",
    "Referer":         "https://www.binance.com/en/launchpool",
    "Accept-Language": "en-US,en;q=0.9",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def _ts(ms):
    if not ms:
        return "—"
    return datetime.utcfromtimestamp(int(ms)/1000).strftime("%Y-%m-%d %H:%M UTC")

def _now_str():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

def load_json(path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default

def save_json(path, data):
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

# ── Fetch proyectos ───────────────────────────────────────────────────────────

def fetch_projects():
    body = json.dumps({"pageIndex": 1, "pageSize": 20}).encode("utf-8")
    req  = urllib.request.Request(DATA_URL, data=body, headers=HEADERS, method="POST")
    with urllib.request.urlopen(req, context=SSL_CTX, timeout=20) as resp:
        raw = json.loads(resp.read().decode("utf-8"))

    if not raw.get("success"):
        print(f"[ERROR] API: {raw.get('message')}")
        return []

    result = []
    for row in raw.get("data", {}).get("rows", []):
        token = row.get("rebateCoin", "")
        ptype = row.get("projectType", "")
        trade_time = None

        if ptype == "lpl" and row.get("lplProjects"):
            trade_time = row["lplProjects"][0].get("coinTradeTime")
        elif ptype == "holder" and row.get("holderProjects"):
            trade_time = row["holderProjects"][0].get("coinTradeTime")

        if not trade_time:
            continue

        result.append({
            "id":            f"{ptype}_{token}",
            "token":         token,
            "symbol":        f"{token}USDT",
            "trade_time_ms": trade_time,
            "trade_time_str": _ts(trade_time),
        })

    return result

# ── Precio real de Binance ────────────────────────────────────────────────────

def get_price(symbol):
    url = PRICE_URL.format(symbol)
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=10) as r:
            data = json.loads(r.read())
        return float(data["price"])
    except Exception as e:
        print(f"[WARN] No se pudo obtener precio de {symbol}: {e}")
        return None

# ── Registrar compra ficticia ─────────────────────────────────────────────────

def record_buy(project, price, portfolio):
    qty      = BUY_USDT / price
    balance  = portfolio.get("balance_usdt", INITIAL_USDT)

    if balance < BUY_USDT:
        print(f"[SKIP] Balance insuficiente (${balance:.2f}) para comprar ${BUY_USDT}")
        return portfolio

    trade = {
        "id":            project["id"],
        "token":         project["token"],
        "symbol":        project["symbol"],
        "buy_price":     price,
        "buy_time":      _now_str(),
        "buy_time_ms":   int(time.time() * 1000),
        "qty":           round(qty, 6),
        "cost_usdt":     BUY_USDT,
        "current_price": price,
        "pnl_usdt":      0.0,
        "pnl_pct":       0.0,
        "last_updated":  _now_str(),
        "status":        "open",
    }

    portfolio["balance_usdt"] = round(balance - BUY_USDT, 4)
    portfolio.setdefault("trades", []).append(trade)
    portfolio["last_updated"] = _now_str()

    print(f"[BUY]  {project['token']} @ ${price} | qty: {qty:.4f} | costo: ${BUY_USDT}")
    print(f"[BAL]  Balance restante: ${portfolio['balance_usdt']:.2f}")
    return portfolio

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"\n[{_now_str()}] bot_paper.py iniciando...")

    seen      = set(load_json(SEEN_FILE, []))
    portfolio = load_json(PORTFOLIO_FILE, {
        "balance_usdt": INITIAL_USDT,
        "initial_usdt": INITIAL_USDT,
        "created_at":   _now_str(),
        "last_updated": _now_str(),
        "trades":       [],
    })

    projects = fetch_projects()
    now_ms   = int(time.time() * 1000)

    # Solo proyectos con listing futuro y no vistos
    pending = [
        p for p in projects
        if p["trade_time_ms"] > now_ms and p["id"] not in seen
    ]

    print(f"[OK] {len(projects)} proyectos / {len(pending)} con listing futuro no registrado")

    if not pending:
        print("[OK] Sin listings pendientes.")
        return

    pending.sort(key=lambda x: x["trade_time_ms"])

    for p in pending:
        wait_ms  = p["trade_time_ms"] - int(time.time() * 1000)
        wait_sec = wait_ms / 1000

        print(f"\n[WAIT] {p['token']} lista en {wait_sec:.0f}s ({p['trade_time_str']})")

        # Si el listing es en mas de 2 horas, no esperar en este run
        # GitHub Actions tiene timeout de 5 minutos
        if wait_sec > 300:
            print(f"[SKIP] Listing muy lejano ({wait_sec/3600:.1f}h). Se procesara en el proximo run.")
            seen.add(p["id"] + "_pending")
            continue

        # Esperar hasta el listing
        pre = max(0, wait_sec - 2)
        if pre > 0:
            time.sleep(pre)

        # Countdown final
        remaining = (p["trade_time_ms"] - int(time.time() * 1000)) / 1000
        while remaining > 0.05:
            remaining = (p["trade_time_ms"] - int(time.time() * 1000)) / 1000
            time.sleep(0.02)

        print(f"[LISTING] {p['token']} — {datetime.utcnow().strftime('%H:%M:%S.%f')[:-3]} UTC")

        # Intentar obtener precio hasta 10 veces (puede tardar unos segundos en aparecer)
        price = None
        for attempt in range(10):
            price = get_price(p["symbol"])
            if price:
                break
            print(f"[RETRY] Intento {attempt+1}/10 — esperando que aparezca el par...")
            time.sleep(1)

        if not price:
            print(f"[ERROR] No se pudo obtener precio de {p['symbol']} — saltando")
            seen.add(p["id"])
            continue

        portfolio = record_buy(p, price, portfolio)
        seen.add(p["id"])

    save_json(SEEN_FILE, list(seen))
    save_json(PORTFOLIO_FILE, portfolio)
    print(f"\n[DONE] portfolio.json actualizado.")

if __name__ == "__main__":
    main()
