#!/usr/bin/env python3
"""Fetch live market data via yfinance using direct API calls."""
import sys
sys.path.insert(0, '/opt/hermes/.venv/lib/python3.13/site-packages')

import requests
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import warnings
warnings.filterwarnings('ignore')

# Custom session to avoid Yahoo rate limiting
_session = requests.Session()
_session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
})

def yf_download(ticker, period='3mo', interval='1d'):
    t = yf.Ticker(ticker, session=_session)
    return t.history(period=period, interval=interval)

def calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1])

def calc_atr(high, low, close, period=14):
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])

def calc_ema(series, period):
    return float(series.ewm(span=period, adjust=False).mean().iloc[-1])

def get_market_data(ticker):
    df = yf_download(ticker)
    if df.empty or len(df) < 30:
        return None
    close = float(df['Close'].iloc[-1])
    prev_close = float(df['Close'].iloc[-2])
    chg = close - prev_close
    
    sma20 = calc_ema(df['Close'], 20)
    sma50 = calc_ema(df['Close'], 50)
    sma200 = calc_ema(df['Close'], 200) if len(df) >= 200 else None
    rsi14 = calc_rsi(df['Close'])
    atr14 = calc_atr(df['High'], df['Low'], df['Close'])
    
    # 20-day return
    ret20 = (close / float(df['Close'].iloc[-21]) - 1) * 100 if len(df) >= 21 else 0
    
    # Volume
    vol = int(df['Volume'].iloc[-1])
    avg_vol = int(df['Volume'].rolling(20).mean().iloc[-1])
    vol_ratio = vol / avg_vol if avg_vol > 0 else 1
    
    # 20-day range position
    low20 = float(df['Low'].rolling(20).min().iloc[-1])
    high20 = float(df['High'].rolling(20).max().iloc[-1])
    range_pos = (close - low20) / (high20 - low20) if (high20 - low20) > 0 else 0.5
    
    # MACD
    ema12 = calc_ema(df['Close'], 12)
    ema26 = calc_ema(df['Close'], 26)
    macd_val = ema12 - ema26
    
    # Structure: HH/HL vs LH/LL over last 20 bars
    highs = df['High'].rolling(5).max()
    lows = df['Low'].rolling(5).min()
    last_highs = highs.tail(5).values
    last_lows = lows.tail(5).values
    
    # Regime
    above_20 = close > sma20
    above_50 = close > sma50
    above_200 = sma200 and close > sma200
    
    if above_20 and above_50 and above_200 and rsi14 > 50:
        regime = "BULL"
    elif not above_20 and not above_50 and (sma200 and not above_200) and rsi14 < 50:
        regime = "BEAR"
    else:
        regime = "TRANSITIONAL"
    
    return {
        'close': close,
        'chg': chg,
        'sma20': sma20,
        'sma50': sma50,
        'sma200': sma200,
        'rsi': rsi14,
        'atr': atr14,
        'atr_pct': (atr14 / close) * 100,
        'macd': macd_val,
        'regime': regime,
        'vol': vol,
        'avg_vol': avg_vol,
        'vol_ratio': vol_ratio,
        'ret20': ret20,
        'low20': low20,
        'high20': high20,
        'range_pos': range_pos,
        'above_20': above_20,
        'above_50': above_50,
        'above_200': above_200,
    }

# ── NASDAQ 100 Components ──────────────────────────────────────
NASDAQ100 = [
    'AAPL','MSFT','NVDA','AMZN','META','GOOGL','GOOG','AVGO','TSLA','AMD',
    'QCOM','TXN','AMAT','MU','INTC','NFLX','INTU','ADP','PANW','NOW',
    'ADSK','CRM','SQ','COIN','SNOW','DDOG','NET','CRWD','ZS','VEEV',
    'KLAC','LRCX','AMAT','MPWR','ON','TER','NXPI','MRVL','KLAC','MCHP',
    'ASML','KLAC','ADI','ON','MRVL','PANW','FTNT','CDNS','SNPS','PANW'
]
# De-duplicate
NASDAQ100 = list(dict.fromkeys(NASDAQ100))

# ── Indices ────────────────────────────────────────────────────
print(f"FETCHING LIVE DATA — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}\n")

indices = {}
for sym in ['QQQ', 'SPY', 'IWM', '^VIX']:
    print(f"Fetching {sym}...", end=' ')
    d = get_market_data(sym)
    if d:
        indices[sym] = d
        print(f"${d['close']:.2f} | RSI={d['rsi']:.1f} | ATR={d['atr']:.2f} | Regime={d['regime']}")
    else:
        print("FAILED")

# ── Individual Stocks ──────────────────────────────────────────
results = []
for sym in NASDAQ100[:40]:  # Limit to avoid rate limiting
    print(f"Scanning {sym}...", end=' ')
    try:
        d = get_market_data(sym)
        if d and d['close'] > 0 and not np.isnan(d['rsi']):
            d['sym'] = sym
            results.append(d)
            print(f"${d['close']:.2f} | RSI={d['rsi']:.1f} | ATR%={d['atr_pct']:.1f}%")
        else:
            print("no data")
    except Exception as e:
        print(f"err: {e}")

# ── Score each stock ────────────────────────────────────────────
for r in results:
    score = 0
    # Trend: above key MAs
    if r['above_20']: score += 2
    if r['above_50']: score += 2
    if r['above_200']: score += 2
    # Momentum: RSI in sweet spot 40-70 for longs, >70 for continuation
    if 45 <= r['rsi'] <= 65: score += 2
    elif r['rsi'] > 65 and r['rsi'] < 80: score += 1
    # MACD positive
    if r['macd'] > 0: score += 2
    # Volume expanding
    if r['vol_ratio'] > 1.2: score += 2
    elif r['vol_ratio'] > 0.8: score += 1
    # 20-day momentum
    if r['ret20'] > 5: score += 2
    elif r['ret20'] > 0: score += 1
    # ATR% (volatility in range that fits swing horizon)
    if 2 <= r['atr_pct'] <= 8: score += 1
    
    r['score'] = score

# Sort by score
results.sort(key=lambda x: x['score'], reverse=True)

# ── Output ──────────────────────────────────────────────────────
output = {
    'scan_time': datetime.now().strftime('%Y-%m-%d %H:%M UTC'),
    'indices': indices,
    'top_long': [],
    'top_short': [],
    'all_results': results[:30]
}

for r in results[:15]:
    output['top_long'].append({
        'sym': r['sym'],
        'close': r['close'],
        'chg': r['chg'],
        'ret20': r['ret20'],
        'rsi': r['rsi'],
        'atr_pct': r['atr_pct'],
        'macd': r['macd'],
        'vol_ratio': r['vol_ratio'],
        'range_pos': r['range_pos'],
        'above_20': r['above_20'],
        'above_50': r['above_50'],
        'above_200': r['above_200'],
        'score': r['score'],
        'low20': r['low20'],
        'high20': r['high20'],
    })

# Save
with open('/opt/data/handbook/scan_live_new.json', 'w') as f:
    json.dump(output, f, indent=2, default=str)

print(f"\n✓ Saved {len(results)} stocks to scan_live_new.json")
print(f"\nTop 10 by score:")
for r in results[:10]:
    print(f"  {r['sym']:6s} | ${r['close']:>10.2f} | RSI={r['rsi']:5.1f} | ATR%={r['atr_pct']:4.1f}% | 20d={r['ret20']:>+6.1f}% | VolR={r['vol_ratio']:.2f} | Score={r['score']}")
