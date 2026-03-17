"""
Binance Launchpool Scraper
Obtiene proyectos activos/proximos y los envia a un endpoint PHP (opcional).

Uso:
    python scraper.py              -> imprime JSON en consola
    python scraper.py --send       -> imprime + envia al endpoint PHP
"""

import json
import sys
import urllib.request
import urllib.parse
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────

API_URL = "https://www.binance.com/bapi/apex/v1/friendly/apex/web/launchpool/holder/project"

# Cambia esta URL por la de tu servidor PHP
PHP_ENDPOINT = "https://tu-servidor.com/receiver.php"

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Content-Type":    "application/json",
    "Accept":          "application/json",
    "Referer":         "https://www.binance.com/en/launchpool",
    "Accept-Language": "en-US,en;q=0.9",
}

# ── Fetch ─────────────────────────────────────────────────────────────────────

def fetch_projects(page=1, size=20):
    body = json.dumps({"pageIndex": page, "pageSize": size}).encode("utf-8")

    req = urllib.request.Request(API_URL, data=body, headers=HEADERS, method="POST")

    # SSL: en Windows puede fallar, usamos context sin verificacion
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
        raw = json.loads(resp.read().decode("utf-8"))

    if not raw.get("success"):
        print(f"[ERROR] API respondio: {raw.get('message')}")
        return []

    rows = raw.get("data", {}).get("rows", [])
    result = []

    for row in rows:
        token  = row.get("rebateCoin", "—")
        status = row.get("status", "—").lower()
        ptype  = row.get("projectType", "—")   # "lpl" o "holder"
        total  = row.get("rebateTotalAmount", 0)
        logo   = row.get("rebateCoinLogo", "")

        pools      = []
        start_time = None
        end_time   = None
        ann_url    = ""

        if ptype == "lpl" and row.get("lplProjects"):
            for pool in row["lplProjects"]:
                pools.append(pool.get("asset", ""))
            first = row["lplProjects"][0]
            start_time = first.get("mineStartTime")
            end_time   = first.get("mineEndTime")
            ann_url    = first.get("announcementUrl", "")

        elif ptype == "holder" and row.get("holderProjects"):
            p = row["holderProjects"][0]
            pools.append(p.get("asset", "BNB"))
            start_time = p.get("holdStartTime")
            end_time   = p.get("holdEndTime")
            ann_url    = p.get("announcementUrl", "")

        if ann_url and not ann_url.startswith("http"):
            ann_url = "https://www.binance.com" + ann_url

        result.append({
            "id":        f"{ptype}_{token}",
            "token":     token,
            "logo":      logo,
            "type":      "launchpool" if ptype == "lpl" else "hodler_airdrop",
            "status":    status,
            "total_amount": total,
            "pools":     pools,
            "start":     _ts(start_time),
            "end":       _ts(end_time),
            "start_ms":  start_time,
            "end_ms":    end_time,
            "url":       ann_url or "https://www.binance.com/en/launchpool",
        })

    return result

def _ts(ms):
    if not ms:
        return None
    try:
        return datetime.utcfromtimestamp(int(ms) / 1000).strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return None

# ── Send to PHP ───────────────────────────────────────────────────────────────

def send_to_php(projects):
    payload = json.dumps({
        "scraped_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "count":      len(projects),
        "projects":   projects,
    }).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "User-Agent":   "BinanceMonitor/1.0",
    }

    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(PHP_ENDPOINT, data=payload, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            status = resp.status
            body   = resp.read().decode("utf-8")
        print(f"[PHP] Respuesta {status}: {body[:200]}")
    except Exception as e:
        print(f"[PHP] Error al enviar: {e}")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC] Fetching Binance Launchpool...")

    projects = fetch_projects(page=1, size=20)

    if not projects:
        print("[!] No se obtuvieron proyectos.")
        return

    print(f"[OK] {len(projects)} proyectos obtenidos\n")

    # Imprimir JSON limpio
    print(json.dumps(projects, indent=2, ensure_ascii=False))

    # Enviar al servidor PHP si se pasa --send
    if "--send" in sys.argv:
        print(f"\n[->] Enviando a {PHP_ENDPOINT} ...")
        send_to_php(projects)

if __name__ == "__main__":
    main()
