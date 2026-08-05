import yfinance as yf
import json
import pandas as pd

def compute_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def compute_atr(hist, period=14):
    high = hist['High']
    low = hist['Low']
    close = hist['Close']
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    return atr

focus = ['AMD', 'TSLA', 'META', 'PANW', 'AVGO', 'NVDA', 'AAPL', 'AMZN', 'MSFT']

results = {}
for t in focus:
    tk = yf.Ticker(t)
    hist = tk.history(period='60d', interval='1d')
    info = tk.info
    
    if hist is None or len(hist) < 20:
        continue
    
    close = hist['Close']
    rsi = compute_rsi(close, 14)
    atr = compute_atr(hist, 14)
    
    ret_5d = float(close.iloc[-1] / close.iloc[-6] - 1) * 100 if len(close) > 5 else 0
    ret_10d = float(close.iloc[-1] / close.iloc[-11] - 1) * 100 if len(close) > 10 else 0
    ret_20d = float(close.iloc[-1] / close.iloc[-21] - 1) * 100 if len(close) > 20 else 0
    
    hi20 = float(close.rolling(20).max().iloc[-1])
    lo20 = float(close.rolling(20).min().iloc[-1])
    price_pos_20d = float((close.iloc[-1] - lo20) / (hi20 - lo20) * 100) if (hi20 - lo20) > 0 else 50
    
    bb_mid = float(close.rolling(20).mean().iloc[-1])
    bb_std = float(close.rolling(20).std().iloc[-1])
    bb_upper = bb_mid + 2*bb_std
    bb_lower = bb_mid - 2*bb_std
    bb_pos = float((close.iloc[-1] - bb_lower) / (bb_upper - bb_lower) * 100) if (bb_upper - bb_lower) > 0 else 50
    
    sma20 = float(close.rolling(20).mean().iloc[-1])
    sma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
    ema12 = float(close.ewm(span=12).mean().iloc[-1])
    ema26 = float(close.ewm(span=26).mean().iloc[-1])
    macd = ema12 - ema26
    signal = float(close.ewm(span=26).mean().ewm(span=9).mean().iloc[-1])
    macd_hist = macd - signal
    
    vol_sma20 = float(hist['Volume'].rolling(20).mean().iloc[-1])
    vol_today = float(hist['Volume'].iloc[-1])
    vol_ratio = vol_today / vol_sma20 if vol_sma20 > 0 else 1
    
    # 10d swing levels
    swing_high_10d = float(hist['High'].rolling(10).max().iloc[-1])
    swing_low_10d = float(hist['Low'].rolling(10).min().iloc[-1])
    
    # Fibonacci levels (from 20d low to 20d high)
    fib_382 = lo20 + (hi20 - lo20) * 0.382
    fib_618 = lo20 + (hi20 - lo20) * 0.618
    fib_786 = lo20 + (hi20 - lo20) * 0.786
    
    results[t] = {
        'price': round(float(close.iloc[-1]), 2),
        'ret_5d': round(ret_5d, 2),
        'ret_10d': round(ret_10d, 2),
        'ret_20d': round(ret_20d, 2),
        'rsi14': round(float(rsi.iloc[-1]), 1),
        'atr14': round(float(atr.iloc[-1]), 2),
        'hi20': round(hi20, 2),
        'lo20': round(lo20, 2),
        'price_pos_20d': round(price_pos_20d, 0),
        'bb_upper': round(bb_upper, 2),
        'bb_mid': round(bb_mid, 2),
        'bb_lower': round(bb_lower, 2),
        'bb_pos': round(bb_pos, 0),
        'sma20': round(sma20, 2),
        'sma50': round(sma50, 2) if sma50 else None,
        'macd': round(macd, 3),
        'macd_hist': round(macd_hist, 3),
        'vol_ratio': round(vol_ratio, 2),
        'swing_high_10d': round(swing_high_10d, 2),
        'swing_low_10d': round(swing_low_10d, 2),
        'fib_382': round(fib_382, 2),
        'fib_618': round(fib_618, 2),
        'fib_786': round(fib_786, 2),
        'market_cap': info.get('marketCap'),
        'pe_ratio': info.get('trailingPE'),
        'beta': info.get('beta'),
        'earnings_next': info.get('earningsNext'),
    }

with open('/opt/data/handbook/swing_deep.json', 'w') as f:
    json.dump(results, f, indent=2)

for t, d in results.items():
    print(f"\n{'='*60}")
    print(f"{t}: ${d['price']}  |  5d:{d['ret_5d']:+.1f}%  10d:{d['ret_10d']:+.1f}%  20d:{d['ret_20d']:+.1f}%")
    print(f"  RSI(14)={d['rsi14']}  ATR=${d['atr14']}  Vol Ratio={d['vol_ratio']}x")
    print(f"  20d Hi:${d['hi20']}  20d Lo:${d['lo20']}  Pos in range:{d['price_pos_20d']:.0f}%")
    print(f"  BB Upper:${d['bb_upper']}  BB Mid:${d['bb_mid']}  BB Lower:${d['bb_lower']}  BB Pos:{d['bb_pos']:.0f}%")
    print(f"  SMA20:${d['sma20']}  SMA50:${d['sma50']}")
    print(f"  MACD={d['macd']}  MACD Hist={d['macd_hist']}")
    print(f"  10d Swing H:${d['swing_high_10d']}  10d Swing L:${d['swing_low_10d']}")
    print(f"  Fib 38.2%:${d['fib_382']}  Fib 61.8%:${d['fib_618']}  Fib 78.6%:${d['fib_786']}")
    if d.get('earnings_next'):
        print(f"  Next Earnings: {d['earnings_next']}")
