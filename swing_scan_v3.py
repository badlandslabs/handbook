#!/usr/bin/env python3
"""NASDAQ Swing Trade Scanner - Live Data Fetch v3"""
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
    df = t.history(period=period, interval=interval)
    # Drop rows with NaN closes
    df = df[df['Close'].notna()]
    return df

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
    hhs = 0
    lls = 0
    highs = recent['High'].values
    lows = recent['Low'].values
    for i in range(2, len(highs)):
        if highs[i] > highs[i-1] and highs[i-1] > highs[i-2]:
            hhs += 1
        if lows[i] > lows[i-1] and lows[i-1] > lows[i-2]:
            lls += 1
    if hhs >= 3 and lls >= 2:
        return 'HH/HL (BULL)'
    elif hhs <= 1 and lls <= 1:
        return 'LH/LL (BEAR)'
    else:
        return 'RANGE'

def serialize_value(v):
    if isinstance(v, (np.floating, np.integer)):
        return float(v)
    elif isinstance(v, (int, float)):
        return v
    elif v is None:
        return None
    else:
        return str(v)

# ── Broad Market ──────────────────────────────────────────────────────────
print("Fetching broad market data...")
indices_data = {}
for ticker, p in [('QQQ','6mo'), ('SPY','6mo'), ('IWM','6mo'), ('^VIX','3mo')]:
    try:
        df = yf_download(ticker, p)
        df = compute_indicators(df)
        indices_data[ticker] = df
        print(f"  {ticker}: {len(df)} rows, last: {df.index[-1].date()}, close: {df['Close'].iloc[-1]:.2f}")
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
failed = []
for ticker in nasdaq100_top:
    try:
        df = yf_download(ticker, '3mo')
        if df.empty or len(df) < 30:
            failed.append((ticker, 'empty'))
            continue
        df = compute_indicators(df)
        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else last

        close = float(last['Close'])
        sma20 = float(last['sma20']) if not pd.isna(last['sma20']) else None
        sma50 = float(last['sma50']) if not pd.isna(last['sma50']) else None
        sma200 = float(last['sma200']) if not pd.isna(last['sma200']) else None
        rsi14 = float(last['rsi']) if not pd.isna(last['rsi']) else None
        atr = float(last['atr']) if not pd.isna(last['atr']) else None
        vol_ratio = float(last['vol_ratio']) if not pd.isna(last['vol_ratio']) else None
        chg_pct = ((close - float(prev['Close'])) / float(prev['Close'])) * 100

        # Recent 5-day performance
        last_5d = df.tail(5)
        last_5d_chg = ((last['Close'] - float(df['Close'].iloc[-6])) / float(df['Close'].iloc[-6])) * 100 if len(df) >= 6 else 0

        results[ticker] = {
            'close': close,
            'chg_pct': chg_pct,
            'last_5d_chg': last_5d_chg,
            'sma20': sma20,
            'sma50': sma50,
            'sma200': sma200,
            'rsi14': rsi14,
            'atr': atr,
            'vol_ratio': vol_ratio,
            'above_sma20': close > sma20 if sma20 else None,
            'above_sma50': close > sma50 if sma50 else None,
            'above_sma200': close > sma200 if sma200 else None,
            'structure': get_structure(df),
            'last_date': str(df.index[-1].date()),
            'volume': int(last['Volume']),
            'avg_volume': int(df['Volume'].tail(20).mean()),
        }
    except Exception as e:
        failed.append((ticker, str(e)[:50]))

print(f"  Fetched: {len(results)}, Failed: {len(failed)}")
if failed:
    print(f"  Failures: {failed[:5]}")

# ── Print Broad Market Summary ─────────────────────────────────────────────
print("\n" + "="*72)
print("BROAD MARKET SUMMARY")
print("="*72)
for ticker, df in indices_data.items():
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last
    close = float(last['Close'])
    chg = ((close - float(prev['Close'])) / float(prev['Close'])) * 100
    sma20_v = float(last['sma20']) if not pd.isna(last['sma20']) else None
    sma50_v = float(last['sma50']) if not pd.isna(last['sma50']) else None
    sma200_v = float(last['sma200']) if not pd.isna(last['sma200']) else None
    rsi_v = float(last['rsi']) if not pd.isna(last['rsi']) else None
    atr_v = float(last['atr']) if not pd.isna(last['atr']) else None
    vr = float(last['vol_ratio']) if not pd.isna(last['vol_ratio']) else None
    print(f"\n{ticker}: Close={close:.2f} Chg={chg:+.2f}%")
    sma20_s = f"{sma20_v:.2f}" if sma20_v else "N/A"
    sma50_s = f"{sma50_v:.2f}" if sma50_v else "N/A"
    sma200_s = f"{sma200_v:.2f}" if sma200_v else "N/A"
    rsi_s = f"{rsi_v:.1f}" if rsi_v else "N/A"
    atr_s = f"{atr_v:.2f}" if atr_v else "N/A"
    vr_s = f"{vr:.2f}" if vr else "N/A"
    print(f"  SMA20={sma20_s}  SMA50={sma50_s}  SMA200={sma200_s}")
    print(f"  RSI={rsi_s}  ATR={atr_s}  VolRatio={vr_s}")
    print(f"  Structure={get_structure(df)}")
    print(f"  >SMA20={close>sma20_v if sma20_v else 'N/A'}  >SMA50={close>sma50_v if sma50_v else 'N/A'}  >SMA200={close>sma200_v if sma200_v else 'N/A'}")

# ── Score and Rank Components ──────────────────────────────────────────────
print("\n" + "="*72)
print("NASDAQ 100 SWING CANDIDATE SCAN")
print("="*72)

scored = []
for ticker, data in results.items():
    score = 0
    flags = []
    risks = []

    # Trend alignment
    if data['above_sma20'] and data['above_sma50']:
        score += 3
        flags.append('Above SMA20+50')
    elif data['above_sma20']:
        score += 1
        flags.append('Above SMA20')
    elif data['above_sma50'] is False and data['above_sma20'] is False:
        score -= 2
        risks.append('Below SMA20+50')

    if data['above_sma200']:
        score += 1
        flags.append('Above SMA200')
    else:
        score -= 1

    # RSI
    rsi = data['rsi14']
    if rsi and 40 <= rsi <= 60:
        score += 2
        flags.append(f'RSI neutral ({rsi:.0f})')
    elif rsi and 60 < rsi <= 70:
        score += 1
        flags.append(f'RSI warm ({rsi:.0f})')
    elif rsi and rsi > 70:
        score -= 1
        risks.append(f'RSI OB ({rsi:.0f})')
    elif rsi and rsi < 40:
        score += 1
        flags.append(f'RSI OS ({rsi:.0f})')

    # Volume
    vr = data['vol_ratio']
    if vr and vr > 1.5:
        score += 2
        flags.append(f'Vol surge ({vr:.1f}x)')
    elif vr and vr > 1.2:
        score += 1
        flags.append(f'Vol above avg ({vr:.1f}x)')

    # Structure
    struct = data['structure']
    if 'BULL' in struct:
        score += 2
        flags.append(struct)
    elif 'BEAR' in struct:
        score -= 2
        risks.append('Bear structure')

    # 5-day momentum
    chg5 = data['last_5d_chg']
    if chg5 > 3:
        score -= 1
        risks.append(f'Overextended +5d ({chg5:.1f}%)')
    elif chg5 < -3:
        score += 1
        flags.append(f'Pullback ({chg5:.1f}%)')

    scored.append({
        'ticker': ticker,
        'close': data['close'],
        'chg_pct': data['chg_pct'],
        'last_5d_chg': chg5,
        'rsi14': rsi,
        'atr': data['atr'],
        'vol_ratio': vr,
        'structure': struct,
        'above_sma20': data['above_sma20'],
        'above_sma50': data['above_sma50'],
        'flags': flags,
        'risks': risks,
        'score': score,
    })

scored.sort(key=lambda x: x['score'], reverse=True)

print(f"\n{'Ticker':<8} {'Close':>8} {'5d%':>6} {'RSI':>5} {'ATR':>6} {'VolR':>5} {'Sc':>3}  Top Flags")
print("-"*75)
for item in scored[:25]:
    f_str = ' | '.join(item['flags'][:3])
    r_str = ', '.join(item['risks'][:2]) if item['risks'] else ''
    rsi_s = f"{item['rsi14']:.0f}" if item['rsi14'] else "N/A"
    atr_s = f"{item['atr']:.2f}" if item['atr'] else "N/A"
    vr_s = f"{item['vol_ratio']:.2f}" if item['vol_ratio'] else "N/A"
    print(f"{item['ticker']:<8} {item['close']:>8.2f} {item['last_5d_chg']:>+6.1f} {rsi_s:>5} {atr_s:>6} {vr_s:>5} {item['score']:>3}  {f_str}")
    if r_str:
        print(f"{'':8}{'':8}{'':6}{'':5}{'':6}{'':5}{'':3}  ⚠ {r_str}")

# Save full results
output = {
    'scan_time': datetime.now().isoformat(),
    'indices': {},
    'components': results,
    'scored': scored,
}
for ticker, df in indices_data.items():
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last
    output['indices'][ticker] = {
        'close': float(last['Close']),
        'chg_pct': float(((last['Close'] - prev['Close']) / prev['Close']) * 100),
        'sma20': float(last['sma20']) if not pd.isna(last['sma20']) else None,
        'sma50': float(last['sma50']) if not pd.isna(last['sma50']) else None,
        'sma200': float(last['sma200']) if not pd.isna(last['sma200']) else None,
        'rsi': float(last['rsi']) if not pd.isna(last['rsi']) else None,
        'atr': float(last['atr']) if not pd.isna(last['atr']) else None,
        'vol_ratio': float(last['vol_ratio']) if not pd.isna(last['vol_ratio']) else None,
        'structure': get_structure(df),
        'last_date': str(df.index[-1].date()),
    }

with open('/opt/data/handbook/swing_scan_results.json', 'w') as f:
    json.dump(output, f, indent=2, default=str)

print(f"\nFull results saved to swing_scan_results.json")
print(f"Scan completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
