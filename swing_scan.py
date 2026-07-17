#!/usr/bin/env python3
"""
NASDAQ Swing Trade Scanner - July 17, 2026
Scans QQQ, SPY, and top NASDAQ 100 components for swing trade setups.
"""

import json
import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import sys

# ─── CONFIG ───────────────────────────────────────────────────────────────────
SCAN_DATE = datetime(2026, 7, 17)
SCAN_TIME = "14:00 ET"
PERIOD_1Y  = "1y"   # for long-term MA context
PERIOD_6M  = "6mo"  # for intermediate trend
PERIOD_3M  = "3mo"  # for recent momentum
INTERVAL   = "1d"

TOP_NASDAQ100 = [
    "AAPL","MSFT","NVDA","GOOGL","AMZN","META","AVGO","TSLA","ADBE","ORCL",
    "CRM","AMD","QCOM","INTC","TXN","AMAT","LRCX","MU","NOW","PANW",
    "NFLX","INTU","PYPL","BKNG","ISRG","ODFL","CHTR","REGN","VRTX","GILD",
    "SNPS","CDNS","MRVL","KLAC","SNOW","DDOG","TEAM","WDAY","ZS","CRWD",
]

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def sma(series, length):
    return series.rolling(length).mean()

def ema(series, length):
    return series.ewm(span=length, adjust=False).mean()

def atr(high, low, close, length=14):
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(length).mean()

def rsi(close, length=14):
    delta = close.diff()
    gain = delta.where(delta > 0, 0)
    loss = (-delta).where(delta < 0, 0)
    avg_gain = gain.ewm(alpha=1/length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/length, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def macd(close, fast=12, slow=26, signal=9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist

def fetch_data(ticker, period=PERIOD_1Y, interval=INTERVAL):
    try:
        data = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=True)
        if data.empty:
            return None
        data.columns = [c.lower() for c in data.columns]
        data['volume'] = data.get('volume', pd.Series([0]*len(data)))
        data['adj close'] = data.get('adj close', data['close'])
        return data
    except Exception as e:
        return None

def analyze_ticker(ticker, data):
    if data is None or len(data) < 60:
        return None

    close = data['close']
    high  = data['high']
    low   = data['low']
    volume = data['volume']

    # ── MAs ──
    ma20  = ema(close, 20)
    ma50  = sma(close, 50)
    ma200 = sma(close, 200)
    current_price = close.iloc[-1]

    # ── Indicators ──
    data['atr'] = atr(high, low, close, 14)
    data['rsi'] = rsi(close, 14)
    macd_line, signal_line, hist = macd(close)
    data['macd_line'] = macd_line
    data['macd_signal'] = signal_line
    data['macd_hist'] = hist

    current_rsi = data['rsi'].iloc[-1]
    current_atr = data['atr'].iloc[-1]
    current_macd_hist = data['macd_hist'].iloc[-1]
    prev_macd_hist = data['macd_hist'].iloc[-2]
    current_macd_line = data['macd_line'].iloc[-1]
    current_macd_signal = data['macd_signal'].iloc[-1]

    # ── Volume ──
    avg_vol_20 = volume.rolling(20).mean().iloc[-1]
    today_vol = volume.iloc[-1]
    vol_ratio = today_vol / avg_vol_20 if avg_vol_20 > 0 else 1

    # ── Recent range ──
    high_20d  = high.tail(20).max()
    low_20d   = low.tail(20).min()
    high_5d   = high.tail(5).max()
    low_5d    = low.tail(5).min()

    # ── Market structure ──
    # Higher High / Higher Low in last 20 days
    last_20_closes = close.tail(20)
    last_20_highs = high.tail(20)
    last_20_lows  = low.tail(20)

    # Identify swing highs/lows in last 20 days
    hh = last_20_highs.max()
    hlc = last_20_lows.max()  # higher low candidate

    # Recent momentum (5-day return)
    ret_5d  = (close.iloc[-1] / close.iloc[-6] - 1) * 100 if len(close) > 6 else 0
    ret_10d = (close.iloc[-1] / close.iloc[-11] - 1) * 100 if len(close) > 11 else 0
    ret_20d = (close.iloc[-1] / close.iloc[-21] - 1) * 100 if len(close) > 21 else 0

    # ── Regime ──
    above_ma20  = current_price > ma20.iloc[-1]
    above_ma50  = current_price > ma50.iloc[-1]
    above_ma200 = current_price > ma200.iloc[-1] if len(close) >= 200 and not pd.isna(ma200.iloc[-1]) else True
    ma20_above_ma50 = ma20.iloc[-1] > ma50.iloc[-1]
    ma50_above_ma200 = ma50.iloc[-1] > ma200.iloc[-1] if len(close) >= 200 and not pd.isna(ma200.iloc[-1]) else True

    # Bullish: price above MA50, MA50 above MA200
    # Bearish: price below MA50, MA50 below MA200
    # Transitional: mixed
    if above_ma200 and above_ma50 and above_ma20:
        regime = "BULL"
    elif not above_ma200 and not above_ma50 and not above_ma20:
        regime = "BEAR"
    else:
        regime = "TRANSITIONAL"

    # ── MACD ──
    macd_bullish = current_macd_line > current_macd_signal
    macd_x_up = prev_macd_hist < 0 and current_macd_hist > 0  # crossed up
    macd_x_dn = prev_macd_hist > 0 and current_macd_hist < 0  # crossed down

    # ── Bollinger Bands ──
    bb_mid = sma(close, 20).iloc[-1]
    bb_std = close.tail(20).std()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std
    bb_width = (bb_upper - bb_lower) / bb_mid * 100

    # ── Gap Analysis ──
    prev_close = close.iloc[-2]
    gap_pct = (current_price - prev_close) / prev_close * 100
    gap_up = gap_pct > 1.0
    gap_dn = gap_pct < -1.0

    return {
        'ticker': ticker,
        'price': current_price,
        'atr': current_atr,
        'atr_pct': current_atr / current_price * 100,
        'rsi': current_rsi,
        'ma20': ma20.iloc[-1],
        'ma50': ma50.iloc[-1],
        'ma200': ma200.iloc[-1] if len(close) >= 200 and not pd.isna(ma200.iloc[-1]) else None,
        'above_ma20': above_ma20,
        'above_ma50': above_ma50,
        'above_ma200': above_ma200,
        'ma20_above_ma50': ma20_above_ma50,
        'ma50_above_ma200': ma50_above_ma200,
        'macd_bullish': macd_bullish,
        'macd_x_up': macd_x_up,
        'macd_x_dn': macd_x_dn,
        'macd_hist': current_macd_hist,
        'macd_hist_prev': prev_macd_hist,
        'vol_ratio': vol_ratio,
        'avg_vol_20': avg_vol_20,
        'high_20d': high_20d,
        'low_20d': low_20d,
        'high_5d': high_5d,
        'low_5d': low_5d,
        'close_5d_ago': close.iloc[-6] if len(close) > 6 else None,
        'ret_5d': ret_5d,
        'ret_10d': ret_10d,
        'ret_20d': ret_20d,
        'regime': regime,
        'bb_upper': bb_upper,
        'bb_mid': bb_mid,
        'bb_lower': bb_lower,
        'bb_width': bb_width,
        'gap_pct': gap_pct,
        'gap_up': gap_up,
        'gap_dn': gap_dn,
        'prev_close': prev_close,
    }

def score_setup(a):
    """Score a ticker 0-100 for swing trade quality."""
    if a is None:
        return -999

    score = 50  # baseline

    # Trend alignment (0-20)
    if a['above_ma20'] and a['above_ma50'] and a['above_ma200']:
        score += 15
    elif a['above_ma20'] and a['above_ma50']:
        score += 8
    elif not a['above_ma20'] and not a['above_ma50'] and not a['above_ma200']:
        score -= 10

    # RSI (0-15): optimal 40-60 for long entry, 30-50 for best upside room
    rsi = a['rsi']
    if 40 <= rsi <= 60:
        score += 10  # neutral zone — room to run
    elif 30 <= rsi < 40:
        score += 5   # slightly oversold, recovery potential
    elif rsi > 70:
        score -= 8   # overbought — less upside room, more risk
    elif rsi < 30:
        score -= 5

    # MACD momentum (0-15)
    if a['macd_x_up']:
        score += 12
    elif a['macd_bullish'] and a['macd_hist'] > 0:
        score += 8
    elif a['macd_bullish'] and a['macd_hist'] > a['macd_hist_prev']:
        score += 5
    elif a['macd_x_dn']:
        score -= 10

    # Recent momentum (0-10)
    if a['ret_5d'] > 3:
        score += 5
    elif a['ret_5d'] < -3:
        score -= 5

    # Volume confirmation (0-10)
    if a['vol_ratio'] > 1.5:
        score += 8
    elif a['vol_ratio'] > 1.2:
        score += 4

    # Gap fill potential (0-10)
    if a['gap_up'] and a['rsi'] < 70:
        score += 6  # gap continuation potential
    elif a['gap_dn']:
        score -= 6

    return round(score, 1)

# ─── MAIN SCAN ────────────────────────────────────────────────────────────────

print("=" * 70)
print(f"NASDAQ SWING TRADE SCANNER — {SCAN_DATE.strftime('%B %d, %Y')} @ {SCAN_TIME}")
print("=" * 70)

# 1. Fetch broad market
print("\n[1/4] Fetching broad market data (QQQ, SPY, IWM, VIX proxy)...")
market_tickers = ['QQQ', 'SPY', 'IWM', '^VIX', 'DXY']
market_data = {}
for t in market_tickers:
    d = fetch_data(t, period=PERIOD_6M)
    market_data[t] = d
    print(f"  {t}: {'OK' if d is not None else 'FAILED'} ({len(d) if d is not None else 0} rows)")

# 2. Analyze broad market
market_results = {}
for t, d in market_data.items():
    if d is not None:
        market_results[t] = analyze_ticker(t, d)

# 3. Fetch top NASDAQ 100 components
print(f"\n[2/4] Fetching {len(TOP_NASDAQ100)} NASDAQ-linked tickers...")
ticker_data = {}
batch_size = 10
for i in range(0, len(TOP_NASDAQ100), batch_size):
    batch = TOP_NASDAQ100[i:i+batch_size]
    for ticker in batch:
        d = fetch_data(ticker, period=PERIOD_6M)
        ticker_data[ticker] = d
        sys.stdout.write(f"  {ticker} ")
        sys.stdout.flush()
    print("")

print(f"\n[3/4] Analyzing {len(ticker_data)} tickers...")
results = []
for ticker, data in ticker_data.items():
    a = analyze_ticker(ticker, data)
    if a:
        a['score'] = score_setup(a)
        results.append(a)

results.sort(key=lambda x: x['score'], reverse=True)

print(f"\n[4/4] Scoring and ranking top setups...")

# ─── OUTPUT ──────────────────────────────────────────────────────────────────

print("\n" + "=" * 70)
print("TOP 10 SCORED SETUPS")
print("=" * 70)
print(f"{'Ticker':<8} {'Price':>9} {'RSI':>6} {'MACD':>6} {'Score':>6} {'Regime':>12} {'5D%':>7} {'VolRatio':>8}")
print("-" * 70)
for r in results[:10]:
    macd_dir = "▲" if r['macd_bullish'] else "▼"
    print(f"{r['ticker']:<8} ${r['price']:>8.2f} {r['rsi']:>6.1f} {macd_dir:>6} {r['score']:>6.1f} {r['regime']:>12} {r['ret_5d']:>7.2f}% {r['vol_ratio']:>8.2f}x")

# ─── BROAD MARKET REGIME ──────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("BROAD MARKET REGIME ANALYSIS")
print("=" * 70)

for t, a in market_results.items():
    if a:
        regime_icon = "🟢" if a['regime'] == 'BULL' else ("🔴" if a['regime'] == 'BEAR' else "🟡")
        print(f"\n{t}: ${a['price']:.2f}")
        print(f"  Regime: {regime_icon} {a['regime']}")
        print(f"  RSI: {a['rsi']:.1f} | MACD Hist: {a['macd_hist']:.3f} | 5D Return: {a['ret_5d']:.2f}%")
        print(f"  MA20: ${a['ma20']:.2f} | MA50: ${a['ma50']:.2f} | MA200: ${a['ma200'] if a['ma200'] else 'N/A'}")
        print(f"  Above MA20: {a['above_ma20']} | Above MA50: {a['above_ma50']} | Above MA200: {a['above_ma200']}")
        print(f"  ATR: ${a['atr']:.2f} ({a['atr_pct']:.2f}% of price)")

# ─── TOP 3 DEEP DIVE ─────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("TOP 3 SWING TRADE SETUPS — DEEP DIVE")
print("=" * 70)

top3 = results[:3]
for i, a in enumerate(top3, 1):
    print(f"\n{'─'*70}")
    print(f"SETUP #{i}: {a['ticker']}  |  Score: {a['score']}/100")
    print(f"{'─'*70}")
    print(f"  Current Price:    ${a['price']:.2f}")
    print(f"  5-Day Return:     {a['ret_5d']:+.2f}%")
    print(f"  10-Day Return:    {a['ret_10d']:+.2f}%")
    print(f"  20-Day Return:    {a['ret_20d']:+.2f}%")
    print(f"  ATR (14):         ${a['atr']:.2f} ({a['atr_pct']:.2f}% of price)")
    print(f"  RSI (14):         {a['rsi']:.1f}")
    print(f"  MACD Histogram:   {a['macd_hist']:.4f} (prev: {a['macd_hist_prev']:.4f})")
    print(f"  MACD Crossover:   {'▲ CROSSED UP' if a['macd_x_up'] else '▼ CROSSED DOWN' if a['macd_x_dn'] else 'no cross today'}")
    print(f"  Volume Ratio:     {a['vol_ratio']:.2f}x 20-day avg")
    print(f"  Regime:           {a['regime']}")
    print(f"  Gap Today:        {a['gap_pct']:+.2f}%")
    print(f"  Bollinger Width:  {a['bb_width']:.2f}% (upper=${a['bb_upper']:.2f}, mid=${a['bb_mid']:.2f}, lower=${a['bb_lower']:.2f})")
    print(f"  20D High:         ${a['high_20d']:.2f} | 20D Low: ${a['low_20d']:.2f}")
    print(f"  5D High:          ${a['high_5d']:.2f} | 5D Low: ${a['low_5d']:.2f}")

    # ── Trade metrics ──
    risk_pct = a['atr_pct'] * 1.5  # 1.5 ATR stop
    stop_price = a['price'] * (1 - risk_pct/100)

    # T1: 2:1 R:R, T2: 3:1 R:R
    risk_amount = a['price'] - stop_price
    t1 = a['price'] + risk_amount * 2.0
    t2 = a['price'] + risk_amount * 3.0

    # Dynamic stop (trailing): move stop to breakeven + 0.5 ATR when price reaches T1
    be_stop = a['price'] + risk_amount * 0.5

    print(f"\n  ── TACTICAL ORDER BLUEPRINT ──")
    print(f"  Direction:         LONG" if a['above_ma20'] and a['regime'] != 'BEAR' else "  Direction:         SHORT" if not a['above_ma20'] and a['regime'] == 'BEAR' else "  Direction:         WATCH")
    print(f"  Entry Type:       Buy Limit @ ${a['price']:.2f} (or market on pullback)")
    print(f"  Stop Loss:        ${stop_price:.2f} (1.5 ATR = {risk_pct:.2f}% risk)")
    print(f"  Risk/Share:       ${risk_amount:.2f}")
    print(f"  T1 (2:1):         ${t1:.2f} (+{risk_amount*2:.2f}/share, {((t1/a['price'])-1)*100:.2f}%)")
    print(f"  T2 (3:1):         ${t2:.2f} (+{risk_amount*3:.2f}/share, {((t2/a['price'])-1)*100:.2f}%)")
    print(f"  Trailing Stop:    Move SL to ${be_stop:.2f} (breakeven + 0.5 ATR) when T1 hit")
    print(f"  Position Size:    Risk 1-2% of portfolio per trade")
    print(f"  Holding Window:   2-10 trading days (exit at T1 or T2, whichever first)")

    # Invalidation
    inv_price = a['low_20d'] if a['above_ma20'] else a['high_20d']
    print(f"  Invalidation:     Price closes below ${inv_price:.2f} (20-day low) = thesis killed")

# ─── JSON EXPORT ─────────────────────────────────────────────────────────────
export = {
    'scan_date': SCAN_DATE.strftime('%Y-%m-%d'),
    'scan_time': SCAN_TIME,
    'broad_market': {t: {k: round(v,4) if isinstance(v, float) else v
                        for k,v in a.items() if k not in ['bb_upper','bb_mid','bb_lower','high_20d','low_20d','high_5d','low_5d']}
                     for t, a in market_results.items() if a},
    'ranked_setups': [
        {k: round(v,4) if isinstance(v, float) else v
         for k,v in r.items() if k not in ['bb_upper','bb_mid','bb_lower','high_20d','low_20d','high_5d','low_5d']}
        for r in results[:10]
    ]
}

with open('/opt/data/handbook/swing_scan_results.json', 'w') as f:
    json.dump(export, f, indent=2, default=str)

print(f"\n✓ Results exported to /opt/data/handbook/swing_scan_results.json")
