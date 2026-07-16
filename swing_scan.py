#!/usr/bin/env python3
"""
NASDAQ Swing Trade Scanner
Fetches real-time data for QQQ, SPY, IWM, VIX, and top NASDAQ-100 components.
"""
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

now = datetime.now()
print(f"Scan date: {now.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"Day: {now.strftime('%A')}")
print("="*70)

# ── 1. Major Indices ──────────────────────────────────────────────────────────
indices = [('QQQ','QQQ'), ('SPY','SPY'), ('IWM','IWM'), ('VIX','^VIX'), ('DXY','UUP')]
idx_data = {}
for name, ticker in indices:
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period='6mo', interval='1d')
        hist = hist[hist['Close'].notna()]  # drop trailing NaN placeholder rows
        if len(hist) > 50:
            close = hist['Close'].iloc[-1]
            prev  = hist['Close'].iloc[-2]
            sma20 = hist['Close'].rolling(20).mean().iloc[-1]
            sma50 = hist['Close'].rolling(50).mean().iloc[-1]
            sma200= hist['Close'].rolling(200).mean().iloc[-1]
            rsi14 = hist['Close'].rolling(14).apply(lambda x: 100 - 100/(1+((x.diff().where(x.diff()>0)).dropna().rolling(14).mean()/-((x.diff().where(x.diff()<0)).dropna().rolling(14).mean())).iloc[-1]) if len(x.dropna())>=14 else 50).iloc[-1]
            pct   = (close - prev) / prev * 100
            vol20 = hist['Volume'].rolling(20).mean().iloc[-1]
            curvol= hist['Volume'].iloc[-1]
            idx_data[name] = {'close':close,'prev':prev,'sma20':sma20,'sma50':sma50,
                              'sma200':sma200,'rsi14':rsi14,'pct':pct,
                              'vol20':vol20,'curvol':curvol,'hist':hist}
            print(f"{name}: ${close:.2f} ({pct:+.2f}%) | SMA20={sma20:.2f} SMA50={sma50:.2f} SMA200={sma200:.2f} | Vol={curvol/vol20:.1f}x20d")
    except Exception as e:
        print(f"Error loading {name}: {e}")

print()

# ── 2. Top NASDAQ-100 Components ──────────────────────────────────────────────
nasdaq100 = [
    'AAPL','MSFT','NVDA','GOOGL','AMZN','META','TSLA','AVGO','AMD','ORCL',
    'CRM','ADBE','CSCO','MU','INTC','QCOM','AMAT','LRCX','KLAC','PANW',
    'NFLX','INTU','TXN','AMGN','ISRG','GILD','BKNG','MDLZ','REGN','ADP',
    'FISV','NXPI','SNPS','CDNS','MELI','ADI','MRVL','MAR','PCAR','TEAM',
    'CTAS','FAST','CSGP','DDOG','CRWD','ON','TTD','APP','GEHC','VRTX',
    'HON','PAYX','CTSH','ABNB','TTWO','WDAY','ZM','COIN','EXC','PYPL',
    'EA','ILMN','LCID','RIVN','PLTR','SE','SNOW','WBD','DOCU','ROKU'
]

# Deduplicate
nasdaq100 = list(dict.fromkeys(nasdaq100))

results = []
for ticker in nasdaq100:
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period='3mo', interval='1d')
        hist = hist[hist['Close'].notna()]  # drop trailing NaN rows
        if len(hist) < 30:
            continue
        close  = hist['Close'].iloc[-1]
        prev   = hist['Close'].iloc[-2] if len(hist) > 1 else close
        sma20  = hist['Close'].rolling(20).mean().iloc[-1]
        sma50  = hist['Close'].rolling(50).mean().iloc[-1]
        sma200 = hist['Close'].rolling(200).mean().iloc[-1]
        high52w= hist['High'].rolling(252).max().iloc[-1]
        low52w = hist['Low'].rolling(252).min().iloc[-1]
        pct5   = (close - hist['Close'].iloc[-6]) / hist['Close'].iloc[-6] * 100
        pct20  = (close - hist['Close'].iloc[-21]) / hist['Close'].iloc[-21] * 100
        vol20  = hist['Volume'].rolling(20).mean().iloc[-1]
        curvol = hist['Volume'].iloc[-1]
        vratio = curvol / vol20 if vol20 > 0 else 0

        # ATR (14-day)
        tr1 = hist['High'] - hist['Low']
        tr2 = abs(hist['High'] - hist['Close'].shift(1))
        tr3 = abs(hist['Low']  - hist['Close'].shift(1))
        tr  = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr14 = tr.rolling(14).mean().iloc[-1]

        # RSI-14
        delta = hist['Close'].diff()
        gain  = delta.where(delta > 0, 0).rolling(14).mean()
        loss  = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs    = gain / loss
        rsi14 = (100 - 100/(1+rs)).iloc[-1]

        # MACD (12,26,9)
        ema12 = hist['Close'].ewm(span=12, adjust=False).mean().iloc[-1]
        ema26 = hist['Close'].ewm(span=26, adjust=False).mean().iloc[-1]
        macd_line = ema12 - ema26
        macd_sig  = hist['Close'].ewm(span=12, adjust=False).mean().ewm(span=9, adjust=False).mean().iloc[-1] - \
                    hist['Close'].ewm(span=26, adjust=False).mean().ewm(span=9, adjust=False).mean().iloc[-1]
        macd_hist = macd_line - macd_sig

        # Slope of SMA20
        slope20 = (sma20 - hist['Close'].rolling(20).mean().iloc[-5]) / 5 if len(hist) > 5 else 0

        results.append({
            'ticker': ticker,
            'close': close, 'prev': prev,
            'sma20': sma20, 'sma50': sma50, 'sma200': sma200,
            'high52': high52w, 'low52': low52w,
            'pct5': pct5, 'pct20': pct20,
            'vol20': vol20, 'curvol': curvol, 'vratio': vratio,
            'atr14': atr14, 'rsi14': rsi14,
            'macd': macd_line, 'macd_sig': macd_sig, 'macd_hist': macd_hist,
            'slope20': slope20,
            'hist': hist
        })
    except Exception as e:
        pass

print(f"Loaded {len(results)} tickers successfully.\n")

# ── 3. Scoring & Filtering ─────────────────────────────────────────────────────
def score(r):
    s = 0
    # Above key SMAs
    if r['close'] > r['sma20']:  s += 2
    if r['close'] > r['sma50']:  s += 2
    if r['close'] > r['sma200']: s += 3
    # Trend direction
    if r['slope20'] > 0:         s += 2
    # MACD positive
    if r['macd_hist'] > 0:       s += 2
    # RSI not overbought
    if 40 < r['rsi14'] < 75:     s += 2
    elif 30 < r['rsi14'] <= 40:  s += 3  # oversold bounce
    # Volume surge
    if r['vratio'] > 1.5:        s += 1
    # Near 52w high
    if r['close'] > r['high52'] * 0.90: s += 2
    # Not too extended
    if r['pct20'] < 25:          s += 1
    return s

for r in results:
    r['score'] = score(r)

# Sort by score descending
results.sort(key=lambda x: x['score'], reverse=True)

print("TOP 10 SCORING TICKERS:")
print(f"{'Ticker':<8} {'Close':>8} {'RSI14':>6} {'MACD_h':>8} {'SMA20':>8} {'SMA50':>8} {'Score':>5} {'5d%':>7} {'20d%':>7} {'VolRat':>6} {'ATR14':>7}")
print("-"*95)
for r in results[:10]:
    print(f"{r['ticker']:<8} ${r['close']:>7.2f} {r['rsi14']:>6.1f} {r['macd_hist']:>8.3f} "
          f"${r['sma20']:>7.2f} ${r['sma50']:>7.2f} {r['score']:>5} {r['pct5']:>+6.1f}% {r['pct20']:>+6.1f}% "
          f"{r['vratio']:>5.1f}x {r['atr14']:>7.2f}")

print()

# ── 4. Sector Classification ───────────────────────────────────────────────────
sectors = {
    'Technology': ['AAPL','MSFT','NVDA','GOOGL','AMZN','META','TSLA','AVGO','AMD','ORACLE','CRM','ADBE','CSCO','MU','INTC','QCOM','AMAT','LRCX','KLAC','PANW','SNPS','CDNS','ADI','MRVL','NXPI'],
    'Biotech/HC' : ['AMGN','GILD','ISRG','REGN','VRTX','ILMN','MRNA'],
    'Consumer'  : ['NFLX','AMZN','BKNG','ABNB','MAR','COIN'],
    'Fin/Broker': ['PYPL','ADP','FISV','PAYX','CTSH','EA','TTWO','TEAM'],
    'Cloud/SW'  : ['DDOG','CRWD','SNOW','WDAY','ZM','DOCU','ROKU','TTD','APP'],
    'Semi'      : ['NVDA','AMD','AVGO','MU','INTC','QCOM','AMAT','LRCX','KLAC','ADI','MRVL','NXPI','ON'],
    'Indust/Fin': ['HON','PCAR','FAST','CSGP','CTAS','GEHC'],
}

# ── 5. Macro Regime Assessment ─────────────────────────────────────────────────
def assess_regime():
    if 'QQQ' not in idx_data or 'SPY' not in idx_data:
        return "TRANSITIONAL"
    q = idx_data['QQQ']
    s = idx_data['SPY']
    v = idx_data.get('VIX', {}).get('close', 20)
    bull = q['close'] > q['sma200'] and q['sma20'] > q['sma50']
    bear = q['close'] < q['sma200'] and q['sma20'] < q['sma50']
    if bull: return "BULL"
    if bear: return "BEAR"
    return "TRANSITIONAL"

regime = assess_regime()
vix_close = idx_data.get('VIX', {}).get('close', 'N/A')
print(f"==> MACRO REGIME: {regime}")
print(f"==> VIX: {vix_close}")
print()

# ── 6. Build Swing Trade Setups ────────────────────────────────────────────────
print("="*70)
print("TOP SWING TRADE SETUPS (2-21 day horizon):")
print("="*70)

# Filter: RSI not overbought, not extended >25% in 20d, positive MACD hist, above SMA20
setups = [r for r in results if 
    r['rsi14'] < 70 and r['rsi14'] > 30 and
    r['macd_hist'] > 0 and
    r['close'] > r['sma20'] and
    r['pct20'] < 30 and
    r['vratio'] > 0.8
][:8]

for i, r in enumerate(setups[:5], 1):
    ticker = r['ticker']
    close  = r['close']
    atr    = r['atr14']
    rsi    = r['rsi14']
    
    # Support: SMA20 or recent swing low
    hist = r['hist']
    swing_low = hist['Low'].iloc[-20:].min()
    support   = max(swing_low, r['sma20'] * 0.97)
    
    # Resistance: recent high or 52w high
    resistance = min(r['high52'], hist['High'].iloc[-20:].max())
    
    # Targets
    t1 = close + (close - support) * 2.0   # 2:1
    t2 = close + (close - support) * 3.0   # 3:1
    stop = support - atr * 0.5
    
    rr1 = (t1 - close) / (close - stop)
    rr2 = (t2 - close) / (close - stop)
    
    print(f"\nSETUP #{i}: {ticker}")
    print(f"  Price: ${close:.2f}  |  RSI: {rsi:.1f}  |  ATR14: ${atr:.2f}")
    print(f"  SMA20: ${r['sma20']:.2f}  SMA50: ${r['sma50']:.2f}  SMA200: ${r['sma200']:.2f}")
    print(f"  MACD Histogram: {r['macd_hist']:.4f} (positive = bullish momentum)")
    print(f"  5d: {r['pct5']:+.1f}%  20d: {r['pct20']:+.1f}%  VolRatio: {r['vratio']:.1f}x")
    print(f"  Support: ${support:.2f}  Resistance: ${resistance:.2f}")
    print(f"  Stop Loss: ${stop:.2f}  |  T1 (2:1): ${t1:.2f}  |  T2 (3:1): ${t2:.2f}")
    print(f"  Reward/Risk T1: {rr1:.1f}:1  |  Reward/Risk T2: {rr2:.1f}:1")

print()
print("="*70)
print("Done scanning.")
