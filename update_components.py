```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Nasdaq-100 自动更新程序
=======================

功能：
1. 从 Nasdaq 获取当前 Nasdaq-100 成分股
2. 从 Yahoo Finance 获取 QQQ 当前持仓权重
3. 自动合并成分股 + 权重
4. 自动新增成分股
5. 自动删除被剔除成分股
6. 自动备份旧的 ndx_components.py
7. 数据异常时不覆盖旧文件
8. 自动进行完整性检查
9. 自动写入 update_ndx.log

输出：
    ndx_components.py

输出格式：
    STOCKS = [
        ("NVDA", "NVIDIA Corporation", "Technology", 8.23),
        ...
    ]

注意：
QQQ 权重是 Nasdaq-100 权重的高质量近似值，
但 QQQ ETF 权重与 NDX 指数权重并非数学上完全相同。

如果你的 Dashboard 本质上分析的是 Nasdaq-100，
建议未来有条件时直接接 Nasdaq 官方 NDX 权重。
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
# 配置
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

OUTPUT_FILE = BASE_DIR / "ndx_components.py"
BACKUP_DIR = BASE_DIR / "backup_ndx"
LOG_FILE = BASE_DIR / "update_ndx.log"

NASDAQ_URL = (
    "https://api.nasdaq.com/api/quote/list-type/nasdaq100"
)

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
# 日志
# ============================================================

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    encoding="utf-8",
)

console = logging.StreamHandler()
console.setLevel(logging.INFO)

formatter = logging.Formatter(
    "%(asctime)s | %(levelname)s | %(message)s"
)

console.setFormatter(formatter)

logging.getLogger().addHandler(console)


# ============================================================
# HTTP Session
# ============================================================

session = requests.Session()
session.headers.update(HEADERS)


# ============================================================
# 工具
# ============================================================

def clean_ticker(ticker):
    """
    清理 ticker。
    """

    if not ticker:
        return None

    ticker = str(ticker).strip().upper()

    # Nasdaq/Yahoo 有时会出现特殊字符
    ticker = ticker.replace(".", "-")

    if not re.match(r"^[A-Z0-9\-]+$", ticker):
        return None

    return ticker


def clean_name(name):
    """
    清理公司名称。
    """

    if not name:
        return ""

    name = str(name).strip()

    name = name.replace('"', "'")
    name = name.replace("\n", " ")
    name = re.sub(r"\s+", " ", name)

    return name


def normalize_sector(sector):
    """
    统一行业名称。
    """

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
# 读取旧文件
# ============================================================

def parse_old_components():
    """
    从现有 ndx_components.py 中读取旧数据。

    返回：

    {
        "NVDA": {
            "name": "...",
            "sector": "...",
            "weight": 8.23
        }
    }
    """

    if not OUTPUT_FILE.exists():
        logging.warning(
            "旧文件不存在：%s",
            OUTPUT_FILE
        )
        return {}

    try:

        content = OUTPUT_FILE.read_text(
            encoding="utf-8"
        )

        pattern = re.compile(
            r'\(\s*'
            r'"([^"]+)"\s*,\s*'
            r'"([^"]*)"\s*,\s*'
            r'"([^"]*)"\s*,\s*'
            r'([\d.]+)'
            r'\s*\)'
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

        logging.info(
            "读取旧数据：%d 只股票",
            len(result)
        )

        return result

    except Exception as e:

        logging.exception(
            "读取旧文件失败：%s",
            e
        )

        return {}


# ============================================================
# Nasdaq 成分股
# ============================================================

def fetch_nasdaq_constituents():
    """
    从 Nasdaq 获取当前 Nasdaq-100 成分股。

    官方 Nasdaq API 的公开接口。
    """

    logging.info(
        "正在从 Nasdaq 获取当前成分股..."
    )

    try:

        response = session.get(
            NASDAQ_URL,
            timeout=30
        )

        response.raise_for_status()

        data = response.json()

        rows = (
            data
            .get("data", {})
            .get("data", [])
        )

        if not rows:

            raise RuntimeError(
                "Nasdaq 返回为空"
            )

        result = {}

        for row in rows:

            ticker = clean_ticker(
                row.get("symbol")
            )

            name = clean_name(
                row.get("companyName")
            )

            if not ticker:
                continue

            result[ticker] = {
                "name": name,
                "sector": "Unknown",
            }

        if len(result) < 90:

            raise RuntimeError(
                f"Nasdaq 返回异常：只有 {len(result)} 只股票"
            )

        logging.info(
            "Nasdaq 成功获取 %d 只成分股",
            len(result)
        )

        return result

    except Exception as e:

        logging.exception(
            "Nasdaq 获取成分股失败：%s",
            e
        )

        return {}


# ============================================================
# Yahoo QQQ 权重
# ============================================================

def fetch_qqq_weights():
    """
    从 Yahoo Finance 获取 QQQ holdings。

    返回：

    {
        "NVDA": 8.23,
        "AAPL": 7.10,
        ...
    }
    """

    logging.info(
        "正在从 Yahoo Finance 获取 QQQ 权重..."
    )

    try:

        response = session.get(
            YAHOO_URL,
            timeout=30
        )

        response.raise_for_status()

        data = response.json()

        result = (
            data
            .get("quoteSummary", {})
            .get("result", [])
        )

        if not result:

            raise RuntimeError(
                "Yahoo quoteSummary 返回为空"
            )

        holdings = (
            result[0]
            .get("etfHoldings", {})
            .get("holdings", [])
        )

        if not holdings:

            raise RuntimeError(
                "Yahoo ETF holdings 返回为空"
            )

        weights = {}

        for item in holdings:

            ticker = clean_ticker(
                item.get("symbol")
            )

            raw_weight = item.get(
                "holdingPercent"
            )

            if not ticker:
                continue

            if raw_weight is None:
                continue

            try:

                weight = float(raw_weight)

            except (ValueError, TypeError):

                continue

            # Yahoo 通常返回 0~1
            if weight <= 1:

                weight *= 100

            if weight <= 0:
                continue

            if weight > 20:
                logging.warning(
                    "异常权重：%s = %.2f%%",
                    ticker,
                    weight
                )
                continue

            weights[ticker] = round(
                weight,
                2
            )

        if len(weights) < 80:

            raise RuntimeError(
                f"Yahoo 权重异常：只有 {len(weights)} 只"
            )

        logging.info(
            "Yahoo 成功获取 %d 只权重",
            len(weights)
        )

        return weights

    except Exception as e:

        logging.exception(
            "Yahoo 获取权重失败：%s",
            e
        )

        return {}


# ============================================================
# 数据完整性检查
# ============================================================

def validate_data(data):
    """
    对最终数据进行严格检查。

    通过返回 True。
    """

    if not data:

        logging.error(
            "最终数据为空"
        )

        return False

    count = len(data)

    logging.info(
        "准备检查最终数据：%d 只股票",
        count
    )

    # --------------------------------------------------------
    # 数量检查
    # --------------------------------------------------------

    # Nasdaq 当前页面有时可能显示 101/103 securities，
    # 因为某些公司存在多个证券类别。
    # 因此不要机械要求 == 100。
    if count < 95 or count > 110:

        logging.error(
            "股票数量异常：%d",
            count
        )

        return False

    # --------------------------------------------------------
    # ticker 检查
    # --------------------------------------------------------

    for ticker, item in data.items():

        if not ticker:

            logging.error(
                "发现空 ticker"
            )

            return False

        if item["weight"] <= 0:

            logging.error(
                "%s 权重异常：%s",
                ticker,
                item["weight"]
            )

            return False

    # --------------------------------------------------------
    # 权重检查
    # --------------------------------------------------------

    total_weight = sum(
        item["weight"]
        for item in data.values()
    )

    logging.info(
        "权重总和：%.2f%%",
        total_weight
    )

    # QQQ holdings 页面有时因为现金、衍生品、
    # 数据截断等原因不一定严格等于 100。
    # 但如果明显偏离，就不能写入。
    if total_weight < 95 or total_weight > 105:

        logging.error(
            "权重总和严重异常：%.2f%%",
            total_weight
        )

        return False

    # --------------------------------------------------------
    # 最大权重检查
    # --------------------------------------------------------

    max_weight = max(
        item["weight"]
        for item in data.values()
    )

    if max_weight > 15:

        logging.error(
            "最大权重异常：%.2f%%",
            max_weight
        )

        return False

    logging.info(
        "数据完整性检查通过"
    )

    return True


# ============================================================
# 合并数据
# ============================================================

def build_final_data(
    constituents,
    weights,
    old_data
):
    """
    以 Nasdaq 当前成分股作为唯一名单。

    规则：

    1. Nasdaq 有 + Yahoo 有
       → 使用最新权重

    2. Nasdaq 有 + Yahoo 没有
       → 使用旧权重（仅作为临时 fallback）

    3. Nasdaq 没有
       → 删除

    4. Yahoo 有但 Nasdaq 没有
       → 忽略

    这意味着：
    成分股名单永远由 Nasdaq 决定。
    """

    final = {}

    added = []
    removed = []
    updated = []
    fallback = []

    old_tickers = set(old_data.keys())
    new_tickers = set(constituents.keys())

    # --------------------------------------------------------
    # 新增
    # --------------------------------------------------------

    added = sorted(
        new_tickers - old_tickers
    )

    # --------------------------------------------------------
    # 删除
    # --------------------------------------------------------

    removed = sorted(
        old_tickers - new_tickers
    )

    # --------------------------------------------------------
    # 构建最终数据
    # --------------------------------------------------------

    for ticker, info in constituents.items():

        name = info["name"]

        if ticker in weights:

            weight = weights[ticker]

        elif ticker in old_data:

            # 只有 Yahoo 权重暂时没有时才使用旧权重
            weight = old_data[ticker]["weight"]

            fallback.append(ticker)

            logging.warning(
                "%s 没有最新权重，暂时使用旧权重 %.2f%%",
                ticker,
                weight
            )

        else:

            # 新股票但没有权重
            logging.warning(
                "%s 是新成分股，但没有权重，跳过",
                ticker
            )

            continue

        # 名称优先使用 Nasdaq
        if not name and ticker in old_data:

            name = old_data[ticker]["name"]

        # 行业暂时沿用旧数据
        if ticker in old_data:

            sector = old_data[ticker]["sector"]

        else:

            sector = "Unknown"

        final[ticker] = {
            "name": name,
            "sector": sector,
            "weight": round(
                float(weight),
                2
            ),
        }

        if ticker in old_data:

            if (
                abs(
                    old_data[ticker]["weight"]
                    - weight
                ) >= 0.01
            ):

                updated.append(ticker)

    logging.info(
        "新增：%d",
        len(added)
    )

    logging.info(
        "删除：%d",
        len(removed)
    )

    logging.info(
        "权重变化：%d",
        len(updated)
    )

    if fallback:

        logging.warning(
            "使用旧权重的股票：%d",
            len(fallback)
        )

    if added:

        logging.info(
            "新增股票：%s",
            ", ".join(added)
        )

    if removed:

        logging.info(
            "删除股票：%s",
            ", ".join(removed)
        )

    return final


# ============================================================
# 备份
# ============================================================

def backup_old_file():
    """
    更新前自动备份。
    """

    if not OUTPUT_FILE.exists():

        return

    BACKUP_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    backup_file = (
        BACKUP_DIR
        / f"ndx_components_{timestamp}.py"
    )

    shutil.copy2(
        OUTPUT_FILE,
        backup_file
    )

    logging.info(
        "旧文件已备份：%s",
        backup_file
    )

    # 只保留最近 30 个备份
    backups = sorted(
        BACKUP_DIR.glob(
            "ndx_components_*.py"
        ),
        key=lambda x: x.stat().st_mtime,
        reverse=True
    )

    for old_backup in backups[30:]:

        try:
            old_backup.unlink()
        except Exception:
            pass


# ============================================================
# 写入文件
# ============================================================

def write_components(data):
    """
    写入 ndx_components.py
    """

    sorted_items = sorted(
        data.items(),
        key=lambda x: x[1]["weight"],
        reverse=True
    )

    now = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    lines = []

    lines.append(
        "# 纳斯达克100成分股列表（自动更新）"
    )

    lines.append(
        f"# 数据更新时间: {now}"
    )

    lines.append(
        "# 成分股来源: Nasdaq"
    )

    lines.append(
        "# 权重来源: Yahoo Finance QQQ"
    )

    lines.append(
        "#"
    )

    lines.append(
        "# 注意：QQQ 权重为 Nasdaq-100 权重的近似值，"
    )

    lines.append(
        "# 不保证与 NDX 官方权重逐项完全一致。"
    )

    lines.append(
        ""
    )

    lines.append(
        "STOCKS = ["
    )

    for ticker, item in sorted_items:

        name = item["name"]
        sector = item["sector"]
        weight = item["weight"]

        lines.append(
            f'    ("{ticker}", '
            f'"{name}", '
            f'"{sector}", '
            f'{weight:.2f}),'
        )

    lines.append(
        "]"
    )

    lines.append(
        ""
    )

    lines.append(
        'SECTORS = sorted(set(s[2] for s in STOCKS))'
    )

    lines.append(
        ""
    )

    lines.append(
        f'LAST_UPDATE = "{now}"'
    )

    lines.append(
        'DATA_SOURCE = "Nasdaq + Yahoo Finance"'
    )

    temp_file = OUTPUT_FILE.with_suffix(
        ".tmp"
    )

    try:

        temp_file.write_text(
            "\n".join(lines),
            encoding="utf-8"
        )

        # 最后一步才真正替换
        temp_file.replace(
            OUTPUT_FILE
        )

        logging.info(
            "成功写入：%s",
            OUTPUT_FILE
        )

        logging.info(
            "最终股票数量：%d",
            len(sorted_items)
        )

        return True

    except Exception as e:

        logging.exception(
            "写入文件失败：%s",
            e
        )

        if temp_file.exists():

            try:
                temp_file.unlink()
            except Exception:
                pass

        return False


# ============================================================
# 主程序
# ============================================================

def main():

    print()
    print("=" * 65)
    print(" Nasdaq-100 自动更新")
    print("=" * 65)

    logging.info(
        "========== 开始更新 =========="
    )

    # --------------------------------------------------------
    # 1. 读取旧数据
    # --------------------------------------------------------

    old_data = parse_old_components()

    # --------------------------------------------------------
    # 2. Nasdaq 成分股
    # --------------------------------------------------------

    constituents = fetch_nasdaq_constituents()

    if not constituents:

        logging.error(
            "无法获取 Nasdaq 成分股"
        )

        print(
            "❌ Nasdaq 成分股获取失败"
        )

        print(
            "❌ 本次不会修改 ndx_components.py"
        )

        return 1

    # --------------------------------------------------------
    # 3. Yahoo 权重
    # --------------------------------------------------------

    weights = fetch_qqq_weights()

    if not weights:

        logging.error(
            "无法获取 QQQ 权重"
        )

        print(
            "❌ QQQ 权重获取失败"
        )

        print(
            "❌ 本次不会修改 ndx_components.py"
        )

        return 1

    # --------------------------------------------------------
    # 4. 合并
    # --------------------------------------------------------

    final_data = build_final_data(
        constituents,
        weights,
        old_data
    )

    # --------------------------------------------------------
    # 5. 完整性检查
    # --------------------------------------------------------

    if not validate_data(final_data):

        logging.error(
            "最终数据检查失败"
        )

        print(
            "❌ 数据完整性检查失败"
        )

        print(
            "❌ 本次不会修改 ndx_components.py"
        )

        return 1

    # --------------------------------------------------------
    # 6. 备份
    # --------------------------------------------------------

    backup_old_file()

    # --------------------------------------------------------
    # 7. 写入
    # --------------------------------------------------------

    if not write_components(final_data):

        print(
            "❌ 文件写入失败"
        )

        return 1

    # --------------------------------------------------------
    # 完成
    # --------------------------------------------------------

    print()
    print("=" * 65)
    print(" ✅ Nasdaq-100 更新成功")
    print("=" * 65)
    print(
        f" 成分股数量：{len(final_data)}"
    )

    print(
        f" 输出文件：{OUTPUT_FILE}"
    )

    print("=" * 65)

    logging.info(
        "========== 更新成功 =========="
    )

    return 0


if __name__ == "__main__":

    raise SystemExit(
        main()
    )
```
