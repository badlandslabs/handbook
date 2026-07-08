import yfinance as yf
import pandas as pd
import numpy as np

tickers = ['NVDA', 'PEP', 'TSLA', 'QQQ']
for t in tickers:
    tk = yf.Ticker(t)
    hist = tk.history(period='1mo')
    if len(hist) < 5:
        print(f"{t}: insufficient data")
        continue
    print(f"\n=== {t} - Last 20 Days ===")
    print(f"{'Date':<12} {'Close':>8} {'High':>8} {'Low':>8} {'Volume':>12} {'Range%':>7}")
    n = len(hist)
    for i in range(-min(n, 20), 0):
        dt = hist.index[i].date()
        c = hist['Close'].iloc[i]
        h = hist['High'].iloc[i]
        l = hist['Low'].iloc[i]
        v = hist['Volume'].iloc[i]
        rng = (h - l) / l * 100
        print(f"{dt}  {c:>8.2f}  {h:>8.2f}  {l:>8.2f}  {v:>12,.0f}  {rng:>6.2f}%")
    # Key stats
    closes = hist['Close']
    highs = hist['High']
    lows = hist['Low']
    print(f"\n20d High: {highs.iloc[-20:].max():.2f}  Low: {lows.iloc[-20:].min():.2f}")
    print(f"Support levels (recent lows): {lows.iloc[-10:].nsmallest(3).values}")
    print(f"Resistance levels (recent highs): {highs.iloc[-10:].nlargest(3).values}")
