"""
Binance Launchpool Scraper
Obtiene todos los proyectos y guarda en data/projects.json
GitHub Actions hace el commit automaticamente cada 15 minutos.
"""

import json
import os
import ssl
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

API_URL = "https://www.binance.com/bapi/apex/v1/friendly/apex/web/launchpool/holder/project"

OUTPUT_FILE = Path("data/projects.json")

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Content-Type":    "application/json",
    "Accept":          "application/json",
    "Referer":         "https://www.binance.com/en/launchpool",
    "Accept-Language": "en-US,en;q=0.9",
}

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode    = ssl.CERT_NONE

# ── Fetch Binance ─────────────────────────────────────────────────────────────

def fetch_projects(page=1, size=20):
    body = json.dumps({"pageIndex": page, "pageSize": size}).encode("utf-8")
    req  = urllib.request.Request(API_URL, data=body, headers=HEADERS, method="POST")

    with urllib.request.urlopen(req, context=SSL_CTX, timeout=20) as resp:
        raw = json.loads(resp.read().decode("utf-8"))

    if not raw.get("success"):
        print(f"[ERROR] Binance API: {raw.get('message')}")
        return []

    rows   = raw.get("data", {}).get("rows", [])
    result = []

    for row in rows:
        token  = row.get("rebateCoin", "—")
        status = row.get("status", "—").lower()
        ptype  = row.get("projectType", "—")
        total  = row.get("rebateTotalAmount", 0)
        logo   = row.get("rebateCoinLogo", "")

        pools    = []
        start_ms = None
        end_ms   = None
        ann_url  = ""

        if ptype == "lpl" and row.get("lplProjects"):
            for pool in row["lplProjects"]:
                pools.append(pool.get("asset", ""))
            first    = row["lplProjects"][0]
            start_ms = first.get("mineStartTime")
            end_ms   = first.get("mineEndTime")
            ann_url  = first.get("announcementUrl", "")

        elif ptype == "holder" and row.get("holderProjects"):
            p        = row["holderProjects"][0]
            pools.append(p.get("asset", "BNB"))
            start_ms = p.get("holdStartTime")
            end_ms   = p.get("holdEndTime")
            ann_url  = p.get("announcementUrl", "")

        if ann_url and not ann_url.startswith("http"):
            ann_url = "https://www.binance.com" + ann_url

        result.append({
            "id":           f"{ptype}_{token}",
            "token":        token,
            "logo":         logo,
            "type":         "launchpool" if ptype == "lpl" else "hodler_airdrop",
            "status":       status,
            "total_amount": total,
            "pools":        pools,
            "start":        _ts(start_ms),
            "end":          _ts(end_ms),
            "start_ms":     start_ms,
            "end_ms":       end_ms,
            "url":          ann_url or "https://www.binance.com/en/launchpool",
        })

    return result

def _ts(ms):
    if not ms:
        return None
    try:
        return datetime.utcfromtimestamp(int(ms) / 1000).strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return None

# ── Guardar JSON ──────────────────────────────────────────────────────────────

def save_json(projects):
    OUTPUT_FILE.parent.mkdir(exist_ok=True)

    output = {
        "scraped_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "count":      len(projects),
        "projects":   projects,
    }

    OUTPUT_FILE.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    print(f"[OK] Guardado en {OUTPUT_FILE}")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC] Fetching Binance Launchpool...")

    projects = fetch_projects(page=1, size=20)

    if not projects:
        print("[!] Sin datos — abortando.")
        sys.exit(1)

    print(f"[OK] {len(projects)} proyectos obtenidos\n")

    for p in projects:
        pools_str = " · ".join(p["pools"]) if p["pools"] else "—"
        print(f"  [{p['status']:12}] {p['token']:10} | {p['type']:14} | pools: {pools_str}")

    save_json(projects)

if __name__ == "__main__":
    main()
