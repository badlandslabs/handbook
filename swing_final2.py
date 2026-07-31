#!/opt/hermes/.venv/bin/python3
import yfinance as yf, warnings, pandas as pd, numpy as np
warnings.filterwarnings('ignore')

def safe_ta(h):
    c = h['Close']
    hi = h['High']
    lo = h['Low']
    vol = h['Volume']
    n = len(c)
    
    s20 = c.rolling(20).mean()
    s50 = c.rolling(50).mean()
    s200 = c.rolling(200).mean() if n >= 200 else pd.Series(np.nan, index=c.index)
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
    bb_mid = c.rolling(20).mean()
    bb_std = c.rolling(20).std()
    bb_u = bb_mid + 2*bb_std
    bb_l = bb_mid - 2*bb_std
    mom20 = (c / c.shift(20) - 1)*100 if n >= 21 else 0
    mom5 = (c / c.shift(5) - 1)*100 if n >= 6 else 0
    
    return {
        's20': s20, 's50': s50, 's200': s200,
        'macd': macd, 'signal': signal,
        'rsi': rsi, 'atr': atr,
        'bb_u': bb_u, 'bb_mid': bb_mid, 'bb_l': bb_l,
        'mom20': mom20, 'mom5': mom5,
        'low52': lo.rolling(252).min() if n >= 252 else lo.rolling(n//2).min(),
        'high52': hi.rolling(252).max() if n >= 252 else hi.rolling(n//2).max(),
    }

print("=== REGIME ===", flush=True)
for name, sym in [('QQQ','^QQQ'), ('SPY','SPY'), ('IWM','IWM')]:
    h = yf.Ticker(sym).history(period='1y', interval='1d')
    if h.empty: continue
    c = h['Close'].iloc[-1]
    ta = safe_ta(h)
    s200 = ta['s200'].iloc[-1]
    regime = "BULL" if (not np.isnan(s200) and c > s200) else ("BEAR" if (not np.isnan(s200) and c < s200) else "TRANSITIONAL")
    m5_val = ta['mom5']
    m20_val = ta['mom20']
    m5 = float(m5_val.iloc[-1]) if hasattr(m5_val, 'iloc') else float(m5_val)
    m20 = float(m20_val.iloc[-1]) if hasattr(m20_val, 'iloc') else float(m20_val)
    print(f"{name}: ${c:.2f} s200={s200:.2f if not np.isnan(s200) else 'N/A'} mom5={m5:+.1f}% mom20={m20:+.1f}% REGIME={regime}", flush=True)

v = yf.Ticker('^VIX').history(period='5d', interval='1d')
t = yf.Ticker('^TNX').history(period='5d', interval='1d')
print(f"VIX={v['Close'].iloc[-1]:.2f} | TNX={t['Close'].iloc[-1]:.4f}%", flush=True)

print("\n=== SECTOR MOMENTUM ===", flush=True)
for sym in ['XLK','XLF','XLV','XLY','XLE']:
    h = yf.Ticker(sym).history(period='60d', interval='1d')
    if not h.empty:
        c = h['Close'].iloc[-1]
        m5 = (c / h['Close'].iloc[-6] - 1)*100 if len(h) >= 6 else 0
        m20 = (c / h['Close'].iloc[-21] - 1)*100 if len(h) >= 21 else 0
        print(f"{sym}: {c:.2f} 5d={m5:+.1f}% 20d={m20:+.1f}%", flush=True)

print("\n=== TOP SWING CANDIDATES ===", flush=True)
for t_sym in ['ADBE', 'ADP', 'CRM', 'MSFT']:
    h = yf.Ticker(t_sym).history(period='1y', interval='1d')
    info = yf.Ticker(t_sym).info
    if h.empty: continue
    ta = safe_ta(h)
    cur = h['Close'].iloc[-1]
    prev = h['Close'].iloc[-2] if len(h) > 1 else cur
    gap = (cur/prev - 1)*100
    vol_t = h['Volume'].iloc[-1]
    vol20 = h['Volume'].rolling(20).mean().iloc[-1]
    atr_v = ta['atr'].iloc[-1]
    rsi_v = ta['rsi'].iloc[-1]
    macd_v = ta['macd'].iloc[-1]
    sig_v = ta['signal'].iloc[-1]
    hist_v = macd_v - sig_v
    s20v = ta['s20'].iloc[-1]
    s50v = ta['s50'].iloc[-1]
    s200v = ta['s200'].iloc[-1]
    bbu = ta['bb_u'].iloc[-1]
    bbm = ta['bb_mid'].iloc[-1]
    bbl = ta['bb_l'].iloc[-1]
    low52 = ta['low52'].iloc[-1]
    high52 = ta['high52'].iloc[-1]
    pct52 = (cur - low52)/(high52 - low52)*100 if (high52 - low52) > 0 else 50
    m5 = ta['mom5'].iloc[-1]
    m20 = ta['mom20'].iloc[-1]
    h5 = h['High'].iloc[-5:].max()
    l5 = h['Low'].iloc[-5:].min()
    target = info.get('targetMeanPrice', None)
    pe = info.get('trailingPE', None)
    beta = info.get('beta', None)
    rec = info.get('recommendationKey', 'N/A')
    analyst_up = (target/cur - 1)*100 if target else 0
    # Fibonacci
    f38 = low52 + 0.382*(high52 - low52)
    f61 = low52 + 0.618*(high52 - low52)
    f78 = low52 + 0.786*(high52 - low52)
    
    print(f"\n{t_sym}: cur={cur:.2f} prev={prev:.2f} gap={gap:+.2f}%", flush=True)
    print(f"  MA: s20={s20v:.2f} s50={s50v:.2f} s200={s200v:.2f if not np.isnan(s200v) else 'N/A'}", flush=True)
    print(f"  RSI={rsi_v:.1f} MACD={macd_v:.4f} Sig={sig_v:.4f} Hist={hist_v:.4f}", flush=True)
    print(f"  ATR={atr_v:.2f} ({(atr_v/cur)*100:.1f}%) BB: u={bbu:.2f} m={bbm:.2f} l={bbl:.2f}", flush=True)
    print(f"  52w: {low52:.2f} to {high52:.2f} (pct={pct52:.0f}%) | Fib: 38.2={f38:.2f} 61.8={f61:.2f} 78.6={f78:.2f}", flush=True)
    print(f"  5d: {l5:.2f}-{h5:.2f} | mom5={m5:+.1f}% mom20={m20:+.1f}%", flush=True)
    print(f"  Vol={vol_t:.0f} / {vol20:.0f} ({vol_t/vol20:.2f}x)", flush=True)
    print(f"  target={target} up={analyst_up:.1f}% pe={pe} beta={beta} rec={rec}", flush=True)
    
    # Stop/target
    stop_dist = atr_v * 2
    stop = cur - stop_dist
    t1 = cur + stop_dist * 2
    t2 = cur + stop_dist * 3
    rr = (t2 - cur) / stop_dist
    print(f"  >>> ENTRY={cur:.2f} STOP={stop:.2f} (-{(stop_dist/cur)*100:.1f}%) T1={t1:.2f} T2={t2:.2f} | R/R={rr:.1f}:1", flush=True)
