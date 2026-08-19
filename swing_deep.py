#!/opt/hermes/.venv/bin/python3
import yfinance as yf
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

candidates = ['NVDA', 'AAPL', 'ADBE', 'SMCI', 'META', 'GOOGL', 'MSFT', 'AMZN', 'TSLA']

for t in candidates:
    try:
        tk = yf.Ticker(t)
        hist = tk.history(period="3mo", interval="1d")
        hist4h = tk.history(period="5d", interval="1h")
        if len(hist) < 30:
            continue
        
        close = hist['Close'].iloc[-1]
        sma20 = hist['Close'].tail(20).mean()
        sma50 = hist['Close'].tail(50).mean()
        sma200 = hist['Close'].tail(200).mean() if len(hist) >= 200 else close
        high20 = hist['High'].tail(20).max()
        low20 = hist['Low'].tail(20).min()
        high252 = hist['High'].tail(252).max() if len(hist) >= 252 else high20
        atr = (hist['High'] - hist['Low']).tail(14).mean()
        
        delta = hist['Close'].diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rsi14 = (100 - 100/(1 + gain/loss)).iloc[-1]
        
        d4 = hist4h['Close'].diff()
        g4 = d4.clip(lower=0).rolling(14).mean()
        l4 = (-d4.clip(upper=0)).rolling(14).mean()
        rsi4h = (100 - 100/(1 + g4/l4)).iloc[-1]
        
        ema12 = hist['Close'].ewm(span=12).mean()
        ema26 = hist['Close'].ewm(span=26).mean()
        macd = ema12.iloc[-1] - ema26.iloc[-1]
        macd_sig = hist['Close'].ewm(span=9).mean().ewm(span=12).mean().ewm(span=9).mean().iloc[-1] - ema26.iloc[-1]
        macd_hist = macd - macd_sig
        
        vol20 = hist['Volume'].tail(20).mean()
        vol_today = hist['Volume'].iloc[-1]
        vol_ratio = vol_today / vol20 if vol20 > 0 else 1
        
        # Support/Resistance from last 20 days
        recent_highs = sorted(hist['High'].tail(20).nlargest(3).values)
        recent_lows = sorted(hist['Low'].tail(20).nsmallest(3).values)
        
        e8_4h = hist4h['Close'].ewm(span=8).mean().iloc[-1] if len(hist4h) > 8 else close
        e20_4h = hist4h['Close'].ewm(span=20).mean().iloc[-1] if len(hist4h) > 20 else close
        e50_4h = hist4h['Close'].ewm(span=50).mean().iloc[-1] if len(hist4h) > 50 else close
        
        # Recent 10-day closes
        r10c = list(zip([str(d.date()) for d in hist.index[-10:]], [f"{c:.2f}" for c in hist['Close'].tail(10)]))
        
        print(f"\n{'='*60}")
        print(f"{t} | ${close:.2f}")
        print(f"{'='*60}")
        print(f"RSI(14): {rsi14:.1f} | 4h RSI: {rsi4h:.1f}")
        print(f"SMA20: {sma20:.2f} | SMA50: {sma50:.2f} | SMA200: {sma200:.2f}")
        print(f"AboveSMA20: {close > sma20} | AboveSMA50: {close > sma50} | AboveSMA200: {close > sma200}")
        print(f"MACD: {macd:.3f} | Signal: {macd_sig:.3f} | Hist: {macd_hist:.3f} {'POSITIVE' if macd_hist>0 else 'NEGATIVE'}")
        print(f"20d High: {high20:.2f} | 20d Low: {low20:.2f} | ATR(14): {atr:.2f} ({atr/close*100:.1f}% of price)")
        print(f"52w High: {high252:.2f} | % from 52w: {(high252-close)/high252*100:.1f}%")
        print(f"VolRatio: {vol_ratio:.2f}x | TodayVol: {vol_today:,.0f} | 20dAvg: {vol20:,.0f}")
        print(f"% from 20d High: {(high20-close)/high20*100:.1f}% | % from 20d Low: {(close-low20)/low20*100:.1f}%")
        print(f"Top R zones: {[f'{h:.2f}' for h in recent_highs]}")
        print(f"Top S zones: {[f'{l:.2f}' for l in recent_lows]}")
        print(f"4h EMA8: {e8_4h:.2f} | 4h EMA20: {e20_4h:.2f} | 4h EMA50: {e50_4h:.2f} | BullCross4h: {e8_4h > e20_4h}")
        print(f"10-day closes: {r10c}")
    except Exception as e:
        print(f"ERROR {t}: {e}")

print("\n" + "="*60)
print("VIX / MACRO")
print("="*60)
vix = yf.Ticker("^VIX")
hvix = vix.history(period="1mo", interval="1d")
print(f"VIX last 10 days: {[(str(d.date()), f'{c:.2f}') for d,c in zip(hvix.index[-10:], hvix['Close'].tail(10))]}")
print(f"VIX 20d avg: {hvix['Close'].tail(20).mean():.2f}")

dxy = yf.Ticker("UUP")
hdxy = dxy.history(period="1mo", interval="1d")
print(f"DXY last 10 days: {[(str(d.date()), f'{c:.2f}') for d,c in zip(hdxy.index[-10:], hdxy['Close'].tail(10))]}")

tlt = yf.Ticker("TLT")
htlt = tlt.history(period="1mo", interval="1d")
print(f"TLT last 10 days: {[(str(d.date()), f'{c:.2f}') for d,c in zip(htlt.index[-10:], htlt['Close'].tail(10))]}")

# HY credit spreads proxy
jnk = yf.Ticker("HYG")
hjnk = jnk.history(period="1mo", interval="1d")
print(f"HYG last 5 days: {list(zip([str(d.date()) for d in hjnk.index[-5:]], [f'{c:.2f}' for c in hjnk['Close'].tail(5)]))}")
