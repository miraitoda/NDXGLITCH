#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Nasdaq-100 Auto Updater (Tiingo + Yahoo fallback)
=================================================

Data sources:
- Nasdaq API: current Nasdaq-100 constituents
- Tiingo API (primary): QQQ holdings weights via /etf/holdings endpoint
- Yahoo Finance (fallback): if Tiingo fails
- Yahoo Finance (sector supplement): for missing sectors

Features:
- Auto-add/remove constituents
- Auto-backup
- Data validation (with reasonable thresholds)
- Full logging
- Sector auto-fill via Yahoo batch API
"""

import os
import re
import json
import shutil
import logging
import time
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
TIINGO_HOLDINGS_URL = "https://api.tiingo.com/tiingo/etf/holdings?tickers=QQQ"
YAHOO_HOLDINGS_URL = "https://query1.finance.yahoo.com/v10/finance/quoteSummary/QQQ?modules=topHoldings"
YAHOO_QUOTE_URL = "https://query1.finance.yahoo.com/v7/finance/quote"

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
        "Financials": "Financials",
        "Communication Services": "Communication Services",
    }
    normalized = sector.strip()
    return mapping.get(normalized, normalized)


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

        # 兼容 Nasdaq API 可能的多种响应结构
        rows = None
        if "data" in data:
            if isinstance(data["data"], dict) and "data" in data["data"]:
                rows = data["data"]["data"].get("rows", [])
            elif isinstance(data["data"], list):
                rows = data["data"]
            else:
                rows = data["data"].get("rows", [])

        if not rows:
            raise RuntimeError("Nasdaq returned empty data")

        result = {}
        for row in rows:
            ticker = clean_ticker(row.get("symbol"))
            name = clean_name(row.get("companyName") or row.get("name"))
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
# Fetch Tiingo weights
# ============================================================

def fetch_tiingo_weights(api_key):
    if not api_key:
        logging.warning("TIINGO_API_KEY not set, skipping Tiingo")
        return {}

    logging.info("Fetching QQQ weights from Tiingo API...")

    try:
        headers = {
            "Authorization": f"Token {api_key}",
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }

        response = requests.get(TIINGO_HOLDINGS_URL, headers=headers, timeout=30)
        
        # 增强错误处理：明确提示权限问题
        if response.status_code in (401, 403):
            logging.error(
                "Tiingo API returned %d. ETF Holdings endpoint may require a paid subscription. "
                "Please check your API key tier at https://www.tiingo.com/account/billing",
                response.status_code
            )
            return {}
        
        response.raise_for_status()
        data = response.json()

        holdings = None
        if isinstance(data, list):
            for item in data:
                if item.get("ticker") == "QQQ":
                    holdings = item.get("holdings", [])
                    break
        elif isinstance(data, dict):
            holdings = data.get("holdings", [])

        if not holdings:
            raise RuntimeError("QQQ holdings not found in Tiingo response")

        weights = {}
        for h in holdings:
            ticker = clean_ticker(h.get("symbol"))
            raw_weight = h.get("holdingPercent")
            if ticker and raw_weight is not None:
                try:
                    weight = float(raw_weight) * 100
                    if weight > 0.01:
                        weights[ticker] = round(weight, 2)
                except (ValueError, TypeError):
                    continue

        if len(weights) < 80:
            raise RuntimeError(f"Tiingo returned only {len(weights)} weights (expected 80+)")

        logging.info("Tiingo: %d weights", len(weights))
        return weights

    except requests.exceptions.RequestException as e:
        logging.error("Tiingo request failed: %s", e)
        return {}
    except Exception as e:
        logging.exception("Tiingo fetch failed: %s", e)
        return {}


# ============================================================
# Fallback: Yahoo Finance (topHoldings)
# ============================================================

def fetch_yahoo_weights():
    logging.info("Falling back to Yahoo Finance for QQQ weights...")

    try:
        response = session.get(YAHOO_HOLDINGS_URL, timeout=30)
        response.raise_for_status()
        data = response.json()

        result = data.get("quoteSummary", {}).get("result", [])
        if not result:
            raise RuntimeError("Yahoo quoteSummary returned empty")

        # 修复：使用 topHoldings 而非 etfHoldings
        top_holdings = result[0].get("topHoldings", {})
        holdings = top_holdings.get("holdings", [])
        
        if not holdings:
            raise RuntimeError("Yahoo topHoldings returned empty")

        weights = {}
        for item in holdings:
            ticker = clean_ticker(item.get("symbol"))
            raw_weight = item.get("holdingPercent")
            if not ticker or raw_weight is None:
                continue
            try:
                weight = float(raw_weight) * 100
            except (ValueError, TypeError):
                continue
            if weight <= 0 or weight > 25:  # 放宽异常阈值
                continue
            weights[ticker] = round(weight, 2)

        if len(weights) < 80:
            raise RuntimeError(f"Yahoo returned only {len(weights)} weights (expected 80+)")

        logging.info("Yahoo (fallback): %d weights", len(weights))
        return weights

    except Exception as e:
        logging.exception("Yahoo fallback failed: %s", e)
        return {}


# ============================================================
# Yahoo Finance: batch sector lookup
# ============================================================

def fetch_yahoo_sectors(tickers, batch_size=50):
    """从 Yahoo Finance v7/quote 批量获取股票 sector"""
    if not tickers:
        return {}

    logging.info("Fetching sectors from Yahoo Finance for %d stocks...", len(tickers))
    sectors = {}
    
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i+batch_size]
        symbols = ",".join(batch)
        url = f"{YAHOO_QUOTE_URL}?symbols={symbols}"
        
        try:
            response = session.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            quotes = data.get("quoteResponse", {}).get("result", [])
            for quote in quotes:
                ticker = clean_ticker(quote.get("symbol"))
                sector = quote.get("sector")
                if ticker and sector:
                    sectors[ticker] = normalize_sector(sector)
            
            # 礼貌性延迟，避免触发限流
            if i + batch_size < len(tickers):
                time.sleep(0.5)
                
        except Exception as e:
            logging.warning("Yahoo sector batch %d failed: %s", i // batch_size + 1, e)
            continue
    
    logging.info("Yahoo sectors fetched: %d", len(sectors))
    return sectors


# ============================================================
# Get weights (primary + fallback)
# ============================================================

def fetch_weights(api_key):
    weights = fetch_tiingo_weights(api_key)
    if weights:
        return weights

    logging.warning("Tiingo failed, trying Yahoo Finance fallback...")
    return fetch_yahoo_weights()


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

    # 放宽总权重校验：85%~115% 为正常区间（再平衡日可能波动）
    if total_weight < 85 or total_weight > 115:
        logging.error("Total weight abnormal: %.2f%%", total_weight)
        return False
    elif total_weight < 95 or total_weight > 105:
        logging.warning("Total weight slightly off: %.2f%% (may be rebalancing day)", total_weight)

    max_weight = max(item["weight"] for item in data.values())
    # 放宽头部股权重校验（NVDA 高峰期可能接近 20%）
    if max_weight > 25:
        logging.error("Max weight abnormal: %.2f%%", max_weight)
        return False
    elif max_weight > 20:
        logging.warning("Max weight high: %.2f%%", max_weight)

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
            logging.warning("%s: using old weight %.2f%% (no new data)", ticker, weight)
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

    # 为缺失 sector 的股票补充 sector（Yahoo 批量查询）
    missing_sector_tickers = [t for t, v in final.items() if v["sector"] == "Unknown"]
    if missing_sector_tickers:
        yahoo_sectors = fetch_yahoo_sectors(missing_sector_tickers)
        for ticker, sector in yahoo_sectors.items():
            if ticker in final:
                final[ticker]["sector"] = sector
                logging.info("%s: sector updated to '%s' (from Yahoo)", ticker, sector)
        
        still_missing = [t for t, v in final.items() if v["sector"] == "Unknown"]
        if still_missing:
            logging.warning("Still missing sector for: %s", ", ".join(still_missing))

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
        "# Source: Nasdaq API + Tiingo API (with Yahoo fallback)",
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
    lines.append('DATA_SOURCE = "Nasdaq + Tiingo/Yahoo"')

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
    print(" Nasdaq-100 Auto Updater (Tiingo + Yahoo fallback)")
    print("=" * 65)

    logging.info("========== Update started ==========")

    tiingo_api_key = os.environ.get("TIINGO_API_KEY", "").strip()
    
    if not tiingo_api_key:
        print("⚠️  Warning: TIINGO_API_KEY not set, will use Yahoo Finance directly")
    else:
        masked = "*" * (len(tiingo_api_key) - 4) + tiingo_api_key[-4:] if len(tiingo_api_key) > 4 else "****"
        print(f"  Tiingo API Key: {masked}")

    old_data = parse_old_components()

    constituents = fetch_nasdaq_constituents()
    if not constituents:
        logging.error("Failed to fetch Nasdaq constituents")
        print("❌ Nasdaq constituents fetch failed")
        print("❌ ndx_components.py will NOT be modified")
        return 1

    weights = fetch_weights(tiingo_api_key)
    if not weights:
        logging.error("Failed to fetch weights from all sources")
        print("❌ All weight sources failed")
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
