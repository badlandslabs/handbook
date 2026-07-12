import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

def atr(df, period=14):
    high = df['High']; low = df['Low']; close = df['Close']
    tr1 = high - low; tr2 = (high - close.shift()).abs(); tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def rsi(df, period=14):
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def ema(df, period): return df['Close'].ewm(span=period, adjust=False).mean()
def sma(df, period): return df['Close'].rolling(period).mean()

print(f"INTRADAY SCAN — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC\n")

targets = ['QQQ','SPY','IWM','TXN','HOOD','META','NVDA','AVGO','AMD','NET','CRM','AAPL','NOW','XLV','XLF','XLK']

for t in targets:
    try:
        tk = yf.Ticker(t)
        daily = tk.history(period='3mo', interval='1d', auto_adjust=True)
        intra = tk.history(period='5d', interval='15m', auto_adjust=True)

        close = daily['Close']
        price = close.iloc[-1]

        # Previous close
        prev_close = close.iloc[-2]
        gap_today = ((price - prev_close) / prev_close) * 100

        # Intraday range
        if len(intra) > 0:
            intra_high = intra['High'].max()
            intra_low  = intra['Low'].min()
            intra_open = intra['Open'].iloc[0]
            intra_range = intra_high - intra_low
            # How far has price moved from open?
            from_open_pct = (price - intra_open) / intra_open * 100
            # Gap fill: is price back inside the gap?
            gap_filled = "FILLED" if (gap_today > 0 and price >= prev_close) or (gap_today < 0 and price <= prev_close) else "OPEN"
        else:
            intra_high = intra_low = intra_open = 0
            from_open_pct = 0
            gap_filled = "N/A"

        # Daily RSI
        rsi14 = rsi(daily, 14).iloc[-1]
        atr14 = atr(daily, 14).iloc[-1]

        # 5-day and 20-day
        ret5  = (close.iloc[-1] / close.iloc[-6] - 1) * 100 if len(close) >= 6 else 0
        ret20 = (close.iloc[-1] / close.iloc[-21] - 1) * 100 if len(close) >= 21 else 0

        # Recent swing low (5-day)
        swing_low_5d  = daily['Low'].tail(5).min()
        swing_high_5d = daily['High'].tail(5).max()

        print(f"{t:6s} ${price:>8.2f}  Gap:{gap_today:>+6.2f}%  [{gap_filled}]  "
              f"IntraRange:{intra_range:.2f}  FromOpen:{from_open_pct:>+5.2f}%  "
              f"RSI:{rsi14:>5.1f}  ATR%:{atr14/price*100:.1f}%  "
              f"5d:{ret5:>+6.1f}%  20d:{ret20:>+6.1f}%  "
              f"5dLow:{swing_low_5d:.2f}  5dHi:{swing_high_5d:.2f}")
    except Exception as e:
        print(f"{t:6s} ERROR: {e}")

print("\n── SWING LEVELS ──")
# Compute key levels for top candidates
for t, entry_approx, stop_approx, t1_approx, t2_approx in [
    ('TXN',   301.87, 285.00, 320.00, 335.00),
    ('HOOD',  111.40, 103.00, 120.00, 127.00),
    ('META',  602.97, 580.00, 640.00, 670.00),
    ('NET',   262.67, 248.00, 275.00, 290.00),
    ('CRM',   165.34, 155.00, 175.00, 183.00),
]:
    risk = entry_approx - stop_approx
    rr1 = (t1_approx - entry_approx) / risk if risk > 0 else 0
    rr2 = (t2_approx - entry_approx) / risk if risk > 0 else 0
    print(f"  {t:6s} Entry:${entry_approx:.2f}  Stop:${stop_approx:.2f}  T1:${t1_approx:.2f}({rr1:.1f}:1)  T2:${t2_approx:.2f}({rr2:.1f}:1)")

