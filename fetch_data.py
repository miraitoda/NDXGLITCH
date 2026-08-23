#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
纳指100每日收盘 Dashboard 数据抓取脚本
赛博朋克 24 色 · 动态数据注入 · 音效引擎 · 历史快照
"""

import json
import math
import os
import sys
from datetime import datetime, timedelta
from collections import defaultdict
import hashlib
import colorsys

import yfinance as yf

# 假设 ndx_components.py 中定义了 STOCKS 列表
from ndx_components import STOCKS

OUTPUT_DIR = "docs"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "index.html")


# =====================================================================
# 24 套赛博朋克配色（涨/跌色）
# 完全避开 #0ff / #f0f 轴
# =====================================================================
COLOR_PALETTES = [
    {"rise": "#FF5E00", "fall": "#00BFFF"},   # 氖橙·赛博蓝
    {"rise": "#FFD700", "fall": "#8A2BE2"},   # 霓虹金·暗影紫
    {"rise": "#39FF14", "fall": "#FF1493"},   # 酸液绿·霓虹粉
    {"rise": "#00CED1", "fall": "#FF4500"},   # 绿松石·熔岩橙
    {"rise": "#9B59B6", "fall": "#F1C40F"},   # 合成紫·电光黄
    {"rise": "#FF2400", "fall": "#1E90FF"},   # 深红·电光蓝
    {"rise": "#FFBF00", "fall": "#4B0082"},   # 琥珀·深海靛蓝
    {"rise": "#FF6F61", "fall": "#008080"},   # 霓虹珊瑚·钴绿
    {"rise": "#BF00FF", "fall": "#00FF7F"},   # 电光紫·薄荷
    {"rise": "#00FF7F", "fall": "#FF007F"},   # 薄荷·热力粉
    {"rise": "#FF4500", "fall": "#0047AB"},   # 橙红·钴蓝
    {"rise": "#7FFF00", "fall": "#8B00FF"},   # 查特酒绿·暗黑紫
    {"rise": "#00BFFF", "fall": "#FF69B4"},   # 深蓝·亮粉
    {"rise": "#FFD700", "fall": "#DC143C"},   # 金·深红
    {"rise": "#00FA9A", "fall": "#9400D3"},   # 春绿·紫罗兰
    {"rise": "#4682B4", "fall": "#FF1A1A"},   # 钢蓝·霓虹红
    {"rise": "#FF8C00", "fall": "#00CED1"},   # 暗橙·绿松石
    {"rise": "#FF1493", "fall": "#39FF14"},   # 深粉·酸液绿
    {"rise": "#1E90FF", "fall": "#FFD700"},   # 道奇蓝·金
    {"rise": "#32CD32", "fall": "#BF00FF"},   # 石灰绿·电光紫
    {"rise": "#FF69B4", "fall": "#00BFFF"},   # 热粉·深蓝
    {"rise": "#FFBF00", "fall": "#1E90FF"},   # 琥珀·道奇蓝
    {"rise": "#00FF7F", "fall": "#FF4500"},   # 薄荷·橙红
    {"rise": "#8A2BE2", "fall": "#FFD700"},   # 蓝紫·金
]


# =====================================================================
# 颜色工具函数
# =====================================================================
def hex_to_rgb(hex_str):
    hex_str = hex_str.lstrip("#")
    return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))

def rgb_to_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(*rgb)

def adjust_brightness(hex_str, factor):
    """调整颜色亮度，factor > 1 变亮，< 1 变暗"""
    r, g, b = hex_to_rgb(hex_str)
    h, l, s = colorsys.rgb_to_hls(r/255, g/255, b/255)
    l = min(1.0, l * factor)
    r2, g2, b2 = colorsys.hls_to_rgb(h, l, s)
    return rgb_to_hex((int(r2*255), int(g2*255), int(b2*255)))

def hex_to_rgba(hex_str, alpha):
    r, g, b = hex_to_rgb(hex_str)
    return f"rgba({r},{g},{b},{alpha})"


# =====================================================================
# 根据日期选择主题索引（每天固定）
# =====================================================================
def get_theme_index(date_str):
    hash_obj = hashlib.md5(date_str.encode())
    return int(hash_obj.hexdigest(), 16) % len(COLOR_PALETTES)


# =====================================================================
# 根据调色板生成完整的主题 CSS 变量（夜间 + 日间），变量名与原始模板完全一致
# =====================================================================
def build_theme_css(palette, light_factor=1.4):
    """
    palette: {'rise': '#...', 'fall': '#...'}
    light_factor: 日间模式亮度提升系数
    返回一段 CSS 字符串，包含 :root 和 html.light 下的变量覆盖
    """
    rise_dark = palette["rise"]
    fall_dark = palette["fall"]
    rise_light = adjust_brightness(rise_dark, light_factor)
    fall_light = adjust_brightness(fall_dark, light_factor)

    def gen_vars(rise, fall):
        rise_bg = hex_to_rgba(rise, 0.12)
        fall_bg = hex_to_rgba(fall, 0.12)
        glitch1 = rise
        glitch2 = fall
        shadow_rise = f"0 0 30px {hex_to_rgba(rise, 0.25)}"
        shadow_fall = f"0 0 30px {hex_to_rgba(fall, 0.25)}"
        glow_rise = hex_to_rgba(rise, 0.25)
        glow_fall = hex_to_rgba(fall, 0.25)
        badge_border = hex_to_rgba(rise, 0.3)
        return {
            "rise": rise,
            "fall": fall,
            "rise_bg": rise_bg,
            "fall_bg": fall_bg,
            "glitch1": glitch1,
            "glitch2": glitch2,
            "shadow_rise": shadow_rise,
            "shadow_fall": shadow_fall,
            "glow_rise": glow_rise,
            "glow_fall": glow_fall,
            "badge_border": badge_border,
        }

    dark = gen_vars(rise_dark, fall_dark)
    light = gen_vars(rise_light, fall_light)

    # 使用原始模板中的变量名（连字符）
    css = f""":root {{
  --color-rise: {dark['rise']};
  --color-fall: {dark['fall']};
  --color-rise-bg: {dark['rise_bg']};
  --color-fall-bg: {dark['fall_bg']};
  --glitch-color1: {dark['glitch1']};
  --glitch-color2: {dark['glitch2']};
  --shadow-rise: {dark['shadow_rise']};
  --shadow-fall: {dark['shadow_fall']};
  --glow-rise: {dark['glow_rise']};
  --glow-fall: {dark['glow_fall']};
  --badge-border: {dark['badge_border']};
}}

html.light {{
  --color-rise: {light['rise']};
  --color-fall: {light['fall']};
  --color-rise-bg: {light['rise_bg']};
  --color-fall-bg: {light['fall_bg']};
  --glitch-color1: {light['glitch1']};
  --glitch-color2: {light['glitch2']};
  --shadow-rise: {light['shadow_rise']};
  --shadow-fall: {light['shadow_fall']};
  --glow-rise: {light['glow_rise']};
  --glow-fall: {light['glow_fall']};
  --badge-border: {light['badge_border']};
}}
"""
    return css


# =====================================================================
# 数据抓取函数（完全保持原样）
# =====================================================================
def ensure_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def fetch_stock_data(tickers, max_batch=25):
    all_data = {}
    for i in range(0, len(tickers), max_batch):
        batch = tickers[i:i + max_batch]
        print(f"  批次 {i // max_batch + 1}: {len(batch)} 只...")
        try:
            data = yf.download(
                " ".join(batch),
                period="5d",
                interval="1d",
                progress=False,
                threads=True,
                group_by="ticker"
            )
            if data.empty:
                print(f"    警告: 批次返回空数据")
                continue
            if len(batch) == 1:
                all_data[batch[0]] = data
            else:
                for ticker in batch:
                    if ticker in data.columns.get_level_values(0):
                        all_data[ticker] = data[ticker]
                    else:
                        print(f"    警告: {ticker} 不在返回数据中")
        except Exception as e:
            print(f"    失败: {e}")
    return all_data


def fetch_index_history(ticker="^NDX", days=30):
    try:
        t = yf.Ticker(ticker)
        end = datetime.now()
        start = end - timedelta(days=days + 15)
        hist = t.history(start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"))
        closes = hist["Close"].dropna().tolist()
        if len(closes) < days:
            print(f"  警告: 仅获取到 {len(closes)} 天历史数据，目标 {days} 天")
        return [round(float(c), 2) for c in closes[-days:]]
    except Exception as e:
        print(f"  指数历史失败: {e}")
        return []


def fetch_index_info(ticker="^NDX"):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="5d", interval="1d")
        if len(hist) < 2:
            return None
        latest = hist.iloc[-1]
        prev = hist.iloc[-2]
        price = float(latest["Close"])
        prev_close = float(prev["Close"])
        change = round((price - prev_close) / prev_close * 100, 2)
        return {"price": round(price, 2), "prev_close": round(prev_close, 2), "change": change}
    except Exception as e:
        print(f"  指数当日失败: {e}")
        return None


def build_data():
    tickers = [s[0] for s in STOCKS]
    print("\n抓取个股数据...")
    raw_data = fetch_stock_data(tickers)
    print(f"  成功获取 {len(raw_data)} 只股票数据")

    stocks = []
    for ticker, name, sector, weight in STOCKS:
        if ticker not in raw_data:
            print(f"  缺失: {ticker}")
            continue
        df = raw_data[ticker]
        if df is None or df.empty or len(df) < 2:
            print(f"  数据不足: {ticker} (len={len(df) if df is not None else 0})")
            continue
        try:
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            close = float(latest["Close"])
            prev_close = float(prev["Close"])
            change = round((close - prev_close) / prev_close * 100, 2)
            if math.isnan(change):
                print(f"  NaN跳过: {ticker}")
                continue
            stocks.append({"ticker": ticker, "name": name, "sector": sector, "weight": weight, "change": change})
        except Exception as e:
            print(f"  处理失败 {ticker}: {e}")

    print(f"  成功解析 {len(stocks)} 只股票")

    if len(stocks) < 50:
        print(f"警告: 仅获取到 {len(stocks)} 只，使用模拟数据...")
        return build_mock_data()

    index_info = fetch_index_info("^NDX")
    if index_info is None:
        total_weight = sum(s["weight"] for s in stocks)
        weighted_change = sum(s["weight"] * s["change"] for s in stocks) / total_weight
        index_info = {"price": 0, "prev_close": 0, "change": round(weighted_change, 2)}

    up = sum(1 for s in stocks if s["change"] > 0)
    down = sum(1 for s in stocks if s["change"] < 0)
    flat = sum(1 for s in stocks if s["change"] == 0)
    index_info.update({"up": up, "down": down, "flat": flat, "total": len(stocks)})

    sectors = defaultdict(lambda: {"weight": 0, "total_change": 0, "count": 0})
    for s in stocks:
        if math.isnan(s["change"]):
            continue
        sectors[s["sector"]]["weight"] += s["weight"]
        sectors[s["sector"]]["total_change"] += s["change"] * s["weight"]
        sectors[s["sector"]]["count"] += 1

    sector_list = []
    for name, d in sectors.items():
        sector_list.append({
            "name": name, "weight": round(d["weight"], 2),
            "change": round(d["total_change"] / d["weight"], 2) if d["weight"] > 0 else 0,
            "count": d["count"]
        })
    sector_list.sort(key=lambda x: -x["weight"])

    bins = [(-999, -3), (-3, -2), (-2, -1), (-1, 0), (0, 1), (1, 2), (2, 3), (3, 999)]
    labels = ["<-3%", "-3~-2%", "-2~-1%", "-1~0%", "0~1%", "1~2%", "2~3%", ">3%"]
    counts = [0] * len(bins)
    for s in stocks:
        c = s["change"]
        for i, (lo, hi) in enumerate(bins):
            if (lo <= c < hi) or (hi == 999 and c >= lo) or (lo == -999 and c < hi):
                counts[i] += 1
                break

    history = fetch_index_history("^NDX", 30)

    sorted_w = sorted(stocks, key=lambda x: -x["weight"])
    top15 = sorted_w[:15]
    others = sorted_w[15:]
    ow = sum(s["weight"] for s in others)
    oc = sum(s["weight"] * s["change"] for s in others) / ow if ow > 0 else 0
    pie = top15 + [{"ticker": "其他", "name": f"其他{len(others)}只", "sector": "", "weight": round(ow, 2), "change": round(oc, 2)}]

    # 选择当日配色主题
    date_str = datetime.now().strftime("%Y-%m-%d")
    theme_idx = get_theme_index(date_str)
    palette = COLOR_PALETTES[theme_idx]
    theme_css = build_theme_css(palette)

    result = {
        "index": index_info,
        "stocks": stocks,
        "pie_stocks": pie,
        "sectors": sector_list,
        "bins": {"labels": labels, "counts": counts},
        "history": history,
        "date": date_str,
        "theme_css": theme_css,
        "theme_idx": theme_idx,
    }

    return result


def build_mock_data():
    import random
    random.seed(42)
    stocks = []
    for ticker, name, sector, weight in STOCKS:
        base = random.gauss(0.3, 1.5)
        if weight > 3:
            base = random.gauss(0.2, 1.0)
        change = round(base, 2)
        stocks.append({"ticker": ticker, "name": name, "sector": sector, "weight": weight, "change": change})

    total_weight = sum(s["weight"] for s in stocks)
    index_change = round(sum(s["weight"] * s["change"] for s in stocks) / total_weight, 2)
    up = sum(1 for s in stocks if s["change"] > 0)
    down = sum(1 for s in stocks if s["change"] < 0)

    sectors = defaultdict(lambda: {"weight": 0, "total_change": 0, "count": 0})
    for s in stocks:
        if math.isnan(s["change"]):
            continue
        sectors[s["sector"]]["weight"] += s["weight"]
        sectors[s["sector"]]["total_change"] += s["change"] * s["weight"]
        sectors[s["sector"]]["count"] += 1

    sector_list = []
    for name, d in sectors.items():
        sector_list.append({
            "name": name, "weight": round(d["weight"], 2),
            "change": round(d["total_change"] / d["weight"], 2) if d["weight"] > 0 else 0,
            "count": d["count"]
        })
    sector_list.sort(key=lambda x: -x["weight"])

    bins = [(-999, -3), (-3, -2), (-2, -1), (-1, 0), (0, 1), (1, 2), (2, 3), (3, 999)]
    labels = ["<-3%", "-3~-2%", "-2~-1%", "-1~0%", "0~1%", "1~2%", "2~3%", ">3%"]
    counts = [0] * len(bins)
    for s in stocks:
        c = s["change"]
        for i, (lo, hi) in enumerate(bins):
            if (lo <= c < hi) or (hi == 999 and c >= lo) or (lo == -999 and c < hi):
                counts[i] += 1
                break

    history = []
    price = 19500
    for _ in range(30):
        change = random.gauss(0.15, 1.2)
        price = price * (1 + change / 100)
        history.append(round(price, 2))

    sorted_w = sorted(stocks, key=lambda x: -x["weight"])
    top15 = sorted_w[:15]
    others = sorted_w[15:]
    ow = sum(s["weight"] for s in others)
    oc = sum(s["weight"] * s["change"] for s in others) / ow if ow > 0 else 0
    pie = top15 + [{"ticker": "其他", "name": f"其他{len(others)}只", "sector": "", "weight": round(ow, 2), "change": round(oc, 2)}]

    date_str = datetime.now().strftime("%Y-%m-%d")
    theme_idx = get_theme_index(date_str)
    palette = COLOR_PALETTES[theme_idx]
    theme_css = build_theme_css(palette)

    result = {
        "index": {"price": history[-1], "prev_close": round(history[-1] / (1 + index_change/100), 2), "change": index_change, "up": up, "down": down, "flat": 0, "total": len(stocks)},
        "stocks": stocks,
        "pie_stocks": pie,
        "sectors": sector_list,
        "bins": {"labels": labels, "counts": counts},
        "history": history,
        "date": date_str,
        "theme_css": theme_css,
        "theme_idx": theme_idx,
    }

    return result


# =====================================================================
# HTML 模板（像素终端风格 · 全英文 · 无三角符号 · 网格背景 · 8-bit 音效）
# 注意：所有布局改动均在模板内完成，Python 逻辑（颜色、数据）未受影响
# =====================================================================
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=yes" />
  <title>NDX · PIXEL TERMINAL</title>
  <link href="https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap" rel="stylesheet" />
  <style>
    /* ================================================================
       ROOT VARIABLES (由 Python 动态注入)
    ================================================================ */
    :root {
      --bg-body: #0a0a0f;
      --bg-sticky: rgba(10, 10, 15, 0.85);
      --bg-card: rgba(255, 255, 255, 0.03);
      --border-color: rgba(255, 255, 255, 0.08);
      --text-primary: #f0f0f0;
      --text-secondary: #aabbcc;
      --text-muted: #556677;
      --text-dim: #334455;
    }
    html.light {
      --bg-body: #e8ecf2;
      --bg-sticky: rgba(255, 255, 255, 0.80);
      --bg-card: rgba(0, 0, 0, 0.03);
      --border-color: rgba(0, 0, 0, 0.10);
      --text-primary: #0a0a12;
      --text-secondary: #1e2a3a;
      --text-muted: #6b7a8a;
      --text-dim: #9aabbb;
    }

    /* ================================================================
       GLOBAL RESET & PIXEL FONT
    ================================================================ */
    * {
      margin: 0;
      padding: 0;
      box-sizing: border-box;
      font-family: 'Press Start 2P', 'Courier New', monospace !important;
      border-radius: 0 !important;
      letter-spacing: 0.02em;
    }

    body {
      background: var(--bg-body);
      color: var(--text-primary);
      padding-top: 110px;
      padding-bottom: 60px;
      padding-left: 4vw;
      padding-right: 4vw;
      min-height: 100vh;
      overflow-x: hidden;
      transition: background 0.4s, color 0.4s;
      position: relative;
    }

    /* ================================================================
       CANVAS BACKGROUND (像素网格 + 浮动块)
    ================================================================ */
    #pixelCanvas {
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      z-index: 0;
      pointer-events: none;
      display: block;
    }

    .scanlines {
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      z-index: 1;
      pointer-events: none;
      background: repeating-linear-gradient(
        0deg,
        rgba(0, 0, 0, 0) 0px,
        rgba(0, 0, 0, 0) 3px,
        rgba(0, 0, 0, 0.06) 3px,
        rgba(0, 0, 0, 0.06) 4px
      );
    }
    html.light .scanlines {
      background: repeating-linear-gradient(
        0deg,
        rgba(255, 255, 255, 0) 0px,
        rgba(255, 255, 255, 0) 3px,
        rgba(255, 255, 255, 0.10) 3px,
        rgba(255, 255, 255, 0.10) 4px
      );
    }

    /* ================================================================
       LAYOUT CONTAINER
    ================================================================ */
    .container {
      max-width: 760px;
      margin: 0 auto;
      position: relative;
      z-index: 2;
    }

    /* ================================================================
       STICKY HEADER / FOOTER
    ================================================================ */
    .sticky-top {
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      z-index: 100;
      background: var(--bg-sticky);
      backdrop-filter: blur(8px);
      border-bottom: 4px solid var(--border-color);
      padding: 0.6vh 0 0.8vh 0;
      display: flex;
      flex-direction: column;
      gap: 0.4vh;
      transition: background 0.3s, border-color 0.3s;
      box-shadow: 4px 4px 0 rgba(0,0,0,0.3);
    }
    html.light .sticky-top {
      box-shadow: 4px 4px 0 rgba(0,0,0,0.06);
    }

    .sticky-top .ticker-track-top {
      overflow: hidden;
      white-space: nowrap;
      width: 100%;
      padding: 0.2vh 0;
      order: 0;
    }
    .sticky-top .ticker-track-top .track-inner {
      display: flex;
      gap: 2.5vw;
      width: max-content;
      font-size: clamp(11px, 1.6vw, 16px);
      font-weight: 700;
      animation: tickerScrollReverse 45s steps(60) infinite;
    }
    .sticky-top .ticker-track-top .track-inner span {
      display: inline-flex;
      align-items: center;
      gap: 0.6vw;
    }
    .sticky-top .ticker-track-top .track-inner .up { color: var(--color-rise); }
    .sticky-top .ticker-track-top .track-inner .down { color: var(--color-fall); }
    @keyframes tickerScrollReverse {
      0% { transform: translateX(-50%); }
      100% { transform: translateX(0); }
    }

    .sticky-top .top-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 0.5vh 1.5vw;
      order: 1;
      padding: 0 4vw;
    }

    .sticky-top .left { display: flex; align-items: baseline; gap: 1.2vw; flex-wrap: wrap; }
    .sticky-top .price {
      font-size: clamp(18px, 3.8vw, 32px);
      font-weight: 900;
      line-height: 1.1;
      color: var(--text-primary);
      display: inline-block;
      white-space: nowrap;
    }
    .sticky-top .change {
      font-size: clamp(14px, 2.4vw, 20px);
      font-weight: 900;
    }
    .sticky-top .change.up { color: var(--color-rise); }
    .sticky-top .change.down { color: var(--color-fall); }
    .sticky-top .meta {
      font-size: clamp(10px, 1.4vw, 13px);
      font-weight: 700;
      color: var(--text-muted);
      display: flex;
      gap: 1.2vw;
      align-items: center;
      flex-wrap: wrap;
    }
    .sticky-top .meta strong { color: var(--text-primary); font-weight: 900; }
    .sticky-top .badge {
      font-size: 9px;
      font-weight: 800;
      letter-spacing: 2px;
      color: var(--color-rise);
      background: var(--color-rise-bg);
      padding: 0.2vh 1.2vw;
      border: 2px solid var(--badge-border);
      text-transform: uppercase;
    }
    .sticky-date {
      font-size: clamp(10px, 1.4vw, 15px);
      color: var(--text-muted);
      margin-left: 0.5vw;
      font-weight: 600;
      letter-spacing: 0.5px;
    }
    .theme-toggle, .mute-btn {
      background: var(--bg-card);
      border: 2px solid var(--border-color);
      color: var(--text-secondary);
      font-size: clamp(9px, 1.1vw, 13px);
      padding: 0.3vh 1vw;
      cursor: pointer;
      font-weight: 700;
      transition: all 0.2s;
      box-shadow: 3px 3px 0 rgba(0,0,0,0.2);
      line-height: 1.5;
    }
    html.light .theme-toggle, html.light .mute-btn {
      box-shadow: 3px 3px 0 rgba(0,0,0,0.05);
    }
    .theme-toggle:hover, .mute-btn:hover {
      border-color: var(--color-rise);
      background: var(--color-rise-bg);
      color: var(--text-primary);
    }

    .nav-group {
      display: flex;
      align-items: center;
      gap: 0.3vw;
      margin-left: 0.5vw;
    }
    .nav-btn {
      background: var(--bg-card);
      border: 2px solid var(--border-color);
      color: var(--text-secondary);
      font-size: clamp(9px, 1.1vw, 13px);
      padding: 0.3vh 0.8vw;
      cursor: pointer;
      font-weight: 700;
      transition: all 0.2s;
      font-family: inherit;
      line-height: 1.5;
      min-width: 2.2vw;
      text-align: center;
      box-shadow: 3px 3px 0 rgba(0,0,0,0.2);
    }
    html.light .nav-btn {
      box-shadow: 3px 3px 0 rgba(0,0,0,0.05);
    }
    .nav-btn:hover:not(:disabled) {
      background: var(--color-rise-bg);
      border-color: var(--color-rise);
      color: var(--text-primary);
    }
    .nav-btn:disabled {
      opacity: 0.3;
      cursor: not-allowed;
    }
    .nav-btn.today-btn {
      font-size: clamp(8px, 1vw, 12px);
      padding: 0.3vh 1vw;
    }

    .sticky-bottom {
      position: fixed;
      bottom: 0;
      left: 0;
      right: 0;
      z-index: 100;
      background: var(--bg-sticky);
      backdrop-filter: blur(8px);
      border-top: 4px solid var(--border-color);
      padding: 1vh 0;
      overflow: hidden;
      white-space: nowrap;
      transition: background 0.3s, border-color 0.3s;
      box-shadow: 4px 4px 0 rgba(0,0,0,0.3);
    }
    html.light .sticky-bottom {
      box-shadow: 4px 4px 0 rgba(0,0,0,0.06);
    }
    .sticky-bottom .ticker-track {
      display: flex;
      gap: 2.5vw;
      width: max-content;
      font-size: clamp(11px, 1.6vw, 16px);
      font-weight: 700;
      animation: tickerScroll 55s steps(60) infinite;
    }
    .sticky-bottom .ticker-track span {
      display: inline-flex;
      align-items: center;
      gap: 0.6vw;
    }
    .sticky-bottom .ticker-track .up { color: var(--color-rise); }
    .sticky-bottom .ticker-track .down { color: var(--color-fall); }
    @keyframes tickerScroll {
      0% { transform: translateX(0); }
      100% { transform: translateX(-50%); }
    }

    /* ================================================================
       MAIN CONTENT BLOCKS
    ================================================================ */
    .block {
      opacity: 0;
      transform: translateY(30px) scale(0.98);
      animation: slideUp 0.6s cubic-bezier(0.16, 1, 0.3, 1) forwards;
    }
    .block:nth-child(2) { animation-delay: 0.06s; }
    .block:nth-child(3) { animation-delay: 0.12s; }
    .block:nth-child(4) { animation-delay: 0.18s; }
    .block:nth-child(5) { animation-delay: 0.24s; }
    .block:nth-child(6) { animation-delay: 0.30s; }
    .block:nth-child(7) { animation-delay: 0.36s; }
    @keyframes slideUp {
      0% { opacity: 0; transform: translateY(30px) scale(0.98); }
      100% { opacity: 1; transform: translateY(0) scale(1); }
    }

    .divider {
      border: none;
      height: 4px;
      background: repeating-linear-gradient(
        90deg,
        var(--border-color) 0px,
        var(--border-color) 6px,
        transparent 6px,
        transparent 12px
      );
      margin: 1vw 0;
      transition: background 0.3s;
    }

    /* ================================================================
       PRICE BLOCK - 价格独占一行，与涨跌幅有间距
    ================================================================ */
    .price-block {
      padding: 2vw 0 0.5vw;
      display: flex;
      flex-direction: column;
      align-items: flex-start;
    }
    .price-block .price-top {
      display: flex;
      flex-direction: column;
      gap: 3vh;
      margin-bottom: 0.5vw;
    }
    .price-main {
      font-size: clamp(56px, 17vw, 110px);
      font-weight: 900;
      letter-spacing: -2px;
      line-height: 0.9;
      display: block;
      color: var(--text-primary);
    }
    .price-change {
      font-size: clamp(26px, 6vw, 50px);
      font-weight: 900;
      display: block;
      letter-spacing: -1px;
    }
    .price-change.up { color: var(--color-rise); }
    .price-change.down { color: var(--color-fall); }

    .price-sub {
      font-size: clamp(11px, 1.6vw, 15px);
      font-weight: 600;
      color: var(--text-muted);
      letter-spacing: 1px;
      margin-top: clamp(6px, 1vw, 14px);
      border-top: 2px solid var(--border-color);
      display: flex;
      flex-wrap: wrap;
      gap: 2vw;
      padding-top: clamp(6px, 1vw, 14px);
    }
    .price-sub strong { color: var(--text-primary); font-weight: 800; }

    /* ================================================================
       KPI, DIST, FLOW, LEADER, TREND (样式精简，与原逻辑兼容)
    ================================================================ */
    .kpi-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 0.8vw;
      margin: 2vw 0;
    }
    .kpi-item {
      background: var(--bg-card);
      padding: 1.2vw 0.5vw;
      text-align: center;
      border: 2px solid var(--border-color);
      transition: background 0.3s, border-color 0.3s;
      box-shadow: 3px 3px 0 rgba(0,0,0,0.2);
    }
    html.light .kpi-item { box-shadow: 3px 3px 0 rgba(0,0,0,0.05); }
    .kpi-item .label {
      font-size: clamp(8px, 1.1vw, 11px);
      font-weight: 700;
      color: var(--text-muted);
      letter-spacing: 2px;
      text-transform: uppercase;
    }
    .kpi-item .number {
      font-size: clamp(28px, 7vw, 56px);
      font-weight: 900;
      line-height: 1.2;
      letter-spacing: -2px;
    }
    .kpi-item .number.up { color: var(--color-rise); }
    .kpi-item .number.down { color: var(--color-fall); }
    .kpi-item .sub {
      font-size: clamp(9px, 1.1vw, 13px);
      font-weight: 600;
      color: var(--text-muted);
    }

    .dist-grid {
      display: flex;
      flex-wrap: wrap;
      gap: 0.6vw 1.2vw;
      justify-content: flex-start;
      margin: 1.2vw 0;
    }
    .dist-chip {
      background: var(--bg-card);
      padding: 0.4vw 1.4vw;
      font-size: clamp(12px, 1.8vw, 18px);
      font-weight: 800;
      letter-spacing: -0.5px;
      border: 2px solid var(--border-color);
      transition: background 0.3s, border-color 0.3s;
      box-shadow: 3px 3px 0 rgba(0,0,0,0.15);
    }
    html.light .dist-chip { box-shadow: 3px 3px 0 rgba(0,0,0,0.04); }
    .dist-chip .num { font-size: 1.2em; margin-right: 0.2vw; }
    .dist-chip.rise { color: var(--color-rise); border-color: var(--color-rise-bg); }
    .dist-chip.fall { color: var(--color-fall); border-color: var(--color-fall-bg); }
    .dist-total {
      font-size: clamp(11px, 1.5vw, 17px);
      font-weight: 700;
      color: var(--text-muted);
      margin-top: 0.5vw;
      letter-spacing: 1px;
    }
    .dist-total strong { font-weight: 900; }

    .flow-list {
      display: flex;
      flex-direction: column;
      gap: 0.4vw;
      margin: 1.5vw 0;
    }
    .flow-row {
      display: flex;
      align-items: baseline;
      padding: 0.6vw 0.4vw;
      border-bottom: 2px solid var(--border-color);
      font-size: clamp(13px, 1.8vw, 21px);
      font-weight: 700;
      letter-spacing: -0.3px;
    }
    .flow-row .left-part {
      display: flex;
      align-items: baseline;
      gap: 0.4vw;
      flex: 1;
    }
    .flow-row .ticker { font-weight: 900; color: var(--text-primary); }
    .flow-row .name {
      color: var(--text-secondary);
      font-weight: 500;
      font-size: 0.65em;
    }
    .flow-row .right-part {
      display: flex;
      align-items: baseline;
      gap: 2vw;
      flex-shrink: 0;
    }
    .flow-row .weight {
      color: var(--text-muted);
      font-weight: 600;
      font-size: 0.65em;
      text-align: right;
      min-width: 4.5vw;
    }
    .flow-row .change {
      font-weight: 900;
      text-align: right;
      min-width: 6vw;
    }
    .flow-row .change.up { color: var(--color-rise); }
    .flow-row .change.down { color: var(--color-fall); }
    .flow-row.others {
      color: var(--text-muted);
      font-size: 0.65em;
      border-bottom: none;
      padding-top: 1vw;
      justify-content: center;
    }

    .leader-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 2vw;
      margin: 1.5vw 0;
    }
    .leader-col .col-title {
      font-size: clamp(10px, 1.2vw, 14px);
      font-weight: 800;
      letter-spacing: 2px;
      color: var(--text-muted);
      border-bottom: 4px solid var(--border-color);
      padding-bottom: 0.3vw;
      margin-bottom: 0.6vw;
    }
    .leader-item {
      display: flex;
      justify-content: space-between;
      padding: 0.3vw 0;
      font-size: clamp(15px, 2.2vw, 26px);
      font-weight: 800;
      border-bottom: 2px solid var(--border-color);
    }
    .leader-item .val { font-weight: 900; }

    .trend-stats {
      display: flex;
      flex-wrap: wrap;
      gap: 1.2vw 3vw;
      background: var(--bg-card);
      padding: 1.2vw 2vw;
      border: 2px solid var(--border-color);
      margin: 1.2vw 0;
      box-shadow: 3px 3px 0 rgba(0,0,0,0.15);
    }
    html.light .trend-stats { box-shadow: 3px 3px 0 rgba(0,0,0,0.04); }
    .trend-item .label {
      font-size: clamp(8px, 1vw, 12px);
      font-weight: 700;
      color: var(--text-muted);
      letter-spacing: 1px;
    }
    .trend-item .value {
      font-size: clamp(26px, 5.5vw, 44px);
      font-weight: 900;
      line-height: 1.2;
      letter-spacing: -1px;
      white-space: nowrap;
    }
    .mini-prices {
      display: flex;
      flex-wrap: wrap;
      gap: 1vw;
      font-size: clamp(13px, 1.8vw, 20px);
      font-weight: 700;
      color: var(--text-muted);
      margin-top: 0.5vw;
      letter-spacing: -0.3px;
    }
    .mini-prices .latest {
      color: var(--text-primary);
      background: var(--bg-card);
      padding: 0 0.5vw;
      border: 2px solid var(--border-color);
    }

    /* ================================================================
       GLITCH & CURSOR
    ================================================================ */
    .glitch-text {
      position: relative;
      display: inline-block;
      transition: color 0.1s;
      cursor: default;
    }
    .glitch-text.active {
      animation: modernGlitch 0.25s ease;
    }
    @keyframes modernGlitch {
      0% { transform: translate(-3px, 2px); color: var(--glitch-color1); }
      20% { transform: translate(4px, -3px); color: var(--glitch-color2); }
      40% { transform: translate(-5px, 1px); color: var(--glitch-color1); }
      60% { transform: translate(3px, -2px); color: var(--glitch-color2); }
      80% { transform: translate(-2px, 3px); color: var(--glitch-color1); }
      100% { transform: translate(0, 0); color: inherit; }
    }

    .cursor-blink::after {
      content: '_';
      display: inline-block;
      animation: blink 1s step-end infinite;
      color: var(--color-rise);
      margin-left: 2px;
      font-weight: 900;
    }
    @keyframes blink {
      0%, 100% { opacity: 1; }
      50% { opacity: 0; }
    }

    /* ================================================================
       RESPONSIVE
    ================================================================ */
    @media (max-width: 600px) {
      body { padding-top: 100px; padding-bottom: 50px; padding-left: 3vw; padding-right: 3vw; }
      .sticky-top { padding: 0.3vh 0 0.5vh; }
      .sticky-top .ticker-track-top .track-inner { font-size: 9px; gap: 3vw; }
      .sticky-top .meta { gap: 1vw; }
      .sticky-bottom .ticker-track { font-size: 10px; gap: 3vw; }
      .sticky-top .top-row { padding: 0 3vw; }
      .kpi-grid { gap: 1vw; }
      .leader-grid { grid-template-columns: 1fr; gap: 4vw; }
      .flow-row { font-size: 13px; }
      .flow-row .right-part { gap: 2.5vw; }
      .flow-row .weight { min-width: 6vw; }
      .flow-row .change { min-width: 8vw; }
      .theme-toggle, .mute-btn { font-size: 9px; padding: 0.1vh 2vw; }
      .nav-btn { font-size: 9px; padding: 0.1vh 1.5vw; min-width: 5vw; }
      .nav-btn.today-btn { font-size: 8px; padding: 0.1vh 2vw; }
      .nav-group { gap: 1vw; margin-left: 0; }
      .trend-stats { gap: 1.5vw 2.5vw; }
      .trend-item .value { font-size: clamp(20px, 5vw, 32px); }
      .sticky-date { font-size: 9px; margin-left: 0.3vw; }
      .price-main { font-size: clamp(40px, 13vw, 72px); }
      .price-change { font-size: clamp(20px, 5vw, 36px); }
      .price-block .price-top { gap: 2.5vh; }
      .price-sub { margin-top: clamp(8px, 2vw, 14px); }
      .price-block { padding: 2.5vw 0 1vw; }
      .divider { margin: 1.2vw 0; }
    }

    /* ===== 主题色占位（由 Python 注入） ===== */
    /* THEME_CSS_PLACEHOLDER */
  </style>
</head>
<body>

  <!-- CANVAS BACKGROUND -->
  <canvas id="pixelCanvas"></canvas>
  <div class="scanlines"></div>

  <!-- ============================================================
       STICKY TOP
  ============================================================ -->
  <div class="sticky-top" id="stickyTop">
    <div class="ticker-track-top"><div class="track-inner" id="tickerTopInner"></div></div>
    <div class="top-row">
      <div class="left">
        <span class="price glitch-text cursor-blink" id="stickyPrice">--</span>
        <span class="change up glitch-text" id="stickyChange">--</span>
        <span class="badge glitch-text">Closed</span>
        <span class="sticky-date glitch-text" id="stickyDate">--</span>
      </div>
      <div class="meta">
        <span>Up <strong id="stickyUp" style="color:var(--color-rise);">--</strong></span>
        <span>Down <strong id="stickyDown" style="color:var(--color-fall);">--</strong></span>
        <span style="color:var(--text-dim);">|</span>
        <span style="color:var(--text-muted);">30D <strong id="stickyTrend" style="color:var(--color-rise);">--</strong></span>
        <span class="nav-group" id="navGroup">
          <button class="nav-btn" id="btnPrev" disabled>&lt;-</button>
          <button class="nav-btn today-btn" id="btnToday" style="display:none;">TODAY</button>
          <button class="nav-btn" id="btnNext" disabled>-&gt;</button>
        </span>
        <button class="theme-toggle" id="themeToggle">Light</button>
        <button class="mute-btn" id="muteBtn">SFX</button>
      </div>
    </div>
  </div>

  <!-- ============================================================
       STICKY BOTTOM
  ============================================================ -->
  <div class="sticky-bottom"><div class="ticker-track" id="tickerBottomTrack"></div></div>

  <!-- ============================================================
       MAIN CONTENT
  ============================================================ -->
  <div class="container">

    <div class="block price-block">
      <div class="price-top">
        <span class="price-main glitch-text" id="mainPrice">--</span>
        <span class="price-change up glitch-text" id="mainChange">--</span>
      </div>
      <div class="price-sub">
        <span>Prev Close <strong id="prevClose">--</strong></span>
        <span>High <strong id="highPrice" style="color:var(--color-rise);">--</strong></span>
        <span>Low <strong id="lowPrice" style="color:var(--color-fall);">--</strong></span>
        <span style="color:var(--color-rise);">●</span> Closed
      </div>
    </div>
    <hr class="divider" />

    <div class="block kpi-grid">
      <div class="kpi-item"><div class="label">Advancers</div><div class="number up glitch-text" id="kpiUp">--</div><div class="sub">Stocks</div></div>
      <div class="kpi-item"><div class="label">Decliners</div><div class="number down glitch-text" id="kpiDown">--</div><div class="sub">Stocks</div></div>
      <div class="kpi-item"><div class="label">30-Day Chg</div><div class="number up glitch-text" id="kpiTrend">--</div><div class="sub">Range</div></div>
    </div>
    <hr class="divider" />

    <div class="block">
      <div class="dist-grid" id="distGrid"></div>
      <div class="dist-total">
        Advancers <strong style="color:var(--color-rise);" class="glitch-text" id="distUp">--</strong>  ·  Decliners <strong style="color:var(--color-fall);" class="glitch-text" id="distDown">--</strong>  ·  Flat <strong style="color:var(--text-muted);" id="distFlat">--</strong>
      </div>
    </div>
    <hr class="divider" />

    <div class="block flow-list" id="flowList"></div>
    <hr class="divider" />

    <div class="block leader-grid" id="leaderGrid"></div>
    <hr class="divider" />

    <div class="block">
      <div class="trend-stats">
        <div class="trend-item"><div class="label">Range Change</div><div class="value glitch-text" id="trendChange" style="color:var(--color-rise);">--</div></div>
        <div class="trend-item"><div class="label">High</div><div class="value glitch-text" id="trendHigh" style="color:var(--color-rise);">--</div></div>
        <div class="trend-item"><div class="label">Low</div><div class="value glitch-text" id="trendLow" style="color:var(--color-fall);">--</div></div>
        <div class="trend-item"><div class="label">Latest</div><div class="value glitch-text" id="trendLatest" style="color:var(--text-primary);">--</div></div>
      </div>
      <div class="mini-prices" id="miniPrices"></div>
    </div>

    <div style="text-align:center; color:var(--text-dim); font-size:9px; letter-spacing:2px; padding:3vw 0 1vw; border-top:4px solid var(--border-color); margin-top:2vw; font-weight:700; transition:color 0.3s,border-color 0.3s;">
      DATA FROM YAHOO FINANCE · AUTO-UPDATED · FOR REFERENCE ONLY · <span id="buildTime"></span>
    </div>
  </div>

  <script>
    // ==============================================================
    // DATA INJECTION
    // ==============================================================
    const DATA = __DATA_JSON__;
    const HISTORY_DATES = __HISTORY_DATES__;
    const IS_HISTORY = __IS_HISTORY__;

    const idx = DATA.index;
    const stocks = DATA.stocks;
    const history = DATA.history;

    function fmtPct(c) { return (c >= 0 ? '+' : '') + c.toFixed(2) + '%'; }
    function cls(c) { return c >= 0 ? 'up' : 'down'; }

    // ==============================================================
    // CANVAS BACKGROUND: Pixel grid + floating blocks
    // ==============================================================
    const canvas = document.getElementById('pixelCanvas');
    const ctx = canvas.getContext('2d');
    let W, H;

    function resizeCanvas() {
      W = canvas.width = window.innerWidth;
      H = canvas.height = window.innerHeight;
    }
    window.addEventListener('resize', resizeCanvas);
    resizeCanvas();

    function getCSSVar(name) {
      return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    }

    let riseColor = getCSSVar('--color-rise') || '#FF5E00';
    let fallColor = getCSSVar('--color-fall') || '#00BFFF';

    function updateColors() {
      riseColor = getCSSVar('--color-rise') || '#FF5E00';
      fallColor = getCSSVar('--color-fall') || '#00BFFF';
      // 更新方块颜色
      for (let b of blocks) {
        b.color = Math.random() > 0.15 ? (Math.random() > 0.5 ? riseColor : fallColor) : '#ffffff';
      }
    }

    // ---- Grid ----
    function drawGrid() {
      const step = 32;
      ctx.save();
      ctx.strokeStyle = 'rgba(255,255,255,0.04)';
      ctx.lineWidth = 1;
      for (let x = 0; x <= W; x += step) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, H);
        ctx.stroke();
      }
      for (let y = 0; y <= H; y += step) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(W, y);
        ctx.stroke();
      }
      ctx.restore();
    }

    // ---- Floating blocks ----
    class PixelBlock {
      constructor() {
        this.size = 16 + Math.floor(Math.random() * 25);
        this.w = this.size;
        this.h = this.size;
        this.x = Math.random() * (W - this.w);
        this.y = Math.random() * (H - this.h);
        this.vx = (Math.random() - 0.5) * 0.2;
        this.vy = (Math.random() - 0.5) * 0.2;
        this.color = Math.random() > 0.15 ? (Math.random() > 0.5 ? riseColor : fallColor) : '#ffffff';
        this.alpha = 0.25 + Math.random() * 0.3;
        this.glow = 0;
      }
      update() {
        this.x += this.vx;
        this.y += this.vy;
        if (this.x < 0) { this.x = 0; this.vx *= -1; this.glow = 1; }
        if (this.x + this.w > W) { this.x = W - this.w; this.vx *= -1; this.glow = 1; }
        if (this.y < 0) { this.y = 0; this.vy *= -1; this.glow = 1; }
        if (this.y + this.h > H) { this.y = H - this.h; this.vy *= -1; this.glow = 1; }
        this.glow *= 0.96;
        if (this.glow < 0.02) this.glow = 0;
      }
      draw(ctx) {
        ctx.save();
        if (this.glow > 0.05) {
          ctx.shadowColor = this.color;
          ctx.shadowBlur = 20 * this.glow;
        } else {
          ctx.shadowColor = this.color;
          ctx.shadowBlur = 6;
        }
        ctx.globalAlpha = this.alpha;
        ctx.fillStyle = this.color;
        ctx.fillRect(this.x, this.y, this.w, this.h);
        ctx.shadowBlur = 0;
        ctx.globalAlpha = 0.15;
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 1;
        ctx.strokeRect(this.x + 1, this.y + 1, this.w - 2, this.h - 2);
        ctx.restore();
      }
    }

    let blocks = [];
    function initBlocks(count = 28) {
      blocks = [];
      for (let i = 0; i < count; i++) blocks.push(new PixelBlock());
    }
    initBlocks();

    // ---- Fusion beams (克制) ----
    function drawFusionEffects(ctx) {
      for (let i = 0; i < blocks.length; i++) {
        for (let j = i + 1; j < blocks.length; j++) {
          const a = blocks[i];
          const b = blocks[j];
          const cx1 = a.x + a.w/2, cy1 = a.y + a.h/2;
          const cx2 = b.x + b.w/2, cy2 = b.y + b.h/2;
          const dx = cx2 - cx1, dy = cy2 - cy1;
          const dist = Math.sqrt(dx*dx + dy*dy);
          const maxDist = 150;
          if (dist < maxDist) {
            const intensity = 1 - (dist / maxDist);
            if (a.color !== b.color && (a.color !== '#ffffff' && b.color !== '#ffffff')) continue;
            ctx.save();
            ctx.globalAlpha = intensity * 0.25;
            ctx.shadowBlur = 0;
            const grad = ctx.createLinearGradient(cx1, cy1, cx2, cy2);
            grad.addColorStop(0, a.color);
            grad.addColorStop(0.5, '#ffffff');
            grad.addColorStop(1, b.color);
            ctx.strokeStyle = grad;
            ctx.lineWidth = 1 + intensity * 3;
            ctx.beginPath();
            ctx.moveTo(cx1, cy1);
            ctx.lineTo(cx2, cy2);
            ctx.stroke();
            ctx.restore();
          }
        }
      }
    }

    function animate() {
      ctx.clearRect(0, 0, W, H);
      drawGrid();
      for (let b of blocks) b.update();
      drawFusionEffects(ctx);
      for (let b of blocks) b.draw(ctx);
      requestAnimationFrame(animate);
    }
    animate();

    window.addEventListener('resize', () => {
      resizeCanvas();
      for (let b of blocks) {
        b.x = Math.min(b.x, W - b.w);
        b.y = Math.min(b.y, H - b.h);
      }
    });

    // ==============================================================
    // THEME TOGGLE
    // ==============================================================
    const toggleBtn = document.getElementById('themeToggle');
    const htmlEl = document.documentElement;
    let useLight = localStorage.getItem('pixelTheme') === 'light' ||
      (localStorage.getItem('pixelTheme') === null && window.matchMedia('(prefers-color-scheme: light)').matches);

    if (useLight) { htmlEl.classList.add('light'); toggleBtn.textContent = 'Dark'; }
    else { htmlEl.classList.remove('light'); toggleBtn.textContent = 'Light'; }

    toggleBtn.addEventListener('click', () => {
      const isLight = htmlEl.classList.toggle('light');
      localStorage.setItem('pixelTheme', isLight ? 'light' : 'dark');
      toggleBtn.textContent = isLight ? 'Dark' : 'Light';
      updateColors();
      playPixelSound('switch');
    });

    // ==============================================================
    // 8-BIT PIXEL SFX ENGINE
    // ==============================================================
    let audioCtx = null;
    let isMuted = localStorage.getItem('pixelMuted') === 'true';
    let audioReady = false;

    function initAudio() {
      if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      if (audioCtx.state === 'suspended') audioCtx.resume().then(() => { audioReady = true; }).catch(() => {});
      else audioReady = true;
    }

    function playPixelSound(type) {
      if (isMuted || !audioReady) return;
      try {
        const now = audioCtx.currentTime;
        if (audioCtx.state !== 'running') return;

        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.type = 'square';

        let freq = 800, duration = 0.08, volume = 0.08;

        switch (type) {
          case 'burst':
            freq = 1200 + Math.random() * 400;
            duration = 0.06;
            volume = 0.06;
            osc.type = Math.random() > 0.5 ? 'square' : 'sawtooth';
            break;
          case 'switch':
            osc.frequency.setValueAtTime(523, now);
            gain.gain.setValueAtTime(0.08, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.08);
            osc.start(now);
            osc.stop(now + 0.08);
            const osc2 = audioCtx.createOscillator();
            const gain2 = audioCtx.createGain();
            osc2.type = 'square';
            osc2.frequency.setValueAtTime(659, now + 0.08);
            gain2.gain.setValueAtTime(0.08, now + 0.08);
            gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.16);
            osc2.connect(gain2);
            gain2.connect(audioCtx.destination);
            osc2.start(now + 0.08);
            osc2.stop(now + 0.16);
            osc.connect(gain);
            gain.connect(audioCtx.destination);
            return;
          case 'tick':
            freq = 600 + Math.random() * 300;
            duration = 0.04;
            volume = 0.04;
            break;
          default:
            freq = 800;
            duration = 0.06;
            volume = 0.06;
        }

        osc.frequency.setValueAtTime(freq, now);
        gain.gain.setValueAtTime(volume, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + duration);
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.start(now);
        osc.stop(now + duration);
      } catch (e) {}
    }

    const muteBtn = document.getElementById('muteBtn');
    muteBtn.textContent = isMuted ? 'Mute' : 'SFX';
    muteBtn.addEventListener('click', () => {
      isMuted = !isMuted;
      localStorage.setItem('pixelMuted', isMuted ? 'true' : 'false');
      muteBtn.textContent = isMuted ? 'Mute' : 'SFX';
      if (!isMuted) { initAudio(); playPixelSound('switch'); }
    });

    document.addEventListener('click', () => { if (!audioReady) { initAudio(); if (!isMuted) playPixelSound('burst'); } }, { once: true });

    // ==============================================================
    // GLITCH ENGINE
    // ==============================================================
    const glitchEls = document.querySelectorAll('.glitch-text');
    function triggerGlitch(el) {
      if (!el) return;
      playPixelSound('burst');
      el.classList.remove('active');
      void el.offsetWidth;
      el.classList.add('active');
      setTimeout(() => el.classList.remove('active'), 280);
    }
    glitchEls.forEach(el => el.addEventListener('mouseenter', function() { triggerGlitch(this); }));
    function storm() {
      const count = 1 + Math.floor(Math.random() * 3);
      for (let i=0; i<count; i++) {
        const el = glitchEls[Math.floor(Math.random() * glitchEls.length)];
        if (el) triggerGlitch(el);
      }
      setTimeout(storm, 400 + Math.random() * 1000);
    }
    setTimeout(() => { glitchEls.forEach(el => triggerGlitch(el)); }, 400);
    storm();

    // ==============================================================
    // RENDER DATA
    // ==============================================================
    document.getElementById('stickyPrice').textContent = idx.price ? idx.price.toLocaleString() : '--';
    document.getElementById('stickyChange').textContent = fmtPct(idx.change);
    document.getElementById('stickyChange').className = 'change ' + cls(idx.change) + ' glitch-text';
    document.getElementById('stickyUp').textContent = idx.up;
    document.getElementById('stickyDown').textContent = idx.down;
    document.getElementById('stickyTrend').textContent = fmtPct(idx.change);
    document.getElementById('stickyDate').textContent = DATA.date;

    document.getElementById('mainPrice').textContent = idx.price ? idx.price.toLocaleString() : '--';
    document.getElementById('mainChange').textContent = fmtPct(idx.change);
    document.getElementById('mainChange').className = 'price-change ' + cls(idx.change) + ' glitch-text';
    document.getElementById('prevClose').textContent = idx.prev_close ? idx.prev_close.toLocaleString() : '--';

    if (history && history.length > 0) {
      const high = Math.max(...history);
      const low = Math.min(...history);
      document.getElementById('highPrice').textContent = high.toLocaleString();
      document.getElementById('lowPrice').textContent = low.toLocaleString();
    }

    document.getElementById('kpiUp').textContent = idx.up;
    document.getElementById('kpiDown').textContent = idx.down;
    const trend30 = history.length >= 2 ? ((history[history.length-1] - history[0]) / history[0] * 100) : 0;
    document.getElementById('kpiTrend').textContent = (trend30 >= 0 ? '+' : '') + trend30.toFixed(2) + '%';
    document.getElementById('kpiTrend').className = 'number ' + cls(trend30) + ' glitch-text';

    const bins = DATA.bins;
    const labels = bins.labels;
    const counts = bins.counts;
    const distGrid = document.getElementById('distGrid');
    labels.forEach((lbl, i) => {
      const isUp = i >= 4;
      const span = document.createElement('span');
      span.className = 'dist-chip ' + (isUp ? 'rise' : 'fall');
      span.innerHTML = '<span class="num ' + (isUp ? 'rise' : 'fall') + ' glitch-text">' + counts[i] + '</span> ' + lbl;
      distGrid.appendChild(span);
    });
    document.getElementById('distUp').textContent = idx.up;
    document.getElementById('distDown').textContent = idx.down;
    document.getElementById('distFlat').textContent = idx.flat || 0;

    const flowList = document.getElementById('flowList');
    const topStocks = stocks.slice().sort((a, b) => b.weight - a.weight).slice(0, 10);
    topStocks.forEach(s => {
      const row = document.createElement('div');
      row.className = 'flow-row';
      row.innerHTML = `
        <span class="left-part">
          <span class="ticker glitch-text">${s.ticker}</span>
          <span class="name">${s.name}</span>
        </span>
        <span class="right-part">
          <span class="weight">${s.weight.toFixed(1)}%</span>
          <span class="change ${cls(s.change)} glitch-text">${fmtPct(s.change)}</span>
        </span>
      `;
      flowList.appendChild(row);
    });
    const othersRow = document.createElement('div');
    othersRow.className = 'flow-row others';
    othersRow.textContent = 'Others (' + (stocks.length - 10) + ' stocks) · Total Weight ' + (100 - topStocks.reduce((a,b) => a + b.weight, 0)).toFixed(1) + '%';
    flowList.appendChild(othersRow);

    const sorted = stocks.slice().sort((a, b) => b.change - a.change);
    const top5 = sorted.slice(0, 5);
    const bottom5 = sorted.slice(-5).reverse();
    const leaderGrid = document.getElementById('leaderGrid');
    const col1 = document.createElement('div');
    col1.className = 'leader-col';
    col1.innerHTML = '<div class="col-title" style="color:var(--color-rise);">TOP GAINERS</div>';
    top5.forEach(s => {
      const item = document.createElement('div');
      item.className = 'leader-item';
      item.innerHTML = `<span class="glitch-text" title="${s.name}">${s.ticker}</span><span class="val glitch-text" style="color:var(--color-rise);">${fmtPct(s.change)}</span>`;
      col1.appendChild(item);
    });
    const col2 = document.createElement('div');
    col2.className = 'leader-col';
    col2.innerHTML = '<div class="col-title" style="color:var(--color-fall);">TOP LOSERS</div>';
    bottom5.forEach(s => {
      const item = document.createElement('div');
      item.className = 'leader-item';
      item.innerHTML = `<span class="glitch-text" title="${s.name}">${s.ticker}</span><span class="val glitch-text" style="color:var(--color-fall);">${fmtPct(s.change)}</span>`;
      col2.appendChild(item);
    });
    leaderGrid.appendChild(col1);
    leaderGrid.appendChild(col2);

    if (history.length >= 2) {
      const change30 = (history[history.length-1] - history[0]) / history[0] * 100;
      const high = Math.max(...history);
      const low = Math.min(...history);
      const latest = history[history.length-1];
      document.getElementById('trendChange').textContent = fmtPct(change30);
      document.getElementById('trendChange').className = 'value glitch-text ' + cls(change30);
      document.getElementById('trendHigh').textContent = high.toLocaleString();
      document.getElementById('trendLow').textContent = low.toLocaleString();
      document.getElementById('trendLatest').textContent = latest.toLocaleString();

      const mini = document.getElementById('miniPrices');
      mini.innerHTML = '<span>Last 5D</span>';
      const last5 = history.slice(-5);
      last5.forEach((v, i) => {
        const span = document.createElement('span');
        span.className = 'glitch-text';
        if (i === last5.length - 1) span.className += ' latest';
        span.textContent = v.toLocaleString();
        mini.appendChild(span);
      });
    }

    document.getElementById('buildTime').textContent = new Date().toLocaleString('en-US', { hour12: false });

    // ==============================================================
    // TICKER
    // ==============================================================
    function buildTickerHTML(data) {
      let html = '';
      const items = data.slice().sort((a, b) => Math.abs(b.change) - Math.abs(a.change));
      for (let rep = 0; rep < 3; rep++) {
        items.forEach(item => {
          const cls = item.change >= 0 ? 'up' : 'down';
          html += `<span class="glitch-text">${item.ticker} <span class="${cls}">${fmtPct(item.change)}</span> <span style="color:var(--text-dim);">|</span></span>`;
        });
      }
      return html;
    }

    document.getElementById('tickerTopInner').innerHTML = buildTickerHTML(stocks);
    document.getElementById('tickerBottomTrack').innerHTML = buildTickerHTML(stocks);

    const topTrack = document.querySelector('.sticky-top .track-inner');
    const bottomTrack = document.querySelector('.sticky-bottom .ticker-track');
    [topTrack, bottomTrack].forEach(track => {
      if (track) {
        track.addEventListener('mouseenter', () => { track.style.animationPlayState = 'paused'; });
        track.addEventListener('mouseleave', () => { track.style.animationPlayState = 'running'; });
      }
    });

    // ==============================================================
    // PRICE SWITCH (NDX / Value)
    // ==============================================================
    const stickyPrice = document.getElementById('stickyPrice');
    let showNDX = false;
    let switching = false;
    let priceValue = idx.price ? idx.price.toLocaleString() : '--';

    function switchPrice() {
      if (switching || !stickyPrice) return;
      switching = true;
      triggerGlitch(stickyPrice);
      setTimeout(() => {
        stickyPrice.textContent = showNDX ? priceValue : 'NDX';
        showNDX = !showNDX;
        switching = false;
      }, 150);
    }
    setInterval(switchPrice, 3200);
    setTimeout(switchPrice, 1200);

    // ==============================================================
    // DECORATIVE TICK SOUND
    // ==============================================================
    setInterval(() => {
      if (!isMuted && audioReady && Math.random() > 0.7) {
        playPixelSound('tick');
      }
    }, 3000);

    // ==============================================================
    // NAVIGATION (unchanged)
    // ==============================================================
    (function() {
      const btnPrev = document.getElementById('btnPrev');
      const btnNext = document.getElementById('btnNext');
      const btnToday = document.getElementById('btnToday');

      if (!btnPrev || !btnNext) return;

      const path = window.location.pathname;
      const isHistory = path.includes('/history/');
      let currentDate = DATA.date;

      if (isHistory) {
        const m = path.match(/history\/(\d{4}-\d{2}-\d{2})/);
        if (m) currentDate = m[1];
        if (btnToday) {
          btnToday.style.display = 'inline-block';
          btnToday.onclick = function() {
            window.location.href = '../index.html';
          };
        }
      } else {
        if (btnToday) btnToday.style.display = 'none';
      }

      if (!HISTORY_DATES || HISTORY_DATES.length === 0) {
        btnPrev.disabled = true;
        btnNext.disabled = true;
        return;
      }

      const idx2 = HISTORY_DATES.indexOf(currentDate);
      if (idx2 === -1) {
        btnPrev.disabled = true;
        btnNext.disabled = true;
        return;
      }

      if (idx2 > 0) {
        const prevDate = HISTORY_DATES[idx2 - 1];
        btnPrev.disabled = false;
        btnPrev.onclick = function() {
          window.location.href = isHistory ? './' + prevDate + '.html' : './history/' + prevDate + '.html';
        };
      } else {
        btnPrev.disabled = true;
      }

      if (idx2 < HISTORY_DATES.length - 1) {
        const nextDate = HISTORY_DATES[idx2 + 1];
        btnNext.disabled = false;
        if (nextDate === DATA.date && isHistory) {
          btnNext.onclick = function() {
            window.location.href = '../index.html';
          };
        } else {
          btnNext.onclick = function() {
            window.location.href = isHistory ? './' + nextDate + '.html' : './history/' + nextDate + '.html';
          };
        }
      } else {
        btnNext.disabled = true;
      }
    })();

    console.log('✦ PIXEL TERMINAL · 8-bit SFX · Grid background ✦');
  </script>
</body>
</html>
"""


# =====================================================================
# 历史管理与 HTML 生成
# =====================================================================
def get_existing_history_dates(output_dir="docs"):
    import glob
    import re
    history_dir = os.path.join(output_dir, "history")
    if not os.path.exists(history_dir):
        return []
    dates = []
    for path in glob.glob(os.path.join(history_dir, "*.html")):
        name = os.path.basename(path)
        m = re.match(r"(\d{4}-\d{2}-\d{2})\.html", name)
        if m:
            dates.append(m.group(1))
    dates.sort()
    return dates


def manage_history(data, output_dir="docs", keep_days=30):
    import glob
    import os
    history_dir = os.path.join(output_dir, "history")
    os.makedirs(history_dir, exist_ok=True)

    date_str = data["date"]
    history_file = os.path.join(history_dir, f"{date_str}.html")

    history_dates = get_existing_history_dates(output_dir)
    if date_str not in history_dates:
        history_dates.append(date_str)
    history_dates.sort()

    html = generate_html(data, history_dates, is_history=True)

    with open(history_file, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  历史快照已保存: {history_file}")

    all_files = sorted(glob.glob(os.path.join(history_dir, "*.html")))
    if len(all_files) > keep_days:
        for old_file in all_files[:-keep_days]:
            os.remove(old_file)
            print(f"  清理旧历史: {os.path.basename(old_file)}")

    return history_dates


def generate_html(data, history_dates, is_history=False):
    import json
    data_with_time = data.copy()
    data_with_time["build_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data_json = json.dumps(data_with_time, ensure_ascii=False, separators=(",", ":"))
    history_dates_json = json.dumps(history_dates, ensure_ascii=False)
    is_history_str = "true" if is_history else "false"

    html = HTML_TEMPLATE
    # 注入主题 CSS（替换占位符）
    html = html.replace("/* THEME_CSS_PLACEHOLDER */", data["theme_css"])
    # 注入数据
    html = html.replace("__DATA_JSON__", data_json)
    html = html.replace("__HISTORY_DATES__", history_dates_json)
    html = html.replace("__IS_HISTORY__", is_history_str)
    return html


# =====================================================================
# 主入口
# =====================================================================
def main():
    print("=" * 50)
    print("NDX Dashboard 数据抓取 (赛博朋克 24 色 · 音效 · 光晕)")
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    ensure_dir()

    data = build_data()
    print(f"\n数据日期: {data['date']}")
    print(f"指数涨跌: {data['index']['change']}%")
    print(f"成分股数: {data['index']['total']}")
    print(f"配色主题: #{data['theme_idx']+1}")

    print("\n[历史快照管理]")
    history_dates = manage_history(data, OUTPUT_DIR, keep_days=30)
    print(f"  历史日期: {history_dates}")

    print("\n[生成主页面]")
    html = generate_html(data, history_dates, is_history=False)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  已写入: {OUTPUT_FILE}")

    print("\n" + "=" * 50)
    print("完成!")
    print("=" * 50)


if __name__ == "__main__":
    main()
