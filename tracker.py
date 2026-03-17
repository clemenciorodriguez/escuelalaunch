"""
tracker.py
Actualiza el precio actual y P&L de cada posicion abierta en portfolio.json.
Corre cada 15 minutos via GitHub Actions.
"""

import json
import ssl
import urllib.request
from datetime import datetime
from pathlib import Path

PORTFOLIO_FILE = Path("data/portfolio.json")
PRICE_URL      = "https://api.binance.com/api/v3/ticker/price?symbol={}"

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode    = ssl.CERT_NONE

def _now_str():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

def get_price(symbol):
    url = PRICE_URL.format(symbol)
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=10) as r:
            return float(json.loads(r.read())["price"])
    except Exception as e:
        print(f"[WARN] Precio no disponible para {symbol}: {e}")
        return None

def main():
    print(f"\n[{_now_str()}] tracker.py iniciando...")

    if not PORTFOLIO_FILE.exists():
        print("[OK] portfolio.json no existe aun — nada que trackear.")
        return

    portfolio = json.loads(PORTFOLIO_FILE.read_text(encoding="utf-8"))
    trades    = portfolio.get("trades", [])
    open_trades = [t for t in trades if t.get("status") == "open"]

    if not open_trades:
        print("[OK] Sin posiciones abiertas.")
        return

    print(f"[OK] Actualizando {len(open_trades)} posiciones abiertas...\n")

    total_pnl  = 0.0
    total_cost = 0.0

    for t in trades:
        if t.get("status") != "open":
            continue

        price = get_price(t["symbol"])
        if not price:
            continue

        current_value = t["qty"] * price
        pnl_usdt      = round(current_value - t["cost_usdt"], 4)
        pnl_pct       = round((pnl_usdt / t["cost_usdt"]) * 100, 2)

        t["current_price"] = price
        t["current_value"] = round(current_value, 4)
        t["pnl_usdt"]      = pnl_usdt
        t["pnl_pct"]       = pnl_pct
        t["last_updated"]  = _now_str()

        total_pnl  += pnl_usdt
        total_cost += t["cost_usdt"]

        arrow = "▲" if pnl_pct >= 0 else "▼"
        print(f"  {t['token']:10} buy: ${t['buy_price']:.6f}  now: ${price:.6f}  {arrow} {pnl_pct:+.1f}%  P&L: ${pnl_usdt:+.4f}")

    # Resumen del portfolio
    portfolio["total_invested"] = round(total_cost, 4)
    portfolio["total_pnl"]      = round(total_pnl, 4)
    portfolio["total_pnl_pct"]  = round((total_pnl / total_cost * 100) if total_cost else 0, 2)
    portfolio["last_updated"]   = _now_str()

    print(f"\n[RESUMEN]")
    print(f"  Invertido:  ${total_cost:.2f}")
    print(f"  P&L total:  ${total_pnl:+.4f}  ({portfolio['total_pnl_pct']:+.2f}%)")
    print(f"  Balance:    ${portfolio['balance_usdt']:.2f}")

    PORTFOLIO_FILE.write_text(
        json.dumps(portfolio, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    print(f"\n[DONE] portfolio.json actualizado.")

if __name__ == "__main__":
    main()
