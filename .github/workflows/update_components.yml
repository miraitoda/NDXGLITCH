#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动更新纳指100成分股及权重
数据源：Alpha Vantage API（主）+ Yahoo Finance（降级）
注意：只更新现有股票的权重，不删除旧股票
"""

import os
import re
import json
import requests
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


def fetch_via_alpha_vantage(api_key):
    """使用 Alpha Vantage API 获取 QQQ 持仓（只返回前 20 大）"""
    if not api_key:
        return {}

    print("📡 尝试 Alpha Vantage API...")
    url = "https://www.alphavantage.co/query"
    params = {
        "function": "ETF_PROFILE",
        "symbol": "QQQ",
        "apikey": api_key
    }
    
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        if "Error Message" in data:
            print(f"❌ Alpha Vantage 错误: {data['Error Message']}")
            return {}
        if "Note" in data and "API call frequency" in data["Note"]:
            print(f"⚠️ Alpha Vantage 限流: {data['Note']}")
            return {}
        
        holdings = data.get("holdings", [])
        if not holdings:
            return {}
        
        weights = {}
        for item in holdings:
            ticker = item.get("symbol")
            weight = item.get("weight")
            if ticker and weight:
                if isinstance(weight, str):
                    weight = float(weight.replace("%", ""))
                elif isinstance(weight, (int, float)) and weight < 1:
                    weight = weight * 100
                if weight > 0.01:
                    weights[ticker] = round(weight, 2)
        
        if weights:
            print(f"✅ Alpha Vantage 获取 {len(weights)} 只股票")
            return weights
    except Exception as e:
        print(f"⚠️ Alpha Vantage 失败: {e}")
    
    return {}


def fetch_via_yahoo():
    """降级：Yahoo Finance API"""
    print("📡 降级到 Yahoo Finance API...")
    url = "https://query1.finance.yahoo.com/v10/finance/quoteSummary/QQQ?modules=etfHoldings"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": "https://finance.yahoo.com/quote/QQQ/holdings",
    }
    
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        result = data.get("quoteSummary", {}).get("result", [])
        if not result:
            return {}
        holdings = result[0].get("etfHoldings", {}).get("holdings", [])
        if not holdings:
            return {}
        weights = {}
        for item in holdings:
            ticker = item.get("symbol")
            weight = item.get("holdingPercent")
            if ticker and weight:
                weights[ticker] = round(weight * 100, 2)
        if weights:
            print(f"✅ Yahoo Finance 获取 {len(weights)} 只股票")
            return weights
    except Exception as e:
        print(f"⚠️ Yahoo Finance 失败: {e}")
    
    return {}


def fetch_qqq_holdings(api_key):
    """获取新权重（先 Alpha Vantage，失败则 Yahoo）"""
    result = {}
    if api_key:
        result = fetch_via_alpha_vantage(api_key)
    if not result:
        result = fetch_via_yahoo()
    return result


def generate_ndx_components(old_mapping, new_weights, output_path="ndx_components.py"):
    """
    合并数据：保留所有旧股票，只更新匹配的权重
    - 旧股票在新权重中存在的 → 更新权重
    - 旧股票在新权重中不存在的 → 保留旧权重
    - 新出现的股票 → 添加（但通常是垃圾数据，忽略）
    """
    if not new_weights:
        print("⚠️ 新权重为空，保留现有数据")
        return 0

    final = {}
    
    # 1. 保留所有旧股票及其旧权重（作为基础）
    for ticker, (name, sector, old_weight) in old_mapping.items():
        final[ticker] = (name, sector, old_weight)
    
    # 2. 用新权重覆盖存在的股票
    updated_count = 0
    for ticker, new_weight in new_weights.items():
        if ticker in final:
            # 更新权重
            final[ticker] = (final[ticker][0], final[ticker][1], new_weight)
            updated_count += 1
        else:
            # 新股票（可能是数据污染），暂不添加，只打印警告
            print(f"⚠️ 忽略新出现的股票: {ticker}（不在现有列表中）")
    
    print(f"✅ 更新了 {updated_count} 只股票的权重，保留了 {len(final)} 只股票")

    # 按权重降序排序
    sorted_items = sorted(final.items(), key=lambda x: x[1][2], reverse=True)

    lines = [
        '# 纳斯达克100成分股列表（自动更新）',
        f'# 数据更新日期: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
        '# 数据源: Alpha Vantage + Yahoo Finance（仅更新权重，不删股票）',
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
    print("📊 纳指100成分股自动更新 (保留旧股票)")
    print("=" * 50)

    api_key = os.environ.get("ALPHA_VANTAGE_API_KEY", "")
    old = parse_ndx_components()
    print(f"📂 现有成分股: {len(old)} 只")

    new_weights = fetch_qqq_holdings(api_key)
    if new_weights:
        count = generate_ndx_components(old, new_weights)
    else:
        print("❌ 无法获取最新权重，保持现有数据不变")
        count = 0

    print("=" * 50)
    print("✅ 完成!")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    exit(main())
