#!/opt/hermes/.venv/bin/python3
import yfinance as yf, warnings, pandas as pd, numpy as np
warnings.filterwarnings('ignore')

print("=== VIX & MACRO ===", flush=True)
for sym in ['^VIX', '^VVIX', 'HYG', 'LQD', '^TNX']:
    try:
        h = yf.Ticker(sym).history(period='3mo', interval='1d')
        if not h.empty:
            c = h['Close'].iloc[-1]
            print(f"  {sym}: {c:.4f}", flush=True)
        else:
            print(f"  {sym}: EMPTY", flush=True)
    except Exception as e:
        print(f"  {sym}: {e}", flush=True)

# Deep dive on top 5
print("\n=== DEEP DIVE TOP 5 ===", flush=True)
top5 = ['ADBE', 'ADP', 'NVDA', 'MSFT', 'META']
tickers_to_check = ['ADBE', 'ADP', 'NVDA', 'MSFT', 'META', 'GOOGL', 'AMZN']

for t in tickers_to_check:
    try:
        tk = yf.Ticker(t)
        h = tk.history(period='3mo', interval='1d')
        info = tk.info
        if h.empty:
            continue
        close = h['Close']
        high = h['High']
        low = h['Low']
        vol = h['Volume']
        
        # MAs
        sma20 = close.rolling(20).mean()
        sma50 = close.rolling(50).mean()
        sma200 = close.rolling(200).mean()
        ema20 = close.ewm(20).mean()
        
        # RSI
        d = close.diff()
        g = d.where(d > 0, 0).rolling(14).mean()
        l = (-d.where(d < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + g/l))
        
        # MACD
        e12 = close.ewm(12).mean()
        e26 = close.ewm(26).mean()
        macd = e12 - e26
        signal = macd.ewm(9).mean()
        
        # ATR
        tr = pd.concat([high-low, (high-close.shift(1)).abs(), (low-close.shift(1)).abs()], axis=1).max(axis=1)
        atr = tr.rolling(14).mean()
        
        # Bollinger
        bb_mid = close.rolling(20).mean()
        bb_std = close.rolling(20).std()
        bb_upper = bb_mid + 2*bb_std
        bb_lower = bb_mid - 2*bb_std
        
        c = close.iloc[-1]
        prev_c = close.iloc[-2] if len(close) > 1 else c
        gap = (c/prev_c - 1)*100
        atr_val = atr.iloc[-1]
        rsi_val = rsi.iloc[-1]
        
        # 52w
        h52 = high.rolling(252).max().iloc[-1]
        l52 = low.rolling(252).min().iloc[-1]
        pct52 = (c - l52)/(h52 - l52)*100
        
        # 5d high/low
        h5d = high.iloc[-5:].max()
        l5d = low.iloc[-5:].min()
        
        print(f"\n  {t}: ${c:.2f} (gap={gap:+.2f}%)", flush=True)
        print(f"    SMA20=${sma20.iloc[-1]:.2f} | SMA50=${sma50.iloc[-1]:.2f} | SMA200=${sma200.iloc[-1]:.2f}" if not sma200.isna().all() else f"    SMA20=${sma20.iloc[-1]:.2f}", flush=True)
        print(f"    RSI(14)={rsi_val:.1f} | MACD={macd.iloc[-1]:.4f} | Signal={signal.iloc[-1]:.4f}", flush=True)
        print(f"    ATR=${atr_val:.2f} ({(atr_val/c)*100:.1f}%) | 5D Range: ${l5d:.2f}-${h5d:.2f}", flush=True)
        print(f"    52w High=${h52:.2f} | 52w Low=${l52:.2f} | 52w%={pct52:.0f}%", flush=True)
        print(f"    BB_upper=${bb_upper.iloc[-1]:.2f} | BB_mid=${bb_mid.iloc[-1]:.2f} | BB_lower=${bb_lower.iloc[-1]:.2f}", flush=True)
        print(f"    Target=${info.get('targetMeanPrice','N/A')} | PE={info.get('trailingPE','N/A')} | Rec={info.get('recommendationKey','N/A')}", flush=True)
        print(f"    Analyst=${info.get('numberOfAnalystOpinions',0)} opinions | Beta={info.get('beta','N/A')}", flush=True)
        
        # Volume profile
        vol_ratio = vol.iloc[-1] / vol.rolling(20).mean().iloc[-1]
        print(f"    Vol(today)={vol.iloc[-1]:.0f} | Vol_20avg={vol.rolling(20).mean().iloc[-1]:.0f} | VolRatio={vol_ratio:.2f}x", flush=True)
        
        # Near-term catalysts
        ed = info.get('earningsDates', [])
        print(f"    Earnings dates: {ed}", flush=True)
        
    except Exception as e:
        print(f"  {t}: ERROR {e}", flush=True)

# Sector rotation check
print("\n=== SECTOR ROTATION ===", flush=True)
sector_etfs = ['XLK', 'XLF', 'XLV', 'XLY', 'XLP', 'XLE', 'XLRE', 'XLB', 'XLI', 'XLUX', 'QQQ']
for sym in sector_etfs:
    try:
        h = yf.Ticker(sym).history(period='60d', interval='1d')
        if not h.empty:
            c = h['Close'].iloc[-1]
            m20 = (c / h['Close'].iloc[-21] - 1)*100 if len(h) >= 21 else 0
            m5 = (c / h['Close'].iloc[-6] - 1)*100 if len(h) >= 6 else 0
            print(f"  {sym}: ${c:.2f} | 5d={m5:+.1f}% | 20d={m20:+.1f}%", flush=True)
    except Exception as e:
        print(f"  {sym}: {e}", flush=True)
