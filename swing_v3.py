#!/opt/hermes/.venv/bin/python3
import yfinance as yf, warnings, pandas as pd, numpy as np
warnings.filterwarnings('ignore')

def compute_ta(df):
    c, hi, lo, vol = df['Close'], df['High'], df['Low'], df['Volume']
    n = len(c)
    s20 = c.rolling(20).mean()
    s50 = c.rolling(50).mean()
    s200 = c.rolling(200).mean() if n >= 200 else c * np.nan
    e12 = c.ewm(12).mean()
    e26 = c.ewm(26).mean()
    macd_line = e12 - e26
    macd_signal = macd_line.ewm(9).mean()
    d = c.diff()
    gain = d.where(d > 0, 0).rolling(14).mean()
    loss = (-d.where(d < 0, 0)).rolling(14).mean()
    rsi = 100 - (100 / (1 + gain/loss))
    tr = pd.concat([hi-lo, (hi-c.shift(1)).abs(), (lo-c.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    bbm = c.rolling(20).mean()
    bbs = c.rolling(20).std()
    bbu = bbm + 2*bbs
    bbl = bbm - 2*bbs
    mom5 = (c / c.shift(5) - 1) * 100 if n >= 6 else c * 0
    mom20 = (c / c.shift(20) - 1) * 100 if n >= 21 else c * 0
    roll = min(n, 252)
    l52 = lo.rolling(roll).min()
    h52 = hi.rolling(roll).max()
    return {
        's20': s20, 's50': s50, 's200': s200,
        'macd': macd_line, 'signal': macd_signal,
        'rsi': rsi, 'atr': atr,
        'bbu': bbu, 'bbm': bbm, 'bbl': bbl,
        'mom5': mom5, 'mom20': mom20,
        'l52': l52, 'h52': h52,
    }

# --- REGIME ---
print("=== REGIME ===")
for nm, sym in [('QQQ','^QQQ'),('SPY','SPY'),('IWM','IWM')]:
    h = yf.Ticker(sym).history(period='1y', interval='1d')
    if h.empty: continue
    cur = float(h['Close'].iloc[-1])
    ta = compute_ta(h)
    s200v = float(ta['s200'].iloc[-1]) if not ta['s200'].isna().iloc[-1] else None
    regime = "BULL" if (s200v and cur > s200v) else ("BEAR" if (s200v and cur < s200v) else "TRANSITIONAL")
    m5 = float(ta['mom5'].iloc[-1])
    m20 = float(ta['mom20'].iloc[-1])
    s200_str = f"${s200v:.2f}" if s200v else "N/A"
    print(f"  {nm}: ${cur:.2f} | SMA200={s200_str} | 5d={m5:+.1f}% | 20d={m20:+.1f}% | REGIME={regime}")

v = yf.Ticker('^VIX').history(period='5d', interval='1d')
t = yf.Ticker('^TNX').history(period='5d', interval='1d')
print(f"  VIX={float(v['Close'].iloc[-1]):.2f} | 10Y Yield={float(t['Close'].iloc[-1]):.4f}%")

print("\n=== SECTOR MOMENTUM ===")
for sym in ['XLK','XLF','XLV','XLY','XLE']:
    h = yf.Ticker(sym).history(period='60d', interval='1d')
    if not h.empty:
        c = float(h['Close'].iloc[-1])
        m5 = (c / float(h['Close'].iloc[-6]) - 1)*100 if len(h) >= 6 else 0.0
        m20 = (c / float(h['Close'].iloc[-21]) - 1)*100 if len(h) >= 21 else 0.0
        print(f"  {sym}: ${c:.2f} | 5d={m5:+.1f}% | 20d={m20:+.1f}%")

print("\n=== SWING CANDIDATES ===")
for sym in ['ADBE', 'ADP', 'CRM', 'MSFT', 'AVGO', 'BKNG']:
    h = yf.Ticker(sym).history(period='1y', interval='1d')
    if h.empty: continue
    info = yf.Ticker(sym).info
    cur = float(h['Close'].iloc[-1])
    prev = float(h['Close'].iloc[-2]) if len(h) > 1 else cur
    gap = (cur/prev - 1)*100
    ta = compute_ta(h)
    
    vals = {k: float(v.iloc[-1]) for k, v in ta.items()}
    # get rolling 52w
    n = len(h)
    roll = min(n, 252)
    l52 = float(h['Low'].rolling(roll).min().iloc[-1])
    h52 = float(h['High'].rolling(roll).max().iloc[-1])
    pct52 = (cur - l52) / (h52 - l52) * 100
    vol_t = int(h['Volume'].iloc[-1])
    vol20 = float(h['Volume'].rolling(20).mean().iloc[-1])
    h5 = float(h['High'].iloc[-5:].max())
    l5 = float(h['Low'].iloc[-5:].min())
    target = info.get('targetMeanPrice', None)
    pe = info.get('trailingPE', None)
    beta = info.get('beta', None)
    rec = info.get('recommendationKey', 'N/A')
    analyst_up = (target/cur - 1)*100 if target else 0.0
    f38 = l52 + 0.382*(h52 - l52)
    f61 = l52 + 0.618*(h52 - l52)
    f78 = l52 + 0.786*(h52 - l52)
    
    # Order levels
    atr_v = vals['atr']
    stop_dist = atr_v * 2
    stop = cur - stop_dist
    t1 = cur + stop_dist * 2
    t2 = cur + stop_dist * 3
    rr = (t2 - cur) / stop_dist
    
    above_s20 = cur > vals['s20']
    above_s50 = cur > vals['s50']
    above_s200 = not np.isnan(vals['s200']) and cur > vals['s200']
    
    print(f"\n  {sym}: ${cur:.2f} | Gap={gap:+.2f}%")
    print(f"    SMA20=${vals['s20']:.2f} | SMA50=${vals['s50']:.2f} | SMA200=${vals['s200']:.2f}" if not np.isnan(vals['s200']) else f"    SMA20=${vals['s20']:.2f} | SMA50=${vals['s50']:.2f} | SMA200=N/A")
    print(f"    RSI(14)={vals['rsi']:.1f} | MACD={vals['macd']:.4f} | Signal={vals['signal']:.4f} | Hist={vals['macd']-vals['signal']:.4f}")
    print(f"    ATR=${atr_v:.2f} ({(atr_v/cur)*100:.1f}%) | BB: u=${vals['bbu']:.2f} m=${vals['bbm']:.2f} l=${vals['bbl']:.2f}")
    print(f"    52w: ${l52:.2f}-${h52:.2f} ({pct52:.0f}%) | Fib: 38=${f38:.2f} 62=${f61:.2f} 79=${f78:.2f}")
    print(f"    5d: ${l5:.2f}-${h5:.2f} | Mom5={vals['mom5']:+.1f}% | Mom20={vals['mom20']:+.1f}%")
    print(f"    Vol: {vol_t:,} / {vol20:,.0f} avg ({vol_t/vol20:.2f}x)")
    print(f"    Target=${target} ({analyst_up:+.1f}%) | PE={pe} | Beta={beta} | Rec={rec}")
    print(f"    Above 20/50/200: {above_s20}/{above_s50}/{above_s200}")
    print(f"    >>> ENTRY~${cur:.2f} | STOP=${stop:.2f} (-{(stop_dist/cur)*100:.1f}%) | T1=${t1:.2f} ({rr:.1f}:1) | T2=${t2:.2f} ({rr*1.5:.1f}:1)")

print("\n=== DONE ===")
