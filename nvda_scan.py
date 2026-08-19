import yfinance as yf
import pandas as pd
import numpy as np

for t in ['NVDA', 'ADI']:
    tk = yf.Ticker(t)
    h = tk.history(period='3mo')
    closes = h['Close']
    c = float(closes.iloc[-1])
    sma20 = float(closes.rolling(20).mean().iloc[-1])
    sma50 = float(closes.rolling(50).mean().iloc[-1])
    tr = pd.concat([h['High']-h['Low'],(h['High']-closes.shift(1)).abs(),(h['Low']-closes.shift(1)).abs()],axis=1).max(axis=1)
    atr = float(tr.rolling(14).mean().iloc[-1])
    delta = closes.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain/loss.replace(0,np.nan)
    rsi = float((100-(100/(1+rs))).iloc[-1])
    mom20 = float((closes.iloc[-1]/closes.iloc[-21]-1)*100) if len(closes)>=21 else 0
    mom5 = float((closes.iloc[-1]/closes.iloc[-6]-1)*100) if len(closes)>=6 else 0
    vol_avg = float(h['Volume'].rolling(20).mean().iloc[-1])
    vol_today = float(h['Volume'].iloc[-1])
    vol_r = vol_today/vol_avg
    bb_mid = float(closes.rolling(20).mean().iloc[-1])
    bb_std = float(closes.rolling(20).std().iloc[-1])
    bb_up = bb_mid+2*bb_std
    bb_low = bb_mid-2*bb_std
    bb_pos = (c-bb_low)/(bb_up-bb_low)
    high20 = float(h['High'].rolling(20).max().iloc[-1])
    ema12 = closes.ewm(span=12, adjust=False).mean()
    ema26 = closes.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    sig = macd.ewm(span=9, adjust=False).mean()
    macd_h = float((macd - sig).iloc[-1])
    macd_h_prev = float((macd - sig).iloc[-2])
    print(f"\n{t}:")
    print(f"  Price: ${c:.2f} | SMA20=${sma20:.2f} SMA50=${sma50:.2f}")
    print(f"  RSI={rsi:.1f} ATR=${atr:.2f} VolRatio={vol_r:.2f}x")
    print(f"  +5D={mom5:+.1f}% +20D={mom20:+.1f}%")
    print(f"  % from 20D High: {(c/high20-1)*100:+.0f}%")
    print(f"  BB: {bb_pos:.2f} ({bb_low:.2f}-{bb_up:.2f})")
    print(f"  MACD Hist: {macd_h:.4f} (prev: {macd_h_prev:.4f})")
    stop = c - max(atr*1.5, c*0.05)
    t1 = c + (c-stop)*2
    t2 = c + (c-stop)*3.5
    print(f"  SWING R:R | Entry=${c:.2f} Stop=${stop:.2f} (-{(stop/c-1)*100:.1f}%) | T1=${t1:.2f} (+{(t1/c-1)*100:.1f}% RR={(t1-c)/(c-stop):.1f}:1) | T2=${t2:.2f} (+{(t2/c-1)*100:.1f}% RR={(t2-c)/(c-stop):.1f}:1)")
