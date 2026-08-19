import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

print("=" * 80)
print(f"SWING TRADE SCAN — {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
print("=" * 80)

# =====================================================================
# STAGE 1A: MACRO REGIME — MAJOR INDICES
# =====================================================================
tickers_majors = ['QQQ', 'SPY', 'IWM', 'VIX', 'TLT', 'HYG']

print("\n[STAGE 1A] MACRO REGIME — MAJOR INDICES")
print("-" * 70)

def get_ta_data(ticker, period='6mo'):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period=period)
        if len(hist) < 30:
            return None
        close = hist['Close']
        high = hist['High']
        low = hist['Low']
        volume = hist['Volume']
        
        # Moving averages
        ema20 = close.ewm(span=20).mean().iloc[-1]
        ema50 = close.ewm(span=50).mean().iloc[-1]
        sma200 = close.rolling(200).mean().iloc[-1]
        
        # ATR
        high_low = high - low
        high_close = np.abs(high - close.shift())
        tr = pd.concat([high_low, high_close], axis=1).max(axis=1)
        atr14 = tr.rolling(14).mean().iloc[-1]
        
        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = (100 - (100 / (1 + rs))).iloc[-1]
        
        # MACD
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd_line = ema12.iloc[-1] - ema26.iloc[-1]
        macd_signal = macd_line.ewm(span=9).mean().iloc[-1]
        macd_hist = macd_line - macd_signal
        
        current = close.iloc[-1]
        prev_close = close.iloc[-2]
        pct_chg_day = (current - prev_close) / prev_close * 100
        pct_chg_1m = (current - close.iloc[-21]) / close.iloc[-21] * 100 if len(close) > 21 else 0
        
        # Recent swing high/low
        swing_high_20 = high.tail(20).max()
        swing_low_20 = low.tail(20).min()
        
        # Trend
        above_ema20 = current > ema20
        above_ema50 = current > ema50
        above_200sma = current > sma200 if not np.isnan(sma200) else True
        
        return {
            'close': current,
            'prev_close': prev_close,
            'pct_chg_day': pct_chg_day,
            'pct_chg_1m': pct_chg_1m,
            'ema20': ema20,
            'ema50': ema50,
            'sma200': sma200,
            'atr14': atr14,
            'rsi14': rsi,
            'macd_line': macd_line,
            'macd_signal': macd_signal,
            'macd_hist': macd_hist,
            'volume_avg_20': volume.tail(20).mean(),
            'volume_today': volume.iloc[-1],
            'swing_high_20': swing_high_20,
            'swing_low_20': swing_low_20,
            'above_ema20': above_ema20,
            'above_ema50': above_ema50,
            'above_200sma': above_200sma,
        }
    except Exception as e:
        return {'error': str(e)}

index_data = {}
for ticker in tickers_majors:
    d = get_ta_data(ticker, '6mo')
    if d:
        index_data[ticker] = d
        if 'error' not in d:
            regime_flag = "BULL" if (d['above_ema50'] and d['above_200sma']) else ("BEAR" if (not d['above_ema50'] and not d['above_200sma']) else "TRANSITIONAL")
            print(f"\n{ticker}: ${d['close']:.2f}  |  Day: {d['pct_chg_day']:+.2f}%  |  1M: {d['pct_chg_1m']:+.1f}%")
            print(f"  EMA20: ${d['ema20']:.2f}  EMA50: ${d['ema50']:.2f}  SMA200: ${d['sma200']:.2f}")
            print(f"  RSI14: {d['rsi14']:.1f}  |  MACD Hist: {d['macd_hist']:.4f}  |  ATR14: {d['atr14']:.2f}")
            print(f"  Regime: {regime_flag}  |  Vol Ratio: {d['volume_today']/d['volume_avg_20']:.2f}x avg")
            print(f"  20d High: ${d['swing_high_20']:.2f}  |  20d Low: ${d['swing_low_20']:.2f}")

# =====================================================================
# STAGE 1B: NASDAQ 100 TOP COMPONENTS SWING SCAN
# =====================================================================
print("\n\n[STAGE 1B] NASDAQ 100 COMPONENT SWING SCAN")
print("-" * 70)

# Top NASDAQ 100 components by weight / relevance for swing trading
nasdaq100_scan = [
    'NVDA', 'AAPL', 'MSFT', 'AMZN', 'GOOGL', 'META', 'AVGO', 'TSLA',
    'AMD', 'NFLX', 'QCOM', 'TXN', 'INTC', 'AMAT', 'MU', 'LRCX',
    'PANW', 'ORLY', 'CSX', 'ADSK', 'CDNS', 'SNPS', 'NXPI', 'KLAC',
    'INTU', 'CTAS', 'FAST', 'CTSH', 'ADP', 'PAYX', 'BKNG', 'VRTX',
    'REGN', 'MRVL', 'ON', 'HPQ', 'DELL', 'CRWD', 'ZS', 'FTNT',
    'TEAM', 'MDB', 'DDOG', 'NET', 'APP', 'SMCI', 'ARM', 'COIN',
    'mar', 'COST', 'PEP', 'SBUX'
]

scan_results = []

for ticker in nasdaq100_scan:
    try:
        d = get_ta_data(ticker, '6mo')
        if d and 'error' not in d:
            # Calculate score metrics
            rsi = d['rsi14']
            macd_ok = d['macd_hist'] > 0
            above_key = d['above_ema20'] and d['above_ema50']
            
            # ATR-based volatility regime
            atr_pct = d['atr14'] / d['close'] * 100
            
            # Near support/resistance scoring
            support_dist = (d['close'] - d['swing_low_20']) / d['close'] * 100
            resistance_dist = (d['swing_high_20'] - d['close']) / d['close'] * 100
            
            # Near 52w high?
            near_high = (d['swing_high_20'] - d['close']) / d['swing_high_20'] < 0.02
            
            scan_results.append({
                'ticker': ticker,
                'close': d['close'],
                'pct_chg_1m': d['pct_chg_1m'],
                'rsi14': rsi,
                'macd_hist': d['macd_hist'],
                'macd_ok': macd_ok,
                'above_ema20': d['above_ema20'],
                'above_ema50': d['above_ema50'],
                'atr_pct': atr_pct,
                'atr14': d['atr14'],
                'support_dist': support_dist,
                'resistance_dist': resistance_dist,
                'near_high': near_high,
                'vol_ratio': d['volume_today'] / d['volume_avg_20'],
            })
    except:
        pass

# Filter: NOT overbought RSI, above key MAs, reasonable volatility
filtered = [
    r for r in scan_results
    if r['above_ema20'] and r['above_ema50']
    and r['rsi14'] < 80
    and r['rsi14'] > 30
    and r['macd_ok']
    and r['atr_pct'] > 0.5  # must be liquid enough
]

# Sort by composite score: momentum + setup quality
for r in filtered:
    # Score: higher RSI(but not overbought) + strong momentum + near support = good
    momentum_score = r['pct_chg_1m'] * 0.3 + r['macd_hist'] / r['close'] * 1000
    setup_score = (70 - r['rsi14']) * 0.5 + r['support_dist'] * 0.3  # prefer pullback setups
    r['score'] = momentum_score + setup_score

filtered.sort(key=lambda x: x['score'], reverse=True)

print("\nTOP SWING SETUPS (Filtered: Above MAs, RSI 30-80, MACD positive)")
print(f"{'Ticker':<8} {'Price':>8} {'1M%':>7} {'RSI':>5} {'MACD_H':>8} {'ATR%':>5} {'SupD%':>6} {'Score':>7}")
print("-" * 60)
for r in filtered[:15]:
    print(f"{r['ticker']:<8} ${r['close']:>7.2f} {r['pct_chg_1m']:>+6.1f}% {r['rsi14']:>5.1f} {r['macd_hist']:>8.3f} {r['atr_pct']:>5.1f} {r['support_dist']:>5.1f}% {r['score']:>7.2f}")

# =====================================================================
# STAGE 2: DEEP DIVE — TOP 3 SETUPS
# =====================================================================
print("\n\n[STAGE 2] DEEP DIVE — TOP 3 SWING TRADE SETUPS")
print("=" * 70)

top3 = filtered[:3]

trade_details = []
for ticker in [r['ticker'] for r in top3]:
    print(f"\n{'='*70}")
    print(f"DEEP DIVE: {ticker}")
    print(f"{'='*70}")
    
    d = get_ta_data(ticker, '6mo')
    if not d or 'error' in d:
        continue
    
    close = d['close']
    atr = d['atr14']
    rsi = d['rsi14']
    
    # Entry: pullback to EMA20 or today's range
    entry_price = round(close * 0.995, 2)  # slight discount
    stop_loss = round(entry_price - 2.0 * atr, 2)
    risk_pct = (entry_price - stop_loss) / entry_price * 100
    
    # Targets: 2:1 and 3:1 R:R
    t1_price = round(entry_price + 2.0 * atr, 2)
    t2_price = round(entry_price + 3.5 * atr, 2)
    
    rr1 = (t1_price - entry_price) / (entry_price - stop_loss)
    rr2 = (t2_price - entry_price) / (entry_price - stop_loss)
    
    # Invalidation: below swing low or macro breakdown
    inv_price = round(d['swing_low_20'] * 0.98, 2)
    
    print(f"  Current Price:     ${close:.2f}")
    print(f"  ATR(14):           ${atr:.2f}  ({d['atr_pct']:.1f}% of price)")
    print(f"  Entry (Limit):     ${entry_price:.2f}  (at/near EMA20 pullback)")
    print(f"  Stop Loss:         ${stop_loss:.2f}  (Risk: {risk_pct:.1f}% / ${entry_price - stop_loss:.2f})")
    print(f"  T1 Target (2:1):   ${t1_price:.2f}  (R:R = {rr1:.1f}:1)")
    print(f"  T2 Target (3:1):   ${t2_price:.2f}  (R:R = {rr2:.1f}:1)")
    print(f"  Invalidation:      ${inv_price:.2f}  (below 20d swing low)")
    print(f"  RSI:               {rsi:.1f}  {'Overbought' if rsi > 70 else 'Neutral' if rsi > 40 else 'Oversold'}")
    print(f"  MACD Histogram:   {d['macd_hist']:.4f}  (Momentum: {'Positive' if d['macd_hist'] > 0 else 'Negative'})")
    print(f"  20d Range:         Low ${d['swing_low_20']:.2f} | High ${d['swing_high_20']:.2f}")
    print(f"  20EMA:             ${d['ema20']:.2f}  |  50EMA: ${d['ema50']:.2f}  |  SMA200: ${d['sma200']:.2f}")
    
    trade_details.append({
        'ticker': ticker,
        'close': close,
        'entry': entry_price,
        'stop': stop_loss,
        't1': t1_price,
        't2': t2_price,
        'inv': inv_price,
        'atr': atr,
        'rsi': rsi,
        'rr1': rr1,
        'rr2': rr2,
        'risk_pct': risk_pct,
        'score': next(r['score'] for r in filtered if r['ticker'] == ticker)
    })

# =====================================================================
# STAGE 3: COGNITIVE CRITIQUE
# =====================================================================
print("\n\n[STAGE 3] COGNITIVE CRITIQUE & REGIME ALIGNMENT")
print("=" * 70)

macro_regime = "TRANSITIONAL"
if 'QQQ' in index_data:
    qqq = index_data['QQQ']
    if qqq['above_ema50'] and qqq['above_200sma'] and qqq['rsi14'] < 70:
        macro_regime = "BULL"
    elif not qqq['above_ema50'] and not qqq['above_200sma'] and qqq['rsi14'] > 50:
        macro_regime = "BEAR"
    else:
        macro_regime = "TRANSITIONAL"

print(f"\n>>> MACRO REGIME ASSESSED: {macro_regime}")
print(f"    QQQ Price: ${index_data.get('QQQ', {}).get('close', 'N/A')} | RSI: {index_data.get('QQQ', {}).get('rsi14', 'N/A'):.1f}")
print(f"    VIX Level: ${index_data.get('VIX', {}).get('close', 'N/A')}")

for td in trade_details:
    ticker = td['ticker']
    d = get_ta_data(ticker, '6mo')
    
    print(f"\n{'─'*70}")
    print(f"CRITIQUE: {ticker}")
    print(f"{'─'*70}")
    
    # Bull case
    print(f"  ✓ BULL CASE: {ticker} above key EMAs, MACD histogram expanding,")
    print(f"    momentum building. ATR suggests {d['atr_pct']:.1f}% daily swings,")
    print(f"    allowing active swing capture.")
    
    # Bear case
    print(f"  ✗ BEAR CASE: Market in {macro_regime} regime — if broad indices")
    print(f"    correct, {ticker} will not decouple. Earnings risk always present.")
    print(f"    {'Overbought RSI on daily' if td['rsi'] > 65 else 'RSI in neutral zone'}")
    
    # Invalidation triggers
    print(f"  ⚠ INVALIDATION: If {ticker} closes below ${td['inv']:.2f}")
    print(f"    (20d swing low = {d['swing_low_20']:.2f}), trade is immediately void.")
    print(f"    If QQQ breaks below EMA50 = macro risk, tighten stop to BE.")

# =====================================================================
# STAGE 4: TACTICAL ORDER BLUEPRINT
# =====================================================================
print("\n\n" + "=" * 70)
print("STAGE 4: TACTICAL ORDER BLUEPRINTS — TOP SWING TRADES")
print("=" * 70)

# Position sizing: risk 1-2% per trade in transitional/volatile environment
risk_pct = 1.5  # conservative for auto-execution

for i, td in enumerate(trade_details, 1):
    risk_amount_per_share = td['entry'] - td['stop']
    shares = int((10000 * risk_pct / 100) / risk_amount_per_share)  # assume $10K account
    
    print(f"""
{'─'*70}
TRADE #{i}: {td['ticker']}
{'─'*70}
  DIRECTION:        {'LONG' if td['entry'] < td['close'] * 1.01 else 'LONG'}
  SETUP RATIONALE:  {td['ticker']} above EMA20/50, MACD positive, 
                    sitting {td['close'] - index_data.get(td['ticker'], {}).get('swing_low_20', td['close'] * 0.95):.2f} above 20d low 
                    — momentum shift setup in {'bull' if macro_regime == 'BULL' else 'transitional'} macro regime.

  ORDER EXECUTION:
    Entry Type:      BUY LIMIT @ ${td['entry']:.2f}  (pullback to EMA20 zone)
    Stop Loss:       SELL STOP-LIMIT @ ${td['stop']:.2f}
                     (2.0× ATR = ${td['atr']:.2f} risk per share)

  PROFIT TARGETS:
    T1 (50% size):   SELL LIMIT @ ${td['t1']:.2f}  →  {td['rr1']:.1f}:1 R:R
    T2 (50% size):   SELL LIMIT @ ${td['t2']:.2f}  →  {td['rr2']:.1f}:1 R:R

  TRAILING STOP (after T1 hit):
    Move SL to BREAKEVEN + 0.5× ATR once T1 is reached.

  POSITION SIZING (@ ${10000 * risk_pct / 100:.0f} risk on $10K acct):
    Risk per share:  ${risk_amount_per_share:.2f}
    Shares:          ~{shares}  |  Capital used: ${shares * td['entry']:.0f}

  INVALIDATION:     Close below ${td['inv']:.2f} (20d swing low)
                    → Immediate exit, no questions.

  HOLDING WINDOW:   2–15 trading days (target T1 within 5 days)
""")

print("=" * 70)
print(f"Scan completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
print("NOTE: Execute with GTC limit orders. Review pre-market if macro shifts.")
print("=" * 70)
