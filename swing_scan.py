#!/usr/bin/env python3
"""
NASDAQ Swing Trade Scanner — August 7, 2026
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

TODAY_DATE = datetime(2026, 8, 7)

def fetch_data(ticker, period="1y", interval="1d"):
    try:
        t = yf.Ticker(ticker)
        df = t.history(period=period, interval=interval, auto_adjust=True)
        return df if len(df) > 100 else None
    except:
        return None

def compute_ta(df):
    close = df['Close']
    high = df['High']
    low = df['Low']
    volume = df['Volume']

    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()
    ma200 = close.rolling(200).mean()

    ema12 = close.ewm(12).mean()
    ema26 = close.ewm(26).mean()
    macd = ema12 - ema26
    signal = macd.ewm(9).mean()
    histogram = macd - signal

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    tr = pd.concat([high - low,
                    (high - close.shift(1)).abs(),
                    (low - close.shift(1)).abs()], axis=1).max(axis=1)
    atr14 = tr.rolling(14).mean()

    bb20 = close.rolling(20).std()
    bb_upper = ma20 + 2 * bb20
    bb_lower = ma20 - 2 * bb20

    vol20 = volume.rolling(20).mean()
    vol10 = volume.rolling(10).mean()

    low52 = close.rolling(252).min()
    high52 = close.rolling(252).max()
    swing_low = low.rolling(20).min().shift(1)
    swing_high = high.rolling(20).max().shift(1)

    return {
        'close': close, 'ma20': ma20, 'ma50': ma50, 'ma200': ma200,
        'macd': macd, 'signal': signal, 'histogram': histogram,
        'rsi': rsi, 'atr14': atr14,
        'bb_upper': bb_upper, 'bb_lower': bb_lower,
        'vol20': vol20, 'vol10': vol10, 'volume': volume,
        'low52': low52, 'high52': high52,
        'swing_high': swing_high, 'swing_low': swing_low,
    }

def regime_info(df, ta):
    close = ta['close']
    price = close.iloc[-1]
    ma200 = ta['ma200'].iloc[-1]
    ma200_20d_ago = ta['ma200'].iloc[-20] if len(ta['ma200']) >= 20 else ma200
    ma50 = ta['ma50'].iloc[-1]

    above_ma200 = price > ma200 if not np.isnan(ma200) else None
    above_ma50 = price > ma50 if not np.isnan(ma50) else None
    above_ma20 = price > ta['ma20'].iloc[-1]

    slope = (ma200 - ma200_20d_ago) / ma200_20d_ago if (not np.isnan(ma200) and not np.isnan(ma200_20d_ago) and ma200_20d_ago != 0) else 0

    ret5 = (close.iloc[-1] / close.iloc[-5] - 1) if len(close) >= 5 else 0
    ret20 = (close.iloc[-1] / close.iloc[-20] - 1) if len(close) >= 20 else 0

    rsi = ta['rsi'].iloc[-1]
    atr = ta['atr14'].iloc[-1]
    vol_today = ta['volume'].iloc[-1]
    vol10_avg = ta['vol10'].iloc[-1]

    if above_ma200 is None:
        regime = "TRANSITIONAL"
    elif above_ma200 and slope > 0:
        regime = "BULL"
    elif not above_ma200 and slope < 0:
        regime = "BEAR"
    else:
        regime = "TRANSITIONAL"

    return {
        'regime': regime, 'price': price, 'above_ma200': above_ma200,
        'above_ma50': above_ma50, 'above_ma20': above_ma20,
        'ma200': ma200, 'ma50': ma50, 'slope': slope,
        'rsi': rsi, 'atr': atr, 'atr_pct': atr/price,
        'ret5': ret5, 'ret20': ret20,
        'vol_ratio': vol_today / vol10_avg if vol10_avg > 0 else 0,
    }

def score_ticker(df, ta, ri, ticker):
    price = ri['price']
    regime = ri['regime']
    rsi = ri['rsi']
    atr = ri['atr']

    # Support / Resistance
    support = ta['swing_low'].iloc[-1]
    resistance = ta['swing_high'].iloc[-1]
    if np.isnan(support): support = ta['close'].rolling(20).min().iloc[-2]
    if np.isnan(resistance): resistance = ta['close'].rolling(20).max().iloc[-2]

    # Stop: below swing low or MA50, whichever is closer below entry
    stop_dist = min(abs(price - support), abs(price - ta['ma50'].iloc[-1]) * 0.5)
    stop_loss = price - stop_dist

    # Targets
    target1 = price + 2 * atr   # T1: 2x ATR
    target2 = resistance if resistance > price else price + 3 * atr  # T2

    rr = (target1 - price) / stop_dist if stop_dist > 0 else 0

    # ── Catalyst scoring ──────────────────────────────────────────────────────
    notes = []
    score = 0

    # Trend alignment
    if ri['above_ma200'] and regime == "BULL":
        score += 2
        notes.append("Aligned with bull regime — above 200-MA")
    elif ri['above_ma200'] is False and regime == "BEAR":
        score += 2
        notes.append("Bear regime short — below 200-MA")
    elif ri['above_ma200'] is None:
        score += 1
        notes.append("MA200 not confirmed — neutral alignment")

    # RSI zones
    if 40 <= rsi <= 60:
        score += 2
        notes.append("RSI neutral zone — room to run")
    elif rsi < 35:
        score += 3
        notes.append(f"RSI oversold ({rsi:.1f}) — bounce candidate")
    elif rsi > 75:
        score -= 1
        notes.append(f"RSI overbought ({rsi:.1f}) — caution on long")

    # MACD histogram flip
    h_now = ta['histogram'].iloc[-1]
    h_prev = ta['histogram'].iloc[-2]
    if h_prev < 0 and h_now > 0:
        score += 2
        notes.append("MACD bullish histogram cross")
    elif h_prev > 0 and h_now < 0:
        score += 1
        notes.append("MACD bearish histogram cross")

    # 52-week position
    pct_52 = (price - ta['low52'].iloc[-1]) / (ta['high52'].iloc[-1] - ta['low52'].iloc[-1]) if ta['high52'].iloc[-1] > ta['low52'].iloc[-1] else 0.5
    if pct_52 < 0.20:
        score += 1
        notes.append(f"Deep value: {pct_52*100:.0f}% of 52wk range — mean reversion setup")
    elif pct_52 > 0.85:
        score += 1
        notes.append(f"Near 52wk high: {pct_52*100:.0f}% of range — momentum continuation")

    # Volume surge
    if ri['vol_ratio'] > 1.5:
        score += 1
        notes.append(f"Volume surge ({ri['vol_ratio']:.1f}x10d avg)")

    # ATR % — sanity check (not too volatile for sizing)
    atr_pct = ri['atr_pct']
    if atr_pct > 0.08:
        score -= 1
        notes.append(f"High ATR ({atr_pct*100:.1f}% of price) — reduce size")

    # MA alignment
    if ri['above_ma20'] and ri['above_ma50']:
        score += 1
        notes.append("Above both MA20 and MA50 — healthy uptrend structure")

    return {
        'ticker': ticker,
        'regime': regime,
        'price': price,
        'above_ma200': ri['above_ma200'],
        'above_ma50': ri['above_ma50'],
        'above_ma20': ri['above_ma20'],
        'rsi': rsi,
        'rsi_zone': 'oversold' if rsi < 35 else ('overbought' if rsi > 70 else 'neutral'),
        'atr': atr,
        'atr_pct': atr_pct,
        'pct_52wk': pct_52,
        'support': support,
        'resistance': resistance,
        'stop_loss': stop_loss,
        'target1': target1,
        'target2': target2,
        'rr_ratio': rr,
        'score': score,
        'catalyst_notes': notes,
        'ret5': ri['ret5'],
        'ret20': ri['ret20'],
        'hist_now': h_now,
        'hist_prev': h_prev,
        'vol_ratio': ri['vol_ratio'],
    }

# ── MAIN ───────────────────────────────────────────────────────────────────────
print("=" * 72)
print(f"SWING TRADE SCAN  |  {TODAY_DATE.strftime('%A, %B %d, %Y')}  |  ~14:00 UTC / 10:00 AM ET")
print("=" * 72)

INDICES = ["QQQ", "SPY", "IWM"]
TICKERS = [
    "NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA",
    "AVGO", "AMD", "QCOM", "PANW", "MU", "LRCX", "KLAC",
    "SNPS", "CDNS", "ORLY", "ADI", "CRWD", "NXPI",
    "AMAT", "FAST", "CTAS", "HON", "PAYX", "MCHP",
    "ROP", "MRVL", "INTU", "ADSK",
]

# Fetch with 1y for MA200 validity
print("\n[1] Fetching index data (1y period for MA200)...")
index_data = {}
for idx in INDICES:
    df = fetch_data(idx, period="1y")
    if df is not None:
        ta = compute_ta(df)
        ri = regime_info(df, ta)
        index_data[idx] = {'df': df, 'ta': ta, 'ri': ri}
        ma200_status = f"{ri['ma200']:.2f}" if not np.isnan(ri['ma200']) else "NaN"
        print(f"  {idx:4s}  regime={ri['regime']:12s}  price={ri['price']:>8.2f}  "
              f"MA200={ma200_status:>8s}  RSI={ri['rsi']:>5.1f}  "
              f"20d_ret={ri['ret20']*100:>+5.1f}%  above_MA200={ri['above_ma200']}")
    else:
        print(f"  {idx}: FAILED")

market_regime = index_data.get('QQQ', {}).get('ri', {}).get('regime', 'TRANSITIONAL')
print(f"\n    --> MARKET REGIME (QQQ proxy): {market_regime}")

print("\n[2] Fetching component data...")
results = []
for t in TICKERS:
    df = fetch_data(t, period="1y")
    if df is None:
        print(f"  {t:6s}: insufficient data"); continue
    ta = compute_ta(df)
    ri = regime_info(df, ta)
    ri['market_regime'] = market_regime
    score = score_ticker(df, ta, ri, t)
    results.append(score)
    print(f"  {t:6s}  regime={score['regime']:12s}  RSI={score['rsi']:>5.1f}  "
          f"52wk%={score['pct_52wk']*100:>5.0f}  score={score['score']:>3d}  "
          f"R/R={score['rr_ratio']:.2f}  vol={score['vol_ratio']:.2f}")

print(f"\n    Tickers analyzed: {len(results)}")

# ── FILTER & RANK ─────────────────────────────────────────────────────────────
print("\n" + "=" * 72)
print("[3] FILTERING & RANKING — TOP SWING SETUPS")
print("=" * 72)

# Filter: R/R >= 1.5, not deeply overbought on long, valid regime
filtered = []
for r in results:
    if r['rr_ratio'] < 1.0:
        continue
    if r['rsi'] > 78 and market_regime != "BEAR":
        continue
    # Must have some alignment with market regime
    if market_regime == "BULL" and r['above_ma200'] is False and r['score'] < 3:
        continue
    filtered.append(r)

filtered.sort(key=lambda x: (x['score'], x['rr_ratio']), reverse=True)

for i, r in enumerate(filtered[:5]):
    print(f"\n  #{i+1}: {r['ticker']}  (score={r['score']}, R/R={r['rr_ratio']:.2f})")
    print(f"       Regime: {r['regime']} | Price: ${r['price']:.2f}")
    print(f"       RSI: {r['rsi']:.1f} ({r['rsi_zone']}) | ATR%: {r['atr_pct']*100:.1f}%")
    print(f"       52wk position: {r['pct_52wk']*100:.0f}% | 5d_ret: {r['ret5']*100:+.1f}%")
    print(f"       Support: ${r['support']:.2f} | Resistance: ${r['resistance']:.2f}")
    print(f"       Stop: ${r['stop_loss']:.2f} | T1: ${r['target1']:.2f} | T2: ${r['target2']:.2f}")
    print(f"       Histogram: prev={r['hist_prev']:.2f} → now={r['hist_now']:.2f}")
    print(f"       Catalysts: {'; '.join(r['catalyst_notes'])}")

top3 = filtered[:3]
if not top3:
    print("\n  [NOTE] No setups met full filter. Relaxing — showing top by score:")
    results.sort(key=lambda x: x['score'], reverse=True)
    top3 = results[:3]

# ── DATA EXPORT ───────────────────────────────────────────────────────────────
print("\n" + "=" * 72)
print("[4] FULL DATA EXPORT — TOP 3 SETUPS")
print("=" * 72)
for i, r in enumerate(top3):
    print(f"\n=== SETUP {i+1}: {r['ticker']} ===")
    for k, v in r.items():
        if k == 'catalyst_notes':
            print(f"  {k}: {v}")
        elif isinstance(v, float):
            print(f"  {k}: {v:.4f}" if abs(v) < 10 and k not in ['price','atr','support','resistance','stop_loss','target1','target2'] else f"  {k}: {v:.2f}")
        else:
            print(f"  {k}: {v}")

# Also print index summary
print("\n=== INDEX SUMMARY ===")
for idx, data in index_data.items():
    r = data['ri']
    print(f"  {idx}: regime={r['regime']}, price={r['price']:.2f}, MA200={r['ma200']:.2f}, "
          f"RSI={r['rsi']:.1f}, above_MA200={r['above_ma200']}, 20d_ret={r['ret20']*100:+.1f}%")
