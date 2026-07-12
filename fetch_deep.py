#!/usr/bin/env python3
"""Deep scan with 6-month data for 200MA confirmation and extended universe."""
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

_session = requests.Session()
_session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
})

def yf_download(ticker, period='6mo', interval='1d'):
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

def get_data(ticker, period='6mo'):
    df = yf_download(ticker, period=period)
    if df.empty or len(df) < 60:
        return None
    close = float(df['Close'].iloc[-1])
    prev_close = float(df['Close'].iloc[-2])
    chg = close - prev_close

    ema20 = calc_ema(df['Close'], 20)
    ema50 = calc_ema(df['Close'], 50)
    sma200 = calc_ema(df['Close'], 200) if len(df) >= 200 else None

    rsi14 = calc_rsi(df['Close'])
    atr14 = calc_atr(df['High'], df['Low'], df['Close'])

    ret20 = (close / float(df['Close'].iloc[-21]) - 1) * 100 if len(df) >= 21 else 0
    ret5 = (close / float(df['Close'].iloc[-6]) - 1) * 100 if len(df) >= 6 else 0

    vol = int(df['Volume'].iloc[-1])
    avg_vol = int(df['Volume'].rolling(20).mean().iloc[-1])
    vol_ratio = vol / avg_vol if avg_vol > 0 else 1
    vol_ratio_5 = int(df['Volume'].tail(5).mean()) / avg_vol if avg_vol > 0 else 1

    low20 = float(df['Low'].rolling(20).min().iloc[-1])
    high20 = float(df['High'].rolling(20).max().iloc[-1])
    range_pos = (close - low20) / (high20 - low20) if (high20 - low20) > 0 else 0.5

    ema12 = calc_ema(df['Close'], 12)
    ema26 = calc_ema(df['Close'], 26)
    macd_val = ema12 - ema26

    above_20 = close > ema20
    above_50 = close > ema50
    above_200 = sma200 and close > sma200

    if above_20 and above_50 and above_200 and rsi14 > 50:
        regime = "BULL"
    elif not above_20 and not above_50 and (sma200 and not above_200) and rsi14 < 50:
        regime = "BEAR"
    else:
        regime = "TRANSITIONAL"

    return {
        'close': close, 'chg': chg, 'ret5': ret5, 'ret20': ret20,
        'sma20': ema20, 'sma50': ema50, 'sma200': sma200,
        'rsi': rsi14, 'atr': atr14, 'atr_pct': (atr14 / close) * 100,
        'macd': macd_val, 'regime': regime,
        'vol': vol, 'avg_vol': avg_vol, 'vol_ratio': vol_ratio, 'vol_ratio_5': vol_ratio_5,
        'ret20': ret20, 'low20': low20, 'high20': high20, 'range_pos': range_pos,
        'above_20': above_20, 'above_50': above_50, 'above_200': above_200,
        'bars': len(df)
    }

# Extended watchlist: all NASDAQ 100 + key semiconductors + software
WATCHLIST = [
    'QQQ','SPY','IWM','^VIX',
    # Mag 7
    'AAPL','MSFT','NVDA','AMZN','META','GOOGL','GOOG','TSLA','AVGO',
    # Semiconductors
    'AMD','AMAT','LRCX','KLAC','MU','INTC','QCOM','TXN','NXPI','MRVL','ADI','ON','MCHP','ASML','SNPS','CDNS',
    # Software / Security
    'PANW','CRWD','ZS','NET','DDOG','NOW','VEEV','SNOW','CRM','INTU','ADSK',
    # Financials / Industrials
    'ADP','HON','GEHC','PYPL','SQ','COIN',
]

results = {}
print(f"DEEP SCAN — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')} | 6mo lookback\n")

for sym in WATCHLIST:
    print(f"  {sym}...", end=' ', flush=True)
    try:
        d = get_data(sym)
        if d and d['close'] > 0 and not np.isnan(d['rsi']):
            results[sym] = d
            print(f"${d['close']:.2f} | RSI={d['rsi']:.1f} | ATR%={d['atr_pct']:.1f}% | 20d={d['ret20']:+.1f}% | 200MA={'Y' if d['above_200'] else 'N'}")
        else:
            print("no data")
    except Exception as e:
        print(f"err: {e}")

# Score stocks
stock_results = []
for sym, d in results.items():
    if sym in ['QQQ','SPY','IWM','^VIX']:
        continue
    score = 0
    if d['above_20']: score += 2
    if d['above_50']: score += 2
    if d['above_200']: score += 2
    if 42 <= d['rsi'] <= 62: score += 3  # sweet spot
    elif 62 < d['rsi'] < 72: score += 1  # extended but still bullish
    if d['macd'] > 0: score += 2
    if d['vol_ratio_5'] > 1.1: score += 2
    elif d['vol_ratio_5'] > 0.85: score += 1
    if d['ret20'] > 10: score += 2
    elif d['ret20'] > 0: score += 1
    if 2 <= d['atr_pct'] <= 7: score += 1
    d['score'] = score
    stock_results.append(d)

stock_results.sort(key=lambda x: x['score'], reverse=True)

output = {
    'scan_time': datetime.now().strftime('%Y-%m-%d %H:%M UTC'),
    'indices': {k: v for k, v in results.items() if k in ['QQQ','SPY','IWM','^VIX']},
    'top_long': stock_results
}

with open('/opt/data/handbook/scan_deep.json', 'w') as f:
    json.dump(output, f, indent=2, default=str)

print(f"\n✓ Saved {len(stock_results)} stocks")
print(f"\nTop 15 by score:")
for r in stock_results[:15]:
    print(f"  {r.get('sym', '?'):6s} Score={r['score']:2d} | ${r['close']:>10.2f} | RSI={r['rsi']:5.1f} | ATR%={r['atr_pct']:4.1f}% | 5d={r['ret5']:>+5.1f}% | 20d={r['ret20']:>+6.1f}% | Vol5R={r['vol_ratio_5']:.2f} | RngPos={r['range_pos']:.2f} | 200MA={'Y' if r['above_200'] else 'N'}")
    print(f"         Range: ${r['low20']:.2f} → ${r['high20']:.2f} | MACD={r['macd']:.2f} | ATR=${r['atr']:.2f}")
