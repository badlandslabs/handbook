#!/opt/hermes/.venv/bin/python3
import yfinance as yf, warnings, pandas as pd, numpy as np
warnings.filterwarnings('ignore')

# Get 1-year data to have enough for 200 SMA
print("=== REGIME & MACRO ===", flush=True)
indices = [('QQQ','^QQQ'), ('SPY','SPY'), ('IWM','IWM')]
for name, sym in indices:
    h = yf.Ticker(sym).history(period='1y', interval='1d')
    if not h.empty:
        c = h['Close'].iloc[-1]
        s20 = h['Close'].rolling(20).mean().iloc[-1]
        s50 = h['Close'].rolling(50).mean().iloc[-1]
        s200 = h['Close'].rolling(200).mean().iloc[-1]
        mom20 = (c / h['Close'].iloc[-21] - 1)*100
        mom5 = (c / h['Close'].iloc[-6] - 1)*100
        regime = "BULL" if (not np.isnan(s200) and c > s200) else ("BEAR" if (not np.isnan(s200) and c < s200) else "TRANSITIONAL")
        print(f"{name}: ${c:.2f} s20={s20:.2f} s50={s50:.2f} s200={s200:.2f} mom5={mom5:+.1f}% mom20={mom20:+.1f}% {regime}", flush=True)

v = yf.Ticker('^VIX').history(period='1mo', interval='1d')
tnx = yf.Ticker('^TNX').history(period='1mo', interval='1d')
print(f"VIX={v['Close'].iloc[-1]:.2f} TNX={tnx['Close'].iloc[-1]:.4f}", flush=True)

# Sector rotation
print("\n=== SECTORS ===", flush=True)
for sym in ['XLK','XLF','XLV','XLY','XLE']:
    h = yf.Ticker(sym).history(period='60d', interval='1d')
    if not h.empty:
        c = h['Close'].iloc[-1]
        m5 = (c / h['Close'].iloc[-6] - 1)*100
        m20 = (c / h['Close'].iloc[-21] - 1)*100
        print(f"{sym}: {c:.2f} 5d={m5:+.1f}% 20d={m20:+.1f}%", flush=True)

# Top 3 candidates: ADBE, ADP, CRM
print("\n=== TOP 3 CANDIDATES ===", flush=True)
for t in ['ADBE', 'ADP', 'CRM']:
    h = yf.Ticker(t).history(period='1y', interval='1d')
    info = yf.Ticker(t).info
    if h.empty: continue
    c = h['Close']
    hi = h['High']
    lo = h['Low']
    vol = h['Volume']
    
    s20 = c.rolling(20).mean()
    s50 = c.rolling(50).mean()
    s200 = c.rolling(200).mean()
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
    
    cur = c.iloc[-1]
    prev = c.iloc[-2]
    gap = (cur/prev - 1)*100
    vol_today = vol.iloc[-1]
    vol20 = vol.rolling(20).mean().iloc[-1]
    atr_v = atr.iloc[-1]
    rsi_v = rsi.iloc[-1]
    macd_v = macd.iloc[-1]
    sig_v = signal.iloc[-1]
    hist_v = macd_v - sig_v
    
    bb_mid = c.rolling(20).mean()
    bb_std = c.rolling(20).std()
    bb_u = bb_mid + 2*bb_std
    bb_l = bb_mid - 2*bb_std
    
    target = info.get('targetMeanPrice', None)
    pe = info.get('trailingPE', None)
    beta = info.get('beta', None)
    rec = info.get('recommendationKey', 'N/A')
    analyst_up = (target/cur - 1)*100 if target else 0
    
    low52 = lo.rolling(252).min().iloc[-1]
    high52 = hi.rolling(252).max().iloc[-1]
    pct52 = (cur - low52)/(high52 - low52)*100 if (high52 - low52) > 0 else 50
    
    # 5d range
    h5 = hi.iloc[-5:].max()
    l5 = lo.iloc[-5:].min()
    
    # Fibonacci (from 52w low to high)
    f38 = low52 + 0.382*(high52 - low52)
    f61 = low52 + 0.618*(high52 - low52)
    f78 = low52 + 0.786*(high52 - low52)
    
    # Order levels
    stop_dist = atr_v * 2
    stop = cur - stop_dist
    t1 = cur + stop_dist * 2
    t2 = cur + stop_dist * 3
    rr = (t2 - cur) / stop_dist
    
    print(f"\n{t}: cur={cur:.2f} prev={prev:.2f} gap={gap:+.2f}%", flush=True)
    print(f"  s20={s20.iloc[-1]:.2f} s50={s50.iloc[-1]:.2f} s200={s200.iloc[-1]:.2f}", flush=True)
    print(f"  rsi={rsi_v:.1f} macd={macd_v:.4f} sig={sig_v:.4f} hist={hist_v:.4f}", flush=True)
    print(f"  atr={atr_v:.2f} ({(atr_v/cur)*100:.1f}%) bbu={bb_u.iloc[-1]:.2f} bbm={bb_mid.iloc[-1]:.2f} bbl={bb_l.iloc[-1]:.2f}", flush=True)
    print(f"  52w: low={low52:.2f} high={high52:.2f} pct={pct52:.0f}%", flush=True)
    print(f"  Fib: 38.2={f38:.2f} 61.8={f61:.2f} 78.6={f78:.2f}", flush=True)
    print(f"  5d: h={h5:.2f} l={l5:.2f}", flush=True)
    print(f"  vol={vol_today:.0f} vol20={vol20:.0f} ratio={vol_today/vol20:.2f}x", flush=True)
    print(f"  target={target} up={analyst_up:.1f}% pe={pe} beta={beta} rec={rec}", flush=True)
    print(f"  >> ENTRY~{cur:.2f} STOP={stop:.2f} T1={t1:.2f} T2={t2:.2f} R/R={rr:.1f}:1", flush=True)

# MSFT separate (overbought RSI so different framing)
print("\n=== MSFT SEPARATE ===", flush=True)
t = 'MSFT'
h = yf.Ticker(t).history(period='1y', interval='1d')
info = yf.Ticker(t).info
c = h['Close']
hi = h['High']
lo = h['Low']
s20 = c.rolling(20).mean().iloc[-1]
s50 = c.rolling(50).mean().iloc[-1]
s200 = c.rolling(200).mean().iloc[-1]
d = c.diff()
g = d.where(d > 0, 0).rolling(14).mean()
l = (-d.where(d < 0, 0)).rolling(14).mean()
rsi = 100 - (100/(1 + g/l))
tr = pd.concat([hi-lo, (hi-c.shift(1)).abs(), (lo-c.shift(1)).abs()], axis=1).max(axis=1)
atr = tr.rolling(14).mean()
cur = c.iloc[-1]
target = info.get('targetMeanPrice', None)
pe = info.get('trailingPE', None)
beta = info.get('beta', None)
rec = info.get('recommendationKey', 'N/A')
cur_atr = atr.iloc[-1]
low52 = lo.rolling(252).min().iloc[-1]
high52 = hi.rolling(252).max().iloc[-1]
pct52 = (cur - low52)/(high52 - low52)*100
print(f"{t}: {cur:.2f} s20={s20:.2f} s50={s50:.2f} s200={s200:.2f} rsi={rsi.iloc[-1]:.1f}", flush=True)
print(f"  atr={cur_atr:.2f} 52w_pct={pct52:.0f}% target={target} pe={pe} beta={beta} rec={rec}", flush=True)
analyst_up = (target/cur - 1)*100 if target else 0
# Tighter stop due to overbought
stop = cur - cur_atr * 1.5
t1 = cur + cur_atr * 2
rr = (t1 - cur) / (cur - stop)
print(f"  analyst_up={analyst_up:.1f}% >> ENTRY~{cur:.2f} STOP={stop:.2f} T1={t1:.2f} R/R={rr:.1f}:1", flush=True)
