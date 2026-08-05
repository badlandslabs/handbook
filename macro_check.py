import yfinance as yf
import pandas as pd

symbols = ['^VIX', '^VXN', 'TLT', 'HYG', 'GLD', 'DXY']
for sym in symbols:
    try:
        tk = yf.Ticker(sym)
        hist = tk.history(period='10d', interval='1d')
        if hist is not None and len(hist) > 0:
            close = hist['Close'].iloc[-1]
            prev = hist['Close'].iloc[-2] if len(hist) > 1 else close
            pct = (close - prev) / prev * 100
            print(f"{sym}: {close:.2f} ({pct:+.2f}%)")
    except Exception as e:
        print(f"{sym}: unavailable - {e}")

tk = yf.Ticker('QQQ')
weekly = tk.history(period='1y', interval='1wk')
if weekly is not None and len(weekly) > 0:
    print(f"\nQQQ Weekly: Last close {weekly['Close'].iloc[-1]:.2f}")
    if len(weekly) >= 10:
        pct_10wk = (weekly['Close'].iloc[-1] / weekly['Close'].iloc[-10] - 1) * 100
        print(f"  10-week return: {pct_10wk:+.1f}%")
    print(f"  Last 4 weekly closes: {list(weekly['Close'].tail(4).round(2))}")
