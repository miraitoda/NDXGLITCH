#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动更新纳指100成分股及权重
数据源（按优先级）：
1. yfinance.get_holdings() - 官方方法（首选）
2. Google 搜索 "qqq holdings" - 解析 AI Overview 或持仓表
3. Schwab 官网 ETF 持仓页面（备选）
运行频率：每周一次（由 workflow 控制）
"""

import os
import re
import time
import json
import requests
from datetime import datetime
from bs4 import BeautifulSoup

# 尝试导入 yfinance
try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False
    print("⚠️ yfinance 未安装，跳过首选数据源")


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

    pattern = r'\(\s*"([A-Z]+)"\s*,\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*([\d.]+)\s*\)'
    matches = re.findall(pattern, content)
    for ticker, name, sector, weight in matches:
        result[ticker] = (name, sector, float(weight))

    return result


# ================================================================
# 数据源 1：yfinance.get_holdings()（官方，推荐）
# ================================================================
def fetch_via_yfinance():
    """使用 yfinance 的 get_holdings() 方法"""
    if not HAS_YFINANCE:
        return {}

    print("📡 [源1] 尝试 yfinance.get_holdings()...")
    try:
        qqq = yf.Ticker("QQQ")
        
        # 方法一：get_holdings()
        if hasattr(qqq, 'get_holdings'):
            holdings_df = qqq.get_holdings()
            if holdings_df is not None and not holdings_df.empty:
                result = {}
                for col in holdings_df.columns:
                    if col.lower() in ['symbol', 'ticker']:
                        ticker_col = col
                    elif col.lower() in ['holdingpercent', 'weight', 'weight%']:
                        weight_col = col
                    elif col.lower() in ['name', 'company']:
                        name_col = col
                
                # 如果没找到标准列名，按位置猜
                if 'ticker_col' not in locals():
                    ticker_col = holdings_df.columns[0]
                if 'weight_col' not in locals():
                    weight_col = holdings_df.columns[1]
                
                for _, row in holdings_df.iterrows():
                    ticker = str(row[ticker_col]).strip()
                    weight = float(row[weight_col]) * 100
                    if ticker and weight > 0.01:
                        result[ticker] = round(weight, 2)
                
                if result:
                    print(f"✅ yfinance 成功获取 {len(result)} 只股票")
                    return result
        
        # 方法二：旧版 .holdings 属性
        if hasattr(qqq, 'holdings'):
            holdings = qqq.holdings
            if holdings is not None and not holdings.empty:
                result = {}
                for ticker, row in holdings.iterrows():
                    weight = float(row.get('holdingPercent', 0)) * 100
                    if ticker and weight > 0.01:
                        result[ticker] = round(weight, 2)
                if result:
                    print(f"✅ yfinance (旧版) 成功获取 {len(result)} 只股票")
                    return result
                    
    except Exception as e:
        print(f"⚠️ yfinance 失败: {e}")
    
    return {}


# ================================================================
# 数据源 2：Google 搜索 + AI Overview / 持仓表
# ================================================================
def fetch_via_google():
    """
    模拟 Google 搜索 "qqq holdings"，从搜索结果中提取持仓数据
    数据源：finance.yahoo.com/quote/QQQ/holdings（Google 搜索结果第一位）
    """
    print("📡 [源2] 尝试 Google 搜索 qqq holdings...")
    
    # Google 搜索 URL
    search_url = "https://www.google.com/search?q=qqq+holdings"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    }
    
    try:
        resp = requests.get(search_url, headers=headers, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # 方法A：找 AI Overview 中的持仓表
        ai_overview = soup.find('div', {'data-attrid': 'ai'})
        if ai_overview:
            # 尝试从 AI Overview 中提取 ticker 和权重
            # AI Overview 通常以表格或列表形式呈现
            print("✅ 找到 AI Overview，尝试解析持仓...")
            # 这里简化处理：用正则找 "AAPL 8.26%" 这种模式
            text = ai_overview.get_text()
            pattern = r'([A-Z]+)\s+([\d.]+)%'
            matches = re.findall(pattern, text)
            if matches:
                result = {}
                for ticker, weight_str in matches:
                    try:
                        weight = float(weight_str)
                        if ticker and weight > 0.01:
                            result[ticker] = round(weight, 2)
                    except:
                        continue
                if result:
                    print(f"✅ 从 Google AI Overview 获取 {len(result)} 只股票")
                    return result
        
        # 方法B：从搜索结果中找第一个链接 -> 跳转到 Yahoo Finance
        # 查找指向 finance.yahoo.com 的链接
        for link in soup.find_all('a', href=True):
            href = link['href']
            if 'finance.yahoo.com' in href and 'holdings' in href:
                # 提取真正的 URL
                match = re.search(r'/url\?q=([^&]+)', href)
                if match:
                    yahoo_url = match.group(1)
                    print(f"📡 跳转到 Yahoo Finance: {yahoo_url}")
                    return fetch_via_yahoo_holdings_page(yahoo_url)
                else:
                    # 直接跳转
                    return fetch_via_yahoo_holdings_page(href)
        
        # 方法C：直接尝试 Yahoo Finance holdings 页面
        print("📡 尝试直接访问 Yahoo Finance holdings 页面...")
        return fetch_via_yahoo_holdings_page("https://finance.yahoo.com/quote/QQQ/holdings")
        
    except Exception as e:
        print(f"⚠️ Google 搜索失败: {e}")
    
    return {}


# ================================================================
# 数据源 2.5：Yahoo Finance holdings 页面（被 Google 引用）
# ================================================================
def fetch_via_yahoo_holdings_page(url):
    """从 Yahoo Finance holdings 页面解析持仓数据"""
    print(f"📡 正在解析 Yahoo Finance 持仓页面...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # 找表格
        table = soup.find('table', {'data-test': 'holdings-table'})
        if not table:
            table = soup.find('table', {'class': 'table'})
        if not table:
            # 尝试找包含 "Symbol" 和 "% Weight" 的任意表格
            tables = soup.find_all('table')
            for t in tables:
                if 'Symbol' in t.get_text() and 'Weight' in t.get_text():
                    table = t
                    break
        
        if not table:
            print("⚠️ 未找到持仓表格")
            return {}
        
        rows = table.find_all('tr')
        result = {}
        for row in rows[1:]:  # 跳过表头
            cols = row.find_all('td')
            if len(cols) >= 2:
                ticker = cols[0].get_text(strip=True)
                weight_text = cols[1].get_text(strip=True).replace('%', '')
                try:
                    weight = float(weight_text)
                    if ticker and weight > 0.01:
                        result[ticker] = round(weight, 2)
                except:
                    continue
        
        if result:
            print(f"✅ 从 Yahoo Finance 页面获取 {len(result)} 只股票")
            return result
        
    except Exception as e:
        print(f"⚠️ 解析 Yahoo Finance 页面失败: {e}")
    
    return {}


# ================================================================
# 数据源 3：Schwab 官网（备选）
# ================================================================
def fetch_via_schwab():
    """从 Schwab 官网 ETF 持仓页面获取数据"""
    print("📡 [源3] 尝试 Schwab 官网...")
    url = "https://www.schwab.wallst.com/schwab/Prospect/research/etfs/schwabETF/index.asp?symbol=QQQ&type=holdings"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        
        # 用 pandas 解析 HTML 表格
        try:
            import pandas as pd
            tables = pd.read_html(resp.text)
            for table in tables:
                cols = [str(col).lower() for col in table.columns]
                col_str = ' '.join(cols)
                if ('symbol' in col_str or 'ticker' in col_str) and ('weight' in col_str or 'holding' in col_str):
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
                            print(f"✅ 从 Schwab 获取 {len(result)} 只股票")
                            return result
        except ImportError:
            print("⚠️ pandas 未安装，跳过 Schwab 解析")
            
    except Exception as e:
        print(f"⚠️ Schwab 抓取失败: {e}")
    
    return {}


# ================================================================
# 主获取函数（三重降级）
# ================================================================
def fetch_qqq_holdings():
    """多数据源降级获取 QQQ 持仓"""
    
    # 源1：yfinance 官方方法
    result = fetch_via_yfinance()
    if result:
        return result
    
    # 源2：Google 搜索 + Yahoo Finance 页面
    result = fetch_via_google()
    if result:
        return result
    
    # 源3：Schwab 官网
    result = fetch_via_schwab()
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
            name, sector = old_mapping[ticker]
        else:
            print(f"🆕 发现新股票: {ticker}，保留 ticker 作为名称")
            name, sector = ticker, '科技'

        final[ticker] = (name, sector, weight)

    sorted_items = sorted(final.items(), key=lambda x: x[1][2], reverse=True)

    lines = [
        '# 纳斯达克100成分股列表（自动更新）',
        f'# 数据更新日期: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
        '# 数据源: yfinance / Google / Schwab (多重降级)',
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
    print("📊 纳指100成分股自动更新 (多数据源降级)")
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
