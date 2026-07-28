#!/usr/bin/env python3
"""NASDAQ Swing Trade Scanner - Live Data Fetch"""
import sys
sys.path.insert(0, '/opt/data/handbook/.venv/lib/python3.13/site-packages')
import requests
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import json
import warnings
warnings.filterwarnings('ignore')

_session = requests.Session()
_session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})

def yf_download(ticker, period='3mo', interval='1d'):
    t = yf.Ticker(ticker, session=_session)
    return t.history(period=period, interval=interval)

def compute_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def compute_atr(df, period=14):
    high_low = df['High'] - df['Low']
    high_close = (df['High'] - df['Close'].shift()).abs()
    low_close = (df['Low'] - df['Close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(14).mean()

def compute_indicators(df):
    df = df.copy()
    df['sma20'] = df['Close'].rolling(20).mean()
    df['sma50'] = df['Close'].rolling(50).mean()
    df['sma200'] = df['Close'].rolling(200).mean()
    df['ema20'] = df['Close'].ewm(span=20).mean()
    df['rsi'] = compute_rsi(df['Close'], 14)
    df['atr'] = compute_atr(df, 14)
    df['vol_ratio'] = df['Volume'] / df['Volume'].rolling(20).mean()
    return df

def get_structure(df, lookback=20):
    recent = df.tail(lookback)
    if len(recent) < 10:
        return 'RANGE'
    hhs = sum([1 for i in range(2, len(recent)) if recent['High'].iloc[i] > recent['High'].iloc[i-1] and recent['High'].iloc[i-1] > recent['High'].iloc[i-2]])
    lls = sum([1 for i in range(2, len(recent)) if recent['Low'].iloc[i] > recent['Low'].iloc[i-1] and recent['Low'].iloc[i-1] > recent['Low'].iloc[i-2]])
    if hhs >= 3 and lls >= 2:
        return 'HH/HL (BULL)'
    elif hhs <= 1 and lls <= 1:
        return 'LH/LL (BEAR)'
    else:
        return 'RANGE'

# ── Broad Market ──────────────────────────────────────────────────────────
print("Fetching broad market data...")
indices_data = {}
for ticker, period in [('QQQ','6mo'), ('SPY','6mo'), ('IWM','6mo'), ('^VIX','3mo')]:
    try:
        df = yf_download(ticker, period)
        indices_data[ticker] = compute_indicators(df)
        print(f"  {ticker}: {len(df)} rows, last date: {df.index[-1].date()}")
    except Exception as e:
        print(f"  {ticker}: FAILED - {e}")

# ── NASDAQ 100 Top Components ──────────────────────────────────────────────
nasdaq100_top = [
    'AAPL','MSFT','NVDA','GOOGL','META','AMZN','AVGO','TSLA','AMD','QCOM',
    'LIN','ADBE','NFLX','CRM','INTU','TXN','AMAT','MU','INTC','PYPL',
    'NOW','SNPS','CDNS','PANW','CRWD','WDAY','ZS','TEAM','DDOG','NET',
    'FTNT','MRVL','ON','NXPI','ADI','LRCX','KLAC','MPWR','MCHP','ASML'
]

print(f"\nFetching {len(nasdaq100_top)} NASDAQ 100 components...")
results = {}
for ticker in nasdaq100_top:
    try:
        df = yf_download(ticker, '3mo')
        if df.empty or len(df) < 30:
            continue
        df = compute_indicators(df)
        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else last

        close = float(last['Close'])
        sma20 = float(last['sma20'])
        sma50 = float(last['sma50'])
        sma200 = float(last['sma200'])
        rsi14 = float(last['rsi'])
        atr = float(last['atr'])
        vol_ratio = float(last['vol_ratio'])
        chg_pct = ((close - float(prev['Close'])) / float(prev['Close'])) * 100

        results[ticker] = {
            'close': close,
            'chg_pct': chg_pct,
            'sma20': sma20,
            'sma50': sma50,
            'sma200': sma200,
            'rsi14': rsi14,
            'atr': atr,
            'vol_ratio': vol_ratio,
            'above_sma20': close > sma20,
            'above_sma50': close > sma50,
            'above_sma200': close > sma200,
            'structure': get_structure(df),
            'last_date': str(df.index[-1].date()),
        }
    except Exception as e:
        print(f"  {ticker}: FAILED - {e}")

print(f"\nSuccessfully fetched {len(results)} tickers")
print(f"Fetch time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# ── Print Broad Market Summary ─────────────────────────────────────────────
print("\n" + "="*70)
print("BROAD MARKET SUMMARY")
print("="*70)
for ticker, df in indices_data.items():
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last
    close = float(last['Close'])
    chg = ((close - float(prev['Close'])) / float(prev['Close'])) * 100
    print(f"\n{ticker}:")
    print(f"  Close: {close:.2f}  |  Chg: {chg:+.2f}%")
    print(f"  SMA20: {float(last['sma20']):.2f}  |  SMA50: {float(last['sma50']):.2f}  |  SMA200: {float(last['sma200']):.2f}")
    print(f"  RSI: {float(last['rsi']):.1f}  |  ATR: {float(last['atr']):.2f}  |  VolRatio: {float(last['vol_ratio']):.2f}")
    structure = get_structure(df)
    print(f"  Structure: {structure}")
    print(f"  Close > SMA20: {close > float(last['sma20'])}  > SMA50: {close > float(last['sma50'])}  > SMA200: {close > float(last['sma200'])}")

# ── Component Analysis ─────────────────────────────────────────────────────
print("\n" + "="*70)
print("NASDAQ 100 COMPONENT SCAN")
print("="*70)

# Score each ticker for swing trade potential
scored = []
for ticker, data in results.items():
    score = 0
    flags = []

    # Trend alignment (bull regime filter)
    if data['above_sma20'] and data['above_sma50']:
        score += 3
        flags.append('Above SMA20+50')
    if data['above_sma200']:
        score += 1
        flags.append('Above SMA200')

    # RSI — prefer 40-70 range for entries, but slight oversold strength is good
    if 45 <= data['rsi14'] <= 65:
        score += 2
        flags.append(f'RSI neutral zone ({data["rsi14"]:.0f})')
    elif data['rsi14'] > 70:
        score -= 1
        flags.append('RSI overbought')
    elif data['rsi14'] < 40:
        score += 1
        flags.append(f'RSI oversold ({data["rsi14"]:.0f})')

    # Volume surge
    if data['vol_ratio'] > 1.3:
        score += 2
        flags.append(f'Vol surge ({data["vol_ratio"]:.1f}x)')
    elif data['vol_ratio'] > 1.1:
        score += 1
        flags.append(f'Vol above avg ({data["vol_ratio"]:.1f}x)')

    # Structure
    if 'BULL' in data['structure']:
        score += 2
        flags.append(data['structure'])
    elif 'BEAR' in data['structure']:
        score -= 1

    # ATR-based volatility check
    atr_pct = (data['atr'] / data['close']) * 100
    if atr_pct < 4:
        score += 1
        flags.append(f'Low vol ({atr_pct:.1f}% ATR)')

    scored.append({
        'ticker': ticker,
        'close': data['close'],
        'chg_pct': data['chg_pct'],
        'rsi14': data['rsi14'],
        'atr': data['atr'],
        'vol_ratio': data['vol_ratio'],
        'structure': data['structure'],
        'above_sma20': data['above_sma20'],
        'above_sma50': data['above_sma50'],
        'above_sma200': data['above_sma200'],
        'flags': flags,
        'score': score,
    })

scored.sort(key=lambda x: x['score'], reverse=True)

print("\nTOP SWING CANDIDATES (sorted by score):")
print(f"{'Ticker':<8} {'Close':>8} {'Chg%':>6} {'RSI':>5} {'ATR':>6} {'VolR':>5} {'Score':>5}  Flags")
print("-"*80)
for item in scored[:20]:
    flags_str = ' | '.join(item['flags'][:3])
    print(f"{item['ticker']:<8} {item['close']:>8.2f} {item['chg_pct']:>+6.1f} {item['rsi14']:>5.0f} {item['atr']:>6.2f} {item['vol_ratio']:>5.2f} {item['score']:>5}  {flags_str}")

# Save raw results
with open('/opt/data/handbook/scan_results.json', 'w') as f:
    json.dump({'indices': {k: {kk: float(vv) if isinstance(vv, (np.floating, np.integer)) else str(vv) if not isinstance(vv, (int, float)) else vv for kk, vv in v.items()} for k, v in indices_data.items()}, 'components': {k: v for k, v in results.items()}, 'scored': scored, 'scan_time': datetime.now().isoformat()}, f, indent=2, default=str)

print(f"\nResults saved to scan_results.json")
