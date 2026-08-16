#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Nasdaq-100 Auto Updater
=======================

Features:
1. Fetch current Nasdaq-100 constituents from Nasdaq API
2. Fetch QQQ holdings weights from Yahoo Finance
3. Auto-merge constituents + weights
4. Auto-add new constituents
5. Auto-remove deleted constituents
6. Auto-backup old ndx_components.py
7. Data validation before overwrite
8. Write to update_ndx.log

Output:
    ndx_components.py
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
# Config
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

OUTPUT_FILE = BASE_DIR / "ndx_components.py"
BACKUP_DIR = BASE_DIR / "backup_ndx"
LOG_FILE = BASE_DIR / "update_ndx.log"

NASDAQ_URL = "https://api.nasdaq.com/api/quote/list-type/nasdaq100"

YAHOO_URL = (
    "https://query1.finance.yahoo.com/v10/finance/"
    "quoteSummary/QQQ?modules=etfHoldings"
)

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

formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
console.setFormatter(formatter)
logging.getLogger().addHandler(console)


# ============================================================
# Session
# ============================================================

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
    sector = str(sector).strip()
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
    return mapping.get(sector, sector)


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
# Fetch Nasdaq constituents
# ============================================================

def fetch_nasdaq_constituents():
    logging.info("Fetching Nasdaq-100 constituents from Nasdaq API...")

    try:
        response = session.get(NASDAQ_URL, timeout=30)
        response.raise_for_status()
        data = response.json()

        # Correct path: data.data.rows
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
# Fetch Yahoo QQQ weights
# ============================================================

def fetch_qqq_weights():
    logging.info("Fetching QQQ weights from Yahoo Finance...")

    try:
        response = session.get(YAHOO_URL, timeout=30)
        response.raise_for_status()
        data = response.json()

        result = data.get("quoteSummary", {}).get("result", [])

        if not result:
            raise RuntimeError("Yahoo quoteSummary returned empty")

        holdings = result[0].get("etfHoldings", {}).get("holdings", [])

        if not holdings:
            raise RuntimeError("Yahoo ETF holdings returned empty")

        weights = {}
        for item in holdings:
            ticker = clean_ticker(item.get("symbol"))
            raw_weight = item.get("holdingPercent")

            if not ticker or raw_weight is None:
                continue

            try:
                weight = float(raw_weight)
            except (ValueError, TypeError):
                continue

            if weight <= 1:
                weight *= 100

            if weight <= 0 or weight > 20:
                continue

            weights[ticker] = round(weight, 2)

        if len(weights) < 80:
            raise RuntimeError(f"Yahoo returned only {len(weights)} weights (expected 80+)")

        logging.info("Yahoo: %d weights", len(weights))
        return weights

    except Exception as e:
        logging.exception("Yahoo fetch failed: %s", e)
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
# Merge
# ============================================================

def build_final_data(constituents, weights, old_data):
    final = {}

    old_tickers = set(old_data.keys())
    new_tickers = set(constituents.keys())

    added = sorted(new_tickers - old_tickers)
    removed = sorted(old_tickers - new_tickers)
    fallback = []
    updated = []

    for ticker, info in constituents.items():
        name = info["name"]

        if ticker in weights:
            weight = weights[ticker]
        elif ticker in old_data:
            weight = old_data[ticker]["weight"]
            fallback.append(ticker)
            logging.warning("%s: using old weight %.2f%% (no Yahoo data)", ticker, weight)
        else:
            logging.warning("%s: new constituent but no weight, skipping", ticker)
            continue

        if not name and ticker in old_data:
            name = old_data[ticker]["name"]

        if ticker in old_data:
            sector = old_data[ticker]["sector"]
        else:
            sector = "Unknown"

        final[ticker] = {
            "name": name,
            "sector": sector,
            "weight": round(float(weight), 2),
        }

        if ticker in old_data and abs(old_data[ticker]["weight"] - weight) >= 0.01:
            updated.append(ticker)

    logging.info("Added: %d", len(added))
    logging.info("Removed: %d", len(removed))
    logging.info("Updated: %d", len(updated))
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

    # Keep only last 30 backups
    backups = sorted(BACKUP_DIR.glob("ndx_components_*.py"), key=lambda x: x.stat().st_mtime, reverse=True)
    for old_backup in backups[30:]:
        try:
            old_backup.unlink()
        except Exception:
            pass


# ============================================================
# Write
# ============================================================

def write_components(data):
    sorted_items = sorted(data.items(), key=lambda x: x[1]["weight"], reverse=True)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "# Nasdaq-100 Constituents (Auto-Updated)",
        f"# Updated: {now}",
        "# Source: Nasdaq API + Yahoo Finance QQQ",
        "#",
        "# Note: QQQ weights are a high-quality approximation of Nasdaq-100 weights.",
        "# They are not mathematically identical to the official NDX index weights.",
        "",
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
    lines.append('DATA_SOURCE = "Nasdaq + Yahoo Finance"')

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
    print(" Nasdaq-100 Auto Updater")
    print("=" * 65)

    logging.info("========== Update started ==========")

    old_data = parse_old_components()

    constituents = fetch_nasdaq_constituents()
    if not constituents:
        logging.error("Failed to fetch Nasdaq constituents")
        print("❌ Nasdaq constituents fetch failed")
        print("❌ ndx_components.py will NOT be modified")
        return 1

    weights = fetch_qqq_weights()
    if not weights:
        logging.error("Failed to fetch QQQ weights")
        print("❌ QQQ weights fetch failed")
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
