#!/opt/data/handbook/venv/bin/python3
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def compute_indicators(df):
    close = df['Close']
    high = df['High']
    low = df['Low']
    volume = df['Volume']
    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()
    ema20 = close.ewm(span=20).mean()
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9).mean()
    macd_hist = macd - signal
    tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    atr14 = tr.rolling(14).mean()
    return {'Close': close, 'High': high, 'Low': low, 'Volume': volume,
            'MA20': ma20, 'MA50': ma50, 'EMA20': ema20,
            'RSI14': rsi, 'MACD_Hist': macd_hist, 'ATR14': atr14}

today = datetime.now().strftime('%Y-%m-%d')
start = (datetime.now() - timedelta(days=200)).strftime('%Y-%m-%d')

print("Fetching indices...")
idx_data = yf.download(['QQQ', 'SPY', 'IWM', '^VIX'], start=start, end=today, progress=False, auto_adjust=True)

for ticker in ['QQQ', 'SPY', 'IWM']:
    c = idx_data['Close'][ticker].dropna()
    h = idx_data['High'][ticker].dropna()
    l = idx_data['Low'][ticker].dropna()
    v = idx_data['Volume'][ticker].dropna()
    common = c.index.intersection(h.index).intersection(l.index).intersection(v.index)
    df = pd.DataFrame({'Close': c, 'High': h, 'Low': l, 'Volume': v}).loc[common]
    ind = compute_indicators(df)
    rsi = ind['RSI14'].iloc[-1]
    macd_hist = ind['MACD_Hist'].iloc[-1]
    atr14 = ind['ATR14'].iloc[-1]
    close = ind['Close'].iloc[-1]
    ma20 = ind['MA20'].iloc[-1]
    ma50 = ind['MA50'].iloc[-1]
    above_ma50 = close > ma50
    above_ma20 = close > ma20
    regime = 'BULL' if (above_ma50 and above_ma20 and ma20 > ma50) else ('BEAR' if (not above_ma50 and not above_ma20 and ma20 < ma50) else 'TRANSITIONAL')
    print(f"{ticker}: close={close:.2f} ma20={ma20:.2f} ma50={ma50:.2f} rsi={rsi:.1f} macdh={macd_hist:.4f} atr={atr14:.2f} atr%={(atr14/close)*100:.2f} regime={regime}")

vix_close = idx_data['Close']['^VIX'].dropna().iloc[-1]
print(f"VIX: {vix_close:.2f}")

# Recent 10-day prices for QQQ
qqq_close = idx_data['Close']['QQQ'].dropna()
for i in range(-10, 0):
    dt = qqq_close.index[i]
    c = qqq_close.iloc[i]
    print(f"QQQ {dt.strftime('%Y-%m-%d')}: {c:.2f}")
