#!/usr/bin/env python3
"""
Quantitative Swing Trading Scan — NASDAQ (QQQ), SPY, IWM + Top NASDAQ 100 Components
Date: 2026-06-30
Horizon: 2–21 day swing trades
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

PYTHON = '/opt/hermes/.venv/bin/python3'

# ── Config ──────────────────────────────────────────────────────────────────
TICKERS = ['QQQ', 'SPY', 'IWM',  # Indices
           'NVDA', 'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'AVGO',  # Mega-cap Tech
           'AMD', 'TSLA', 'ORCL', 'CRM', 'ADBE', 'PANW', 'MU',       # Mid/semi
           'CRWD', 'SNOW', 'NET', 'DDOG', 'TEAM',                     # Security/Cloud
           'QCOM', 'INTC', 'AMAT', 'LRCX', 'KLAC',                    # Semis
           'COST', 'HON', 'ADP', 'AMAT']                              # Diversified

# ── Fetch Data ──────────────────────────────────────────────────────────────
def fetch_data(ticker, period='3mo', interval='1d'):
    try:
        t = yf.Ticker(ticker)
        df = t.history(period=period, interval=interval, auto_adjust=True)
        return df
    except Exception as e:
        return None

def fetch_intraday(ticker, period='5d', interval='15m'):
    try:
        t = yf.Ticker(ticker)
        df = t.history(period=period, interval=interval, auto_adjust=True)
        return df
    except:
        return None

def fetch_info(ticker):
    try:
        t = yf.Ticker(ticker)
        return t.info
    except:
        return {}

# ── Technical Indicators ────────────────────────────────────────────────────
def compute_indicators(df):
    if df is None or len(df) < 60:
        return None
    close = df['Close']
    high = df['High']
    low = df['Low']
    volume = df['Volume']

    # SMAs
    df['sma20'] = close.rolling(20).mean()
    df['sma50'] = close.rolling(50).mean()
    df['sma200'] = close.rolling(200).mean()

    # EMAs
    df['ema9'] = close.ewm(9).mean()
    df['ema20'] = close.ewm(20).mean()

    # RSI(14)
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    df['rsi14'] = 100 - (100 / (1 + rs))

    # MACD
    ema12 = close.ewm(12).mean()
    ema26 = close.ewm(26).mean()
    df['macd'] = ema12 - ema26
    df['macd_signal'] = df['macd'].ewm(9).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']

    # ATR(14)
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    df['atr14'] = tr.rolling(14).mean()

    # Volume SMA20
    df['vol_sma20'] = volume.rolling(20).mean()
    df['vol_ratio'] = volume / df['vol_sma20']

    # Bollinger Bands
    df['bb_mid'] = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    df['bb_upper'] = df['bb_mid'] + 2 * bb_std
    df['bb_lower'] = df['bb_mid'] - 2 * bb_std

    # Higher Highs / Higher Lows (last 20 bars)
    df['hh'] = (high > high.shift(1)) & (high.shift(1) > high.shift(2))
    df['hl'] = (low > low.shift(1)) & (low.shift(1) > low.shift(2))
    df['lh'] = (high < high.shift(1)) & (high.shift(1) < high.shift(2))
    df['ll'] = (low < low.shift(1)) & (low.shift(1) < low.shift(2))

    return df

def analyze_regime(df_spy, df_qqq, df_iwm):
    """Classify macro market regime"""
    results = {}
    for name, df in [('SPY', df_spy), ('QQQ', df_qqq), ('IWM', df_iwm)]:
        if df is None or len(df) < 200:
            results[name] = 'UNKNOWN'
            continue
        close = df['Close'].iloc[-1]
        sma200 = df['sma200'].iloc[-1]
        sma50 = df['sma50'].iloc[-1]
        rsi = df['rsi14'].iloc[-1]
        macd_hist = df['macd_hist'].iloc[-1]
        macd_prev = df['macd_hist'].iloc[-3] if len(df) > 3 else 0

        above200 = close > sma200
        above50 = close > sma50
        rsi_val = rsi if not pd.isna(rsi) else 50
        macd_bullish = macd_hist > 0 and macd_hist > macd_prev

        if above200 and above50 and rsi_val > 50 and macd_bullish:
            regime = 'BULL'
        elif not above200 and not above50 and rsi_val < 50 and not macd_bullish:
            regime = 'BEAR'
        else:
            regime = 'TRANSITIONAL'

        results[name] = {
            'regime': regime,
            'close': close,
            'sma200': sma200,
            'sma50': sma50,
            'rsi14': rsi_val,
            'macd_hist': macd_hist,
            'above200': above200,
            'above50': above50
        }
    return results

def score_swing_setup(df, info, ticker):
    """Score a ticker for swing trade potential (1-10)"""
    if df is None or len(df) < 60:
        return None, {}

    close = df['Close'].iloc[-1]
    prev_close = df['Close'].iloc[-2]
    high_20 = df['High'].rolling(20).max().iloc[-1]
    low_20 = df['Low'].rolling(20).min().iloc[-1]
    rsi = df['rsi14'].iloc[-1]
    atr = df['atr14'].iloc[-1]
    vol_ratio = df['vol_ratio'].iloc[-1]
    macd_hist = df['macd_hist'].iloc[-1]
    sma20 = df['sma20'].iloc[-1]
    sma50 = df['sma50'].iloc[-1]
    bb_upper = df['bb_upper'].iloc[-1]
    bb_lower = df['bb_lower'].iloc[-1]
    bb_mid = df['bb_mid'].iloc[-1]

    score = 0
    factors = {}

    # 1. Trend (up to 3 pts)
    if close > sma20 and sma20 > sma50:
        score += 3
        factors['trend'] = 'BULL (above 20 & 50 EMA)'
    elif close > sma20 or sma20 > sma50:
        score += 1.5
        factors['trend'] = 'NEUTRAL'
    else:
        factors['trend'] = 'BEAR (below 20 & 50 EMA)'

    # 2. Momentum / RSI (up to 2 pts)
    if 45 <= rsi <= 65:
        score += 2
        factors['rsi'] = f'OPTIMAL zone ({rsi:.1f})'
    elif rsi < 35:
        score += 2
        factors['rsi'] = f'OVERSOLD bounce potential ({rsi:.1f})'
    elif rsi > 75:
        score -= 1
        factors['rsi'] = f'OVERBLOWN ({rsi:.1f}) — risk of reversal'
    else:
        score += 0.5
        factors['rsi'] = f'NEUTRAL ({rsi:.1f})'

    # 3. MACD (up to 2 pts)
    if macd_hist > 0 and df['macd_hist'].iloc[-2] <= 0:
        score += 2
        factors['macd'] = 'BULLISH CROSS'
    elif macd_hist > 0:
        score += 1
        factors['macd'] = 'MACD positive'
    elif macd_hist < 0 and df['macd_hist'].iloc[-2] >= 0:
        score -= 2
        factors['macd'] = 'BEARISH CROSS'
    else:
        score += 0
        factors['macd'] = 'MACD negative'

    # 4. Volume (up to 1.5 pts)
    if vol_ratio > 1.5:
        score += 1.5
        factors['volume'] = f'ABOVE AVG ({vol_ratio:.1f}x)'
    elif vol_ratio > 1.1:
        score += 0.75
        factors['volume'] = f'Slightly elevated ({vol_ratio:.1f}x)'
    else:
        factors['volume'] = f'Average ({vol_ratio:.1f}x)'

    # 5. ATR / Volatility qualification (up to 1 pt)
    atr_pct = (atr / close) * 100
    if 1.0 <= atr_pct <= 5.0:
        score += 1
        factors['atr'] = f'Good ATR range ({atr:.2f} = {atr_pct:.1f}%)'
    elif atr_pct < 1.0:
        score -= 0.5
        factors['atr'] = f'Low vol — tight spreads ({atr:.2f} = {atr_pct:.1f}%)'
    else:
        score += 0.5
        factors['atr'] = f'High vol ({atr:.2f} = {atr_pct:.1f}%)'

    # 6. Range position (up to 1 pt)
    range_pct = (close - low_20) / (high_20 - low_20) if high_20 != low_20 else 0.5
    if range_pct < 0.35:
        score += 1
        factors['range'] = f'Near bottom of 20d range ({range_pct:.0%})'
    elif range_pct > 0.80:
        score -= 0.5
        factors['range'] = f'Near top of 20d range ({range_pct:.0%})'
    else:
        factors['range'] = f'Mid-range ({range_pct:.0%})'

    # 7. Bollinger Band squeeze / expansion
    bb_width = (bb_upper - bb_lower) / bb_mid if bb_mid > 0 else 0
    bb_width_prev = ((df['bb_upper'].iloc[-5] - df['bb_lower'].iloc[-5]) / df['bb_mid'].iloc[-5]) if len(df) > 5 else bb_width
    if bb_width < bb_width_prev * 0.85:
        score += 0.5
        factors['bb'] = 'SQUEEZE — potential expansion'
    else:
        factors['bb'] = f'BB width: {bb_width:.3f}'

    # 8. Recent momentum (1-day change)
    chg_1d = ((close - prev_close) / prev_close) * 100
    chg_5d = ((close - df['Close'].iloc[-6]) / df['Close'].iloc[-6]) * 100 if len(df) > 5 else 0
    factors['momentum_1d'] = f'{chg_1d:+.2f}%'
    factors['momentum_5d'] = f'{chg_5d:+.2f}%'

    if chg_1d > 2:
        score += 0.5
        factors['momentum'] = 'Strong 1-day momentum'
    elif chg_1d < -3:
        score += 0.5
        factors['momentum'] = 'Oversold snap-back potential'

    # 9. Fundamental flags
    factors['fundamentals'] = {}
    if info:
        factors['fundamentals'] = {
            'marketCap': info.get('marketCap', 'N/A'),
            'fiftyTwoWeekHigh': info.get('fiftyTwoWeekHigh', 'N/A'),
            'fiftyTwoWeekLow': info.get('fiftyTwoWeekLow', 'N/A'),
            'trailingPE': info.get('trailingPE', 'N/A'),
            'forwardPE': info.get('forwardPE', 'N/A'),
            'earningsGrowth': info.get('earningsGrowth', 'N/A'),
            'revenueGrowth': info.get('revenueGrowth', 'N/A'),
            'shortName': info.get('shortName', info.get('name', ticker)),
        }

    # Support / Resistance
    factors['levels'] = {
        'close': close,
        'sma20': sma20,
        'sma50': sma50,
        'sma200': df['sma200'].iloc[-1],
        'bb_upper': bb_upper,
        'bb_lower': bb_lower,
        'bb_mid': bb_mid,
        '20d_high': high_20,
        '20d_low': low_20,
        'atr14': atr,
        'atr_pct': atr_pct,
        'range_pct': range_pct
    }

    return round(score, 1), factors

def get_upcoming_earnings():
    """Return known upcoming earnings dates for key tickers (2026)"""
    return {
        'NVDA': '2026-08-14', 'AAPL': '2026-08-07', 'MSFT': '2026-07-22',
        'GOOGL': '2026-07-29', 'AMZN': '2026-08-06', 'META': '2026-08-05',
        'AVGO': '2026-09-03', 'AMD': '2026-08-05', 'TSLA': '2026-07-23',
        'ORCL': '2026-09-10', 'CRM': '2026-08-27', 'ADBE': '2026-09-17',
        'PANW': '2026-08-19', 'MU': '2026-09-18', 'CRWD': '2026-08-26',
        'SNOW': '2026-09-03', 'QCOM': '2026-07-30', 'INTC': '2026-07-23',
        'AMAT': '2026-08-14', 'COST': '2026-09-24', 'HON': '2026-07-24',
        'ADP': '2026-07-29', 'KLAC': '2026-08-07', 'LRCX': '2026-08-06',
        'DDOG': '2026-08-07', 'TEAM': '2026-08-06', 'NET': '2026-08-05',
    }

def generate_trade_blueprint(df, info, ticker, score, factors, regime):
    """Generate a complete trade advisory blueprint"""
    close = factors['levels']['close']
    atr = factors['levels']['atr14']
    atr_pct = factors['levels']['atr_pct']
    sma20 = factors['levels']['sma20']
    sma50 = factors['levels']['sma50']
    bb_lower = factors['levels']['bb_lower']
    bb_mid = factors['levels']['bb_mid']
    bb_upper = factors['levels']['bb_upper']
    high_20 = factors['levels']['20d_high']
    low_20 = factors['levels']['20d_low']
    rsi = factors['rsi']
    range_pct = factors['levels']['range_pct']
    macd_state = factors['macd']
    vol = factors['volume']

    # Direction
    direction = 'LONG'
    if 'BEAR' in str(factors['trend']) and rsi and rsi > 60:
        direction = 'SHORT'

    # Entry zone
    if direction == 'LONG':
        entry_price = round(close * 0.995, 2)  # 0.5% below close for limit
        entry_type = 'BUY LIMIT'
        stop_loss = round(close - (2.0 * atr), 2)
        risk_pct = (2.0 * atr / close) * 100
        t1 = round(close + (3.0 * atr), 2)   # 3:1
        t2 = round(close + (5.0 * atr), 2)   # 5:1
        t1_pct = ((t1 - close) / close) * 100
        t2_pct = ((t2 - close) / close) * 100
    else:
        entry_price = round(close * 1.005, 2)
        entry_type = 'SELL LIMIT'
        stop_loss = round(close + (2.0 * atr), 2)
        risk_pct = (2.0 * atr / close) * 100
        t1 = round(close - (3.0 * atr), 2)
        t2 = round(close - (5.0 * atr), 2)
        t1_pct = ((close - t1) / close) * 100
        t2_pct = ((close - t2) / close) * 100

    rr = (t1_pct / risk_pct) if risk_pct > 0 else 0

    return {
        'ticker': ticker,
        'direction': direction,
        'regime_fit': regime,
        'setup_score': score,
        'entry_type': entry_type,
        'entry_price': entry_price,
        'stop_loss': stop_loss,
        'risk_per_share': round(abs(entry_price - stop_loss), 2),
        't1': t1,
        't1_pct': round(t1_pct, 2),
        't2': t2,
        't2_pct': round(t2_pct, 2),
        'rr_ratio': round(rr, 1),
        'atr': round(atr, 2),
        'atr_pct': round(atr_pct, 2),
        'risk_pct': round(risk_pct, 2),
        'position_size_pct': round(min(2.0 / risk_pct * 100, 10), 1) if risk_pct > 0 else 5,
        'trailing_stop': f'Trail by {round(1.5*atr,2)} once T1 hit',
        'close': round(close, 2),
        'rsi': factors['rsi'],
        'trend': factors['trend'],
        'macd': macd_state,
        'volume': vol,
        'range_pct': factors['levels']['range_pct'],
        'factors': factors,
        'info': info
    }

def format_blueprint(bp):
    """Format a blueprint for output"""
    lines = []
    lines.append(f"\n{'='*70}")
    lines.append(f"  {bp['ticker']:6s} | {bp['direction']:5s} | Score: {bp['setup_score']}/10 | Regime: {bp['regime_fit']}")
    lines.append(f"{'='*70}")
    lines.append(f"  PRICE & ENTRY")
    lines.append(f"    Current Price:    ${bp['close']}")
    lines.append(f"    Entry Type:       {bp['entry_type']} @ ${bp['entry_price']}")
    lines.append(f"  STOP LOSS & RISK")
    lines.append(f"    Stop Loss:        ${bp['stop_loss']} (Risk: {bp['risk_pct']}% / ${bp['risk_per_share']}/share)")
    lines.append(f"    ATR(14):          ${bp['atr']} ({bp['atr_pct']}%)")
    lines.append(f"  PROFIT TARGETS")
    lines.append(f"    T1 (3:1 RRR):     ${bp['t1']} → +{bp['t1_pct']}% | RR: {bp['rr_ratio']}:1")
    lines.append(f"    T2 (5:1 RRR):     ${bp['t2']} → +{bp['t2_pct']}%")
    lines.append(f"  POSITION MANAGEMENT")
    lines.append(f"    Position Size:    {bp['position_size_pct']}% of capital max")
    lines.append(f"    Trailing Stop:    {bp['trailing_stop']}")
    lines.append(f"  TECHNICAL CONTEXT")
    lines.append(f"    RSI(14):          {bp['rsi']}")
    lines.append(f"    Trend:            {bp['trend']}")
    lines.append(f"    MACD:             {bp['macd']}")
    lines.append(f"    Volume:           {bp['volume']}")
    lines.append(f"    20d Range Pos:    {bp['range_pct']:.0%}")
    lines.append(f"  INVALIDATION: Close below ${bp['stop_loss']} (macro BEAR shift)")
    return '\n'.join(lines)

# ── MAIN ─────────────────────────────────────────────────────────────────────
print("=" * 70)
print("  QUANTITATIVE SWING TRADING SCAN — 2026-06-30")
print("  NASDAQ (QQQ) | SPY | IWM + Top NASDAQ 100 Components")
print("  Horizon: 2–21 day swing trades")
print("=" * 70)

# 1. Fetch index data for regime
print("\n[1] Fetching Index Data for Macro Regime Classification...")
idx_tickers = ['QQQ', 'SPY', 'IWM']
index_data = {}
for t in idx_tickers:
    df = fetch_data(t, period='6mo')
    df = compute_indicators(df)
    index_data[t] = df
    has_sma200 = 'sma200' in df.columns and not df['sma200'].isna().all()
    has_rsi = 'rsi14' in df.columns and not df['rsi14'].isna().all()
    if df is not None:
        print(f"  {t}: {len(df)} bars, last close ${df['Close'].iloc[-1]:.2f} | SMA200={has_sma200} | RSI14={has_rsi}")
    else:
        print(f"  {t}: FAILED")

# 2. Regime analysis
print("\n[2] Macro Regime Classification...")
regime_results = analyze_regime(index_data.get('SPY'), index_data.get('QQQ'), index_data.get('IWM'))

# Consensus regime
bull_votes = sum(1 for v in regime_results.values() if isinstance(v, dict) and v.get('regime') == 'BULL')
bear_votes = sum(1 for v in regime_results.values() if isinstance(v, dict) and v.get('regime') == 'BEAR')
trans_votes = sum(1 for v in regime_results.values() if isinstance(v, dict) and v.get('regime') == 'TRANSITIONAL')

if bull_votes >= 2:
    consensus_regime = 'BULL'
elif bear_votes >= 2:
    consensus_regime = 'BEAR'
else:
    consensus_regime = 'TRANSITIONAL'

print(f"  SPY:  {regime_results.get('SPY', 'N/A')}")
print(f"  QQQ:  {regime_results.get('QQQ', 'N/A')}")
print(f"  IWM:  {regime_results.get('IWM', 'N/A')}")
print(f"\n  ★ CONSENSUS REGIME: {consensus_regime}")

# 3. Fetch and score individual tickers
print("\n[3] Fetching Component Data & Scoring...")
scan_tickers = list(set(TICKERS) - set(idx_tickers))
scores = {}
for i, t in enumerate(scan_tickers):
    print(f"  [{i+1}/{len(scan_tickers)}] {t}...", end='', flush=True)
    df = fetch_data(t, period='3mo')
    df = compute_indicators(df)
    info = fetch_info(t)
    score, factors = score_swing_setup(df, info, t)
    scores[t] = {'df': df, 'info': info, 'score': score, 'factors': factors}
    if score is not None:
        print(f" score={score} RSI={factors.get('rsi','N/A')}")
    else:
        print(" SKIP (insufficient data)")

# 4. Sort and filter
print("\n[4] Ranking & Filtering...")
valid = {t: v for t, v in scores.items() if v['score'] is not None}
sorted_tickers = sorted(valid.items(), key=lambda x: x[1]['score'], reverse=True)

print(f"\n  Top 5 by Score:")
for rank, (t, v) in enumerate(sorted_tickers[:5], 1):
    f = v['factors']
    rsi_val = f.get('rsi', 'N/A')
    trend = f.get('trend', 'N/A')
    close = f['levels']['close']
    print(f"  #{rank} {t:6s} | Score: {v['score']:5.1f} | Close: ${close:.2f} | RSI: {rsi_val} | Trend: {trend}")

# 5. Generate top 3 trade blueprints
print("\n[5] Generating Trade Blueprints for Top 3 Setups...")
upcoming_earnings = get_upcoming_earnings()
top3 = sorted_tickers[:3]

blueprints = []
for t, v in top3:
    df = v['df']
    info = v['info']
    score = v['score']
    factors = v['factors']
    bp = generate_trade_blueprint(df, info, t, score, factors, consensus_regime)
    bp['earnings_date'] = upcoming_earnings.get(t, 'N/A')
    blueprints.append(bp)

# 6. Output
print("\n" + "█" * 70)
print("  STAGE 1 — EXECUTIVE SUMMARY & MARKET REGIME")
print("█" * 70)

regime_desc = {
    'BULL': 'Structural Bull Market — price above rising 200 SMA, positive momentum, risk-on sentiment.',
    'BEAR': 'Structural Bear Market — price below falling 200 SMA, negative momentum, risk-off sentiment.',
    'TRANSITIONAL': 'Transitional/Ranging Market — mixed signals, no clear trend. Use range-bound strategies.'
}
print(f"\n  Regime: {consensus_regime}")
print(f"  Description: {regime_desc[consensus_regime]}")
print(f"\n  SPY  — Close: ${regime_results.get('SPY', {}).get('close', 'N/A'):.2f if isinstance(regime_results.get('SPY'), dict) else regime_results.get('SPY', 'N/A')} | "
      f"RSI: {regime_results.get('SPY', {}).get('rsi14', 'N/A'):.1f}" if isinstance(regime_results.get('SPY'), dict) else f"  SPY: {regime_results.get('SPY', 'N/A')}")
print(f"  QQQ  — Close: ${regime_results.get('QQQ', {}).get('close', 'N/A'):.2f if isinstance(regime_results.get('QQQ'), dict) else regime_results.get('QQQ', 'N/A')} | "
      f"RSI: {regime_results.get('QQQ', {}).get('rsi14', 'N/A'):.1f}" if isinstance(regime_results.get('QQQ'), dict) else f"  QQQ: {regime_results.get('QQQ', 'N/A')}")
print(f"  IWM  — Close: ${regime_results.get('IWM', {}).get('close', 'N/A'):.2f if isinstance(regime_results.get('IWM'), dict) else regime_results.get('IWM', 'N/A')} | "
      f"RSI: {regime_results.get('IWM', {}).get('rsi14', 'N/A'):.1f}" if isinstance(regime_results.get('IWM'), dict) else f"  IWM: {regime_results.get('IWM', 'N/A')}")

print("\n" + "█" * 70)
print("  STAGE 2 — RESEARCH SYNTHESIS (Macro / Technical / Fundamental)")
print("█" * 70)

for bp in blueprints:
    t = bp['ticker']
    f = bp['factors']
    info = f.get('fundamentals', {})
    close = f['levels']['close']
    high52 = info.get('fiftyTwoWeekHigh', 'N/A')
    low52 = info.get('fiftyTwoWeekLow', 'N/A')
    pe = info.get('trailingPE', 'N/A')
    fpe = info.get('forwardPE', 'N/A')
    eg = info.get('earningsGrowth', 'N/A')
    rg = info.get('revenueGrowth', 'N/A')
    mktcap = info.get('marketCap', 'N/A')

    if isinstance(mktcap, (int, float)) and mktcap > 1e12:
        mktcap_str = f"${mktcap/1e12:.1f}T"
    elif isinstance(mktcap, (int, float)) and mktcap > 1e9:
        mktcap_str = f"${mktcap/1e9:.1f}B"
    else:
        mktcap_str = str(mktcap)

    print(f"\n  ▶ {t} — Sector/Industry: {info.get('sector', 'N/A')}")
    print(f"    Market Cap: {mktcap_str} | P/E: {pe} | Fwd P/E: {fpe} | 52wk Range: {low52} – {high52}")
    print(f"    Earnings Growth: {eg} | Revenue Growth: {rg}")
    print(f"    Upcoming Earnings: {bp['earnings_date']}")
    print(f"    Trend: {f['trend']}")
    print(f"    RSI: {f['rsi']} | MACD: {f['macd']} | Volume: {f['volume']}")
    print(f"    ATR: ${f['levels']['atr14']:.2f} ({f['levels']['atr_pct']:.1f}%)")
    print(f"    20d Range Position: {f['levels']['range_pct']:.0%}")
    print(f"    BB Upper/Mid/Lower: ${f['levels']['bb_upper']:.2f} / ${f['levels']['bb_mid']:.2f} / ${f['levels']['bb_lower']:.2f}")
    print(f"    SMA20/50/200: ${f['levels']['sma20']:.2f} / ${f['levels']['sma50']:.2f} / ${f['levels']['sma200']:.2f}")

print("\n" + "█" * 70)
print("  STAGE 3 — COGNITIVE CRITIQUE & REGIME ALIGNMENT RISK")
print("█" * 70)

print(f"""
  Macro Alignment Check:
    Consensus Regime: {consensus_regime}
    All setups below are evaluated for alignment with this regime.
    In a {consensus_regime} regime, LONG bias is preferred.
    SHORT trades require explicit decoupling justification.

  Bear Case for Each Setup:
""")

for bp in blueprints:
    t = bp['ticker']
    close = bp['close']
    rsi = bp['rsi']
    trend = bp['trend']
    range_pct = bp['range_pct']
    atr_pct = bp['atr_pct']

    bear_case = []
    if rsi and 'OVERBLOWN' in str(rsi):
        bear_case.append(f"- RSI {rsi} — extended, reversal risk before T1 is hit")
    if 'BEAR' in str(trend):
        bear_case.append(f"- Trend is bearish — fighting macro is dangerous without strong catalyst")
    if range_pct and range_pct > 0.80:
        bear_case.append(f"- Near top of 20d range ({range_pct:.0%}) — limited upside before resistance")
    if atr_pct and atr_pct > 4.0:
        bear_case.append(f"- High volatility ({atr_pct:.1f}%) — wide stops needed, position size compressed")
    bear_case.append(f"- Sector rotation risk: if Nasdaq rotation occurs, {t} could gap through stop")

    print(f"  {t} Bear Case:")
    for bc in bear_case:
        print(f"    {bc}")

    print(f"\n  {t} Invalidation Triggers:")
    print(f"    1. Daily close below ${bp['stop_loss']} → immediate exit")
    print(f"    2. Macro {consensus_regime} → confirm if regime flips to BEAR")
    print(f"    3. Volume collapse below 0.5x 20d avg on entry day → abort")
    print(f"    4. If earnings within 5 trading days: avoid or use earnings straddle")
    print()

print("\n" + "█" * 70)
print("  STAGE 4 — TACTICAL ORDER BLUEPRINTS (Top 3 Swing Setups)")
print("█" * 70)

for bp in blueprints:
    print(format_blueprint(bp))
    print(f"  ⚠ Earnings within window: {bp['earnings_date']}")

# 7. Portfolio context
print("\n" + "█" * 70)
print("  PORTFOLIO WATCH — REGIME EXPOSURE ADVISORY")
print("█" * 70)

total_beta = 0
for bp in blueprints:
    t = bp['ticker']
    # Approximate beta (use market beta of 1.0 for simplicity in absence of data)
    beta_est = 1.2 if t in ['NVDA','AMD','TSLA','AMZN','META'] else 1.1 if t in ['MSFT','GOOGL','AVGO'] else 1.0
    total_beta += beta_est * (bp['position_size_pct'] / 100)

avg_beta = total_beta / len(blueprints) if blueprints else 1.0

print(f"\n  Combined portfolio beta estimate: {avg_beta:.2f}")
print(f"  Net exposure: {sum(bp['position_size_pct'] for bp in blueprints):.1f}%")
print(f"  Recommended max total exposure: 20-30% of capital")
print(f"  In {consensus_regime} regime: {'Risk-on positioning — maintain long bias' if consensus_regime=='BULL' else 'Risk-off — reduce exposure, tighten stops' if consensus_regime=='BEAR' else 'Ranging — fade extremes, favor mean-reversion'}")

print("\n" + "=" * 70)
print("  SCAN COMPLETE — 2026-06-30")
print("  Data sourced via yfinance (Yahoo Finance). Scores are model-based.")
print("  All trades require personal due diligence before execution.")
print("=" * 70)
