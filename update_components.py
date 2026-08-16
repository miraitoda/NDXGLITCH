#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动更新纳指100成分股及权重
数据源：Yahoo Finance CSV 导出 (QQQ 持仓)
"""

import os
import re
import requests
import csv
import io
from datetime import datetime


def parse_ndx_components(filepath="ndx_components.py"):
    """从现有文件解析出 {ticker: (name, sector, weight)}"""
    result = {}
    if not os.path.exists(filepath):
        return result

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = r'\(\s*"([A-Z]+)"\s*,\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*([\d.]+)\s*\)'
    matches = re.findall(pattern, content)
    for ticker, name, sector, weight in matches:
        result[ticker] = (name, sector, float(weight))

    return result


def fetch_qqq_holdings():
    """从 Yahoo Finance CSV 导出获取 QQQ 持仓"""
    print("📡 正在从 Yahoo Finance 下载 QQQ 持仓 CSV...")
    url = "https://query1.finance.yahoo.com/v7/finance/quote/QQQ/holdings?download=1"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()

        # 解析 CSV
        content = resp.text
        # 跳过注释行（以 # 开头）
        lines = [line for line in content.splitlines() if not line.startswith('#')]
        csv_data = csv.DictReader(lines)

        result = {}
        for row in csv_data:
            # 列名可能是 'Symbol', 'Name', '% Weight'
            symbol = row.get('Symbol', '').strip()
            weight_str = row.get('% Weight', '').replace('%', '').strip()
            if symbol and weight_str:
                try:
                    weight = float(weight_str)
                    if weight > 0.01:
                        result[symbol] = round(weight, 2)
                except ValueError:
                    continue

        print(f"✅ 成功获取 {len(result)} 只股票权重")
        return result

    except Exception as e:
        print(f"❌ 抓取失败: {e}")
        return {}


def generate_ndx_components(old_mapping, new_weights, output_path="ndx_components.py"):
    """合并新旧数据，生成新的 Python 文件"""
    final = {}
    all_tickers = set(old_mapping.keys()) | set(new_weights.keys())

    for ticker in all_tickers:
        weight = new_weights.get(ticker, 0.0)
        if weight == 0.0:
            continue

        if ticker in old_mapping:
            name, sector = old_mapping[ticker]
        else:
            print(f"🆕 发现新股票: {ticker}，保留 ticker 作为名称")
            name, sector = ticker, '科技'

        final[ticker] = (name, sector, weight)

    sorted_items = sorted(final.items(), key=lambda x: x[1][2], reverse=True)

    lines = [
        '# 纳斯达克100成分股列表（自动更新）',
        f'# 数据更新日期: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
        '# 数据源: Yahoo Finance CSV 导出 (QQQ 持仓)',
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
