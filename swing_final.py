#!/opt/hermes/.venv/bin/python3
import yfinance as yf, warnings, pandas as pd, numpy as np
warnings.filterwarnings('ignore')

print("=== MACRO REGIME ===", flush=True)

# Indices + regime
indices = {'QQQ': '^QQQ', 'SPY': 'SPY', 'IWM': 'IWM'}
for name, sym in indices.items():
    h = yf.Ticker(sym).history(period='6mo', interval='1d')
    if not h.empty:
        c = h['Close'].iloc[-1]
        sma20 = h['Close'].rolling(20).mean().iloc[-1]
        sma50 = h['Close'].rolling(50).mean().iloc[-1]
        sma200 = h['Close'].rolling(200).mean().iloc[-1]
        mom20 = (c / h['Close'].iloc[-21] - 1)*100 if len(h) >= 21 else 0
        mom5 = (c / h['Close'].iloc[-6] - 1)*100 if len(h) >= 6 else 0
        regime = "BULL" if c > sma200 and sma200 > sma200 else ("BEAR" if c < sma200 else "TRANSITIONAL")
        print(f"  {name}: ${c:.2f} | SMA20={sma20:.2f} | SMA50={sma50:.2f} | SMA200={sma200:.2f} | 5d={mom5:+.1f}% 20d={mom20:+.1f}% | Regime={regime}", flush=True)

# VIX
for sym in ['^VIX', '^TNX']:
    h = yf.Ticker(sym).history(period='3mo', interval='1d')
    if not h.empty:
        print(f"  {sym}: {h['Close'].iloc[-1]:.4f}", flush=True)

# Sector ETFs
print("\n=== SECTOR MOMENTUM ===", flush=True)
for sym in ['XLK','XLF','XLV','XLY','XLP','XLE']:
    h = yf.Ticker(sym).history(period='60d', interval='1d')
    if not h.empty:
        c = h['Close'].iloc[-1]
        m5 = (c / h['Close'].iloc[-6] - 1)*100 if len(h) >= 6 else 0
        m20 = (c / h['Close'].iloc[-21] - 1)*100 if len(h) >= 21 else 0
        print(f"  {sym}: ${c:.2f} | 5d={m5:+.1f}% | 20d={m20:+.1f}%", flush=True)

# Top 4 deep dive
print("\n=== TOP 4 DEEP DIVE ===", flush=True)
top4 = ['ADBE', 'ADP', 'MSFT', 'CRM']
for t in top4:
    h = yf.Ticker(t).history(period='6mo', interval='1d')
    info = yf.Ticker(t).info
    if h.empty:
        continue
    c = h['Close']
    hi = h['High']
    lo = h['Low']
    vol = h['Volume']
    
    sma20 = c.rolling(20).mean()
    sma50 = c.rolling(50).mean()
    sma200 = c.rolling(200).mean()
    e12 = c.ewm(12).mean()
    e26 = c.ewm(26).mean()
    macd = e12 - e26
    signal = macd.ewm(9).mean()
    
    d = c.diff()
    g = d.where(d > 0, 0).rolling(14).mean()
    l = (-d.where(d < 0, 0)).rolling(14).mean()
    rsi = 100 - (100/(1 + g/l))
    
    tr = pd.concat([hi-lo, (hi-c.shift(1)).abs(), (lo-c.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    
    bb = c.rolling(20)
    bb_std = bb.std()
    bb_mid = bb.mean()
    bb_upper = bb_mid + 2*bb_std
    bb_lower = bb_mid - 2*bb_std
    
    cur = c.iloc[-1]
    prev = c.iloc[-2]
    gap = (cur/prev - 1)*100
    
    vol_today = vol.iloc[-1]
    vol_avg = vol.rolling(20).mean().iloc[-1]
    
    target = info.get('targetMeanPrice', None)
    pe = info.get('trailingPE', None)
    beta = info.get('beta', None)
    rec = info.get('recommendationKey', 'N/A')
    analyst_upside = (target/cur - 1)*100 if target else 0
    
    # Fib retracement from 6m low to high
    low6m = lo.rolling(126).min().iloc[-1]
    high6m = hi.rolling(126).max().iloc[-1]
    fib382 = low6m + 0.382*(high6m - low6m)
    fib618 = low6m + 0.618*(high6m - low6m)
    fib786 = low6m + 0.786*(high6m - low6m)
    
    # Key support/resistance
    recent_high_5d = hi.iloc[-5:].max()
    recent_low_5d = lo.iloc[-5:].min()
    
    # Risk metrics
    atr_val = atr.iloc[-1]
    stop_distance = atr_val * 2
    
    print(f"\n  {t}: ${cur:.2f} | Gap: {gap:+.2f}%", flush=True)
    print(f"    SMA20={sma20.iloc[-1]:.2f} | SMA50={sma50.iloc[-1]:.2f} | SMA200={sma200.iloc[-1]:.2f}" if not sma200.isna().all() else f"    SMA20={sma20.iloc[-1]:.2f} | SMA50={sma50.iloc[-1]:.2f}", flush=True)
    print(f"    RSI={rsi.iloc[-1]:.1f} | MACD={macd.iloc[-1]:.4f} | Signal={signal.iloc[-1]:.4f}", flush=True)
    print(f"    ATR=${atr_val:.2f} ({(atr_val/cur)*100:.1f}%) | BB_upper=${bb_upper.iloc[-1]:.2f} | BB_mid=${bb_mid.iloc[-1]:.2f} | BB_lower=${bb_lower.iloc[-1]:.2f}", flush=True)
    print(f"    6m Range: ${low6m:.2f}-${high6m:.2f} | Fib382=${fib382:.2f} | Fib618=${fib618:.2f} | Fib786=${fib786:.2f}", flush=True)
    print(f"    5D High=${recent_high_5d:.2f} | 5D Low=${recent_low_5d:.2f}", flush=True)
    print(f"    Vol: {vol_today:.0f} / {vol_avg:.0f} avg ({vol_today/vol_avg:.2f}x)", flush=True)
    print(f"    Target=${target:.2f} ({analyst_upside:+.1f}%) | PE={pe} | Beta={beta} | Rec={rec}", flush=True)
    
    # Stop and target calculations
    stop_loss = cur - stop_distance
    risk_pct = (stop_distance / cur) * 100
    t1 = cur + (stop_distance * 2)
    t2 = cur + (stop_distance * 3)
    rr = (t2 - cur) / stop_distance
    
    print(f"    >> R/R Calc: Entry~${cur:.2f} | Stop=${stop_loss:.2f} (-{risk_pct:.1f}%) | T1=${t1:.2f} ({rr:.1f}:1) | T2=${t2:.2f} ({rr*1.5:.1f}:1)", flush=True)

# Also check for upcoming earnings
print("\n=== EARNINGS CALENDAR (next 30 days) ===", flush=True)
earnings_tickers = ['ADBE', 'ADP', 'MSFT', 'CRM', 'NVDA', 'AMZN', 'META', 'AVGO', 'AMD']
import datetime
today = datetime.date.today()
for t in earnings_tickers:
    info = yf.Ticker(t).info
    ed = info.get('earningsDates', [])
    next_earnings = None
    if ed and len(ed) > 0:
        for e in ed:
            if isinstance(e, dict):
                d = e.get('Earnings Date')
                if d:
                    try:
                        edate = pd.to_datetime(d).date()
                        if edate >= today:
                            next_earnings = edate
                            break
                    except:
                        pass
    if next_earnings:
        days_out = (next_earnings - today).days
        print(f"  {t}: {next_earnings} ({days_out} days)", flush=True)
    else:
        # Try earnings_calendar
        try:
            cal = yf.Ticker(t).calendar
            if cal is not None and not cal.empty:
                print(f"  {t}: CAL={cal.to_dict()}", flush=True)
        except:
            pass
        print(f"  {t}: No confirmed earnings in next 30 days", flush=True)
