#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
纳指100每日收盘 Dashboard 数据抓取脚本
Glitch 风格 · 纯数字展示 · 动态数据注入 · 音效引擎
"""

import json
import math
import os
import sys
from datetime import datetime, timedelta
from collections import defaultdict

import yfinance as yf

from ndx_components import STOCKS

OUTPUT_DIR = "docs"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "index.html")


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

    result = {
        "index": index_info,
        "stocks": stocks,
        "pie_stocks": pie,
        "sectors": sector_list,
        "bins": {"labels": labels, "counts": counts},
        "history": history,
        "date": datetime.now().strftime("%Y-%m-%d"),
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

    result = {
        "index": {"price": history[-1], "prev_close": round(history[-1] / (1 + index_change/100), 2), "change": index_change, "up": up, "down": down, "flat": 0, "total": len(stocks)},
        "stocks": stocks,
        "pie_stocks": pie,
        "sectors": sector_list,
        "bins": {"labels": labels, "counts": counts},
        "history": history,
        "date": datetime.now().strftime("%Y-%m-%d"),
    }

    return result


# =====================================================================
# Glitch 风格 HTML 模板 — 动态数据注入版（含完整导航 + 音效，无花屏）
# =====================================================================
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=yes">
  <title>NDX 数据流</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@500;600;700;800;900&family=Noto+Sans+SC:wght@500;700;900&display=swap" rel="stylesheet">
  <style>
    /* ===== 全局 CSS 变量（暗色默认） ===== */
    :root {
      --bg-body: #0b0b0b;
      --bg-sticky: rgba(11, 11, 11, 0.92);
      --bg-card: rgba(255,255,255,0.02);
      --border-color: rgba(255,255,255,0.06);
      --text-primary: #ffffff;
      --text-secondary: #aaaaaa;
      --text-muted: #666666;
      --text-dim: #444444;
      --color-rise: #0ff;
      --color-fall: #f0f;
      --color-rise-bg: rgba(0,255,255,0.1);
      --color-fall-bg: rgba(255,0,255,0.1);
      --glitch-color1: #0ff;
      --glitch-color2: #f0f;
      --shadow-rise: 0 0 30px rgba(0,255,255,0.2);
      --shadow-fall: 0 0 30px rgba(255,0,255,0.2);
      --badge-border: rgba(0,255,255,0.3);
      --glow-rise: rgba(0, 255, 255, 0.25);
      --glow-fall: rgba(255, 0, 255, 0.25);
    }

    /* ===== 日间模式 ===== */
    html.light {
      --bg-body: #f2f4f8;
      --bg-sticky: rgba(255, 255, 255, 0.85);
      --bg-card: rgba(0, 0, 0, 0.03);
      --border-color: rgba(0, 0, 0, 0.08);
      --text-primary: #0a0a0a;
      --text-secondary: #2d2d2d;
      --text-muted: #6b7280;
      --text-dim: #9ca3af;
      --color-rise: #0ea5e9;
      --color-fall: #ec4899;
      --color-rise-bg: rgba(14, 165, 233, 0.12);
      --color-fall-bg: rgba(236, 72, 153, 0.12);
      --glitch-color1: #0ea5e9;
      --glitch-color2: #ec4899;
      --shadow-rise: 0 0 25px rgba(14, 165, 233, 0.25);
      --shadow-fall: 0 0 25px rgba(236, 72, 153, 0.25);
      --badge-border: rgba(14, 165, 233, 0.3);
      --glow-rise: rgba(14, 165, 233, 0.20);
      --glow-fall: rgba(236, 72, 153, 0.20);
    }

    /* ===== 重置 ===== */
    * { margin:0; padding:0; box-sizing:border-box; }
    body {
      background: var(--bg-body);
      color: var(--text-primary);
      font-family: 'Inter','Noto Sans SC',-apple-system,sans-serif;
      font-weight:700;
      padding-top:110px;
      padding-bottom:60px;
      padding-left:4vw;
      padding-right:4vw;
      min-height:100vh;
      overflow-x:hidden;
      transition:background 0.3s,color 0.3s;
      position:relative;
    }

    /* ===== 背景光晕 ===== */
    .bg-layers {
      position:fixed;
      inset:0;
      pointer-events:none;
      z-index:0;
      overflow:hidden;
    }
    .hero-glow {
      position:absolute;
      top:-20%;
      left:0;
      right:0;
      height:80%;
      background:radial-gradient(ellipse at 50% 0%, var(--glow-rise) 0%, var(--glow-fall) 50%, transparent 80%);
      transition:background 0.3s;
      filter:blur(60px);
      opacity:0.9;
    }
    .contour-texture {
      position:absolute;
      inset:0;
    }
    .contour-green {
      position:absolute;
      inset:-50%;
      background:radial-gradient(ellipse 800px 500px at 20% 85%, var(--glow-rise) 0%, transparent 70%);
      animation:drift-rise 25s ease-in-out infinite alternate;
      filter:blur(80px);
      opacity:0.8;
    }
    .contour-purple {
      position:absolute;
      inset:-50%;
      background:radial-gradient(ellipse 750px 480px at 80% 75%, var(--glow-fall) 0%, transparent 65%);
      animation:drift-fall 30s ease-in-out infinite alternate;
      filter:blur(80px);
      opacity:0.8;
    }
    @keyframes drift-rise {
      0% { transform:translate(0,0) scale(1); }
      33% { transform:translate(3%,-2%) scale(1.04); }
      66% { transform:translate(-2%,3%) scale(0.96); }
      100% { transform:translate(2%,2%) scale(1.02); }
    }
    @keyframes drift-fall {
      0% { transform:translate(0,0) scale(1); }
      33% { transform:translate(-3%,2%) scale(0.98); }
      66% { transform:translate(2%,-3%) scale(1.06); }
      100% { transform:translate(-2%,-2%) scale(1); }
    }

    .container { max-width:720px; margin:0 auto; position:relative; z-index:1; }

    /* ===== 顶部 Sticky（含导航按钮） ===== */
    .sticky-top {
      position:fixed; top:0; left:0; right:0; z-index:100;
      background:var(--bg-sticky);
      backdrop-filter:blur(12px);
      border-bottom:1px solid var(--border-color);
      padding:0.6vh 4vw 0.8vh;
      display:flex; flex-direction:column; gap:0.4vh;
      transition:background 0.3s,border-color 0.3s;
    }
    .sticky-top .ticker-track-top {
      overflow:hidden; white-space:nowrap; width:100%; padding:0.2vh 0; order:0;
    }
    .sticky-top .ticker-track-top .track-inner {
      display:flex; gap:2.5vw;
      animation:tickerScrollReverse 50s linear infinite;
      width:max-content;
      font-size:clamp(14px, 2vw, 20px);
      font-weight:700;
    }
    .sticky-top .ticker-track-top .track-inner span { display:inline-flex; align-items:center; gap:0.6vw; }
    .sticky-top .ticker-track-top .track-inner .up { color:var(--color-rise); }
    .sticky-top .ticker-track-top .track-inner .down { color:var(--color-fall); }
    @keyframes tickerScrollReverse {
      0% { transform:translateX(-50%); }
      100% { transform:translateX(0); }
    }
    .sticky-top .top-row {
      display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.5vh 2vw; order:1;
    }
    .sticky-top .left { display:flex; align-items:baseline; gap:1.2vw; flex-wrap:wrap; }
    .sticky-top .price {
      font-size:clamp(22px,4.5vw,38px); font-weight:900; letter-spacing:-1px;
      line-height:1.1; color:var(--text-primary); display:inline-block; white-space:nowrap;
    }
    .sticky-top .change { font-size:clamp(16px,2.8vw,24px); font-weight:900; }
    .sticky-top .change.up { color:var(--color-rise); }
    .sticky-top .change.down { color:var(--color-fall); }
    .sticky-top .meta {
      font-size:clamp(12px,1.8vw,16px); font-weight:700; color:var(--text-muted);
      display:flex; gap:1.5vw; align-items:center;
      flex-wrap:wrap;
    }
    .sticky-top .meta strong { color:var(--text-primary); font-weight:900; }
    .sticky-top .badge {
      font-size:11px; font-weight:800; letter-spacing:1px;
      color:var(--color-rise); background:var(--color-rise-bg);
      padding:0.2vh 1.2vw; border-radius:40px; border:1px solid var(--badge-border);
    }
    .sticky-date {
      font-size:clamp(12px,1.6vw,18px);
      color:var(--text-muted);
      margin-left:0.5vw;
      font-weight:600;
      letter-spacing:0.5px;
    }
    .theme-toggle {
      background:none; border:1px solid var(--border-color); border-radius:40px;
      color:var(--text-secondary);
      font-size:clamp(12px,1.6vw,18px); padding:0.2vh 1vw;
      cursor:pointer; font-weight:700; transition:all 0.2s; font-family:inherit; line-height:1.5;
    }
    .theme-toggle:hover { background:var(--bg-card); border-color:var(--color-rise); color:var(--text-primary); }
    /* 静音按钮 — 纯汉字 */
    .mute-btn {
      background:none; border:1px solid var(--border-color); border-radius:40px;
      color:var(--text-secondary);
      font-size:clamp(12px,1.6vw,18px); padding:0.2vh 0.8vw;
      cursor:pointer; font-weight:700; transition:all 0.2s; font-family:inherit; line-height:1.5;
    }
    .mute-btn:hover { background:var(--bg-card); border-color:var(--color-rise); color:var(--text-primary); }
    /* 导航按钮组 */
    .nav-group {
      display:flex;
      align-items:center;
      gap:0.3vw;
      margin-left:0.5vw;
    }
    .nav-btn {
      background:none;
      border:1px solid var(--border-color);
      border-radius:40px;
      color:var(--text-secondary);
      font-size:clamp(10px,1.2vw,14px);
      padding:0.1vh 0.6vw;
      cursor:pointer;
      font-weight:700;
      transition:all 0.2s;
      font-family:inherit;
      line-height:1.5;
      min-width:2.2vw;
      text-align:center;
    }
    .nav-btn:hover:not(:disabled) {
      background:var(--bg-card);
      border-color:var(--color-rise);
      color:var(--text-primary);
    }
    .nav-btn:disabled {
      opacity:0.3;
      cursor:not-allowed;
    }
    .nav-btn.today-btn {
      font-size:clamp(9px,1vw,12px);
      padding:0.1vh 0.8vw;
    }

    /* ===== 底部 Sticky ===== */
    .sticky-bottom {
      position:fixed; bottom:0; left:0; right:0; z-index:100;
      background:var(--bg-sticky);
      backdrop-filter:blur(12px);
      border-top:1px solid var(--border-color);
      padding:1vh 4vw;
      overflow:hidden; white-space:nowrap;
      transition:background 0.3s,border-color 0.3s;
    }
    .sticky-bottom .ticker-track {
      display:flex; gap:2.5vw;
      animation:tickerScroll 60s linear infinite;
      width:max-content;
      font-size:clamp(14px, 2vw, 20px);
      font-weight:700;
    }
    .sticky-bottom .ticker-track span { display:inline-flex; align-items:center; gap:0.6vw; }
    .sticky-bottom .ticker-track .up { color:var(--color-rise); }
    .sticky-bottom .ticker-track .down { color:var(--color-fall); }
    @keyframes tickerScroll {
      0% { transform:translateX(0); }
      100% { transform:translateX(-50%); }
    }

    /* ===== 其他元素 ===== */
    .block {
      opacity:0;
      transform:translateY(30px) scale(0.98);
      animation:slideUp 0.7s cubic-bezier(0.16,1,0.3,1) forwards;
    }
    .block:nth-child(2) { animation-delay:0.08s; }
    .block:nth-child(3) { animation-delay:0.16s; }
    .block:nth-child(4) { animation-delay:0.24s; }
    .block:nth-child(5) { animation-delay:0.32s; }
    .block:nth-child(6) { animation-delay:0.40s; }
    .block:nth-child(7) { animation-delay:0.48s; }
    @keyframes slideUp {
      0% { opacity:0; transform:translateY(30px) scale(0.98); }
      100% { opacity:1; transform:translateY(0) scale(1); }
    }

    .divider {
      border:none; height:1px;
      background:linear-gradient(90deg, transparent, var(--border-color), transparent);
      margin:2vw 0; transition:background 0.3s;
    }
    .price-block { padding:1vw 0 0.5vw; }
    .price-main {
      font-size:clamp(80px,22vw,160px); font-weight:900; letter-spacing:-4px;
      line-height:0.9; display:inline-block; color:var(--text-primary);
    }
    .price-change {
      font-size:clamp(32px,8vw,64px); font-weight:900; margin-left:12px;
      display:inline-block; letter-spacing:-1px;
    }
    .price-change.up { color:var(--color-rise); }
    .price-change.down { color:var(--color-fall); }
    .price-sub {
      font-size:clamp(14px,2.2vw,18px); font-weight:600; color:var(--text-muted);
      letter-spacing:1px; margin-top:0.2vw; display:flex; flex-wrap:wrap; gap:2vw;
    }
    .price-sub strong { color:var(--text-primary); font-weight:800; }

    .kpi-grid {
      display:grid; grid-template-columns:repeat(3,1fr); gap:0.8vw; margin:2vw 0;
    }
    .kpi-item {
      background:var(--bg-card); padding:1.2vw 0.5vw; text-align:center; border-radius:4px;
      transition:background 0.3s;
    }
    .kpi-item .label {
      font-size:clamp(10px,1.4vw,14px); font-weight:700; color:var(--text-muted);
      letter-spacing:2px; text-transform:uppercase;
    }
    .kpi-item .number {
      font-size:clamp(40px,10vw,80px); font-weight:900; line-height:1; letter-spacing:-2px;
    }
    .kpi-item .number.up { color:var(--color-rise); }
    .kpi-item .number.down { color:var(--color-fall); }
    .kpi-item .sub { font-size:clamp(12px,1.4vw,16px); font-weight:600; color:var(--text-muted); }

    .dist-grid {
      display:flex; flex-wrap:wrap; gap:0.6vw 1.2vw; justify-content:flex-start; margin:1.2vw 0;
    }
    .dist-chip {
      background:var(--bg-card); padding:0.4vw 1.4vw; border-radius:40px;
      font-size:clamp(16px,2.4vw,26px); font-weight:800; letter-spacing:-0.5px;
      border:1px solid var(--border-color);
      transition:background 0.3s,border-color 0.3s;
    }
    .dist-chip .num { font-size:1.2em; margin-right:0.2vw; }
    .dist-chip.rise { color:var(--color-rise); border-color:var(--color-rise-bg); }
    .dist-chip.fall { color:var(--color-fall); border-color:var(--color-fall-bg); }
    .dist-total {
      font-size:clamp(14px,1.8vw,20px); font-weight:700; color:var(--text-muted);
      margin-top:0.5vw; letter-spacing:1px;
    }
    .dist-total strong { font-weight:900; }

    .flow-list {
      display:flex; flex-direction:column; gap:0.4vw; margin:1.5vw 0;
    }
    .flow-row {
      display:flex; align-items:baseline; padding:0.6vw 0.4vw;
      border-bottom:1px solid var(--border-color);
      font-size:clamp(16px,2.2vw,26px); font-weight:700; letter-spacing:-0.3px;
      transition:border-color 0.3s;
    }
    .flow-row .left-part {
      display:flex; align-items:baseline; gap:0.4vw; flex:1;
    }
    .flow-row .ticker { font-weight:900; color:var(--text-primary); }
    .flow-row .name {
      color:var(--text-secondary); font-weight:500; font-size:0.8em;
    }
    .flow-row .right-part {
      display:flex; align-items:baseline; gap:2vw; flex-shrink:0;
    }
    .flow-row .weight {
      color:var(--text-muted); font-weight:600; font-size:0.8em;
      text-align:right; min-width:4.5vw;
    }
    .flow-row .change {
      font-weight:900; text-align:right; min-width:6vw;
    }
    .flow-row .change.up { color:var(--color-rise); }
    .flow-row .change.down { color:var(--color-fall); }
    .flow-row.others {
      color:var(--text-muted); font-size:0.8em; border-bottom:none;
      padding-top:1vw; justify-content:center;
    }

    .leader-grid {
      display:grid; grid-template-columns:1fr 1fr; gap:2vw; margin:1.5vw 0;
    }
    .leader-col .col-title {
      font-size:clamp(12px,1.4vw,16px); font-weight:800; letter-spacing:2px;
      color:var(--text-muted); border-bottom:2px solid var(--border-color);
      padding-bottom:0.3vw; margin-bottom:0.6vw;
      transition:border-color 0.3s;
    }
    .leader-item {
      display:flex; justify-content:space-between; padding:0.3vw 0;
      font-size:clamp(18px,2.6vw,32px); font-weight:800;
      border-bottom:1px solid var(--border-color);
    }
    .leader-item .val { font-weight:900; }

    .trend-stats {
      display:flex;
      flex-wrap:wrap;
      gap:1.2vw 3vw;
      background:var(--bg-card);
      padding:1.2vw 2vw;
      border-radius:8px;
      margin:1.2vw 0;
      border:1px solid var(--border-color);
      transition:background 0.3s,border-color 0.3s;
    }
    .trend-item .label {
      font-size:clamp(10px,1.2vw,14px);
      font-weight:700;
      color:var(--text-muted);
      letter-spacing:1px;
    }
    .trend-item .value {
      font-size:clamp(32px,7vw,56px);
      font-weight:900;
      line-height:1.2;
      letter-spacing:-1px;
      white-space:nowrap;
    }
    .mini-prices {
      display:flex; flex-wrap:wrap; gap:1vw;
      font-size:clamp(16px,2.2vw,26px); font-weight:700; color:var(--text-muted);
      margin-top:0.5vw; letter-spacing:-0.3px;
    }
    .mini-prices .latest {
      color:var(--text-primary); background:var(--bg-card); padding:0 0.5vw; border-radius:2px;
    }

    /* ===== Glitch ===== */
    .glitch-text {
      position:relative; display:inline-block; transition:color 0.1s; cursor:default;
    }
    .glitch-text.active {
      animation:modernGlitch 0.25s ease;
    }
    @keyframes modernGlitch {
      0% { transform:translate(-3px,2px); color:var(--glitch-color1); }
      20% { transform:translate(4px,-3px); color:var(--glitch-color2); }
      40% { transform:translate(-5px,1px); color:var(--glitch-color1); }
      60% { transform:translate(3px,-2px); color:var(--glitch-color2); }
      80% { transform:translate(-2px,3px); color:var(--glitch-color1); }
      100% { transform:translate(0,0); color:inherit; }
    }

    /* ===== 响应式 ===== */
    @media (max-width:600px) {
      body { padding-top:100px; padding-bottom:50px; padding-left:3vw; padding-right:3vw; }
      .sticky-top { padding:0.3vh 3vw 0.5vh; }
      .sticky-top .ticker-track-top .track-inner { font-size:12px; gap:3vw; }
      .sticky-top .meta { gap:1vw; }
      .sticky-bottom .ticker-track { font-size:14px; gap:3vw; }
      .kpi-grid { gap:1vw; }
      .leader-grid { grid-template-columns:1fr; gap:4vw; }
      .flow-row { font-size:16px; }
      .flow-row .right-part { gap:2.5vw; }
      .flow-row .weight { min-width:6vw; }
      .flow-row .change { min-width:8vw; }
      .theme-toggle { font-size:12px; padding:0.1vh 2vw; }
      .trend-stats { gap:1.5vw 2.5vw; }
      .trend-item .value { font-size:clamp(26px,6vw,40px); }
      .sticky-date { font-size:11px; margin-left:0.3vw; }
      .nav-btn { font-size:10px; padding:0.1vh 1.5vw; min-width:5vw; }
      .nav-btn.today-btn { font-size:9px; padding:0.1vh 2vw; }
      .nav-group { gap:1vw; }
      .mute-btn { font-size:11px; padding:0.1vh 1.5vw; }
    }
  </style>
</head>
<body>

<!-- ===== 背景光晕 ===== -->
<div class="bg-layers">
  <div class="hero-glow"></div>
  <div class="contour-texture">
    <div class="contour-green"></div>
    <div class="contour-purple"></div>
  </div>
</div>

<!-- ===== 顶部 Sticky ===== -->
<div class="sticky-top" id="stickyTop">
  <div class="ticker-track-top"><div class="track-inner" id="tickerTopInner"></div></div>
  <div class="top-row">
    <div class="left">
      <span class="price glitch-text" id="stickyPrice">--</span>
      <span class="change up glitch-text" id="stickyChange">--</span>
      <span class="badge glitch-text">已收盘</span>
      <span class="sticky-date glitch-text" id="stickyDate">--</span>
    </div>
    <div class="meta">
      <span>涨 <strong id="stickyUp" style="color:var(--color-rise);">--</strong></span>
      <span>跌 <strong id="stickyDown" style="color:var(--color-fall);">--</strong></span>
      <span style="color:var(--text-dim);">|</span>
      <span style="color:var(--text-muted);">30日 <strong id="stickyTrend" style="color:var(--color-rise);">--</strong></span>
      <!-- 导航按钮组 -->
      <span class="nav-group" id="navGroup">
        <button class="nav-btn" id="btnPrev" disabled>←</button>
        <button class="nav-btn today-btn" id="btnToday" style="display:none;">今天</button>
        <button class="nav-btn" id="btnNext" disabled>→</button>
      </span>
      <button class="theme-toggle" id="themeToggle">日间</button>
      <button class="mute-btn" id="muteBtn">音效</button>
    </div>
  </div>
</div>

<!-- ===== 底部 Sticky ===== -->
<div class="sticky-bottom"><div class="ticker-track" id="tickerBottomTrack"></div></div>

<!-- ===== 主内容 ===== -->
<div class="container">
  <div class="block price-block">
    <div>
      <span class="price-main glitch-text" id="mainPrice">--</span>
      <span class="price-change up glitch-text" id="mainChange">--</span>
    </div>
    <div class="price-sub">
      <span>前收 <strong id="prevClose">--</strong></span>
      <span>高 <strong id="highPrice" style="color:var(--color-rise);">--</strong></span>
      <span>低 <strong id="lowPrice" style="color:var(--color-fall);">--</strong></span>
      <span style="color:var(--color-rise);">●</span> 已收盘
    </div>
  </div>
  <hr class="divider">
  <div class="block kpi-grid">
    <div class="kpi-item"><div class="label">上涨</div><div class="number up glitch-text" id="kpiUp">--</div><div class="sub">家</div></div>
    <div class="kpi-item"><div class="label">下跌</div><div class="number down glitch-text" id="kpiDown">--</div><div class="sub">家</div></div>
    <div class="kpi-item"><div class="label">30日涨跌</div><div class="number up glitch-text" id="kpiTrend">--</div><div class="sub">区间</div></div>
  </div>
  <hr class="divider">
  <div class="block">
    <div class="dist-grid" id="distGrid">
      <!-- 由 JS 动态生成 -->
    </div>
    <div class="dist-total">
      上涨 <strong style="color:var(--color-rise);" class="glitch-text" id="distUp">--</strong>  · 下跌 <strong style="color:var(--color-fall);" class="glitch-text" id="distDown">--</strong>  · 平盘 <strong style="color:var(--text-muted);" id="distFlat">--</strong>
    </div>
  </div>
  <hr class="divider">
  <div class="block flow-list" id="flowList">
    <!-- 由 JS 动态生成 Top 10 -->
  </div>
  <hr class="divider">
  <div class="block leader-grid" id="leaderGrid">
    <!-- 由 JS 动态生成 -->
  </div>
  <hr class="divider">
  <div class="block">
    <div class="trend-stats">
      <div class="trend-item"><div class="label">区间涨跌</div><div class="value glitch-text" id="trendChange" style="color:var(--color-rise);">--</div></div>
      <div class="trend-item"><div class="label">最高</div><div class="value glitch-text" id="trendHigh" style="color:var(--color-rise);">--</div></div>
      <div class="trend-item"><div class="label">最低</div><div class="value glitch-text" id="trendLow" style="color:var(--color-fall);">--</div></div>
      <div class="trend-item"><div class="label">最新</div><div class="value glitch-text" id="trendLatest" style="color:var(--text-primary);">--</div></div>
    </div>
    <div class="mini-prices" id="miniPrices">
      <!-- 由 JS 动态生成 -->
    </div>
  </div>
  <div style="text-align:center; color:var(--text-dim); font-size:10px; letter-spacing:2px; padding:3vw 0 1vw; border-top:1px solid var(--border-color); margin-top:2vw; font-weight:700; transition:color 0.3s,border-color 0.3s;">
    数据来自 Yahoo Finance · 每日自动更新 · 仅供参考 · <span id="buildTime"></span>
  </div>
</div>

<script>
  // ==============================================================
  // 数据注入
  // ==============================================================
  const DATA = __DATA_JSON__;
  const HISTORY_DATES = __HISTORY_DATES__;
  const IS_HISTORY = __IS_HISTORY__;

  const idx = DATA.index;
  const stocks = DATA.stocks;
  const history = DATA.history;

  function fmtPct(c) { return (c >= 0 ? "▲ +" : "▼ ") + c.toFixed(2) + "%"; }
  function fmtPctRaw(c) { return (c >= 0 ? "+" : "") + c.toFixed(2) + "%"; }
  function cls(c) { return c >= 0 ? "up" : "down"; }

  // ==============================================================
  // Glitch 音效引擎 (Web Audio API)
  // ==============================================================
  const AudioCtx = window.AudioContext || window.webkitAudioContext;
  let audioCtx = null;
  let isMuted = false;
  let audioReady = false;  // 标记音频是否已激活

  // 读取静音状态
  const muteState = localStorage.getItem('ndxMuted');
  if (muteState === 'true') {
    isMuted = true;
  }

  function initAudio() {
    if (!audioCtx) {
      audioCtx = new AudioCtx();
    }
    if (audioCtx.state === 'suspended') {
      audioCtx.resume().then(() => {
        audioReady = true;
        console.log('🎵 音频已激活');
      }).catch(e => console.warn('音频激活失败', e));
    } else {
      audioReady = true;
    }
  }

  // 页面加载后绑定一次点击事件，用于激活音频
  function activateAudioOnFirstClick() {
    if (audioReady) return;
    const handler = function() {
      initAudio();
      // 播放一个极短提示音（可选）
      if (!isMuted) {
        try {
          const now = audioCtx.currentTime;
          const osc = audioCtx.createOscillator();
          const gain = audioCtx.createGain();
          osc.type = 'sine';
          osc.frequency.setValueAtTime(800, now);
          gain.gain.setValueAtTime(0.02, now);
          gain.gain.exponentialRampToValueAtTime(0.001, now + 0.05);
          osc.connect(gain);
          gain.connect(audioCtx.destination);
          osc.start(now);
          osc.stop(now + 0.05);
        } catch(e) {}
      }
      document.removeEventListener('click', handler);
    };
    document.addEventListener('click', handler);
  }

  // 播放故障音效
  function playGlitchSound(type) {
    if (isMuted) return;
    // 如果音频还没激活，尝试激活
    if (!audioReady) {
      initAudio();
      // 如果激活后仍然不可用，则放弃本次播放
      if (!audioReady) return;
    }
    try {
      const now = audioCtx.currentTime;
      if (audioCtx.state === 'suspended') {
        audioCtx.resume();
        return;
      }
      if (type === 'burst') {
        const bufferSize = audioCtx.sampleRate * 0.08;
        const buffer = audioCtx.createBuffer(1, bufferSize, audioCtx.sampleRate);
        const data = buffer.getChannelData(0);
        for (let i = 0; i < bufferSize; i++) {
          data[i] = (Math.random() * 2 - 1) * Math.pow(Math.random(), 3);
        }
        const source = audioCtx.createBufferSource();
        source.buffer = buffer;
        const gain = audioCtx.createGain();
        gain.gain.setValueAtTime(0.15, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.08);
        source.connect(gain);
        gain.connect(audioCtx.destination);
        source.start(now);
        source.stop(now + 0.08);
      }
      if (type === 'scratch') {
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        const freq = 800 + Math.random() * 1200;
        osc.type = 'sawtooth';
        osc.frequency.setValueAtTime(freq, now);
        osc.frequency.exponentialRampToValueAtTime(freq * 2.5, now + 0.06);
        gain.gain.setValueAtTime(0.06, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.06);
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.start(now);
        osc.stop(now + 0.06);
      }
      if (type === 'switch') {
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(600, now);
        osc.frequency.exponentialRampToValueAtTime(900, now + 0.04);
        gain.gain.setValueAtTime(0.04, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.04);
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.start(now);
        osc.stop(now + 0.04);
      }
    } catch (e) {}
  }

  // 静音切换（纯汉字）
  const muteBtn = document.getElementById('muteBtn');
  if (muteBtn) {
    muteBtn.textContent = isMuted ? '静音' : '音效';
    muteBtn.addEventListener('click', function() {
      isMuted = !isMuted;
      localStorage.setItem('ndxMuted', isMuted ? 'true' : 'false');
      muteBtn.textContent = isMuted ? '静音' : '音效';
      if (!isMuted) {
        // 激活音频并播放一个提示音
        initAudio();
        if (!audioReady) {
          // 如果尚未激活，尝试用点击激活
          audioReady = true;
          // 直接播放一个短音
        }
        playGlitchSound('switch');
      }
    });
  }

  // 页面加载后绑定激活监听器
  activateAudioOnFirstClick();

  // ==============================================================
  // 主题切换（自动跟随系统 + 手动覆盖）
  // ==============================================================
  const toggleBtn = document.getElementById('themeToggle');
  const htmlEl = document.documentElement;

  const systemPrefersLight = window.matchMedia('(prefers-color-scheme: light)').matches;
  const storedTheme = localStorage.getItem('ndxTheme');

  let useLight = false;
  if (storedTheme !== null) {
    useLight = (storedTheme === 'light');
  } else {
    useLight = systemPrefersLight;
  }

  if (useLight) {
    htmlEl.classList.add('light');
    toggleBtn.textContent = '夜间';
  } else {
    htmlEl.classList.remove('light');
    toggleBtn.textContent = '日间';
  }

  toggleBtn.addEventListener('click', () => {
    const isLight = htmlEl.classList.toggle('light');
    localStorage.setItem('ndxTheme', isLight ? 'light' : 'dark');
    toggleBtn.textContent = isLight ? '夜间' : '日间';
    playGlitchSound('switch');
  });

  const mediaQuery = window.matchMedia('(prefers-color-scheme: light)');
  mediaQuery.addEventListener('change', (e) => {
    if (localStorage.getItem('ndxTheme') === null) {
      if (e.matches) {
        htmlEl.classList.add('light');
        toggleBtn.textContent = '夜间';
      } else {
        htmlEl.classList.remove('light');
        toggleBtn.textContent = '日间';
      }
    }
  });

  // ==============================================================
  // 渲染主数据
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
  document.getElementById('kpiTrend').textContent = (trend30 >= 0 ? "+" : "") + trend30.toFixed(2) + "%";
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
  othersRow.textContent = '其他 ' + (stocks.length - 10) + ' 只 · 合计权重 ' + (100 - topStocks.reduce((a,b) => a + b.weight, 0)).toFixed(1) + '%';
  flowList.appendChild(othersRow);

  const sorted = stocks.slice().sort((a, b) => b.change - a.change);
  const top5 = sorted.slice(0, 5);
  const bottom5 = sorted.slice(-5).reverse();
  const leaderGrid = document.getElementById('leaderGrid');
  const col1 = document.createElement('div');
  col1.className = 'leader-col';
  col1.innerHTML = '<div class="col-title" style="color:var(--color-rise);">▲ 领涨</div>';
  top5.forEach(s => {
    const item = document.createElement('div');
    item.className = 'leader-item';
    item.innerHTML = `<span class="glitch-text">${s.ticker}</span><span class="val glitch-text" style="color:var(--color-rise);">${fmtPct(s.change)}</span>`;
    col1.appendChild(item);
  });
  const col2 = document.createElement('div');
  col2.className = 'leader-col';
  col2.innerHTML = '<div class="col-title" style="color:var(--color-fall);">▼ 领跌</div>';
  bottom5.forEach(s => {
    const item = document.createElement('div');
    item.className = 'leader-item';
    item.innerHTML = `<span class="glitch-text">${s.ticker}</span><span class="val glitch-text" style="color:var(--color-fall);">${fmtPct(s.change)}</span>`;
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
    mini.innerHTML = '<span>近5日</span>';
    const last5 = history.slice(-5);
    last5.forEach((v, i) => {
      const span = document.createElement('span');
      span.className = 'glitch-text';
      if (i === last5.length - 1) span.className += ' latest';
      span.textContent = v.toLocaleString();
      mini.appendChild(span);
    });
  }

  document.getElementById('buildTime').textContent = new Date().toLocaleString('zh-CN');

  // ==============================================================
  // 滚动行情数据
  // ==============================================================
  function buildTickerHTML(data) {
    let html = '';
    const items = data.slice().sort((a, b) => Math.abs(b.change) - Math.abs(a.change));
    for (let rep = 0; rep < 2; rep++) {
      items.forEach(item => {
        const cls = item.change >= 0 ? 'up' : 'down';
        const arrow = item.change >= 0 ? '▲' : '▼';
        html += `<span class="glitch-text">${item.ticker} <span class="${cls}">${arrow} ${fmtPct(item.change)}</span> <span style="color:var(--text-dim);">|</span></span>`;
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
  // Glitch 引擎（含美元彩蛋 50%）
  // ==============================================================
  const glitchElements = document.querySelectorAll('.glitch-text');

  function triggerGlitch(el) {
    if (!el) return;
    playGlitchSound('burst');
    el.classList.remove('active');
    void el.offsetWidth;
    el.classList.add('active');
    setTimeout(() => el.classList.remove('active'), 300);
  }

  const originalTexts = new Map();

  function dollarEasterEgg() {
    const elements = Array.from(glitchElements).filter(el => el.textContent.trim().length > 0);
    if (elements.length === 0) return;
    const el = elements[Math.floor(Math.random() * elements.length)];
    if (el.id === 'stickyPrice' || el.id === 'mainPrice') {
      const others = elements.filter(e => e.id !== 'stickyPrice' && e.id !== 'mainPrice');
      if (others.length === 0) return;
      const target = others[Math.floor(Math.random() * others.length)];
      if (!target) return;
      if (!originalTexts.has(target)) {
        originalTexts.set(target, target.textContent);
      }
      playGlitchSound('scratch');
      target.textContent = '$';
      target.style.color = 'var(--color-rise)';
      triggerGlitch(target);
      setTimeout(() => {
        target.textContent = originalTexts.get(target) || '';
        target.style.color = '';
        originalTexts.delete(target);
      }, 400);
    } else {
      if (!originalTexts.has(el)) {
        originalTexts.set(el, el.textContent);
      }
      playGlitchSound('scratch');
      el.textContent = '$';
      el.style.color = 'var(--color-rise)';
      triggerGlitch(el);
      setTimeout(() => {
        el.textContent = originalTexts.get(el) || '';
        el.style.color = '';
        originalTexts.delete(el);
      }, 400);
    }
  }

  setTimeout(() => {
    glitchElements.forEach(el => triggerGlitch(el));
  }, 400);

  function glitchStorm() {
    const count = Math.floor(Math.random() * 4) + 1;
    for (let i=0; i<count; i++) {
      const el = glitchElements[Math.floor(Math.random() * glitchElements.length)];
      if (el) triggerGlitch(el);
    }
    if (Math.random() < 0.5) {
      dollarEasterEgg();
    }
    if (Math.random() > 0.5) {
      const stickyPrice = document.getElementById('stickyPrice');
      if (stickyPrice) triggerGlitch(stickyPrice);
    }
    setTimeout(glitchStorm, 150 + Math.random() * 500);
  }
  glitchStorm();

  glitchElements.forEach(el => {
    el.addEventListener('mouseenter', function() {
      triggerGlitch(this);
    });
  });

  // ==============================================================
  // 头部价格数字在「净值」和「NDX」之间切换
  // ==============================================================
  const stickyPrice = document.getElementById('stickyPrice');
  const stickyChange = document.getElementById('stickyChange');
  const stickyBadge = document.querySelector('.sticky-top .badge');
  let priceValue = idx.price ? idx.price.toLocaleString() : '--';
  let showNDX = false;
  let switching = false;

  function switchPrice() {
    if (switching || !stickyPrice) return;
    switching = true;

    playGlitchSound('switch');
    triggerGlitch(stickyPrice);
    if (stickyChange) {
      setTimeout(() => triggerGlitch(stickyChange), 50);
    }
    if (stickyBadge) {
      setTimeout(() => triggerGlitch(stickyBadge), 100);
    }

    setTimeout(() => {
      if (showNDX) {
        stickyPrice.textContent = priceValue;
      } else {
        stickyPrice.textContent = 'NDX';
      }
      showNDX = !showNDX;
      switching = false;
    }, 150);
  }

  setInterval(() => {
    switchPrice();
  }, 2800 + Math.random() * 1200);

  setTimeout(() => {
    switchPrice();
  }, 1800);

  // ==============================================================
  // 导航
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

  console.log('✦ Glitch 风格 · 音效已加载 ✦');
</script>
</body>
</html>
"""


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
    html = html.replace("__DATA_JSON__", data_json)
    html = html.replace("__HISTORY_DATES__", history_dates_json)
    html = html.replace("__IS_HISTORY__", is_history_str)
    return html


def main():
    print("=" * 50)
    print("NDX Dashboard 数据抓取 (Glitch 风格 · 音效)")
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    ensure_dir()

    data = build_data()
    print(f"\n数据日期: {data['date']}")
    print(f"指数涨跌: {data['index']['change']}%")
    print(f"成分股数: {data['index']['total']}")

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
