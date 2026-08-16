#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动更新纳指100成分股及权重
数据源：Schwab 官网 (QQQ 持仓)
"""

import os
import re
import requests
import pandas as pd
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
    """从 Schwab 官网获取 QQQ 持仓"""
    print("📡 正在从 Schwab 获取 QQQ 持仓...")
    
    url = "https://www.schwab.wallst.com/schwab/Prospect/research/etfs/schwabETF/index.asp?symbol=QQQ&type=holdings"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        
        # 用 pandas 解析 HTML 表格
        tables = pd.read_html(resp.text)
        
        # 找持仓表（通常第一个大表就是）
        for table in tables:
            if 'Symbol' in table.columns or 'Ticker' in table.columns:
                # 找到 ticker 列和权重列
                ticker_col = None
                weight_col = None
                for col in table.columns:
                    if 'Symbol' in str(col) or 'Ticker' in str(col):
                        ticker_col = col
                    if 'Weight' in str(col) or 'Portfolio Weight' in str(col):
                        weight_col = col
                
                if ticker_col and weight_col:
                    result = {}
                    for _, row in table.iterrows():
                        ticker = str(row[ticker_col]).strip()
                        weight_str = str(row[weight_col]).replace('%', '').strip()
                        try:
                            weight = float(weight_str)
                            if ticker and weight > 0.01:
                                result[ticker] = round(weight, 2)
                        except:
                            continue
                    
                    if result:
                        print(f"✅ 成功获取 {len(result)} 只股票权重")
                        return result
        
        print("❌ 未找到持仓表")
        return {}
        
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
        '# 数据源: Schwab 官网 (QQQ 持仓)',
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
