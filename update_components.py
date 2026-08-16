#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Nasdaq-100 Auto Updater
=======================
Data sources:
- Nasdaq API: current constituents (ticker, name)
- Slickcharts: QQQ/NDX weights
- Built-in fallback: cached weights + sector map

Features:
- Auto-add/remove constituents
- Auto-backup
- Data validation
- Full logging
- Never fails completely (uses fallback weights if sources down)
"""

import os
import re
import shutil
import logging
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup


# ============================================================
# Configuration
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = BASE_DIR / "ndx_components.py"
BACKUP_DIR = BASE_DIR / "backup_ndx"
LOG_FILE = BASE_DIR / "update_ndx.log"

NASDAQ_URL = "https://api.nasdaq.com/api/quote/list-type/nasdaq100"
SLICKCHARTS_URL = "https://www.slickcharts.com/nasdaq100"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


# ============================================================
# Built-in Fallback Data (last updated: 2026-08-16)
# ============================================================

FALLBACK_WEIGHTS = {
    "NVDA": 12.96, "AAPL": 10.61, "MSFT": 8.74, "AMZN": 6.73,
    "GOOGL": 5.18, "GOOG": 4.84, "AVGO": 4.44, "SPCX": 4.39,
    "META": 3.57, "TSLA": 3.21, "MU": 2.61, "WMT": 2.18,
    "AMD": 2.00, "ASML": 1.68, "INTC": 1.23, "CSCO": 1.05,
    "COST": 1.01, "PLTR": 0.99, "LRCX": 0.99, "AMAT": 0.96,
    "NFLX": 0.77, "PANW": 0.74, "ARM": 0.71, "KLAC": 0.63,
    "TXN": 0.61, "SNDK": 0.57, "AMGN": 0.53, "LIN": 0.53,
    "CRWD": 0.53, "STX": 0.52, "MRVL": 0.47, "SHOP": 0.47,
    "TMUS": 0.47, "PEP": 0.46, "ADI": 0.45, "WDC": 0.42,
    "QCOM": 0.41, "GILD": 0.41, "BKNG": 0.38, "ISRG": 0.33,
    "VRTX": 0.30, "SBUX": 0.29, "PDD": 0.29, "FTNT": 0.28,
    "ABNB": 0.26, "ADP": 0.26, "APP": 0.25, "ADBE": 0.25,
    "CEG": 0.24, "INTU": 0.22, "DASH": 0.22, "MELI": 0.22,
    "MAR": 0.22, "CSX": 0.22, "CMCSA": 0.22, "DDOG": 0.22,
    "MNST": 0.22, "CDNS": 0.21, "REGN": 0.20, "LITE": 0.20,
    "MDLZ": 0.19, "SNPS": 0.19, "CTAS": 0.19, "ROST": 0.19,
    "NBIS": 0.18, "HON": 0.18, "ORLY": 0.18, "WBD": 0.17,
    "MPWR": 0.16, "PCAR": 0.16, "AEP": 0.16, "TER": 0.16,
    "BKR": 0.15, "NXPI": 0.14, "FAST": 0.14, "CRWV": 0.14,
    "FANG": 0.13, "ALAB": 0.13, "ADSK": 0.13, "PYPL": 0.13,
    "HONA": 0.13, "RKLB": 0.12, "AXON": 0.12, "XEL": 0.12,
    "WDAY": 0.12, "CCEP": 0.11, "EXC": 0.11, "FER": 0.11,
    "TTWO": 0.11, "TRI": 0.11, "ODFL": 0.10, "IDXX": 0.10,
    "PAYX": 0.10, "MCHP": 0.10, "KDP": 0.10, "ROP": 0.09,
    "MSTR": 0.09, "DXCM": 0.08, "GEHC": 0.08, "ALNY": 0.07,
    "KHC": 0.07, "CPRT": 0.07,
}

SECTOR_MAP = {
    "NVDA": "Technology", "AAPL": "Technology", "MSFT": "Technology",
    "AVGO": "Technology", "MU": "Technology", "AMD": "Technology",
    "ASML": "Technology", "INTC": "Technology", "CSCO": "Technology",
    "AMAT": "Technology", "LRCX": "Technology", "ARM": "Technology",
    "KLAC": "Technology", "TXN": "Technology", "SNDK": "Technology",
    "MRVL": "Technology", "ADI": "Technology", "WDC": "Technology",
    "QCOM": "Technology", "FTNT": "Technology", "APP": "Technology",
    "ADBE": "Technology", "CDNS": "Technology", "SNPS": "Technology",
    "MPWR": "Technology", "TER": "Technology", "NXPI": "Technology",
    "MCHP": "Technology", "ALAB": "Technology", "ADSK": "Technology",
    "PYPL": "Technology", "WDAY": "Technology", "DDOG": "Technology",
    "LITE": "Technology", "NBIS": "Communication Services", "CRWV": "Technology",
    "PLTR": "Technology", "PANW": "Technology", "CRWD": "Technology",
    "INTU": "Technology", "MSTR": "Technology", "GOOGL": "Communication Services",
    "GOOG": "Communication Services", "META": "Communication Services",
    "NFLX": "Communication Services", "CMCSA": "Communication Services",
    "TTWO": "Communication Services", "TRI": "Communication Services",
    "WBD": "Communication Services", "TMUS": "Communication Services",
    "AMZN": "Consumer Discretionary", "TSLA": "Consumer Discretionary",
    "WMT": "Consumer Discretionary", "COST": "Consumer Discretionary",
    "SBUX": "Consumer Discretionary", "PDD": "Consumer Discretionary",
    "ABNB": "Consumer Discretionary", "DASH": "Consumer Discretionary",
    "MELI": "Consumer Discretionary", "MAR": "Consumer Discretionary",
    "ROST": "Consumer Discretionary", "BKNG": "Consumer Discretionary",
    "ORLY": "Consumer Discretionary", "SHOP": "Consumer Discretionary",
    "SPCX": "Industrials", "PEP": "Consumer Staples", "MNST": "Consumer Staples",
    "MDLZ": "Consumer Staples", "KDP": "Consumer Staples", "CCEP": "Consumer Staples",
    "KHC": "Consumer Staples", "AMGN": "Health Care", "GILD": "Health Care",
    "ISRG": "Health Care", "VRTX": "Health Care", "REGN": "Health Care",
    "IDXX": "Health Care", "DXCM": "Health Care", "GEHC": "Health Care",
    "ALNY": "Health Care", "LIN": "Industrials", "STX": "Industrials",
    "ADP": "Industrials", "CSX": "Industrials", "CTAS": "Industrials",
    "ODFL": "Industrials", "PCAR": "Industrials", "FAST": "Industrials",
    "HON": "Industrials", "HONA": "Industrials", "BKR": "Industrials",
    "FER": "Industrials", "RKLB": "Industrials", "AXON": "Industrials",
    "ROP": "Industrials", "CPRT": "Industrials", "PAYX": "Industrials",
    "CEG": "Utilities", "AEP": "Utilities", "XEL": "Utilities", "EXC": "Utilities",
    "FANG": "Energy",
}


# ============================================================
# Logging
# ============================================================

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    encoding="utf-8",
)

console = logging.StreamHandler()
console.setLevel(logging.INFO)
console.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
logging.getLogger().addHandler(console)

session = requests.Session()
session.headers.update(HEADERS)


# ============================================================
# Utils
# ============================================================

def clean_ticker(ticker):
    if not ticker:
        return None
    ticker = str(ticker).strip().upper().replace(".", "-")
    if not re.match(r"^[A-Z0-9\-]+$", ticker):
        return None
    return ticker


def clean_name(name):
    if not name:
        return ""
    name = str(name).strip().replace('"', "'").replace("\n", " ")
    return re.sub(r"\s+", " ", name)


# ============================================================
# Read old components
# ============================================================

def parse_old_components():
    if not OUTPUT_FILE.exists():
        return {}
    try:
        content = OUTPUT_FILE.read_text(encoding="utf-8")
        pattern = re.compile(r'\(\s*"([^"]+)"\s*,\s*"([^"]*)"\s*,\s*"([^"]*)"\s*,\s*([\d.]+)\s*\)')
        result = {}
        for m in pattern.finditer(content):
            ticker = clean_ticker(m.group(1))
            if ticker:
                result[ticker] = {
                    "name": clean_name(m.group(2)),
                    "sector": m.group(3),
                    "weight": float(m.group(4)),
                }
        logging.info("Read old data: %d stocks", len(result))
        return result
    except Exception as e:
        logging.exception("Failed to read old file: %s", e)
        return {}


# ============================================================
# Fetch Nasdaq constituents
# ============================================================

def fetch_nasdaq_constituents():
    logging.info("Fetching Nasdaq-100 constituents...")
    try:
        resp = session.get(NASDAQ_URL, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        rows = None
        if "data" in data:
            d = data["data"]
            if isinstance(d, dict) and "data" in d:
                rows = d["data"].get("rows", [])
            elif isinstance(d, list):
                rows = d
            else:
                rows = d.get("rows", [])

        if not rows:
            raise RuntimeError("Empty data")

        result = {}
        for row in rows:
            ticker = clean_ticker(row.get("symbol"))
            name = clean_name(row.get("companyName") or row.get("name"))
            if ticker:
                result[ticker] = name

        if len(result) < 90:
            raise RuntimeError(f"Only {len(result)} stocks")

        logging.info("Nasdaq: %d constituents", len(result))
        return result

    except Exception as e:
        logging.exception("Nasdaq fetch failed: %s", e)
        return {}


# ============================================================
# Fetch Slickcharts weights
# ============================================================

def fetch_slickcharts_weights():
    logging.info("Fetching weights from Slickcharts...")
    try:
        resp = session.get(SLICKCHARTS_URL, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        table = soup.find("table", {"class": "table"})
        if not table:
            # fallback: any table with enough rows
            tables = soup.find_all("table")
            for t in tables:
                if len(t.find_all("tr")) > 50:
                    table = t
                    break

        if not table:
            raise RuntimeError("No table found")

        weights = {}
        for row in table.find_all("tr")[1:]:  # skip header
            cols = row.find_all("td")
            if len(cols) >= 4:
                # cols: [rank, name, ticker, weight, ...]
                ticker = clean_ticker(cols[2].get_text(strip=True))
                weight_text = cols[3].get_text(strip=True).replace("%", "")
                if ticker:
                    try:
                        weight = float(weight_text)
                        if weight > 0:
                            weights[ticker] = round(weight, 2)
                    except ValueError:
                        continue

        if len(weights) < 80:
            raise RuntimeError(f"Only {len(weights)} weights")

        logging.info("Slickcharts: %d weights", len(weights))
        return weights

    except Exception as e:
        logging.exception("Slickcharts fetch failed: %s", e)
        return {}


# ============================================================
# Merge & Build
# ============================================================

def build_final_data(constituents, weights, old_data):
    final = {}
    old_tickers = set(old_data.keys())
    new_tickers = set(constituents.keys())

    added = sorted(new_tickers - old_tickers)
    removed = sorted(old_tickers - new_tickers)
    fallback = []

    for ticker, name in constituents.items():
        if ticker in weights:
            weight = weights[ticker]
        elif ticker in old_data:
            weight = old_data[ticker]["weight"]
            fallback.append(ticker)
            logging.warning("%s: using old weight %.2f%%", ticker, weight)
        elif ticker in FALLBACK_WEIGHTS:
            weight = FALLBACK_WEIGHTS[ticker]
            fallback.append(ticker)
            logging.warning("%s: using built-in fallback weight %.2f%%", ticker, weight)
        else:
            logging.warning("%s: no weight data, skipping", ticker)
            continue

        if not name:
            name = old_data.get(ticker, {}).get("name", ticker)

        sector = SECTOR_MAP.get(ticker)
        if not sector and ticker in old_data:
            sector = old_data[ticker]["sector"]
        if not sector:
            sector = "Unknown"

        final[ticker] = {
            "name": name,
            "sector": sector,
            "weight": round(float(weight), 2),
        }

    logging.info("Added: %d, Removed: %d, Fallback: %d", len(added), len(removed), len(fallback))
    return final


# ============================================================
# Validation
# ============================================================

def validate_data(data):
    if not data:
        logging.error("Empty data")
        return False

    count = len(data)
    if count < 95:
        logging.error("Count abnormal: %d", count)
        return False

    for ticker, item in data.items():
        if item["weight"] <= 0:
            logging.error("%s weight abnormal", ticker)
            return False

    total = sum(i["weight"] for i in data.values())
    logging.info("Total weight: %.2f%%", total)

    if total < 85 or total > 115:
        logging.error("Total weight abnormal: %.2f%%", total)
        return False

    mx = max(i["weight"] for i in data.values())
    if mx > 25:
        logging.error("Max weight abnormal: %.2f%%", mx)
        return False

    logging.info("Validation passed")
    return True


# ============================================================
# Backup & Write
# ============================================================

def backup_old_file():
    if not OUTPUT_FILE.exists():
        return
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = BACKUP_DIR / f"ndx_components_{ts}.py"
    shutil.copy2(OUTPUT_FILE, dst)
    logging.info("Backup: %s", dst)
    # keep last 30
    backups = sorted(BACKUP_DIR.glob("ndx_components_*.py"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[30:]:
        try:
            old.unlink()
        except Exception:
            pass


def write_components(data):
    items = sorted(data.items(), key=lambda x: x[1]["weight"], reverse=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "# Nasdaq-100 Constituents (Auto-Updated)",
        f"# Updated: {now}",
        "# Source: Nasdaq API + Slickcharts (with built-in fallback)",
        "#",
        "STOCKS = [",
    ]
    for ticker, item in items:
        lines.append(f'    (\"{ticker}\", \"{item[\"name\"]}\", \"{item[\"sector\"]}\", {item[\"weight\"]:.2f}),')
    lines.append("]")
    lines.append("")
    lines.append('SECTORS = sorted(set(s[2] for s in STOCKS))')
    lines.append("")
    lines.append(f'LAST_UPDATE = \"{now}\"')
    lines.append('DATA_SOURCE = \"Nasdaq + Slickcharts\"')

    tmp = OUTPUT_FILE.with_suffix(".tmp")
    try:
        tmp.write_text("\n".join(lines), encoding="utf-8")
        tmp.replace(OUTPUT_FILE)
        logging.info("Wrote %s (%d stocks)", OUTPUT_FILE, len(items))
        return True
    except Exception as e:
        logging.exception("Write failed: %s", e)
        if tmp.exists():
            tmp.unlink()
        return False


# ============================================================
# Main
# ============================================================

def main():
    print("=" * 65)
    print(" Nasdaq-100 Auto Updater")
    print("=" * 65)

    old_data = parse_old_components()

    constituents = fetch_nasdaq_constituents()
    if not constituents:
        print("❌ Nasdaq fetch failed")
        return 1

    weights = fetch_slickcharts_weights()
    if not weights:
        logging.warning("Using built-in fallback weights...")
        weights = {}

    final_data = build_final_data(constituents, weights, old_data)

    if not validate_data(final_data):
        print("❌ Validation failed")
        return 1

    backup_old_file()

    if not write_components(final_data):
        print("❌ Write failed")
        return 1

    print(" ✅ Update successful: %d constituents" % len(final_data))
    print("=" * 65)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
