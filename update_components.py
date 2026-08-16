#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Nasdaq-100 Auto Updater (Tiingo + Nasdaq)
=========================================

Data sources:
- Nasdaq API: current Nasdaq-100 constituents
- Tiingo API: QQQ holdings weights (full list, no compression)

Features:
- Auto-add new constituents
- Auto-remove deleted constituents
- Auto-backup old file
- Data validation before overwrite
- Full logging
"""

import os
import re
import json
import shutil
import logging
from datetime import datetime
from pathlib import Path

import requests


# ============================================================
# Configuration
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

OUTPUT_FILE = BASE_DIR / "ndx_components.py"
BACKUP_DIR = BASE_DIR / "backup_ndx"
LOG_FILE = BASE_DIR / "update_ndx.log"

NASDAQ_URL = "https://api.nasdaq.com/api/quote/list-type/nasdaq100"

TIINGO_URL = "https://api.tiingo.com/tiingo/etf/QQQ/holdings"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/151.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nasdaq.com/",
    "Origin": "https://www.nasdaq.com",
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
    ticker = str(ticker).strip().upper()
    ticker = ticker.replace(".", "-")
    if not re.match(r"^[A-Z0-9\-]+$", ticker):
        return None
    return ticker


def clean_name(name):
    if not name:
        return ""
    name = str(name).strip()
    name = name.replace('"', "'")
    name = name.replace("\n", " ")
    name = re.sub(r"\s+", " ", name)
    return name


def normalize_sector(sector):
    if not sector:
        return "Unknown"
    mapping = {
        "Technology": "Technology",
        "Consumer Discretionary": "Consumer Discretionary",
        "Consumer Staples": "Consumer Staples",
        "Health Care": "Health Care",
        "Industrials": "Industrials",
        "Telecommunications": "Telecommunications",
        "Utilities": "Utilities",
        "Energy": "Energy",
        "Basic Materials": "Basic Materials",
        "Real Estate": "Real Estate",
    }
    return mapping.get(sector.strip(), sector.strip())


# ============================================================
# Read old components
# ============================================================

def parse_old_components():
    if not OUTPUT_FILE.exists():
        logging.warning("Old file not found: %s", OUTPUT_FILE)
        return {}

    try:
        content = OUTPUT_FILE.read_text(encoding="utf-8")
        pattern = re.compile(
            r'\(\s*"([^"]+)"\s*,\s*"([^"]*)"\s*,\s*"([^"]*)"\s*,\s*([\d.]+)\s*\)'
        )

        result = {}
        for match in pattern.finditer(content):
            ticker = clean_ticker(match.group(1))
            if not ticker:
                continue
            result[ticker] = {
                "name": clean_name(match.group(2)),
                "sector": normalize_sector(match.group(3)),
                "weight": float(match.group(4)),
            }

        logging.info("Read old data: %d stocks", len(result))
        return result

    except Exception as e:
        logging.exception("Failed to read old file: %s", e)
        return {}


# ============================================================
# Fetch Nasdaq constituents (fix: data.data.rows)
# ============================================================

def fetch_nasdaq_constituents():
    logging.info("Fetching Nasdaq-100 constituents from Nasdaq API...")

    try:
        response = session.get(NASDAQ_URL, timeout=30)
        response.raise_for_status()
        data = response.json()

        # CORRECT PATH: data.data.rows (not data.data)
        rows = data.get("data", {}).get("data", {}).get("rows", [])

        if not rows:
            raise RuntimeError("Nasdaq returned empty data")

        result = {}
        for row in rows:
            ticker = clean_ticker(row.get("symbol"))
            name = clean_name(row.get("companyName"))
            if not ticker:
                continue
            result[ticker] = {"name": name, "sector": "Unknown"}

        if len(result) < 90:
            raise RuntimeError(f"Nasdaq returned only {len(result)} stocks (expected 90+)")

        logging.info("Nasdaq: %d constituents", len(result))
        return result

    except Exception as e:
        logging.exception("Nasdaq fetch failed: %s", e)
        return {}


# ============================================================
# Fetch Tiingo QQQ weights (full list)
# ============================================================

def fetch_tiingo_weights(api_key):
    if not api_key:
        logging.warning("TIINGO_API_KEY not set, skipping Tiingo")
        return {}

    logging.info("Fetching QQQ weights from Tiingo API...")

    try:
        url = f"{TIINGO_URL}?token={api_key}"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()

        if not data or not isinstance(data, list):
            raise RuntimeError("Tiingo returned empty or invalid data")

        weights = {}
        for item in data:
            ticker = clean_ticker(item.get("symbol"))
            raw_weight = item.get("holdingPercent")

            if not ticker or raw_weight is None:
                continue

            try:
                weight = float(raw_weight) * 100  # Convert to percentage
            except (ValueError, TypeError):
                continue

            if weight <= 0 or weight > 20:
                continue

            weights[ticker] = round(weight, 2)

        if len(weights) < 80:
            raise RuntimeError(f"Tiingo returned only {len(weights)} weights (expected 80+)")

        logging.info("Tiingo: %d weights", len(weights))
        return weights

    except Exception as e:
        logging.exception("Tiingo fetch failed: %s", e)
        return {}


# ============================================================
# Validation
# ============================================================

def validate_data(data):
    if not data:
        logging.error("Final data is empty")
        return False

    count = len(data)
    logging.info("Validating: %d stocks", count)

    if count < 95 or count > 110:
        logging.error("Stock count abnormal: %d", count)
        return False

    for ticker, item in data.items():
        if not ticker:
            logging.error("Empty ticker found")
            return False
        if item["weight"] <= 0:
            logging.error("%s weight abnormal: %.2f", ticker, item["weight"])
            return False

    total_weight = sum(item["weight"] for item in data.values())
    logging.info("Total weight: %.2f%%", total_weight)

    if total_weight < 95 or total_weight > 105:
        logging.error("Total weight abnormal: %.2f%%", total_weight)
        return False

    max_weight = max(item["weight"] for item in data.values())
    if max_weight > 15:
        logging.error("Max weight abnormal: %.2f%%", max_weight)
        return False

    logging.info("Validation passed")
    return True


# ============================================================
# Merge data
# ============================================================

def build_final_data(constituents, weights, old_data):
    final = {}

    old_tickers = set(old_data.keys())
    new_tickers = set(constituents.keys())

    added = sorted(new_tickers - old_tickers)
    removed = sorted(old_tickers - new_tickers)
    fallback = []

    for ticker, info in constituents.items():
        name = info["name"]

        if ticker in weights:
            weight = weights[ticker]
        elif ticker in old_data:
            weight = old_data[ticker]["weight"]
            fallback.append(ticker)
            logging.warning("%s: using old weight %.2f%% (no Tiingo data)", ticker, weight)
        else:
            logging.warning("%s: new constituent but no weight, skipping", ticker)
            continue

        if not name and ticker in old_data:
            name = old_data[ticker]["name"]

        sector = old_data[ticker]["sector"] if ticker in old_data else "Unknown"

        final[ticker] = {
            "name": name,
            "sector": sector,
            "weight": round(float(weight), 2),
        }

    logging.info("Added: %d", len(added))
    logging.info("Removed: %d", len(removed))
    logging.info("Fallback (old weights): %d", len(fallback))

    if added:
        logging.info("Added stocks: %s", ", ".join(added))
    if removed:
        logging.info("Removed stocks: %s", ", ".join(removed))

    return final


# ============================================================
# Backup
# ============================================================

def backup_old_file():
    if not OUTPUT_FILE.exists():
        return

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = BACKUP_DIR / f"ndx_components_{timestamp}.py"

    shutil.copy2(OUTPUT_FILE, backup_file)
    logging.info("Backup saved: %s", backup_file)

    backups = sorted(BACKUP_DIR.glob("ndx_components_*.py"), key=lambda x: x.stat().st_mtime, reverse=True)
    for old_backup in backups[30:]:
        try:
            old_backup.unlink()
        except Exception:
            pass


# ============================================================
# Write file
# ============================================================

def write_components(data):
    sorted_items = sorted(data.items(), key=lambda x: x[1]["weight"], reverse=True)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "# Nasdaq-100 Constituents (Auto-Updated)",
        f"# Updated: {now}",
        "# Source: Nasdaq API + Tiingo API (QQQ holdings)",
        "#",
        "# Tiingo provides full QQQ holdings with no weight compression.",
        "#",
        "STOCKS = [",
    ]

    for ticker, item in sorted_items:
        name = item["name"]
        sector = item["sector"]
        weight = item["weight"]
        lines.append(f'    ("{ticker}", "{name}", "{sector}", {weight:.2f}),')

    lines.append("]")
    lines.append("")
    lines.append('SECTORS = sorted(set(s[2] for s in STOCKS))')
    lines.append("")
    lines.append(f'LAST_UPDATE = "{now}"')
    lines.append('DATA_SOURCE = "Nasdaq + Tiingo"')

    temp_file = OUTPUT_FILE.with_suffix(".tmp")

    try:
        temp_file.write_text("\n".join(lines), encoding="utf-8")
        temp_file.replace(OUTPUT_FILE)
        logging.info("Successfully wrote: %s (%d stocks)", OUTPUT_FILE, len(sorted_items))
        return True

    except Exception as e:
        logging.exception("Write failed: %s", e)
        if temp_file.exists():
            try:
                temp_file.unlink()
            except Exception:
                pass
        return False


# ============================================================
# Main
# ============================================================

def main():
    print()
    print("=" * 65)
    print(" Nasdaq-100 Auto Updater (Tiingo + Nasdaq)")
    print("=" * 65)

    logging.info("========== Update started ==========")

    # Read API key from environment
    tiingo_api_key = os.environ.get("TIINGO_API_KEY", "")

    old_data = parse_old_components()

    constituents = fetch_nasdaq_constituents()
    if not constituents:
        logging.error("Failed to fetch Nasdaq constituents")
        print("❌ Nasdaq constituents fetch failed")
        print("❌ ndx_components.py will NOT be modified")
        return 1

    weights = fetch_tiingo_weights(tiingo_api_key)
    if not weights:
        logging.error("Failed to fetch Tiingo weights")
        print("❌ Tiingo weights fetch failed")
        print("❌ ndx_components.py will NOT be modified")
        return 1

    final_data = build_final_data(constituents, weights, old_data)

    if not validate_data(final_data):
        logging.error("Data validation failed")
        print("❌ Data validation failed")
        print("❌ ndx_components.py will NOT be modified")
        return 1

    backup_old_file()

    if not write_components(final_data):
        print("❌ Write failed")
        return 1

    print()
    print("=" * 65)
    print(" ✅ Nasdaq-100 Update Successful")
    print("=" * 65)
    print(f"  Constituents: {len(final_data)}")
    print(f"  Output: {OUTPUT_FILE}")
    print("=" * 65)

    logging.info("========== Update successful ==========")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
