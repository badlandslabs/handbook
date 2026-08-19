#!/usr/bin/env python3
"""Swing Trade Analysis Engine — August 19, 2026"""
import json
import math
import statistics
from datetime import datetime

def load_ohlc(ticker):
    try:
        with open(f'/tmp/{ticker}_hist.json') as f:
            d = json.load(f)
        if not d.get('data'):
            return None
        rows = d['data']['tradesTable']['rows']
        data = []
        for r in rows:
            date = r['date']
            # parse date
            parts = date.split('/')
            m, day, yr = int(parts[0]), int(parts[1]), int(parts[2])
            close = float(r['close'].replace('$','').replace(',',''))
            high = float(r['high'].replace('$','').replace(',',''))
            low = float(r['low'].replace('$','').replace(',',''))
            vol = int(r['volume'].replace(',',''))
            data.append({'date': f"{yr}-{m:02d}-{day:02d}", 'close': close, 'high': high, 'low': low, 'volume': vol})
        data.reverse()  # oldest first
        return data
    except Exception as e:
        return None

def ema(data, key, period):
    k = 2/(period+1)
    ema_val = None
    result = []
    for row in data:
        if ema_val is None:
            # seed with SMA of first 'period' values
            if len(result) < period:
                result.append(row[key])
            else:
                ema_val = sum(result[-period:])/period
                ema_val = ema_val * (1-k) + row[key] * k
                result.append(ema_val)
        else:
            ema_val = ema_val * (1-k) + row[key] * k
            result.append(ema_val)
    return result

def sma(data, key, period):
    result = []
    vals = []
    for row in data:
        vals.append(row[key])
        if len(vals) >= period:
            result.append(sum(vals[-period:])/period)
        else:
            result.append(None)
    return result

def rsi(data, key, period=14):
    deltas = []
    for i, row in enumerate(data):
        if i == 0:
            deltas.append(0)
        else:
            deltas.append(row[key] - data[i-1][key])
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    result = []
    avg_gain = None
    avg_loss = None
    for i in range(len(deltas)):
        if i < period:
            result.append(None)
        elif i == period:
            avg_gain = sum(gains[1:period+1])/period
            avg_loss = sum(losses[1:period+1])/period
            if avg_loss == 0:
                result.append(100)
            else:
                rs = avg_gain / avg_loss
                result.append(100 - 100/(1+rs))
        else:
            avg_gain = (avg_gain * (period-1) + gains[i]) / period
            avg_loss = (avg_loss * (period-1) + losses[i]) / period
            if avg_loss == 0:
                result.append(100)
            else:
                rs = avg_gain / avg_loss
                result.append(100 - 100/(1+rs))
    return result

def macd_hist(data, key, fast=12, slow=26, signal=9):
    e_fast = ema(data, key, fast)
    e_slow = ema(data, key, slow)
    macd_line = [f - s if (f is not None and s is not None) else None
                 for f, s in zip(e_fast, e_slow)]
    # Signal line is EMA of MACD line
    macd_vals = [m for m in macd_line if m is not None]
    sig = []
    k = 2/(signal+1)
    sig_val = None
    idx = 0
    for m in macd_line:
        if m is None:
            sig.append(None)
        else:
            if sig_val is None:
                if len([x for x in macd_vals[:signal] if x is not None]) >= signal:
                    seed = sum([x for x in macd_vals[:signal] if x is not None])/signal
                    sig_val = seed
                    sig.append(sig_val)
                else:
                    sig.append(None)
            else:
                sig_val = sig_val * (1-k) + m * k
                sig.append(sig_val)
    hist = [m - s if (m is not None and s is not None) else None
            for m, s in zip(macd_line, sig)]
    return hist

def atr(data, period=14):
    tr_list = []
    for i, row in enumerate(data):
        if i == 0:
            tr_list.append(row['high'] - row['low'])
        else:
            hl = row['high'] - row['low']
            hc = abs(row['high'] - data[i-1]['close'])
            lc = abs(row['low'] - data[i-1]['close'])
            tr_list.append(max(hl, hc, lc))
    # EMA-style ATR
    k = 1/period
    atr_val = None
    result = []
    for tr in tr_list:
        if atr_val is None:
            result.append(tr)
            if len(result) >= period:
                atr_val = sum(result[-period:])/period
        else:
            atr_val = atr_val * (1-k) + tr * k
            result.append(atr_val)
    return result

def ta_metrics(ticker):
    data = load_ohlc(ticker)
    if not data or len(data) < 30:
        return None
    
    closes = [r['close'] for r in data]
    highs = [r['high'] for r in data]
    lows = [r['low'] for r in data]
    vols = [r['volume'] for r in data]
    
    current = closes[-1]
    prev_close = closes[-2]
    
    ema20 = ema(data, 'close', 20)
    ema50 = ema(data, 'close', 50)
    sma200_vals = sma(data, 'close', 200)
    rsi_vals = rsi(data, 'close', 14)
    macd_h = macd_hist(data, 'close')
    atr_vals = atr(data, 14)
    
    e20_val = ema20[-1] if ema20 else None
    e50_val = ema50[-1] if ema50 else None
    sma200_val = sma200_vals[-1] if sma200_vals else None
    rsi_val = rsi_vals[-1] if rsi_vals else None
    macd_h_val = macd_h[-1] if macd_h else None
    atr_val = atr_vals[-1] if atr_vals else None
    
    pct_1m = (current - closes[-21]) / closes[-21] * 100 if len(closes) > 21 else 0
    pct_1w = (current - closes[-6]) / closes[-6] * 100 if len(closes) > 5 else 0
    pct_day = (current - prev_close) / prev_close * 100
    
    vol_avg20 = sum(vols[-20:])/20 if len(vols) >= 20 else sum(vols)/len(vols)
    vol_ratio = vols[-1] / vol_avg20 if vol_avg20 > 0 else 1
    
    # 20-day swing high/low
    sw_high_20 = max(highs[-20:])
    sw_low_20 = min(lows[-20:])
    
    return {
        'ticker': ticker,
        'data': data,
        'close': current,
        'prev_close': prev_close,
        'pct_day': pct_day,
        'pct_1w': pct_1w,
        'pct_1m': pct_1m,
        'ema20': e20_val,
        'ema50': e50_val,
        'sma200': sma200_val,
        'rsi14': rsi_val,
        'macd_hist': macd_h_val,
        'atr14': atr_val,
        'atr_pct': (atr_val/current*100) if atr_val else 0,
        'vol_ratio': vol_ratio,
        'vol_avg20': vol_avg20,
        'sw_high_20': sw_high_20,
        'sw_low_20': sw_low_20,
        'highs': highs,
        'lows': lows,
        'closes': closes,
        'vols': vols,
        'above_ema20': current > e20_val if e20_val else False,
        'above_ema50': current > e50_val if e50_val else False,
        'above_200sma': current > sma200_val if sma200_val else True,
    }

# =====================================================================
# SCAN ALL TICKERS
# =====================================================================
indices = ['QQQ', 'SPY', 'IWM']
stocks = ['NVDA','AAPL','MSFT','AMZN','GOOGL','META','AVGO','TSLA','AMD','NFLX',
          'QCOM','TXN','INTC','AMAT','MU','LRCX','PANW','ORLY','CSX','ADSK',
          'CDNS','SNPS','NXPI','KLAC','INTU','CTAS','FAST','CTSH','ADP','PAYX',
          'BKNG','VRTX','REGN','MRVL','ON','HPQ','DELL','CRWD','ZS','FTNT',
          'TEAM','MDB','DDOG','NET','APP','SMCI','ARM','COIN','MAR','COST','PEP','SBUX']

print("=" * 80)
print(f"SWING TRADE SCAN — {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
print("=" * 80)

# VIX from FRED
vix_data = []
try:
    import urllib.request
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=VIXCLS&vintage_date=2026-08-19"
    with urllib.request.urlopen(url, timeout=10) as resp:
        lines = resp.read().decode().strip().split('\n')
        for line in lines[1:]:
            parts = line.split(',')
            if len(parts) == 2:
                vix_data.append({'date': parts[0], 'vix': float(parts[1])})
except:
    pass
vix_current = vix_data[-1]['vix'] if vix_data else None

print(f"\nVIX (Aug 18): {vix_current}")

# =====================================================================
# INDEX REGIME ANALYSIS
# =====================================================================
print("\n" + "="*80)
print("[STAGE 1] MACRO REGIME ANALYSIS")
print("="*80)

for ticker in indices:
    m = ta_metrics(ticker)
    if not m:
        print(f"{ticker}: NO DATA")
        continue
    
    regime = "BULL" if (m['above_ema50'] and m['above_200sma']) else ("BEAR" if (not m['above_ema50'] and not m['above_200sma'] and m['sma200'] is not None) else "TRANSITIONAL")
    
    print(f"\n{ticker}: ${m['close']:.2f} | Day: {m['pct_day']:+.2f}% | 1W: {m['pct_1w']:+.1f}% | 1M: {m['pct_1m']:+.1f}%")
    sma200_str = f"${m['sma200']:.2f}" if m['sma200'] else "N/A (data <200d)"
    print(f"  EMA20: ${m['ema20']:.2f}  EMA50: ${m['ema50']:.2f}  SMA200: {sma200_str}")
    print(f"  RSI: {m['rsi14']:.1f}  |  MACD Hist: {m['macd_hist']:.4f}  |  ATR14: ${m['atr14']:.2f} ({m['atr_pct']:.1f}%)")
    print(f"  Vol Ratio: {m['vol_ratio']:.2f}x  |  20d Range: ${m['sw_low_20']:.2f}–${m['sw_high_20']:.2f}")
    print(f"  REGIME: {regime} | Above EMA20: {m['above_ema20']} | Above EMA50: {m['above_ema50']} | Above 200SMA: {m['above_200sma']}")

# =====================================================================
# STOCK SCAN
# =====================================================================
print("\n" + "="*80)
print("[STAGE 1B] SWING CANDIDATE SCAN")
print("="*80)

results = []
for ticker in stocks:
    m = ta_metrics(ticker)
    if not m:
        continue
    
    # Filters: above key MAs, RSI in range, MACD positive, liquid
    if not (m['above_ema20'] and m['above_ema50']):
        continue
    if not (30 < m['rsi14'] < 80):
        continue
    if m['macd_hist'] is None or m['macd_hist'] <= 0:
        continue
    if m['atr_pct'] < 0.5:  # must be tradeable
        continue
    
    # Pullback score: how close to 20d low (prefer pullbacks)
    pullback_pct = (m['close'] - m['sw_low_20']) / m['close'] * 100
    breakout_pct = (m['sw_high_20'] - m['close']) / m['close'] * 100
    
    # Momentum score
    momentum = m['pct_1m'] * 0.4 + m['pct_1w'] * 0.3 + m['macd_hist']/m['close']*100 * 0.3
    
    # Setup score: prefer RSI not overbought + pullback zone
    setup = (65 - m['rsi14']) * 0.5 + pullback_pct * 0.5
    
    score = momentum + setup
    
    results.append({
        **m,
        'pullback_pct': pullback_pct,
        'breakout_pct': breakout_pct,
        'score': score
    })

results.sort(key=lambda x: x['score'], reverse=True)

print(f"\n{'Ticker':<8} {'Price':>8} {'1W%':>6} {'1M%':>6} {'RSI':>5} {'MACD_H':>8} {'ATR%':>5} {'PullBk':>7} {'Score':>7}")
print("-" * 70)
for r in results[:20]:
    print(f"{r['ticker']:<8} ${r['close']:>7.2f} {r['pct_1w']:>+5.1f}% {r['pct_1m']:>+5.1f}% {r['rsi14']:>5.1f} {r['macd_hist']:>8.4f} {r['atr_pct']:>5.1f} {r['pullback_pct']:>5.1f}% {r['score']:>7.2f}")

# =====================================================================
# TOP 3 DEEP DIVE + ORDER BLUEPRINTS
# =====================================================================
top3 = results[:3]

# Macro regime determination
qqq_m = ta_metrics('QQQ')
if qqq_m:
    if qqq_m['above_ema50'] and qqq_m['above_200sma'] and qqq_m['rsi14'] < 70:
        macro_regime = "BULL"
    elif not qqq_m['above_ema50'] and not qqq_m['above_200sma']:
        macro_regime = "BEAR"
    else:
        macro_regime = "TRANSITIONAL"
else:
    macro_regime = "TRANSITIONAL"

print("\n" + "="*80)
print(f"[STAGE 2] COGNITIVE CRITIQUE — MACRO REGIME: {macro_regime}")
print("="*80)

for i, r in enumerate(top3, 1):
    ticker = r['ticker']
    print(f"\n{'─'*70}")
    print(f"CRITIQUE #{i}: {ticker}")
    print(f"{'─'*70}")
    
    # Regime alignment
    alignment = "ALIGNED" if r['above_ema20'] and r['above_ema50'] else "COUNTER-TREND"
    print(f"  Regime Alignment: {alignment} with {macro_regime} macro")
    
    # Bull case
    print(f"  ✓ BULL CASE: {ticker} above EMA20/50, MACD histogram positive ({r['macd_hist']:.4f}),")
    print(f"    {r['pullback_pct']:.1f}% pullback from 20d low, RSI neutral zone ({r['rsi14']:.1f}).")
    print(f"    ATR of ${r['atr14']:.2f} ({r['atr_pct']:.1f}%) allows meaningful swing capture.")
    
    # Bear case
    print(f"  ✗ BEAR CASE: If QQQ breaks below EMA50 (${qqq_m['ema50']:.2f}) in {macro_regime} regime,")
    print(f"    {ticker} will not decouple. Earnings/cycle risk always present.")
    if r['rsi14'] > 60:
        print(f"    RSI elevated at {r['rsi14']:.1f} — less room to run, re-test risk high.")
    
    # Invalidation
    print(f"  ⚠ INVALIDATION: Close below ${r['sw_low_20']:.2f} (20d swing low) → EXIT IMMEDIATELY")
    print(f"  ⚠ STOP TIGHTEN: If QQQ drops >3% from current → cut position size 50%")

# =====================================================================
# STAGE 3: TACTICAL ORDER BLUEPRINTS
# =====================================================================
print("\n" + "="*80)
print("[STAGE 3] TACTICAL ORDER BLUEPRINTS — TOP SWING TRADES")
print("="*80)

risk_pct = 1.5  # 1.5% risk per trade

for i, r in enumerate(top3, 1):
    ticker = r['ticker']
    close = r['close']
    atr = r['atr14']
    e20 = r['ema20']
    sw_low = r['sw_low_20']
    
    # Entry: slight pullback to EMA20 zone
    entry = round(e20 if e20 < close else close * 0.995, 2)
    # Stop: 2× ATR below entry
    stop = round(entry - 2.0 * atr, 2)
    # T1: 2× ATR above entry (2:1)
    t1 = round(entry + 2.0 * atr, 2)
    # T2: 3.5× ATR above entry (3.5:1)
    t2 = round(entry + 3.5 * atr, 2)
    
    rr1 = (t1 - entry) / (entry - stop)
    rr2 = (t2 - entry) / (entry - stop)
    
    inv = round(sw_low * 0.98, 2)
    risk_per_share = entry - stop
    
    # Position sizing (assume $10K account)
    acct = 10000
    risk_amount = acct * risk_pct / 100
    shares = max(1, int(risk_amount / risk_per_share))
    capital_used = shares * entry
    
    print(f"""
╔{'═'*70}
║  TRADE #{i}: {ticker}
╠{'═'*70}
║  DIRECTION:         LONG
║  SETUP RATIONALE:  {ticker} above EMA20/50, MACD histogram expanding positive,
║                     pulling back {r['pullback_pct']:.1f}% from 20d low into EMA20 support
║                     ({e20:.2f}) — momentum re-accumulation in {macro_regime} macro regime.
╠{'─'*70}
║  ORDER EXECUTION:
║    Entry Type:      BUY LIMIT @ ${entry:.2f}  (at EMA20 support zone)
║    Stop Loss:       SELL STOP-LIMIT @ ${stop:.2f}
║                     (2.0× ATR = ${atr:.2f} × 2 = ${risk_per_share:.2f}/share risk)
╠{'─'*70}
║  PROFIT TARGETS:
║    T1 (50% @):       SELL LIMIT @ ${t1:.2f}  →  R:R = {rr1:.1f}:1
║    T2 (50% @):       SELL LIMIT @ ${t2:.2f}  →  R:R = {rr2:.1f}:1
╠{'─'*70}
║  TRAILING STOP PROTOCOL:
║    → Upon T1 hit: Move SL to BREAKEVEN + $0.10 buffer immediately
║    → After T1: Trail by 1× ATR daily close
║    → On T2 entry: Let run with 1.5× ATR trailing stop
╠{'─'*70}
║  POSITION SIZING (@ {risk_pct}% risk on $10K acct = ${risk_amount:.0f} max risk):
║    Shares:           ~{shares}  |  Capital: ${capital_used:,.0f}  |  Risk: ${shares*risk_per_share:.2f}
╠{'─'*70}
║  INVALIDATION:     Close below ${inv:.2f} (20d swing low ${sw_low:.2f} -2% buffer)
║                     → Immediate exit. No holding through macro breakdown.
╠{'─'*70}
║  HOLDING WINDOW:   Target T1 within 5 days. Max hold: 15 trading days.
║  CATALYST WATCH:   Earnings within window → reduce size or exit pre-earnings
╚{'═'*70}
""")

# =====================================================================
# PORTFOLIO SUMMARY TABLE
# =====================================================================
print("\n" + "="*80)
print("PORTFOLIO SUMMARY")
print("="*80)
print(f"\n{'Trade':<8} {'Entry':>8} {'Stop':>8} {'T1':>8} {'T2':>8} {'RR1':>5} {'RR2':>5} {'Risk%':>6} {'Shares':>7} {'Capital':>10}")
print("-" * 80)
for i, r in enumerate(top3, 1):
    ticker = r['ticker']
    entry = round(r['ema20'] if r['ema20'] < r['close'] else r['close'] * 0.995, 2)
    stop = round(entry - 2.0 * r['atr14'], 2)
    t1 = round(entry + 2.0 * r['atr14'], 2)
    t2 = round(entry + 3.5 * r['atr14'], 2)
    rr1 = (t1 - entry) / (entry - stop)
    rr2 = (t2 - entry) / (entry - stop)
    risk_ps = entry - stop
    shares = max(1, int((10000 * risk_pct / 100) / risk_ps))
    capital = shares * entry
    print(f"{ticker:<8} ${entry:>7.2f} ${stop:>7.2f} ${t1:>7.2f} ${t2:>7.2f} {rr1:>4.1f}:1 {rr2:>4.1f}:1 {risk_pct:>5.1f}% {shares:>7} ${capital:>9,.0f}")

total_capital = sum(
    max(1, int((10000 * risk_pct / 100) / (round((r['ema20'] if r['ema20'] < r['close'] else r['close']*0.995), 2) - round((round(r['ema20'] if r['ema20'] < r['close'] else r['close']*0.995, 2) - 2.0*r['atr14']), 2)))) 
    * round(r['ema20'] if r['ema20'] < r['close'] else r['close']*0.995, 2)
    for r in top3
)
print(f"\nTotal Capital at Risk (all 3 trades): ~${total_capital:,.0f}")
print(f"Max Loss if All 3 Invalidate (3×${10000*risk_pct/100:.0f}): ${3*10000*risk_pct/100:.0f}")
print(f"\nNOTE: If any single trade wins T2, it more than covers all 3 max losses.")
print(f"Macro Regime: {macro_regime} | VIX: {vix_current} | Date: Aug 19, 2026")
print("="*80)
