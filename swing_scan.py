import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

today = datetime.now().strftime('%Y-%m-%d')

TICKERS = ['QQQ', 'SPY', 'IWM',
           'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'TSLA',
           'AMD', 'AVGO', 'NFLX', 'CRM', 'ORCL', 'ADBE', 'QCOM', 'INTC',
           'PANW', 'SNOW', 'DDOG', 'MU', 'LRCX', 'KLAC', 'AMAT']

def fetch_data(ticker, period='5mo'):
    try:
        t = yf.Ticker(ticker)
        df = t.history(period=period, auto_adjust=True)
        return df
    except Exception as e:
        return None

def compute_indicators(df):
    df = df.copy()
    df['sma20'] = df['Close'].rolling(20).mean()
    df['sma50'] = df['Close'].rolling(50).mean()
    df['sma200'] = df['Close'].rolling(200).mean()
    df['ema20'] = df['Close'].ewm(span=20).mean()
    df['ema50'] = df['Close'].ewm(span=50).mean()

    delta = df['Close'].diff()
    gain = delta.clip(lower=0).ewm(alpha=2/14).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=2/14).mean()
    rs = gain / loss.replace(0, np.nan)
    df['rsi'] = 100 - (100 / (1 + rs))

    exp1 = df['Close'].ewm(span=12).mean()
    exp2 = df['Close'].ewm(span=26).mean()
    df['macd'] = exp1 - exp2
    df['macd_signal'] = df['macd'].ewm(span=9).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']

    df['atr'] = (df['High'] - df['Low']).rolling(14).mean()
    df['volume_sma20'] = df['Volume'].rolling(20).mean()
    df['vol_ratio'] = df['Volume'] / df['volume_sma20']
    df['daily_return'] = df['Close'].pct_change()
    df['volatility_20'] = df['daily_return'].rolling(20).std() * np.sqrt(252)

    return df

def analyze_ticker(ticker):
    df = fetch_data(ticker)
    if df is None or len(df) < 60:
        return None

    df = compute_indicators(df)

    # Fill sma200/sma50 if insufficient history
    for col in ['sma200', 'sma50', 'sma20']:
        if col not in df.columns or df[col].isna().all():
            df[col] = df['Close'].rolling(min({'sma200': 200, 'sma50': 50, 'sma20': 20}[col], len(df))).mean()

    cur = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else cur

    price = cur['Close']

    above_200sma = price > cur['sma200'] if not pd.isna(cur['sma200']) else None
    above_50sma = price > cur['sma50'] if not pd.isna(cur['sma50']) else None
    above_20sma = price > cur['sma20'] if not pd.isna(cur['sma20']) else None

    if above_200sma and above_50sma:
        trend = 'BULL'
    elif not above_200sma and not above_50sma:
        trend = 'BEAR'
    else:
        trend = 'TRANSITIONAL'

    rsi_val = cur['rsi'] if not pd.isna(cur['rsi']) else 50.0
    macd_bullish = cur['macd'] > cur['macd_signal'] if not (pd.isna(cur['macd']) or pd.isna(cur['macd_signal'])) else False
    macd_cross_recent = (prev['macd'] <= prev['macd_signal']) and (cur['macd'] > cur['macd_signal']) if len(df) >= 2 else False

    vol_ratio = float(cur['vol_ratio']) if not pd.isna(cur['vol_ratio']) else 1.0
    high_vol = vol_ratio > 1.5
    atr = float(cur['atr']) if not pd.isna(cur['atr']) else price * 0.02
    risk_pct = (atr / price) * 100

    # Slope of 20 SMA
    sma20_series = df['sma20'].dropna()
    slope_20 = 0.0
    if len(sma20_series) >= 11:
        slope_20 = (sma20_series.iloc[-1] - sma20_series.iloc[-11]) / sma20_series.iloc[-11] * 100

    # Momentum score
    score = 0
    if above_20sma: score += 1
    if above_50sma: score += 1
    if above_200sma: score += 1
    if 45 < rsi_val < 70: score += 1
    if rsi_val < 35: score -= 1
    if rsi_val > 75: score -= 1
    if macd_bullish: score += 1
    if macd_cross_recent: score += 2
    if high_vol: score += 1
    if slope_20 > 0.5: score += 1
    if above_20sma and above_50sma and above_200sma: score += 1

    ret_5d = float((price / df['Close'].iloc[-6] - 1) * 100) if len(df) > 5 else 0.0
    ret_10d = float((price / df['Close'].iloc[-11] - 1) * 100) if len(df) > 10 else 0.0
    ret_20d = float((price / df['Close'].iloc[-21] - 1) * 100) if len(df) > 20 else 0.0

    # Recent high/low context
    high_20 = df['High'].tail(20).max()
    low_20 = df['Low'].tail(20).min()
    near_high = (price / high_20 - 1) * 100 if high_20 > 0 else 0
    near_low = (price / low_20 - 1) * 100 if low_20 > 0 else 0

    return {
        'ticker': ticker,
        'price': float(price),
        'sma20': float(cur['sma20']) if not pd.isna(cur['sma20']) else None,
        'sma50': float(cur['sma50']) if not pd.isna(cur['sma50']) else None,
        'sma200': float(cur['sma200']) if not pd.isna(cur['sma200']) else None,
        'rsi': float(rsi_val),
        'macd_bullish': macd_bullish,
        'macd_cross': macd_cross_recent,
        'vol_ratio': vol_ratio,
        'atr': float(atr),
        'risk_pct': float(risk_pct),
        'above_200sma': above_200sma,
        'above_50sma': above_50sma,
        'above_20sma': above_20sma,
        'trend': trend,
        'score': score,
        'slope_20': float(slope_20),
        'ret_5d': ret_5d,
        'ret_10d': ret_10d,
        'ret_20d': ret_20d,
        'high_vol': high_vol,
        'high_20': float(high_20),
        'low_20': float(low_20),
        'near_high_pct': float(near_high),
        'near_low_pct': float(near_low),
        'volume': int(cur['Volume']) if not pd.isna(cur['Volume']) else 0,
        'date': str(cur.name.date()) if hasattr(cur.name, 'date') else today,
    }

# ─── FETCH ALL ─────────────────────────────────────────────────────────────
print("Fetching market data...")
results = {}
for t in TICKERS:
    print(f"  {t}...", end=' ', flush=True)
    r = analyze_ticker(t)
    if r:
        results[t] = r
        print(f"OK  price={r['price']:.2f}  RSI={r['rsi']:.1f}  score={r['score']}")
    else:
        print(f"FAILED (insufficient data)")

print(f"\n{len(results)}/{len(TICKERS)} tickers fetched.\n")

# ─── SUMMARY TABLE ───────────────────────────────────────────────────────────
print("="*100)
hdr = f"{'TICKER':<7} {'PRICE':>8} {'SMA20':>8} {'SMA50':>8} {'SMA200':>8} {'RSI':>5} {'MACD':>5} {'VOLx':>5} {'ATR%':>5} {'SCORE':>5} {'TREND':<14} {'5D%':>6} {'10D%':>6}"
print(hdr)
print("="*100)

sorted_results = sorted(results.items(), key=lambda x: x[1]['score'], reverse=True)
for ticker, r in sorted_results:
    macd_sym = "XOVER" if r['macd_cross'] else ("BULL" if r['macd_bullish'] else "BEAR")
    print(f"{ticker:<7} {r['price']:>8.2f} {r['sma20'] if r['sma20'] else 0:>8.2f} {r['sma50'] if r['sma50'] else 0:>8.2f} "
          f"{r['sma200'] if r['sma200'] else 0:>8.2f} {r['rsi']:>5.1f} {macd_sym:>5} "
          f"{r['vol_ratio']:>5.2f} {r['risk_pct']:>5.2f} {r['score']:>5} {r['trend']:<14} {r['ret_5d']:>6.1f} {r['ret_10d']:>6.1f}")

print()
print("="*100)
print("HIGH VOLUME + NEAR BREAKOUT SCANNER (vol > 1.5x avg AND near 20d high)")
print("="*100)
print(f"{'TICKER':<7} {'PRICE':>8} {'20dHIGH':>8} {'20dLOW':>8} {'nrHIGH%':>8} {'nrLOW%':>8} {'VOLx':>5} {'SCORE':>5}")
print("-"*100)
for ticker, r in sorted_results:
    if r['high_vol'] and r['near_high_pct'] > -3.0:
        print(f"{ticker:<7} {r['price']:>8.2f} {r['high_20']:>8.2f} {r['low_20']:>8.2f} {r['near_high_pct']:>8.1f} {r['near_low_pct']:>8.1f} {r['vol_ratio']:>5.2f} {r['score']:>5}")

print()
print("="*100)
print(f"DATA AS OF: {results.get('QQQ', {}).get('date', today)}")
print("="*100)
