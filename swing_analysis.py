#!/usr/bin/env python3
"""Quantitative Swing Trading Analysis Engine"""
import pickle
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# Load data
with open('/opt/data/handbook/market_data.pkl', 'rb') as f:
    data = pickle.load(f)

print("=" * 80)
print("QUANTITATIVE SWING TRADING ADVISORY — NASDAQ SCAN")
print(f"Report Generated: {datetime.now().strftime('%Y-%m-%d %H:%M ET')}")
print("Data as of: 2026-08-03 (Prior trading day close)")
print("=" * 80)

# ── Helper Functions ─────────────────────────────────────────────────────────

def sma(series, period):
    return series.rolling(period).mean()

def ema(series, period):
    return series.ewm(span=period).mean()

def atr(df, period=14):
    high = df['High']
    low = df['Low']
    close = df['Close']
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(14).mean()

def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period-1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period-1, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def macd_signal(series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def analyze_ticker(ticker, df):
    close = df['Close'].squeeze()
    high = df['High'].squeeze()
    low = df['Low'].squeeze()
    volume = df['Volume'].squeeze()

    close_20ema = ema(close, 20)
    close_50sma = sma(close, 50)
    close_200sma = sma(close, 200)
    rsi_val = rsi(close)
    macd_line, signal_line, hist = macd_signal(close)
    atr_val = atr(df).iloc[-1]

    last = close.iloc[-1]
    prev = close.iloc[-2]
    prev2 = close.iloc[-3]
    prev4 = close.iloc[-5]
    prev20 = close.iloc[-21] if len(close) >= 21 else close.iloc[0]
    prev10 = close.iloc[-11] if len(close) >= 11 else close.iloc[0]

    # 20-day range position
    low20 = close.iloc[-20:].min()
    high20 = close.iloc[-20:].max()
    range_pos = (last - low20) / (high20 - low20) if high20 != low20 else 0.5

    # 50-day range position
    low50 = close.iloc[-50:].min() if len(close) >= 50 else close.min()
    high50 = close.iloc[-50:].max() if len(close) >= 50 else close.max()
    range_pos50 = (last - low50) / (high50 - low50) if high50 != low50 else 0.5

    # Momentum: 10-day return
    ret10 = (last - prev10) / prev10 * 100

    # Trend classification
    above_20ema = last > close_20ema.iloc[-1]
    above_50sma = last > close_50sma.iloc[-1]
    above_200sma = last > close_200sma.iloc[-1] if not pd.isna(close_200sma.iloc[-1]) else True
    ema20_above_50 = close_20ema.iloc[-1] > close_50sma.iloc[-1] if not pd.isna(close_50sma.iloc[-1]) else True

    # Volume
    avg_vol = volume.iloc[-20:].mean()
    vol_ratio = volume.iloc[-1] / avg_vol if avg_vol > 0 else 1

    # RSI
    rsi_curr = rsi_val.iloc[-1]

    # MACD
    macd_curr = macd_line.iloc[-1]
    signal_curr = signal_line.iloc[-1]
    hist_curr = hist.iloc[-1]
    hist_prev = hist.iloc[-2]
    macd_cross_up = hist_curr > 0 and hist_prev <= 0
    macd_bullish = macd_curr > signal_curr and macd_curr > 0

    # Recent swing
    swing_high_20 = high.iloc[-20:].max()
    swing_low_20 = low.iloc[-20:].min()

    # 5-day momentum
    mom5 = (last - prev5) / prev5 * 100 if len(close) >= 6 else 0
    prev5 = close.iloc[-6] if len(close) >= 6 else close.iloc[0]

    # ATR-based volatility
    pct_atr = atr_val / last * 100

    # Regime
    if above_200sma and close_20ema.iloc[-1] > close_50sma.iloc[-1] if not pd.isna(close_50sma.iloc[-1]) else True:
        regime = "BULL"
    elif not above_200sma and close_20ema.iloc[-1] < close_50sma.iloc[-1] if not pd.isna(close_50sma.iloc[-1]) else False:
        regime = "BEAR"
    else:
        regime = "TRANSITIONAL"

    return {
        'ticker': ticker,
        'close': last,
        'prev_close': prev,
        'change_pct': (last - prev) / prev * 100,
        'rsi': rsi_curr,
        'macd': macd_curr,
        'macd_signal': signal_curr,
        'macd_hist': hist_curr,
        'macd_cross_up': macd_cross_up,
        'macd_bullish': macd_bullish,
        'above_20ema': above_20ema,
        'above_50sma': above_50sma,
        'above_200sma': above_200sma,
        'ema20_above_50': ema_above_50,
        'atr': atr_val,
        'pct_atr': pct_atr,
        'vol_ratio': vol_ratio,
        'range_pos20': range_pos,
        'range_pos50': range_pos50,
        'ret10': ret10,
        'swing_high_20': swing_high_20,
        'swing_low_20': swing_low_20,
        'close_20ema': close_20ema.iloc[-1],
        'close_50sma': close_50sma.iloc[-1],
        'close_200sma': close_200sma.iloc[-1],
        'regime': regime,
        'close_20ema': close_20ema.iloc[-1],
    }

def ema_above_50_func(df):
    close = df['Close'].squeeze()
    ema20 = ema(close, 20)
    sma50 = sma(close, 50)
    return ema20.iloc[-1] > sma50.iloc[-1] if not pd.isna(sma50.iloc[-1]) else True

# ── Stage 1: Macro Market Regime ────────────────────────────────────────────
print("\n" + "=" * 80)
print("STAGE 1: MACRO MARKET REGIME ANALYSIS")
print("=" * 80)

# Indices analysis
index_tickers = ['QQQ', 'SPY', 'IWM']
indices_analysis = {}
for t in index_tickers:
    if t in data:
        df = data[t]
        close = df['Close'].squeeze()
        close_20ema = ema(close, 20)
        close_50sma = sma(close, 50)
        close_200sma = sma(close, 200)
        rsi_val = rsi(close).iloc[-1]
        last = close.iloc[-1]
        prev = close.iloc[-2]

        above_200 = last > close_200sma.iloc[-1] if not pd.isna(close_200sma.iloc[-1]) else True
        ema_above_50 = close_20ema.iloc[-1] > close_50sma.iloc[-1] if not pd.isna(close_50sma.iloc[-1]) else True
        ema_above_200 = close_20ema.iloc[-1] > close_200sma.iloc[-1] if not pd.isna(close_200sma.iloc[-1]) else True

        if above_200 and ema_above_50 and ema_above_200:
            regime = "BULL"
        elif not above_200 and not ema_above_50 and not ema_above_200:
            regime = "BEAR"
        else:
            regime = "TRANSITIONAL"

        # VIX proxy
        vix = None
        if 'VIXY' in data:
            vix_close = data['VIXY']['Close'].squeeze()
            vix = vix_close.iloc[-1]
            vix_rsi = rsi(vix_close).iloc[-1]

        indices_analysis[t] = {
            'close': last,
            'prev_close': prev,
            'change': (last - prev) / prev * 100,
            'rsi': rsi_val,
            'above_200sma': above_200,
            'ema_above_50': ema_above_50,
            'ema_above_200': ema_above_200,
            'close_200sma': close_200sma.iloc[-1],
            'regime': regime,
        }

        print(f"\n{t}: ${last:.2f} | Change: {indices_analysis[t]['change']:+.2f}%")
        print(f"  RSI(14): {rsi_val:.1f} | Regime: {regime}")
        print(f"  Above 200 SMA: {above_200} | EMA20 > SMA50: {ema_above_50} | EMA20 > SMA200: {ema_above_200}")
        print(f"  200 SMA: ${close_200sma.iloc[-1]:.2f}")

        if t == 'QQQ':
            # ATR for QQQ
            qqq_atr = atr(data['QQQ']).iloc[-1]
            qqq_pct_atr = qqq_atr / last * 100
            print(f"  ATR(14): ${qqq_atr:.2f} ({qqq_pct_atr:.2f}% of price)")
            # 5-day trend
            close_5d_ago = close.iloc[-6]
            ret5 = (last - close_5d_ago) / close_5d_ago * 100
            print(f"  5-Day Return: {ret5:+.2f}%")
            # 20-day range
            low20 = close.iloc[-20:].min()
            high20 = close.iloc[-20:].max()
            print(f"  20-Day Range: ${low20:.2f} – ${high20:.2f}")

        if vix is not None and t == 'SPY':
            print(f"  VIX Proxy (VIXY): ${vix:.2f} | RSI: {vix_rsi:.1f}")

# Overall market regime
qqq_regime = indices_analysis['QQQ']['regime']
spy_regime = indices_analysis['SPY']['regime']
iwm_regime = indices_analysis['IWM']['regime']

overall_regime = qqq_regime
if qqq_regime == spy_regime == iwm_regime:
    overall_regime = qqq_regime
elif qqq_regime == 'BULL' and spy_regime == 'BULL':
    overall_regime = 'BULL'
elif qqq_regime == 'BEAR' and spy_regime == 'BEAR':
    overall_regime = 'BEAR'
else:
    overall_regime = 'TRANSITIONAL'

print(f"\n>>> OVERALL MARKET REGIME: {overall_regime}")
print(f"    QQQ: {qqq_regime} | SPY: {spy_regime} | IWM: {iwm_regime}")

# ── Stage 2: Individual Stock Scan ────────────────────────────────────────────
print("\n" + "=" * 80)
print("STAGE 2: INDIVIDUAL TICKER TECHNICAL SCAN")
print("=" * 80)

stock_tickers = ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'TSLA', 'AMD', 'INTC', 'NFLX', 'COIN', 'SMCI', 'AVGO']

scan_results = []
for t in stock_tickers:
    if t not in data:
        continue
    df = data[t]
    close = df['Close'].squeeze()
    high = df['High'].squeeze()
    low = df['Low'].squeeze()
    volume = df['Volume'].squeeze()

    last = close.iloc[-1]
    prev = close.iloc[-2]

    # Moving averages
    ema20 = ema(close, 20)
    sma50 = sma(close, 50)
    sma200 = sma(close, 200)
    ema20_val = ema20.iloc[-1]
    sma50_val = sma50.iloc[-1]
    sma200_val = sma200.iloc[-1]

    # Indicators
    rsi_val = rsi(close).iloc[-1]
    macd_line, signal_line, hist = macd_signal(close)
    macd_curr = macd_line.iloc[-1]
    signal_curr = signal_line.iloc[-1]
    hist_curr = hist.iloc[-1]
    hist_prev = hist.iloc[-2]
    atr_val = atr(df).iloc[-1]
    pct_atr = atr_val / last * 100

    # Volume
    avg_vol = volume.iloc[-20:].mean()
    vol_ratio = volume.iloc[-1] / avg_vol if avg_vol > 0 else 1

    # Trend flags
    above_20ema = last > ema20_val
    above_50sma = last > sma50_val if not pd.isna(sma50_val) else True
    above_200sma = last > sma200_val if not pd.isna(sma200_val) else True
    ema_above_50 = ema20_val > sma50_val if not pd.isna(sma50_val) else True
    ema_above_200 = ema20_val > sma200_val if not pd.isna(sma200_val) else True

    # Range position
    low20 = close.iloc[-20:].min()
    high20 = close.iloc[-20:].max()
    range_pos20 = (last - low20) / (high20 - low20) if high20 != low20 else 0.5
    low50 = close.iloc[-50:].min() if len(close) >= 50 else close.min()
    high50 = close.iloc[-50:].max() if len(close) >= 50 else close.max()
    range_pos50 = (last - low50) / (high50 - low50) if high50 != low50 else 0.5

    # Momentum
    ret10 = (last - close.iloc[-11]) / close.iloc[-11] * 100 if len(close) >= 11 else 0
    ret5 = (last - close.iloc[-6]) / close.iloc[-6] * 100 if len(close) >= 6 else 0
    ret20 = (last - close.iloc[-21]) / close.iloc[-21] * 100 if len(close) >= 21 else 0

    # MACD cross
    macd_cross_up = hist_curr > 0 and hist_prev <= 0
    macd_cross_down = hist_curr < 0 and hist_prev >= 0

    # RSI divergence check (simple: price making HH but RSI making LH = bearish div)
    # Recent 20-day high
    price_hh_20 = high.iloc[-20:].max()
    price_hh_idx = high.iloc[-20:].idxmax()

    # Regime
    if above_200sma and ema_above_50 and ema_above_200:
        regime = "BULL"
    elif not above_200sma and not ema_above_50 and not ema_above_200:
        regime = "BEAR"
    else:
        regime = "TRANSITIONAL"

    # Swing scores
    score = 0
    if above_20ema: score += 2
    if above_50sma: score += 2
    if above_200sma: score += 1
    if ema_above_50: score += 2
    if macd_cross_up: score += 3
    if macd_curr > signal_curr: score += 1
    if hist_curr > 0: score += 1
    if rsi_val > 50: score += 1
    if vol_ratio > 1.2: score += 1
    if range_pos20 > 0.7: score -= 1  # Slightly penalized if near 20d high
    if rsi_val > 70: score -= 1  # Overbought penalty

    result = {
        'ticker': t,
        'close': last,
        'prev_close': prev,
        'change': (last - prev) / prev * 100,
        'rsi': rsi_val,
        'macd': macd_curr,
        'macd_signal': signal_curr,
        'macd_hist': hist_curr,
        'macd_cross_up': macd_cross_up,
        'macd_cross_down': macd_cross_down,
        'above_20ema': above_20ema,
        'above_50sma': above_50sma,
        'above_200sma': above_200sma,
        'ema_above_50': ema_above_50,
        'ema_above_200': ema_above_200,
        'atr': atr_val,
        'pct_atr': pct_atr,
        'vol_ratio': vol_ratio,
        'range_pos20': range_pos20,
        'range_pos50': range_pos50,
        'ret5': ret5,
        'ret10': ret10,
        'ret20': ret20,
        'low20': low20,
        'high20': high20,
        'swing_high_20': high20,
        'swing_low_20': low20,
        'ema20': ema20_val,
        'sma50': sma50_val,
        'sma200': sma200_val,
        'regime': regime,
        'score': score,
    }
    scan_results.append(result)

    print(f"\n{t}: ${last:.2f} | {result['change']:+.2f}% | Score: {score}")
    print(f"  RSI: {rsi_val:.1f} | MACD Hist: {hist_curr:+.4f} | MACD X-Up: {macd_cross_up}")
    print(f"  EMA20: ${ema20_val:.2f} | SMA50: ${sma50_val:.2f} | SMA200: ${sma200_val:.2f}")
    print(f"  Above 20EMA: {above_20ema} | Above 50SMA: {above_50sma} | Above 200SMA: {above_200sma}")
    print(f"  ATR: ${atr_val:.2f} ({pct_atr:.1f}%) | Vol Ratio: {vol_ratio:.2f}x")
    print(f"  Range Pos (20d): {range_pos20:.0%} | Ret5: {ret5:+.1f}% | Ret20: {ret20:+.1f}%")
    print(f"  20D Low: ${low20:.2f} | 20D High: ${high20:.2f} | Regime: {regime}")

# Sort by score
scan_results.sort(key=lambda x: x['score'], reverse=True)

print("\n" + "=" * 80)
print("TICKER SCOREBOARD (sorted by composite score)")
print("=" * 80)
for r in scan_results:
    print(f"  {r['ticker']:6s} | Score: {r['score']:3d} | RSI: {r['rsi']:5.1f} | "
          f"MACD Hist: {r['macd_hist']:+.4f} | Range20d: {r['range_pos20']:.0%} | "
          f"Ret5: {r['ret5']:+.1f}% | Regime: {r['regime']}")

# ── Stage 3: Top Setups Selection ───────────────────────────────────────────
print("\n" + "=" * 80)
print("STAGE 3: TOP SWING TRADE SETUPS — RISK/REWARD ANALYSIS")
print("=" * 80)

top_setups = []
for r in scan_results[:5]:  # Top 5 by score
    t = r['ticker']
    df = data[t]
    close = df['Close'].squeeze()

    last = r['close']
    atr_val = r['atr']
    pct_atr = r['pct_atr']
    low20 = r['low20']
    high20 = r['high20']
    rsi_val = r['rsi']
    range_pos20 = r['range_pos20']

    # Calculate support/resistance
    # Support 1: Recent swing low or EMA20
    support1 = max(r['ema20'], r['swing_low_20'])
    # Support 2: 50 SMA or deeper
    support2 = r['sma50'] if not pd.isna(r['sma50']) else support1 * 0.95

    # Resistance
    resistance1 = r['swing_high_20']
    resistance2 = r['sma200'] if not pd.isna(r['sma200']) and r['sma200'] > r['swing_high_20'] else r['swing_high_20'] * 1.03

    # Stop loss: Below swing low or EMA20, whichever is deeper
    stop = min(support1 * 0.995, r['swing_low_20'] * 0.995)
    risk_pct = (last - stop) / last * 100

    # Targets
    # T1: 2:1 R:R on the ATR, or the 20-day high
    t1_candidates = [
        last + atr_val * 2,
        resistance1,
    ]
    t1 = min([x for x in t1_candidates if x > last])
    reward_pct_t1 = (t1 - last) / last * 100
    rr_t1 = reward_pct_t1 / risk_pct if risk_pct > 0 else 0

    # T2: 3:1 R:R
    t2_candidates = [
        last + atr_val * 3,
        resistance2,
    ]
    t2 = min([x for x in t2_candidates if x > last])
    reward_pct_t2 = (t2 - last) / last * 100
    rr_t2 = reward_pct_t2 / risk_pct if risk_pct > 0 else 0

    # If shorting (RSI > 70 or bearish setup)
    if r['rsi'] > 70 or r['macd_cross_down']:
        # Bearish: target below swing low
        t1_bear = max(support1 * 0.98, low20)
        t2_bear = support2
        rr_bear = (last - t1_bear) / risk_pct if risk_pct > 0 else 0
    else:
        t1_bear = None
        t2_bear = None
        rr_bear = None

    setup = {
        **r,
        'support1': support1,
        'support2': support2,
        'resistance1': resistance1,
        'resistance2': resistance2,
        'stop_loss': stop,
        'risk_pct': risk_pct,
        't1': t1,
        'rr_t1': rr_t1,
        't2': t2,
        'rr_t2': rr_t2,
    }
    top_setups.append(setup)

    print(f"\n{'─' * 60}")
    print(f"  {r['ticker']} | Score: {r['score']} | Regime: {r['regime']}")
    print(f"  Price: ${last:.2f} | ATR: ${atr_val:.2f} ({pct_atr:.1f}%)")
    print(f"  Support 1 (EMA20/SwLow): ${support1:.2f} | Support 2 (SMA50): ${support2:.2f}")
    print(f"  Resistance 1 (SwHigh): ${resistance1:.2f} | Resistance 2: ${resistance2:.2f}")
    print(f"  Stop Loss: ${stop:.2f} | Risk: {risk_pct:.2f}%")
    print(f"  T1: ${t1:.2f} | Reward: {reward_pct_t1:.2f}% | R:R = {rr_t1:.1f}:1")
    print(f"  T2: ${t2:.2f} | Reward: {reward_pct_t2:.2f}% | R:R = {rr_t2:.1f}:1")
    print(f"  RSI: {rsi_val:.1f} | MACD Hist: {r['macd_hist']:+.4f} | Range Pos: {range_pos20:.0%}")

print("\n" + "=" * 80)
print("STAGE 4: FINAL TACTICAL ADVISORY")
print("=" * 80)

# Filter for actionable setups: RR >= 2:1, RSI not extreme
actionable = [s for s in top_setups if s['rr_t1'] >= 2.0 and 30 < s['rsi'] < 80]
actionable.sort(key=lambda x: (x['score'], x['rr_t1']), reverse=True)

for i, s in enumerate(actionable[:3], 1):
    print(f"\n{'═' * 60}")
    print(f"  TRADE #{i}: {s['ticker']}")
    print(f"{'═' * 60}")
    print(f"  DIRECTION: {'LONG' if s['change'] > -2 else 'WATCH'}")
    print(f"  Entry Zone: ${s['close']:.2f} ± ${s['atr']:.2f} (today's range)")
    print(f"  Stop Loss: ${s['stop_loss']:.2f} ({s['risk_pct']:.1f}% risk)")
    print(f"  T1: ${s['t1']:.2f} ({s['rr_t1']:.1f}:1 R:R)")
    print(f"  T2: ${s['t2']:.2f} ({s['rr_t2']:.1f}:1 R:R)")
    print(f"  Key Catalyst: {'MACD bullish cross' if s['macd_cross_up'] else 'Strong trend + momentum'}")
    print(f"  Regime Alignment: {s['regime']} (Market: {overall_regime})")
    print(f"  RSI: {s['rsi']:.1f} | ATR: ${s['atr']:.2f} | Position Size: 2-3% risk per trade")

print(f"\n{'=' * 80}")
print(f"MARKET CONTEXT NOTES:")
print(f"  - QQQ Regime: {overall_regime}")
print(f"  - QQQ RSI: {indices_analysis['QQQ']['rsi']:.1f}")
print(f"  - Data Date: 2026-08-03 (prior close)")
print(f"  - WARNING: Trading during NASDAQ hours — use limit orders, not market orders")
print(f"{'=' * 80}")
