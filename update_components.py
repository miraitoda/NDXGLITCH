#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动更新纳指100成分股及权重
数据源：Schwab 官网 QQQ 持仓页面（BeautifulSoup 直接解析表格）
运行频率：每周一次（由 workflow 控制）
"""

import os
import re
import requests
from bs4 import BeautifulSoup
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
    """从 Schwab 官网解析 QQQ 持仓表格"""
    url = "https://www.schwab.wallst.com/schwab/Prospect/research/etfs/schwabETF/index.asp?symbol=QQQ&type=holdings"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    }
    print("📡 正在从 Schwab 获取 QQQ 持仓...")
    
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # 找持仓表格（id="tthHoldingsTable"）
        table = soup.find('table', {'id': 'tthHoldingsTable'})
        if not table:
            # 备用：找 class="standard sortable" 的表格
            table = soup.find('table', {'class': 'standard sortable'})
        
        if not table:
            print("❌ 未找到持仓表格")
            return {}
        
        tbody = table.find('tbody')
        if not tbody:
            print("❌ 未找到表格主体")
            return {}
        
        rows = tbody.find_all('tr')
        result = {}
        for row in rows:
            cols = row.find_all('td')
            if len(cols) < 3:
                continue
            # 第一列是 Symbol，第三列是 % Portfolio Weight（带 % 符号）
            ticker = cols[0].get_text(strip=True)
            weight_text = cols[2].get_text(strip=True).replace('%', '')
            try:
                weight = float(weight_text)
                if ticker and weight > 0.01:
                    result[ticker] = round(weight, 2)
            except ValueError:
                continue
        
        if result:
            print(f"✅ 成功从 Schwab 获取 {len(result)} 只股票权重")
            return result
        else:
            print("❌ 未解析到任何数据")
            return {}
            
    except Exception as e:
        print(f"❌ 请求或解析失败: {e}")
        return {}


def generate_ndx_components(old_mapping, new_weights, output_path="ndx_components.py"):
    """合并新旧数据，生成新的 Python 文件"""
    if not new_weights:
        print("⚠️ 新权重为空，保留现有数据")
        return 0

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
    print("📊 纳指100成分股自动更新 (Schwab 数据源)")
    print("=" * 50)

    old = parse_ndx_components()
    print(f"📂 现有成分股: {len(old)} 只")

    new_weights = fetch_qqq_holdings()
    if new_weights:
        count = generate_ndx_components(old, new_weights)
    else:
        print("❌ 无法获取最新权重，但不会退出（保持现有数据）")
        count = 0

    print("=" * 50)
    print("✅ 完成!")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    exit(main())
