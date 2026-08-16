#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动更新纳指100成分股及权重
数据源：Alpha Vantage API（主）+ Yahoo Finance API（降级备选）
运行频率：每周一次（由 workflow 控制）
"""

import os
import re
import json
import time
import requests
from datetime import datetime


# ================================================================
# Alpha Vantage API Key（从环境变量读取）
# ================================================================
ALPHA_VANTAGE_API_KEY = os.environ.get("ALPHA_VANTAGE_API_KEY", "")


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


# ================================================================
# 数据源 1：Alpha Vantage API（首选）
# ================================================================
def fetch_via_alpha_vantage():
    """使用 Alpha Vantage ETF_PROFILE API 获取 QQQ 持仓"""
    if not ALPHA_VANTAGE_API_KEY:
        print("⚠️ Alpha Vantage API Key 未配置，跳过")
        return {}

    print("📡 [源1] 尝试 Alpha Vantage API...")
    url = "https://www.alphavantage.co/query"
    params = {
        "function": "ETF_PROFILE",
        "symbol": "QQQ",
        "apikey": ALPHA_VANTAGE_API_KEY
    }
    
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        # 检查错误
        if "Error Message" in data:
            print(f"❌ Alpha Vantage 错误: {data['Error Message']}")
            return {}
        
        # 检查限流
        if "Note" in data and "API call frequency" in data["Note"]:
            print(f"⚠️ Alpha Vantage 限流: {data['Note']}")
            return {}
        
        holdings = data.get("holdings", [])
        if not holdings:
            print("❌ Alpha Vantage 未返回持仓数据")
            return {}
        
        weights = {}
        for item in holdings:
            ticker = item.get("symbol")
            weight = item.get("weight")
            if ticker and weight:
                # weight 可能是小数（0.0855）或百分比字符串（"8.55%"）
                if isinstance(weight, str):
                    weight = float(weight.replace("%", ""))
                elif isinstance(weight, (int, float)):
                    if weight < 1:  # 0.0855 表示 8.55%
                        weight = weight * 100
                if weight > 0.01:
                    weights[ticker] = round(weight, 2)
        
        if weights:
            print(f"✅ Alpha Vantage 成功获取 {len(weights)} 只股票")
            return weights
        else:
            print("❌ Alpha Vantage 未解析到有效数据")
            return {}
            
    except requests.exceptions.RequestException as e:
        print(f"⚠️ Alpha Vantage 网络请求失败: {e}")
        return {}
    except json.JSONDecodeError as e:
        print(f"⚠️ Alpha Vantage JSON 解析失败: {e}")
        return {}


# ================================================================
# 数据源 2：Yahoo Finance API（降级备选）
# ================================================================
def fetch_via_yahoo():
    """降级方案：使用 Yahoo Finance API"""
    print("📡 [源2] 降级到 Yahoo Finance API...")
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
            print(f"✅ Yahoo Finance 成功获取 {len(weights)} 只股票（降级）")
            return weights
        return {}
        
    except Exception as e:
        print(f"⚠️ Yahoo Finance 降级失败: {e}")
        return {}


# ================================================================
# 主获取函数（降级链）
# ================================================================
def fetch_qqq_holdings():
    """多数据源降级获取 QQQ 持仓"""
    
    # 源1：Alpha Vantage（如果 API Key 存在）
    if ALPHA_VANTAGE_API_KEY:
        result = fetch_via_alpha_vantage()
        if result:
            return result
    
    # 源2：Yahoo Finance（降级备选）
    result = fetch_via_yahoo()
    if result:
        return result
    
    print("❌ 所有数据源均失败")
    return {}


# ================================================================
# 生成 ndx_components.py
# ================================================================
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
            name, sector, _ = old_mapping[ticker]
        else:
            print(f"🆕 发现新股票: {ticker}，保留 ticker 作为名称")
            name, sector = ticker, '科技'

        final[ticker] = (name, sector, weight)

    sorted_items = sorted(final.items(), key=lambda x: x[1][2], reverse=True)

    lines = [
        '# 纳斯达克100成分股列表（自动更新）',
        f'# 数据更新日期: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
        '# 数据源: Alpha Vantage API + Yahoo Finance（降级）',
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
# 主函数
# ================================================================
def main():
    print("=" * 50)
    print("📊 纳指100成分股自动更新 (Alpha Vantage + 降级)")
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
