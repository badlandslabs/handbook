import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

print("=== VIX / FEAR INDEX ===")
vix = yf.Ticker("^VIX").history(period="5d")
if len(vix):
    print(f"  VIX: {vix['Close'].iloc[-1]:.2f}  (high={vix['High'].iloc[-1]:.2f}, low={vix['Low'].iloc[-1]:.2f})")
else:
    print("  VIX data unavailable")

print("\n=== CREDIT SPREAD (RISK SENTIMENT) ===")
hyg = yf.Ticker("HYG").history(period="5d")
lqd = yf.Ticker("LQD").history(period="5d")
if len(hyg) and len(lqd):
    print(f"  HYG: {hyg['Close'].iloc[-1]:.2f}  LQD: {lqd['Close'].iloc[-1]:.2f}")
    print(f"  HYG/LQD ratio: {hyg['Close'].iloc[-1]/lqd['Close'].iloc[-1]:.4f}")

print("\n=== DOLLAR INDEX ===")
dxy = yf.Ticker("DXY").history(period="5d")
if len(dxy):
    print(f"  DXY: {dxy['Close'].iloc[-1]:.2f}")

print("\n=== 20Y TREASURY (TLT) ===")
tlt = yf.Ticker("TLT").history(period="5d")
if len(tlt):
    chg = (tlt['Close'].iloc[-1] - tlt['Close'].iloc[-5]) / tlt['Close'].iloc[-5] * 100
    print(f"  TLT: {tlt['Close'].iloc[-1]:.2f}  5d change: {chg:+.1f}%")

print("\n=== SMALL CAP BREADTH (IWM/SPY) ===")
iwmy = yf.Ticker("IWM").history(period="20d")
spyy = yf.Ticker("SPY").history(period="20d")
if len(iwmy) and len(spyy):
    ratio = (iwmy['Close'] / spyy['Close'] * 10)
    print(f"  Ratio 20d: {ratio.iloc[0]:.4f} -> {ratio.iloc[-1]:.4f}  {('RISING' if ratio.iloc[-1] > ratio.iloc[0] else 'FALLING')}")

print("\n=== SECTOR ROTATION (20d vs SPY) ===")
xlk = yf.Ticker("XLK").history(period="20d")
xly = yf.Ticker("XLY").history(period="20d")
xlu = yf.Ticker("XLU").history(period="20d")
spy_s = yf.Ticker("SPY").history(period="20d")
for name, ticker in [("XLK (Tech)", xlk), ("XLY (Disc)", xly), ("XLU (Utils)", xlu)]:
    if len(ticker) and len(spy_s):
        rel = ticker['Close'].iloc[-1] / ticker['Close'].iloc[0] * 100 - 100
        print(f"  {name}: {rel:+.1f}% (20d)")

print("\n=== UPGRADES / DOWNGRADES (last 7 days) ===")
for ticker_sym in ['AAPL', 'NVDA', 'META', 'AMD', 'AVGO', 'AMZN']:
    t = yf.Ticker(ticker_sym)
    try:
        recs = t.recommendations.tail(5)
        if len(recs):
            last = recs.iloc[-1]
            print(f"  {ticker_sym}: {last.get('Grade', 'N/A') if hasattr(last, 'get') else last}  action={last.get('Action', 'N/A')}")
    except:
        pass
