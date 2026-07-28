#!/usr/bin/env python3
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
import warnings
warnings.filterwarnings('ignore')

now_et = datetime.now(timezone(timedelta(hours=-5)))
print(f"Current ET: {now_et.strftime('%Y-%m-%d %H:%M:%S %Z')}")
print(f"Trading hours: {'OPEN' if 9*60+30 <= now_et.hour*60+now_et.minute <= 16*60 else 'PRE/POST MARKET'}")
print(f"Day: {now_et.strftime('%A')}")
print()

# ── Stage 1: Core index data ──────────────────────────────────────────────────
tickers_core = ['QQQ', 'SPY', 'IWM', '^VIX', 'TLT', 'GLD']
data = {}
for t in tickers_core:
    try:
        tk = yf.Ticker(t)
        hist = tk.history(period='6mo', interval='1d')
        if len(hist) > 0:
            data[t] = hist
            last = hist['Close'].iloc[-1]
            prev = hist['Close'].iloc[-2] if len(hist) > 1 else last
            chg = (last - prev) / prev * 100
            print(f"✓ {t}: {len(hist)} rows | Close: ${last:.2f} ({chg:+.2f}%)")
        else:
            print(f"✗ {t}: no data")
    except Exception as e:
        print(f"✗ {t}: {e}")

print()

# ── Compute regime indicators ─────────────────────────────────────────────────
def regime(df, short=20, long=50, very_long=200):
    close = df['Close']
    sma20  = close.rolling(short).mean()
    sma50  = close.rolling(long).mean()
    sma200 = close.rolling(very_long).mean() if len(close) >= very_long else None
    rsi14  = 100 - (100 / (1 + df['Close'].pct_change().rolling(14).apply(lambda x: x[x>0].sum()/(-x[x<0].sum()), raw=False)))
    vol20  = df['Volume'].rolling(20).mean()
    return sma20, sma50, sma200, rsi14, vol20

results = {}
for t, df in data.items():
    if len(df) < 60:
        continue
    sma20, sma50, sma200, rsi14, _ = regime(df)
    last_close = df['Close'].iloc[-1]
    rsi = rsi14.iloc[-1]
    sma200_val = sma200.iloc[-1] if sma200 is not None and not sma200.isna().all() else None
    above_200 = (sma200_val < last_close) if sma200_val is not None else 'N/A'
    trend = 'BULL' if sma20.iloc[-1] > sma50.iloc[-1] else 'BEAR'
    results[t] = {
        'close': last_close,
        'sma20': sma20.iloc[-1],
        'sma50': sma50.iloc[-1],
        'sma200': sma200_val,
        'rsi14': rsi,
        'above_200': above_200,
        'trend': trend,
        'vol_avg20': df['Volume'].rolling(20).mean().iloc[-1],
        'vol_today': df['Volume'].iloc[-1],
        'atr14': (df['High'] - df['Low']).rolling(14).mean().iloc[-1],
        'pct_below_52w': (df['Close'].max() - last_close) / df['Close'].max() * 100,
        'pct_from_52w_high': (df['Close'].max() - last_close) / df['Close'].max() * 100,
    }
    sma200_str = f"${sma200_val:.2f}" if sma200_val is not None else 'N/A'
    print(f"  {t}: price=${last_close:.2f} | SMA20=${sma20.iloc[-1]:.2f} | SMA50=${sma50.iloc[-1]:.2f} | SMA200={sma200_str} | RSI={rsi:.1f} | Above200={above_200} | {trend}")

print()

# ── Stage 2: NASDAQ 100 top components ───────────────────────────────────────
nasdaq100 = ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'TSLA', 'AVGO', 'AMD',
             'QCOM', 'TXN', 'NFLX', 'COST', 'INTU', 'AMAT', 'MU', 'BKNG', 'ADI',
             'LRCX', 'PANW', 'KLAC', 'SNPS', 'CDNS', 'CRWD', 'ORLY', 'MAR', 'ABNB',
             'NXPI', 'MRVL', 'FTNT', 'CTAS', 'CPRT', 'ROP', 'CSGP', 'FAST', 'AZNM']

print(f"Fetching {len(nasdaq100)} NASDAQ 100 components...")
comp_data = {}
for t in nasdaq100:
    try:
        tk = yf.Ticker(t)
        hist = tk.history(period='3mo', interval='1d')
        if len(hist) > 30:
            sma20, sma50, _, rsi14, _ = regime(hist)
            last_close = hist['Close'].iloc[-1]
            high52 = hist['High'].max()
            low52 = hist['Low'].min()
            vol20 = hist['Volume'].rolling(20).mean().iloc[-1]
            vol_today = hist['Volume'].iloc[-1]
            atr14 = (hist['High'] - hist['Low']).rolling(14).mean().iloc[-1]
            rsi = rsi14.iloc[-1]
            sma20_v = sma20.iloc[-1]
            sma50_v = sma50.iloc[-1]
            above_sma20 = last_close > sma20_v
            above_sma50 = last_close > sma50_v
            pct_from_high = (high52 - last_close) / high52 * 100
            # 20-day momentum
            mom20 = (last_close - hist['Close'].iloc[-21]) / hist['Close'].iloc[-21] * 100 if len(hist) > 21 else 0
            comp_data[t] = {
                'close': last_close,
                'sma20': sma20_v,
                'sma50': sma50_v,
                'rsi14': rsi,
                'vol_ratio': vol_today / vol20 if vol20 > 0 else 0,
                'atr14': atr14,
                'atr_pct': atr14 / last_close * 100,
                'above_sma20': above_sma20,
                'above_sma50': above_sma50,
                'pct_from_high': pct_from_high,
                'mom20': mom20,
                'high52': high52,
                'low52': low52,
                'vol_today': vol_today,
                'vol20': vol20,
            }
    except Exception as e:
        pass

print(f"Loaded data for {len(comp_data)} components")
print()

# ── Score setups ──────────────────────────────────────────────────────────────
# Scoring rubric (higher = better for LONG):
# - Above both SMAs: +2, above one: +1
# - RSI 40-70 (sweet spot): +2, 30-40 or 70-80: +1, else 0
# - Within 10% of 52w high: +2, 10-20%: +1, <20%: 0
# - Positive 20d momentum: +2, negative: 0
# - Volume > 1.2x avg: +1
# - ATR% < 8% (liquid): +1

scores = {}
for t, d in comp_data.items():
    s = 0
    if d['above_sma20'] and d['above_sma50']:
        s += 2
    elif d['above_sma20']:
        s += 1
    rsi = d['rsi14']
    if 40 <= rsi <= 65:
        s += 2
    elif 30 <= rsi < 40 or 65 < rsi <= 75:
        s += 1
    pct = d['pct_from_high']
    if pct <= 10:
        s += 2
    elif pct <= 20:
        s += 1
    if d['mom20'] > 0:
        s += 2
    if d['vol_ratio'] > 1.2:
        s += 1
    if d['atr_pct'] < 8:
        s += 1
    scores[t] = s

ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
print("=== TOP 10 SCORED SETUPS ===")
for t, s in ranked[:10]:
    d = comp_data[t]
    print(f"  {t:6s} SCORE={s:2d} | Price=${d['close']:.2f} | RSI={d['rsi14']:.1f} | "
          f"PctFromHigh={d['pct_from_high']:.1f}% | Mom20={d['mom20']:.1f}% | "
          f"VolRatio={d['vol_ratio']:.2f}x | ATR%={d['atr_pct']:.1f}% | "
          f"AboveSMA20={d['above_sma20']} | AboveSMA50={d['above_sma50']}")

print()

# ── Deep dive top 3 ────────────────────────────────────────────────────────────
top3 = [t for t, s in ranked[:3]]
for t in top3:
    print(f"\n{'='*60}")
    print(f"DEEP DIVE: {t}")
    print(f"{'='*60}")
    tk = yf.Ticker(t)
    hist = tk.history(period='6mo', interval='1d')
    news = tk.news
    info = tk.info
    
    d = comp_data[t]
    print(f"Price: ${d['close']:.2f}")
    print(f"52W Range: ${d['low52']:.2f} – ${d['high52']:.2f}")
    print(f"Distance from 52w High: {d['pct_from_high']:.1f}%")
    print(f"20 SMA: ${d['sma20']:.2f} | 50 SMA: ${d['sma50']:.2f}")
    print(f"RSI(14): {d['rsi14']:.1f}")
    print(f"20-Day Momentum: {d['mom20']:.1f}%")
    print(f"ATR(14): ${d['atr14']:.2f} ({d['atr_pct']:.1f}% of price)")
    print(f"Volume Today: {d['vol_today']:,.0f} | 20D Avg: {d['vol20']:,.0f} | Ratio: {d['vol_ratio']:.2f}x")
    print(f"Market Cap: ${info.get('marketCap', 'N/A'):,}" if isinstance(info.get('marketCap'), (int,float)) else f"Market Cap: {info.get('marketCap', 'N/A')}")
    print(f"Sector: {info.get('sector', 'N/A')}")
    print(f"Industry: {info.get('industry', 'N/A')}")
    print(f"Beta: {info.get('beta', 'N/A')}")
    print(f"P/E: {info.get('trailingPE', 'N/A'):.1f}" if isinstance(info.get('trailingPE'), float) else f"P/E: {info.get('trailingPE', 'N/A')}")
    
    # Key support/resistance from recent price action
    recent = hist.tail(30)
    supp = []
    res = []
    for _, row in recent.iterrows():
        supp.append(row['Low'])
        res.append(row['High'])
    
    print(f"\nRecent 30d Range: ${recent['Low'].min():.2f} – ${recent['High'].max():.2f}")
    print(f"Recent 30d Avg Volume: {recent['Volume'].mean():,.0f}")
    
    # Compute swing levels
    highs = hist['High'].tail(20)
    lows = hist['Low'].tail(20)
    print(f"20d Swing High: ${highs.max():.2f}")
    print(f"20d Swing Low: ${lows.min():.2f}")
    
    # Recent news
    if news:
        print(f"\nRecent News ({len(news)} items):")
        for n in news[:5]:
            print(f"  - [{n.get('provider','')}] {n.get('title','')[:100]}")
    else:
        print("\nNo recent news available.")
    
    # Risk/Reward calc
    entry = d['close']
    stop = d['sma50'] if d['above_sma50'] else d['sma20'] * 0.97
    risk = entry - stop
    t1 = entry + risk * 2.5
    t2 = entry + risk * 4.0
    print(f"\n--- Risk/Reward ---")
    print(f"Entry: ${entry:.2f}")
    print(f"Stop:  ${stop:.2f} (risk ${risk:.2f}, {risk/entry*100:.1f}%)")
    print(f"T1:    ${t1:.2f} ({risk*2.5/entry*100:.1f}% from entry, {risk*2.5/risk:.1f}:1)")
    print(f"T2:    ${t2:.2f} ({risk*4.0/entry*100:.1f}% from entry, {risk*4.0/risk:.1f}:1)")
    print(f"ATR-based stop: ${entry - d['atr14']*2:.2f} (2xATR)")

print()

# ── Market Regime Summary ──────────────────────────────────────────────────────
print("="*60)
print("MARKET REGIME SUMMARY")
print("="*60)
for t in ['QQQ', 'SPY', 'IWM']:
    if t in results:
        r = results[t]
        regime_str = 'BULL' if r['above_200'] and r['trend']=='BULL' else ('BEAR' if r['above_200']==False and r['trend']=='BEAR' else 'TRANSITIONAL')
        sma200_str = f"${r['sma200']:.2f}" if r['sma200'] is not None else 'N/A'
        print(f"{t}: ${r['close']:.2f} | SMA20=${r['sma20']:.2f} | SMA50=${r['sma50']:.2f} | SMA200={sma200_str} | RSI={r['rsi14']:.1f} | Regime={regime_str}")

if '^VIX' in data:
    vix = data['^VIX']['Close'].iloc[-1]
    print(f"VIX: {vix:.2f} ({'LOW VOL (bullish backdrop)' if vix < 18 else 'NORMAL' if vix < 25 else 'HIGH VOL (caution)'} regime)")

print()
print(f"Scan completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
