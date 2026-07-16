#!/opt/data/handbook/venv/bin/python3
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys

today = datetime.now().strftime('%Y-%m-%d')
start = (datetime.now() - timedelta(days=200)).strftime('%Y-%m-%d')

# Download in small batches with timeout handling
batch1 = ['AAPL', 'MSFT', 'NVDA']
batch2 = ['GOOGL', 'AMZN', 'META']
batch3 = ['TSLA', 'AVGO', 'ORCL']
batch4 = ['AMD', 'NFLX', 'CRM']
batch5 = ['ADBE', 'INTU', 'TXN']
batch6 = ['QCOM', 'AMAT', 'MU']
batch7 = ['LRCX', 'KLAC']

all_data = {}
for batch_idx, batch in enumerate([batch1, batch2, batch3, batch4, batch5, batch6, batch7]):
    print(f"Batch {batch_idx+1}/7: {batch}", flush=True)
    try:
        data = yf.download(batch, start=start, end=today, progress=False, auto_adjust=True, timeout=15)
        for t in batch:
            try:
                all_data[t] = {
                    'close': data['Close'][t].dropna(),
                    'high': data['High'][t].dropna(),
                    'low': data['Low'][t].dropna(),
                    'volume': data['Volume'][t].dropna(),
                }
                print(f"  {t}: {len(all_data[t]['close'])} rows", flush=True)
            except Exception as e:
                print(f"  {t}: FAILED - {e}", flush=True)
    except Exception as e:
        print(f"  Batch failed: {e}", flush=True)

print(f"\nTotal tickers fetched: {len(all_data)}")

# Now compute scores
def score_ticker(name, d):
    close_s = d['close']
    high_s = d['high']
    low_s = d['low']
    vol_s = d['volume']
    
    common = close_s.index.intersection(high_s.index).intersection(low_s.index).intersection(vol_s.index)
    close = close_s.loc[common]
    high = high_s.loc[common]
    low = low_s.loc[common]
    vol = vol_s.loc[common]
    
    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9).mean()
    macd_hist = macd - signal
    tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    atr14 = tr.rolling(14).mean()
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std
    swing_high = high.rolling(20).max().shift(1)
    swing_low = low.rolling(20).min().shift(1)
    vol_sma = vol.rolling(20).mean()
    vol_ratio = vol / vol_sma
    
    c = close.iloc[-1]
    pc = close.iloc[-2]
    rsi_v = rsi.iloc[-1]
    macd_h = macd_hist.iloc[-1]
    prev_macd_h = macd_hist.iloc[-2]
    atr = atr14.iloc[-1]
    vr = vol_ratio.iloc[-1]
    bbu = bb_upper.iloc[-1]
    bbl = bb_lower.iloc[-1]
    sh = swing_high.iloc[-1]
    sl = swing_low.iloc[-1]
    m20 = ma20.iloc[-1]
    m50 = ma50.iloc[-1]
    
    pct = ((c - pc) / pc) * 100
    score = 0
    sigs = []
    if c > m20: score += 2; sigs.append('>MA20')
    if c > m50: score += 2; sigs.append('>MA50')
    if m20 > m50: score += 1; sigs.append('MA20>MA50')
    if 40 <= rsi_v <= 65: score += 2; sigs.append(f'RSI{rsi_v:.0f}')
    elif rsi_v < 30: score += 1; sigs.append(f'RSI_S{rsi_v:.0f}')
    elif rsi_v > 70: score -= 1; sigs.append(f'RSI_B{rsi_v:.0f}')
    if macd_h > 0 and prev_macd_h <= 0: score += 3; sigs.append('MACD_X')
    elif macd_h > 0 and macd_h > prev_macd_h: score += 1; sigs.append('MACD_exp')
    elif macd_h < 0: score -= 1; sigs.append('MACD_bear')
    if vr > 1.5: score += 2; sigs.append(f'Vol{vr:.1f}x')
    elif vr > 1.0: score += 1; sigs.append(f'Vol{vr:.1f}x')
    
    distR = ((sh - c) / c) * 100 if pd.notna(sh) else 0
    distS = ((c - sl) / c) * 100 if pd.notna(sl) else 0
    bb_pct = ((c - bbl) / (bbu - bbl)) * 100 if pd.notna(bbu) and bbu != bbl else 50
    atr_pct = (atr / c) * 100
    
    return {
        'ticker': name, 'close': c, 'pct_change': pct,
        'rsi': rsi_v, 'macd_hist': macd_h, 'atr14': atr, 'atr_pct': atr_pct,
        'vol_ratio': vr, 'bb_pct': bb_pct,
        'swing_high': sh, 'swing_low': sl,
        'dist_to_resistance': distR, 'dist_to_support': distS,
        'ma20': m20, 'ma50': m50,
        'score': score, 'signals': sigs,
    }

results = []
for name, d in all_data.items():
    try:
        r = score_ticker(name, d)
        results.append(r)
    except Exception as e:
        print(f"Scoring {name} failed: {e}")

results.sort(key=lambda x: x['score'], reverse=True)

for r in results:
    print(f"{r['ticker']}|{r['close']:.2f}|{r['rsi']:.1f}|{r['macd_hist']:.4f}|{r['atr_pct']:.2f}|{r['vol_ratio']:.2f}|{r['bb_pct']:.0f}|{r['dist_to_resistance']:.1f}|{r['dist_to_support']:.1f}|{r['score']}|{','.join(r['signals'])}")
