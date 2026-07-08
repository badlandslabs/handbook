import yfinance as yf
import pandas as pd
import numpy as np

tickers = ['QQQ', 'SPY', 'NVDA', 'ASML', 'PEP', 'TSLA', 'MSFT', 'GOOGL', 'META', 'AAPL']
results = {}
for t in tickers:
    try:
        tk = yf.Ticker(t)
        hist = tk.history(period='6mo')
        if len(hist) < 20:
            print(f"{t}: INSUFFICIENT DATA")
            continue
        closes = hist['Close']
        vol = hist['Volume']
        latest_close = closes.iloc[-1]
        latest_date = hist.index[-1].date()
        sma20 = closes.iloc[-20:].mean()
        sma50 = closes.iloc[-50:].mean() if len(closes) >= 50 else closes.mean()
        sma200 = closes.iloc[-200:].mean() if len(closes) >= 200 else closes.mean()
        vol_avg20 = vol.iloc[-20:].mean()
        # ATR proxy: 14-day
        high = hist['High']
        low = hist['Low']
        prev_close = closes.shift(1)
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr14 = tr.iloc[-14:].mean()
        # RSI(14)
        delta = closes.diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.iloc[-14:].mean()
        avg_loss = loss.iloc[-14:].mean()
        rs = avg_gain / avg_loss if avg_loss != 0 else 100
        rsi = 100 - (100/(1+rs))
        # 52wk
        high52 = closes.iloc[-252:].max() if len(closes) >= 252 else closes.max()
        low52 = closes.iloc[-252:].min() if len(closes) >= 252 else closes.min()
        above_20ema = latest_close > sma20
        above_50sma = latest_close > sma50
        above_200sma = latest_close > sma200
        pct_52wk = (latest_close - low52) / (high52 - low52) * 100 if high52 != low52 else 50
        results[t] = {
            'date': latest_date, 'close': latest_close,
            'sma20': sma20, 'sma50': sma50, 'sma200': sma200,
            'atr14': atr14, 'rsi14': rsi,
            'vol_avg20': vol_avg20,
            'high52': high52, 'low52': low52,
            'above_20ema': above_20ema, 'above_50sma': above_50sma, 'above_200sma': above_200sma,
            'pct_52wk': pct_52wk,
        }
        print(f"{t}: close={latest_close:.2f} ({latest_date}), 20ema={sma20:.2f}, 50sma={sma50:.2f}, 200sma={sma200:.2f}, ATR14={atr14:.2f}, RSI14={rsi:.1f}, vol20={vol_avg20:.0f}, above20={above_20ema}, above50={above_50sma}, above200={above_200sma}, pct_52wk={pct_52wk:.1f}%")
    except Exception as e:
        print(f"{t}: ERROR {e}")

# VIX
try:
    vix = yf.Ticker('^VIX')
    vh = vix.history(period='5d')
    if len(vh) > 0:
        print(f"\nVIX: close={vh['Close'].iloc[-1]:.2f} on {vh.index[-1].date()}")
except Exception as e:
    print(f"VIX error: {e}")

# SP500 level
try:
    spy = yf.Ticker('SPY')
    sph = spy.history(period='5d')
    if len(sph) > 0:
        print(f"SPY: close={sph['Close'].iloc[-1]:.2f} on {sph.index[-1].date()}")
except Exception as e:
    print(f"SPY error: {e}")

# High-yield spread
try:
    hy = yf.Ticker('HYG')
    ih = hy.history(period='5d')
    ie = yf.Ticker('IEF')
    ieh = ie.history(period='5d')
    if len(ih) > 0 and len(ieh) > 0:
        spread = (ih['Close'].iloc[-1] / ieh['Close'].iloc[-1]) * 100
        print(f"HYG/IEF ratio: {spread:.2f}")
except Exception as e:
    print(f"Credit spread error: {e}")
