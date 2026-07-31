#!/opt/hermes/.venv/bin/python3
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings, json, sys
warnings.filterwarnings('ignore')

print(f"=== START: {datetime.now().strftime('%H:%M:%S ET')} ===\n", flush=True)

# ── INDICES ─────────────────────────────────────────────────────────────────
indices = ['QQQ', 'SPY', 'IWM', 'VIX=X']
idx_hist = {}
for t in indices:
    try:
        h = yf.Ticker(t).history(period='6mo', interval='1d')
        idx_hist[t] = h
        c = h['Close'].iloc[-1] if not h.empty else None
        print(f"  {t}: n={len(h)}, last_close={c:.2f}" if c else f"  {t}: EMPTY", flush=True)
    except Exception as e:
        print(f"  {t}: ERROR {e}", flush=True)

print(flush=True)

# ── COMPONENTS ──────────────────────────────────────────────────────────────
comps = ['NVDA','AAPL','MSFT','GOOGL','AMZN','META','TSLA','AMD','AVGO',
         'CRM','ADBE','NFLX','QCOM','AMAT','MU','LRCX','KLAC','PANW','SNPS',
         'CRWD','ORCL','COST','TXN','BKNG','CMCSA','PYPL','INTU','MDLZ','ADP']

results = {}
for t in comps:
    try:
        tk = yf.Ticker(t)
        h = tk.history(period='6mo', interval='1d')
        info = tk.info
        if not h.empty:
            results[t] = {'hist': h, 'info': info}
            print(f"  {t}: n={len(h)}, close={h['Close'].iloc[-1]:.2f}", flush=True)
        else:
            print(f"  {t}: no history", flush=True)
    except Exception as e:
        print(f"  {t}: ERROR {str(e)[:50]}", flush=True)

print(f"\n=== FETCH COMPLETE: {datetime.now().strftime('%H:%M:%S ET')} ===", flush=True)

# ── ANALYSIS ─────────────────────────────────────────────────────────────────
def compute_ta(df, name):
    """Technical analysis on daily data."""
    close = df['Close']
    high = df['High']
    low = df['Low']
    vol = df['Volume']
    
    # Moving averages
    sma20 = close.rolling(20).mean()
    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()
    
    # EMA
    ema20 = close.ewm(20).mean()
    
    # RSI (14)
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    # MACD
    ema12 = close.ewm(12).mean()
    ema26 = close.ewm(26).mean()
    macd = ema12 - ema26
    signal = macd.ewm(9).mean()
    hist = macd - signal
    
    # ATR (14)
    tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    
    # Volume SMA
    vol_sma20 = vol.rolling(20).mean()
    
    # Recent range
    recent_high = high.rolling(20).max().iloc[-1]
    recent_low = low.rolling(20).min().iloc[-1]
    
    cur = close.iloc[-1]
    prev_close = close.iloc[-2] if len(close) > 1 else cur
    
    # Market structure
    above_20 = cur > sma20.iloc[-1]
    above_50 = cur > sma50.iloc[-1]
    above_200 = cur > sma200.iloc[-1] if not sma200.isna().all() else False
    trend_20 = sma20.iloc[-1] > sma20.iloc[-5] if len(sma20) >= 5 else False
    
    # 52w high / low
    high_52w = high.rolling(252).max().iloc[-1]
    low_52w = low.rolling(252).min().iloc[-1]
    
    # Momentum
    mom5 = (cur / close.iloc[-6] - 1) * 100 if len(close) >= 6 else 0
    mom20 = (cur / close.iloc[-21] - 1) * 100 if len(close) >= 21 else 0
    
    return {
        'close': cur, 'prev_close': prev_close,
        'sma20': sma20.iloc[-1], 'sma50': sma50.iloc[-1], 'sma200': sma200.iloc[-1],
        'ema20': ema20.iloc[-1],
        'rsi': rsi.iloc[-1],
        'macd': macd.iloc[-1], 'signal': signal.iloc[-1], 'hist': hist.iloc[-1],
        'atr': atr.iloc[-1],
        'vol_avg': vol_sma20.iloc[-1], 'vol_today': vol.iloc[-1],
        'above_20': above_20, 'above_50': above_50, 'above_200': above_200,
        'trend_20': trend_20,
        'high_52w': high_52w, 'low_52w': low_52w,
        'recent_high': recent_high, 'recent_low': recent_low,
        'mom5': mom5, 'mom20': mom20,
        'pct_52w_range': (cur - low_52w) / (high_52w - low_52w) * 100 if (high_52w - low_52w) > 0 else 50,
    }

# ── COMPUTE TA FOR ALL ──────────────────────────────────────────────────────
analysis = {}
for t, data in results.items():
    try:
        analysis[t] = compute_ta(data['hist'], t)
        info = data['info']
        analysis[t]['market_cap'] = info.get('marketCap', None)
        analysis[t]['pe_ratio'] = info.get('trailingPE', None)
        analysis[t]['fwd_pe'] = info.get('forwardPE', None)
        analysis[t]['eps'] = info.get('trailingEps', None)
        analysis[t]['recommendation'] = info.get('recommendationKey', 'N/A')
        analysis[t]['target_mean'] = info.get('targetMeanPrice', None)
        analysis[t]['analyst_count'] = info.get('numberOfAnalystOpinions', 0)
        analysis[t]['50_day_avg'] = info.get('fiftyDayAverage', None)
        analysis[t]['200_day_avg'] = info.get('twoHundredDayAverage', None)
        analysis[t]['beta'] = info.get('beta', None)
        analysis[t]['earnings_dates'] = info.get('earningsDates', [])
        analysis[t]['dividend_yield'] = info.get('dividendYield', 0) or 0
    except Exception as e:
        print(f"  TA ERROR {t}: {e}", flush=True)

# ── INDEX REGIME ANALYSIS ───────────────────────────────────────────────────
print("\n=== REGIME ANALYSIS ===", flush=True)
for t, h in idx_hist.items():
    if not h.empty:
        close = h['Close']
        sma200 = close.rolling(200).mean()
        cur = close.iloc[-1]
        sma200_val = sma200.iloc[-1]
        regime = "ABOVE_200SMA" if cur > sma200_val else "BELOW_200SMA"
        print(f"  {t}: ${cur:.2f} | SMA200=${sma200_val:.2f} | Regime={regime}", flush=True)
        # VIX specific
        if t == 'VIX=X':
            vix_val = cur
            vol_regime = "HIGH_VOL" if vix_val > 25 else ("MODERATE" if vix_val > 15 else "LOW_VOL")
            print(f"    VIX={vix_val:.2f} -> Vol Regime: {vol_regime}", flush=True)

# ── TOP SWING SCORE ─────────────────────────────────────────────────────────
print("\n=== SWING SCORING ===", flush=True)
scores = []
for t, a in analysis.items():
    score = 0
    reasons = []
    
    rsi = a.get('rsi', 50)
    mom5 = a.get('mom5', 0)
    mom20 = a.get('mom20', 0)
    close = a.get('close', 0)
    atr = a.get('atr', close * 0.02)
    pct_52w = a.get('pct_52w_range', 50)
    above_20 = a.get('above_20', False)
    above_50 = a.get('above_50', False)
    above_200 = a.get('above_200', False)
    hist_val = a.get('hist', 0)
    vol_today = a.get('vol_today', 0)
    vol_avg = a.get('vol_avg', 1)
    target_mean = a.get('target_mean', None)
    close_price = a.get('close', 0)
    
    # Bullish factors
    if above_20: score += 2; reasons.append("Above 20 SMA")
    if above_50: score += 2; reasons.append("Above 50 SMA")
    if above_200: score += 2; reasons.append("Above 200 SMA")
    if a.get('trend_20'): score += 1; reasons.append("20 SMA rising")
    
    # MACD bullish
    if hist_val > 0 and a.get('macd', 0) > 0: score += 2; reasons.append("MACD bullish")
    if a.get('macd', 0) > a.get('signal', 0): score += 1; reasons.append("MACD above signal")
    
    # RSI zone
    if 40 < rsi < 60: score += 1; reasons.append("RSI neutral-healthy")
    elif rsi < 35: score += 2; reasons.append("RSI oversold")
    elif rsi > 70: score -= 1; reasons.append("RSI overbought (penalty)")
    
    # Momentum
    if mom5 > 2: score += 1; reasons.append(f"+5d momentum {mom5:.1f}%")
    if mom20 > 5: score += 1; reasons.append(f"+20d momentum {mom20:.1f}%")
    elif mom20 < -5: score -= 1; reasons.append(f"-20d momentum {mom20:.1f}% (penalty)")
    
    # 52w position
    if pct_52w > 80: score += 1; reasons.append(f"Near 52w HIGH ({pct_52w:.0f}%)")
    elif pct_52w < 20: score += 1; reasons.append(f"Near 52w LOW ({pct_52w:.0f}%)")
    
    # Volume
    if vol_today > vol_avg * 1.3: score += 1; reasons.append("Above-avg volume")
    
    # Upside to analyst target
    if target_mean and close_price:
        upside = (target_mean / close_price - 1) * 100
        if upside > 15: score += 1; reasons.append(f"Analyst upside {upside:.0f}%")
    
    scores.append({
        'ticker': t, 'score': score, 'reasons': reasons,
        'close': close, 'rsi': rsi, 'mom5': mom5, 'mom20': mom20,
        'atr': atr, 'pct_52w': pct_52w,
        'above_20': above_20, 'above_50': above_50, 'above_200': above_200,
        'macd_hist': hist_val,
        'target_mean': target_mean,
        'recommendation': a.get('recommendation', 'N/A'),
        'beta': a.get('beta', None),
        'market_cap': a.get('market_cap', None),
        'pe_ratio': a.get('pe_ratio', None),
        'earnings_dates': a.get('earnings_dates', []),
        'vol_today': vol_today, 'vol_avg': vol_avg,
    })

scores_sorted = sorted(scores, key=lambda x: x['score'], reverse=True)

print("\nTOP 10 SWING CANDIDATES (by composite score):", flush=True)
for i, s in enumerate(scores_sorted[:10]):
    print(f"  {i+1}. {s['ticker']:6s} | Score={s['score']:3d} | RSI={s['rsi']:.1f} | "
          f"Mom5={s['mom5']:+.1f}% | Mom20={s['mom20']:+.1f}% | "
          f"52w%={s['pct_52w']:.0f}% | Close=${s['close']:.2f} | "
          f"ATR=${s['atr']:.2f}", flush=True)
    print(f"       Reasons: {'; '.join(s['reasons'])}", flush=True)

# ── DETAILED TOP 3 ──────────────────────────────────────────────────────────
print("\n=== TOP 3 DEEP DIVE ===", flush=True)
for i, s in enumerate(scores_sorted[:3]):
    t = s['ticker']
    a = analysis[t]
    h = results[t]['hist']
    close = h['Close']
    vol = h['Volume']
    high = h['High']
    low = h['Low']
    
    # Recent 5-day high/low
    h5d = high.iloc[-5:].max()
    l5d = low.iloc[-5:].max()
    l5d_low = low.iloc[-5:].min()
    
    # ATR %
    atr_pct = (a['atr'] / close.iloc[-1]) * 100
    
    # Gap analysis
    prev_close = close.iloc[-2] if len(close) > 1 else close.iloc[-1]
    gap = (close.iloc[-1] / prev_close - 1) * 100
    
    print(f"\n  {i+1}. {t}", flush=True)
    print(f"     Price: ${close.iloc[-1]:.2f} | Gap: {gap:+.2f}%", flush=True)
    print(f"     ATR: ${a['atr']:.2f} ({atr_pct:.1f}%) | 5D Range: ${l5d_low:.2f} - ${h5d:.2f}", flush=True)
    print(f"     RSI(14): {a['rsi']:.1f} | MACD Hist: {a['hist']:.4f}", flush=True)
    print(f"     SMA20: ${a['sma20']:.2f} | SMA50: ${a['sma50']:.2f} | SMA200: ${a['sma200']:.2f}", flush=True)
    print(f"     Above 20/50/200: {s['above_20']}/{s['above_50']}/{s['above_200']}", flush=True)
    print(f"     Beta: {s['beta']} | Market Cap: {s['market_cap']}", flush=True)
    print(f"     Analyst Target: ${s['target_mean']:.2f}" if s['target_mean'] else "     Analyst Target: N/A", flush=True)
    print(f"     Recommendation: {s['recommendation']}", flush=True)
    print(f"     Earnings Dates: {s['earnings_dates']}", flush=True)
    print(f"     Score={s['score']}: {'; '.join(s['reasons'])}", flush=True)

# ── SAVE RESULTS ────────────────────────────────────────────────────────────
import json
output = {
    'timestamp': datetime.now().isoformat(),
    'regime': {t: {'close': float(h['Close'].iloc[-1]), 'len': len(h)} 
               for t, h in idx_hist.items() if not h.empty},
    'scores': [{'ticker': s['ticker'], 'score': s['score'], 
                'rsi': round(s['rsi'],1), 'mom5': round(s['mom5'],1),
                'mom20': round(s['mom20'],1), 'close': round(s['close'],2),
                'atr': round(s['atr'],2), 'reasons': s['reasons']}
               for s in scores_sorted[:10]]
}
with open('/opt/data/handbook/swing_scan_results.json', 'w') as f:
    json.dump(output, f, indent=2, default=str)

print("\n=== ALL DONE ===", flush=True)
