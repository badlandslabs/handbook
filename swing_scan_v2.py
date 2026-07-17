#!/usr/bin/env python3
"""
NASDAQ Swing Trade Scanner — Real-time Multi-Dimensional Analysis
Fetches live market data and outputs actionable swing trade advisories.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# ── Config ────────────────────────────────────────────────────────────────────
TICKERS = {
    'indices': ['QQQ', 'SPY', 'IWM', 'VIX'],
    'nasdaq100': [
        'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'TSLA', 'AMD', 'AVGO',
        'COST', 'NFLX', 'ADBE', 'CRM', 'ORCL', 'QCOM', 'TXN', 'INTC', 'AMAT',
        'MU', 'LRCX', 'KLAC', 'PANW', 'SNPS', 'CDNS', 'MRVL', 'FTNT', 'HON',
        'INTU', 'ADP', 'GILD', 'REGN', 'BIIB', 'MDLZ', 'KDP', 'NXPI', 'ADI',
        'ON', 'FSLR', 'CTAS', 'PAYX', 'CPRT', 'ROST', 'SBUX', 'KHC', 'MELI',
        'DDOG', 'SNOW', 'NET', 'CRWD', 'ZS', 'WDAY', 'TEAM', 'OKTA', 'DOCU',
        'MRNA', 'EXC', 'AMT', 'PLD', 'EQIX', 'SPGI', 'CME', 'ICE'
    ]
}
TODAY = datetime.utcnow()
DATE_STR = TODAY.strftime('%Y-%m-%d %H:%M UTC')
print(f"{'='*80}")
print(f"  NASDAQ SWING TRADE SCANNER  |  {DATE_STR}")
print(f"{'='*80}\n")

# ── Helper: Fetch data with fallbacks ─────────────────────────────────────────
def fetch(ticker, period='3mo', interval='1d', attempts=2):
    for _ in range(attempts):
        try:
            t = yf.Ticker(ticker)
            df = t.history(period=period, interval=interval, auto_adjust=True)
            if df is not None and len(df) > 5:
                return df
        except Exception:
            pass
    return pd.DataFrame()

def fetch_intraday(ticker, period='5d', interval='60m', attempts=2):
    for _ in range(attempts):
        try:
            t = yf.Ticker(ticker)
            df = t.history(period=period, interval=interval, auto_adjust=True)
            if df is not None and len(df) > 10:
                return df
        except Exception:
            pass
    return pd.DataFrame()

# ── TA Engine ─────────────────────────────────────────────────────────────────
def compute_ta(df):
    """Compute technical indicators on OHLCV data."""
    if df.empty or len(df) < 50:
        return {}
    close = df['Close']
    high = df['High']
    low = df['Low']
    volume = df['Volume']

    # Moving averages
    ma5  = close.rolling(5).mean()
    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()
    ma200= close.rolling(200).mean()
    ema20= close.ewm(20).mean()

    # RSI(14)
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/14, min_periods=14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    # MACD (12,26,9)
    ema12 = close.ewm(12).mean()
    ema26 = close.ewm(26).mean()
    macd = ema12 - ema26
    signal = macd.ewm(9).mean()
    macd_hist = macd - signal

    # ATR(14)
    tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.ewm(14).mean()

    # ATR% (current price / ATR)
    last = close.iloc[-1]
    atr_pct = (atr.iloc[-1] / last) * 100 if last > 0 else 0

    # Volume analysis
    vol_20 = volume.rolling(20).mean()
    vol_ratio = volume.iloc[-1] / vol_20.iloc[-1] if vol_20.iloc[-1] > 0 else 1

    # Momentum (20-day % change)
    mom20 = (close.iloc[-1] / close.iloc[-20] - 1) * 100 if len(close) >= 20 else 0

    # 52w high / low
    high52 = high.rolling(252).max().iloc[-1]
    low52  = low.rolling(252).min().iloc[-1]

    # Position relative to MAs
    above_20 = last > ma20.iloc[-1]
    above_50 = last > ma50.iloc[-1]
    above_200= last > ma200.iloc[-1]

    # Trend direction (20 vs 50 MA slope)
    slope20 = (ma20.iloc[-1] - ma20.iloc[-5]) / ma20.iloc[-5] * 100 if len(ma20) >= 5 else 0
    slope50 = (ma50.iloc[-1] - ma50.iloc[-10]) / ma50.iloc[-10] * 100 if len(ma50) >= 10 else 0

    # RSI value
    rsi_val = rsi.iloc[-1]

    # MACD signal
    macd_bullish = macd_hist.iloc[-1] > 0 and macd_hist.iloc[-2] <= 0
    macd_bearish = macd_hist.iloc[-1] < 0 and macd_hist.iloc[-2] >= 0

    return {
        'last': last,
        'atr': atr.iloc[-1],
        'atr_pct': atr_pct,
        'rsi': rsi_val,
        'macd': macd.iloc[-1],
        'macd_signal': signal.iloc[-1],
        'macd_hist': macd_hist.iloc[-1],
        'macd_bullish_cross': macd_bullish,
        'macd_bearish_cross': macd_bearish,
        'ma5': ma5.iloc[-1],
        'ma20': ma20.iloc[-1],
        'ma50': ma50.iloc[-1],
        'ma200': ma200.iloc[-1],
        'ema20': ema20.iloc[-1],
        'above_20': above_20,
        'above_50': above_50,
        'above_200': above_200,
        'mom20': mom20,
        'slope20': slope20,
        'slope50': slope50,
        'vol_ratio': vol_ratio,
        'vol_20': vol_20.iloc[-1],
        'high52': high52,
        'low52': low52,
        'dist_high52': (last / high52 - 1) * 100,
        'dist_low52': (last / low52 - 1) * 100,
    }

def score_setup(ta, name=''):
    """Score a ticker 0-100 on swing trade setup quality."""
    if not ta:
        return -999, {}
    s = 0
    reasons_bull = []
    reasons_bear = []

    # Trend (max 25 pts)
    if ta['above_200']:   s += 10
    if ta['above_50']:    s += 8
    if ta['above_20']:    s += 7
    if ta['slope20'] > 0: s += 5
    elif ta['slope20'] < -3: s -= 5

    # Momentum (max 25 pts)
    rsi = ta['rsi']
    if 40 <= rsi <= 60:   s += 10  # neutral zone — room to run
    elif 30 <= rsi < 40:  s += 15  # oversold bounce potential
    elif 60 < rsi <= 70:  s += 8   # healthy momentum
    elif rsi > 70:         s -= 5   # overbought — risk
    elif rsi < 30:         s -= 10  # strong downtrend

    if ta['mom20'] > 3:   s += 8
    elif ta['mom20'] < -5: s -= 8

    if ta['macd_bullish_cross']: s += 7
    elif ta['macd_bearish_cross']: s -= 7
    else:
        if ta['macd_hist'] > 0: s += 3

    # Volume (max 15 pts)
    if ta['vol_ratio'] > 1.5: s += 8
    elif ta['vol_ratio'] > 1.2: s += 4
    elif ta['vol_ratio'] < 0.6: s -= 4

    # Structure (max 20 pts)
    dist = ta['dist_high52']
    if dist < -15:   s += 12  # deep pullback → high upside runway
    elif dist < -8:  s += 8
    elif dist < -3:  s += 4
    elif dist > 90:  s -= 5   # near 52w high — less room

    # ATR% environment (max 15 pts)
    atr = ta['atr_pct']
    if 2.0 <= atr <= 4.0: s += 8   # ideal swing volatility
    elif 1.5 <= atr < 2.0: s += 5
    elif atr > 5.0: s += 6         # high volatility — bigger moves
    elif atr < 1.0: s -= 5         # too tight — chop

    # Build summary
    if ta['above_200'] and ta['above_50']:
        reasons_bull.append('Above key MAs (200+50)')
    if ta['macd_bullish_cross']:
        reasons_bull.append('MACD bullish cross')
    if ta['rsi'] < 40:
        reasons_bull.append(f'Oversold RSI={rsi:.1f} — bounce setup')
    elif 40 <= ta['rsi'] <= 60:
        reasons_bull.append(f'RSI={rsi:.1f} — neutral room to run')
    if ta['vol_ratio'] > 1.5:
        reasons_bull.append(f'Surge volume  {ta["vol_ratio"]:.1f}x avg')
    if ta['dist_high52'] < -10:
        reasons_bull.append(f'Deep pullback {ta["dist_high52"]:.1f}% from 52w high')
    if ta['slope20'] > 1:
        reasons_bull.append('Rising 20d slope')

    if ta['rsi'] > 70:
        reasons_bear.append(f'Overbought RSI={rsi:.1f}')
    if ta['macd_bearish_cross']:
        reasons_bear.append('MACD bearish cross')
    if not ta['above_200']:
        reasons_bear.append('Below 200 SMA — bear bias')
    if ta['mom20'] < -5:
        reasons_bear.append(f'Strong downtrend mom20={ta["mom20"]:.1f}%')

    return s, {'bull': reasons_bull, 'bear': reasons_bear}

# ── STAGE 1: Fetch all data ───────────────────────────────────────────────────
print("Fetching index data...")
idx_data = {}
for sym in TICKERS['indices']:
    df = fetch(sym)
    ta = compute_ta(df)
    idx_data[sym] = {'ta': ta, 'df': df}
    print(f"  {sym}: {'OK' if ta else 'FAILED'}")

print("\nFetching NASDAQ 100 component data...")
comp_data = {}
ok_count = 0
fail_count = 0
for sym in TICKERS['nasdaq100']:
    df = fetch(sym)
    ta = compute_ta(df)
    if ta:
        comp_data[sym] = {'ta': ta, 'df': df}
        ok_count += 1
    else:
        fail_count += 1
print(f"  Retrieved {ok_count} | Failed {fail_count}")

# ── STAGE 2: Score everything ─────────────────────────────────────────────────
print("\nScoring setups...")
results = []
for sym, data in comp_data.items():
    score, details = score_setup(data['ta'], sym)
    results.append({
        'symbol': sym,
        'score': score,
        'ta': data['ta'],
        'bull_case': details['bull'],
        'bear_case': details['bear'],
    })

results.sort(key=lambda x: x['score'], reverse=True)
top_long = [r for r in results if r['score'] > 0][:10]

# ── STAGE 3: Macro regime analysis ────────────────────────────────────────────
def regime_check(ta_dict):
    """Determine market regime from index data."""
    qqq = ta_dict.get('QQQ', {}).get('ta', {})
    spy = ta_dict.get('SPY', {}).get('ta', {})
    iwm = ta_dict.get('IWM', {}).get('ta', {})
    vix = ta_dict.get('VIX', {}).get('ta', {})

    if not all([qqq, spy, iwm, vix]):
        return 'UNKNOWN', {}

    vix_val = vix.get('last', 20)
    qqq_above_200 = qqq.get('above_200', False)
    qqq_above_50  = qqq.get('above_50', False)
    spy_above_200 = spy.get('above_200', False)
    spy_above_50  = spy.get('above_50', False)
    iwm_above_50  = iwm.get('above_50', False)
    iwm_mom       = iwm.get('mom20', 0)
    qqq_mom       = qqq.get('mom20', 0)
    qqq_rsi       = qqq.get('rsi', 50)
    vix_rsi       = vix.get('rsi', 50)

    # Count bullish signals
    bull_count = sum([qqq_above_200, qqq_above_50, spy_above_200, spy_above_50, iwm_above_50])

    if vix_val < 15 and bull_count >= 4 and qqq_mom > 0:
        regime = 'BULL'
    elif vix_val > 25 or (bull_count <= 2 and qqq_mom < -3):
        regime = 'BEAR'
    else:
        regime = 'TRANSITIONAL'

    return regime, {
        'qqq': qqq, 'spy': spy, 'iwm': iwm, 'vix': vix,
        'bull_count': bull_count
    }

regime, regime_ctx = regime_check(idx_data)

# ── STAGE 4: Generate detailed output ─────────────────────────────────────────
print(f"\n{'='*80}")
print(f"MARKET REGIME: {regime}")
print(f"{'='*80}\n")

# Index summary
print("── INDEX SNAPSHOT ──")
for sym in TICKERS['indices']:
    ta = idx_data.get(sym, {}).get('ta', {})
    if ta:
        vix_str = f"  VIX" if sym == 'VIX' else ""
        rsi_emoji = "🔥" if ta['rsi'] > 65 else "🟢" if ta['rsi'] > 50 else "🔴"
        print(f"  {sym:5s}: ${ta['last']:>10.2f}  RSI={ta['rsi']:5.1f}  ATR%={ta['atr_pct']:4.1f}%  "
              f"20d={ta['mom20']:>+6.1f}%  {rsi_emoji}")

# Top setups
print(f"\n{'='*80}")
print("TOP SWING TRADE SETUPS (sorted by score)")
print(f"{'='*80}\n")

for i, r in enumerate(top_long[:5], 1):
    ta = r['ta']
    print(f"#{i}  {r['symbol']:6s}  SCORE={r['score']:+.0f}")
    print(f"     Price: ${ta['last']:.2f}  |  ATR: ${ta['atr']:.2f} ({ta['atr_pct']:.1f}%)")
    print(f"     RSI: {ta['rsi']:.1f}  |  20d Mom: {ta['mom20']:.1f}%  |  Slope20: {ta['slope20']:.2f}%")
    print(f"     MAs: above_200={ta['above_200']}  above_50={ta['above_50']}  above_20={ta['above_20']}")
    print(f"     MACD hist: {ta['macd_hist']:.4f}  ({'BULL cross' if ta['macd_bullish_cross'] else 'no cross'})")
    print(f"     Vol ratio: {ta['vol_ratio']:.2f}x  |  52w range: {ta['dist_high52']:.1f}% from high")
    print(f"     🟢 Bull: {', '.join(r['bull_case']) if r['bull_case'] else 'N/A'}")
    print(f"     🔴 Bear: {', '.join(r['bear_case']) if r['bear_case'] else 'N/A'}")
    print()

# ── STAGE 5: Build full advisory ──────────────────────────────────────────────
print(f"\n{'='*80}")
print("FULL SWING TRADE ADVISORY")
print(f"{'='*80}\n")

# Select top 3
top3 = top_long[:3]

# Compute risk/reward for each
advisories = []
for r in top3:
    ta = r['ta']
    price = ta['last']
    atr = ta['atr']
    atr_pct = ta['atr_pct']

    # Stop loss: below recent support / -1.5 ATR
    stop_dist = atr * 1.5
    stop_loss = price - stop_dist
    risk_per_share = price - stop_loss

    # Targets based on structure
    # T1: 2:1 R/R — partial take
    t1_target = price + risk_per_share * 2.0
    # T2: 3:1 R/R — full target
    t2_target = price + risk_per_share * 3.0
    # T3: Near 52w high if close
    if ta['dist_high52'] > -20:
        t3_target = price * 1.08  # 8% if near high
    else:
        t3_target = ta['high52']

    rr_t1 = 2.0
    rr_t2 = 3.0

    # Entry type
    if ta['rsi'] < 40:
        entry_type = 'BUY LIMIT at current price (oversold bounce trigger)'
        entry_price = price
    elif ta['macd_bullish_cross']:
        entry_type = 'BUY STOP-LIMIT 1-2% above current price (confirm MACD cross)'
        entry_price = price * 1.015
    else:
        entry_type = 'BUY LIMIT 1-2% below current price (wait for pullback)'
        entry_price = price * 0.985

    advisories.append({
        'symbol': r['symbol'],
        'score': r['score'],
        'price': price,
        'entry_price': entry_price,
        'entry_type': entry_type,
        'stop_loss': stop_loss,
        'atr': atr,
        'atr_pct': atr_pct,
        't1_target': t1_target,
        't2_target': t2_target,
        't3_target': t3_target,
        'rr_t1': rr_t1,
        'rr_t2': rr_t2,
        'ta': ta,
        'bull': r['bull_case'],
        'bear': r['bear_case'],
    })

for adv in advisories:
    ta = adv['ta']
    print(f"{'='*60}")
    print(f"  ADVISORY: {adv['symbol']}  |  Score: {adv['score']:+.0f}  |  Regime: {regime}")
    print(f"{'='*60}")
    print(f"  Current Price : ${adv['price']:.2f}")
    print(f"  ATR           : ${adv['atr']:.2f} ({adv['atr_pct']:.1f}% of price)")
    print(f"  Entry         : {adv['entry_type']}")
    print(f"  Stop Loss     : ${adv['stop_loss']:.2f}  (risk ${adv['price'] - adv['stop_loss']:.2f} = {((adv['price'] - adv['stop_loss'])/adv['price'])*100:.1f}%)")
    print(f"  T1 (2:1)      : ${adv['t1_target']:.2f}  (+{((adv['t1_target']-adv['price'])/adv['price'])*100:.1f}%)")
    print(f"  T2 (3:1)      : ${adv['t2_target']:.2f}  (+{((adv['t2_target']-adv['price'])/adv['price'])*100:.1f}%)")
    print(f"  T3 (near ATH) : ${adv['t3_target']:.2f}  (+{((adv['t3_target']-adv['price'])/adv['price'])*100:.1f}%)")
    print(f"  ")
    print(f"  Catalysts     : {', '.join(adv['bull']) if adv['bull'] else 'See TA summary'}")
    print(f"  Bear risks    : {', '.join(adv['bear']) if adv['bear'] else 'Minimal'}")
    print()

# ── Position sizing guidance ──────────────────────────────────────────────────
print(f"{'='*60}")
print(f"  RISK MANAGEMENT & POSITION SIZING")
print(f"{'='*60}")
print(f"  Regime: {regime}")
if regime == 'BULL':
    print(f"  → Aggressive sizing OK: 3-5% risk per trade")
    print(f"  → Use momentum entries; trail stops in your favor")
elif regime == 'TRANSITIONAL':
    print(f"  → Moderate sizing: 1.5-2.5% risk per trade")
    print(f"  → Require 2+ confirmations before entry")
else:
    print(f"  → Defensive sizing: 1% risk per trade or avoid longs")

print(f"  ")
print(f"  Position sizing formula: Position Size = (Account * Risk%) / (Entry - Stop)")
print(f"  Example: $100k account, 2% risk, $5 stock risk = $100k * 0.02 / $5 = $4,000 = ~800 shares")
print(f"  ")
print(f"  Trailing stop: Activate after T1 hit — move SL to breakeven + 0.5% buffer")
print(f"  Time stop: Exit if no progress toward T1 within 10 trading days")
print(f"  ")

# ── Output summary table ──────────────────────────────────────────────────────
print(f"\n{'='*80}")
print("ADVISORY SUMMARY TABLE")
print(f"{'='*80}")
print(f"{'SYMBOL':8s} {'PRICE':>8s} {'ENTRY':>8s} {'STOP':>8s} {'T1':>8s} {'T2':>8s} {'R:R1':>5s} {'R:R2':>5s} {'SCORE':>5s}")
print(f"{'-'*80}")
for adv in advisories:
    print(f"{adv['symbol']:8s} ${adv['price']:>7.2f} ${adv['entry_price']:>7.2f} "
          f"${adv['stop_loss']:>7.2f} ${adv['t1_target']:>7.2f} ${adv['t2_target']:>7.2f} "
          f"1:{adv['rr_t1']:.0f}   1:{adv['rr_t2']:.0f}   {adv['score']:+.0f}")

print(f"\n{'='*80}")
print(f"  Scan completed: {DATE_STR}")
print(f"{'='*80}")

# Save advisory
with open('/opt/data/handbook/swing_advisory_live.txt', 'w') as f:
    f.write(f"{'='*80}\n")
    f.write(f"  NASDAQ SWING TRADE ADVISORY  |  {DATE_STR}\n")
    f.write(f"{'='*80}\n\n")
    f.write(f"MARKET REGIME: {regime}\n\n")
    for sym in TICKERS['indices']:
        ta = idx_data.get(sym, {}).get('ta', {})
        if ta:
            f.write(f"{sym}: ${ta['last']:.2f} | RSI={ta['rsi']:.1f} | ATR%={ta['atr_pct']:.1f}% | 20d={ta['mom20']:+.1f}%\n")
    f.write(f"\n{'='*80}\n")
    f.write("TOP ADVISORIES\n")
    f.write(f"{'='*80}\n")
    for i, adv in enumerate(advisories, 1):
        f.write(f"\n#{i} {adv['symbol']} | Score={adv['score']:+.0f} | Regime={regime}\n")
        f.write(f"   Entry: {adv['entry_type']}\n")
        f.write(f"   SL: ${adv['stop_loss']:.2f} | T1: ${adv['t1_target']:.2f} | T2: ${adv['t2_target']:.2f}\n")
        f.write(f"   R:R: 1:{adv['rr_t1']:.0f} / 1:{adv['rr_t2']:.0f}\n")
        f.write(f"   Bull: {', '.join(adv['bull'])}\n")
        f.write(f"   Bear: {', '.join(adv['bear'])}\n")

print("\nAdvisory saved to /opt/data/handbook/swing_advisory_live.txt")
