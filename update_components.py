#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动更新纳指100成分股及权重
数据源：Schwab 官网 QQQ 持仓页面（纯 HTML，稳定可靠）
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
    """从 Schwab 官网获取 QQQ 持仓（纯 HTML，无 JavaScript 渲染）"""
    print("📡 正在从 Schwab 获取 QQQ 持仓...")
    
    # Schwab QQQ 持仓页面 URL（稳定，无需 session token）
    url = "https://www.schwab.wallst.com/schwab/Prospect/research/etfs/schwabETF/index.asp?symbol=QQQ&type=holdings"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        
        # 使用 pandas 解析 HTML 表格
        tables = pd.read_html(resp.text)
        
        # 遍历所有表格，找持仓表（包含 Symbol、% Portfolio Weight 等列）
        for table in tables:
            # 检查是否包含持仓表的标志列
            cols = [str(col).lower() for col in table.columns]
            col_str = ' '.join(cols)
            
            # 持仓表的特征：包含 symbol、weight、market value 等
            if ('symbol' in col_str or 'ticker' in col_str) and ('weight' in col_str or 'holding' in col_str):
                # 找 ticker 列和权重列
                ticker_col = None
                weight_col = None
                for col in table.columns:
                    col_lower = str(col).lower()
                    if 'symbol' in col_lower or 'ticker' in col_lower:
                        ticker_col = col
                    if 'weight' in col_lower or 'holding' in col_lower:
                        weight_col = col
                
                if ticker_col and weight_col:
                    result = {}
                    for _, row in table.iterrows():
                        ticker = str(row[ticker_col]).strip()
                        weight_str = str(row[weight_col]).replace('%', '').strip()
                        try:
                            weight = float(weight_str)
                            if ticker and weight > 0.01 and ticker != 'nan':
                                result[ticker] = round(weight, 2)
                        except:
                            continue
                    
                    if result:
                        print(f"✅ 成功从 Schwab 获取 {len(result)} 只股票权重")
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
