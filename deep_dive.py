import yfinance as yf
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

# Deep dive top candidates
candidates = ['CRWD', 'PANW', 'NVDA', 'AMAT', 'FAST', 'TSLA', 'AAPL', 'META']
print("=== TOP CANDIDATE DEEP DIVE ===")

for sym in candidates:
    try:
        df = yf.download(sym, period='3mo', interval='1d', progress=False)
        if df.empty:
            print(f"\n{sym}: No data")
            continue
        
        close = df['Close'].squeeze()
        high = df['High'].squeeze()
        low = df['Low'].squeeze()
        latest = close.iloc[-1]
        
        # Swing highs/lows (last 20 days)
        recent_highs = []
        recent_lows = []
        for i in range(2, min(len(df)-2, 22)):
            if df['High'].iloc[i] > df['High'].iloc[i-1] and df['High'].iloc[i] > df['High'].iloc[i+1]:
                recent_highs.append(df['High'].iloc[i])
            if df['Low'].iloc[i] < df['Low'].iloc[i-1] and df['Low'].iloc[i] < df['Low'].iloc[i+1]:
                recent_lows.append(df['Low'].iloc[i])
        
        # ATR
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr14 = tr.rolling(14).mean().iloc[-1]
        
        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0).ewm(span=14, adjust=False).mean()
        loss = (-delta.where(delta < 0, 0)).ewm(span=14, adjust=False).mean()
        rs = gain/loss
        rsi = (100 - (100/(1+rs))).iloc[-1]
        
        # Bollinger
        bb_mid = close.rolling(20).mean().iloc[-1]
        bb_std = close.rolling(20).std().iloc[-1]
        bb_upper = bb_mid + 2*bb_std
        bb_lower = bb_mid - 2*bb_std
        
        # SMAs
        sma20 = close.rolling(20).mean().iloc[-1]
        sma50 = close.rolling(50).mean().iloc[-1]
        sma200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else np.nan
        
        # MACD
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd = (ema12 - ema26)
        macd_sig = macd.ewm(span=9, adjust=False).mean()
        
        # Returns
        ret_1d = (close.iloc[-1]/close.iloc[-2]-1)*100
        ret_5d = (close.iloc[-1]/close.iloc[-6]-1)*100 if len(close) > 5 else 0
        ret_10d = (close.iloc[-1]/close.iloc[-11]-1)*100 if len(close) > 10 else 0
        
        print(f"\n{sym}: ${latest:.2f}")
        print(f"  RSI={rsi:.1f} | ATR14={atr14:.2f} ({(atr14/latest)*100:.1f}%)")
        print(f"  SMA20={sma20:.2f} | SMA50={sma50:.2f} | SMA200={sma200:.2f if not np.isnan(sma200) else 'N/A'}")
        print(f"  BB: {bb_lower:.2f} - {bb_upper:.2f} | Pos={(latest-bb_lower)/(bb_upper-bb_lower)*100:.0f}%")
        print(f"  MACD: {macd.iloc[-1]:.3f} | Signal: {macd_sig.iloc[-1]:.3f} | {'ABOVE' if macd.iloc[-1] > macd_sig.iloc[-1] else 'BELOW'}")
        print(f"  Returns: 1d={ret_1d:+.1f}% | 5d={ret_5d:+.1f}% | 10d={ret_10d:+.1f}%")
        print(f"  Recent swing highs: {sorted(recent_highs, reverse=True)[:3]}")
        print(f"  Recent swing lows: {sorted(recent_lows)[:3]}")
        
        # Earnings info
        try:
            t = yf.Ticker(sym)
            cal = t.calendar
            if cal is not None:
                print(f"  Earnings cal: {cal}")
        except:
            pass
        
    except Exception as e:
        print(f"\n{sym}: ERROR - {e}")

print("\n\n=== REGIME DATA ===")
for sym, period in [('SPY','3mo'),('QQQ','3mo'),('^VIX','1mo')]:
    df = yf.download(sym, period=period, interval='1d', progress=False)
    if not df.empty:
        c = df['Close'].squeeze().iloc[-1]
        h = df['High'].squeeze().iloc[-1]
        l = df['Low'].squeeze().iloc[-1]
        print(f"{sym}: {c:.2f} | Range: {l:.2f}-{h:.2f}")
