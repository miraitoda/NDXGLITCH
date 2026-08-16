#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动更新纳指100成分股及权重
数据源：Yahoo Finance API (QQQ 持仓)
运行频率：每周一次（由 workflow 控制）
"""

import os
import re
import time
import json
import requests
from datetime import datetime


# ================================================================
# 1. 读取现有的 ndx_components.py，保留名称和行业映射
# ================================================================
def parse_ndx_components(filepath="ndx_components.py"):
    """从现有文件解析出 {ticker: (name, sector, weight)}"""
    result = {}
    if not os.path.exists(filepath):
        return result

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # 匹配 STOCKS = [ ("AAPL", "苹果", "科技", 11.04), ... ]
    pattern = r'\(\s*"([A-Z]+)"\s*,\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*([\d.]+)\s*\)'
    matches = re.findall(pattern, content)
    for ticker, name, sector, weight in matches:
        result[ticker] = (name, sector, float(weight))

    return result


# ================================================================
# 2. 从 Yahoo Finance API 获取 QQQ 持仓
# ================================================================
def fetch_qqq_holdings():
    """通过 Yahoo Finance API 获取 QQQ 最新持仓，返回 {ticker: weight} 字典"""
    print("📡 正在通过 API 获取 QQQ 持仓...")
    url = "https://query1.finance.yahoo.com/v10/finance/quoteSummary/QQQ?modules=etfHoldings"

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()

        # 解析持仓
        holdings_data = data.get("quoteSummary", {}).get("result", [])[0].get("etfHoldings", {})
        holdings_list = holdings_data.get("holdings", [])

        if not holdings_list:
            print("❌ API 返回的持仓列表为空")
            return {}

        result = {}
        for item in holdings_list:
            ticker = item.get("symbol")
            weight = item.get("holdingPercent")  # 返回的是小数，如 0.0772 表示 7.72%
            if ticker and weight:
                result[ticker] = round(weight * 100, 2)  # 转为百分比

        print(f"✅ 成功获取 {len(result)} 只股票权重")
        return result

    except requests.exceptions.RequestException as e:
        print(f"❌ 网络请求失败: {e}")
        return {}
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        print(f"❌ 解析数据失败: {e}")
        return {}


# ================================================================
# 3. 如果出现新股票，尝试获取名称和行业（使用 Yahoo Finance info）
# ================================================================
def fetch_stock_info(ticker):
    """获取单只股票的名称和行业（通过 yfinance，但仅用于新股票）"""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        info = t.info
        name = info.get('shortName', ticker)
        sector = info.get('sector', '科技')
        return name, sector
    except:
        return ticker, '科技'


# ================================================================
# 4. 生成新的 ndx_components.py
# ================================================================
def generate_ndx_components(old_mapping, new_weights, output_path="ndx_components.py"):
    """合并新旧数据，生成新的 Python 文件"""

    # 合并数据：保留旧名称/行业，用新权重覆盖
    final = {}
    all_tickers = set(old_mapping.keys()) | set(new_weights.keys())

    for ticker in all_tickers:
        weight = new_weights.get(ticker, 0.0)
        if weight == 0.0:
            # 如果在 QQQ 持仓中找不到，可能已经被剔除，跳过
            continue

        if ticker in old_mapping:
            name, sector = old_mapping[ticker]
        else:
            print(f"🆕 发现新股票: {ticker}，尝试获取信息...")
            name, sector = fetch_stock_info(ticker)
            time.sleep(0.5)

        final[ticker] = (name, sector, weight)

    # 按权重降序排序
    sorted_items = sorted(final.items(), key=lambda x: x[1][2], reverse=True)

    # 生成文件内容
    lines = [
        '# 纳斯达克100成分股列表（自动更新）',
        f'# 数据更新日期: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
        '# 数据源: Yahoo Finance API (QQQ 持仓)',
        '#',
        'STOCKS = [',
    ]

    for ticker, (name, sector, weight) in sorted_items:
        lines.append(f'    ("{ticker}", "{name}", "{sector}", {weight:.2f}),')

    lines.append(']')
    lines.append('')
    lines.append('SECTORS = sorted(set(s[2] for s in STOCKS))')

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"✅ 已更新 {output_path}，共 {len(sorted_items)} 只股票")
    return len(sorted_items)


# ================================================================
# 5. 主函数
# ================================================================
def main():
    print("=" * 50)
    print("📊 纳指100成分股自动更新 (每周)")
    print("=" * 50)

    old = parse_ndx_components()
    print(f"📂 现有成分股: {len(old)} 只")

    new_weights = fetch_qqq_holdings()
    if not new_weights:
        print("❌ 无法获取最新权重，退出")
        return 1

    count = generate_ndx_components(old, new_weights)

    print("=" * 50)
    print("✅ 完成!")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    exit(main())
