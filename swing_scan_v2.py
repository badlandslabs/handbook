#!/opt/hermes/.venv/bin/python3
import yfinance as yf, warnings, pandas as pd, numpy as np
warnings.filterwarnings('ignore')

def ta(h):
    c, hi, lo, vol = h['Close'], h['High'], h['Low'], h['Volume']
    n = len(c)
    s20 = c.rolling(20).mean()
    s50 = c.rolling(50).mean()
    s200 = c.rolling(200).mean() if n >= 200 else c * np.nan
    e12, e26 = c.ewm(12).mean(), c.ewm(26).mean()
    macd, signal = e12 - e26, macd.ewm(9).mean()
    d = c.diff()
    gain = d.where(d > 0, 0).rolling(14).mean()
    loss = (-d.where(d < 0, 0)).rolling(14).mean()
    rsi = 100 - (100 / (1 + gain/loss))
    tr = pd.concat([hi-lo, (hi-c.shift(1)).abs(), (lo-c.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    bbm = c.rolling(20).mean()
    bbs = c.rolling(20).std()
    bbu, bbl = bbm + 2*bbs, bbm - 2*bbs
    mom5 = (c / c.shift(5) - 1) * 100 if n >= 6 else c * 0
    mom20 = (c / c.shift(20) - 1) * 100 if n >= 21 else c * 0
    roll52 = min(n, 252)
    l52 = lo.rolling(roll52).min()
    h52 = hi.rolling(roll52).max()
    return s20, s50, s200, macd, signal, rsi, atr, bbu, bbm, bbl, mom5, mom20, l52, h52

# === REGIME ===
print("=== REGIME ===")
for nm, sym in [('QQQ','^QQQ'),('SPY','SPY'),('IWM','IWM')]:
    h = yf.Ticker(sym).history(period='1y', interval='1d')
    if h.empty: continue
    c = h['Close'].iloc[-1]
    s20, s50, s200, macd, signal, rsi, atr, bbu, bbm, bbl, mom5, mom20, l52, h52 = ta(h)
    s200v = float(s200.iloc[-1]) if not s200.isna().iloc[-1] else None
    regime = "BULL" if (s200v and c > s200v) else ("BEAR" if (s200v and c < s200v) else "TRANSITIONAL")
    m5 = float(mom5.iloc[-1])
    m20 = float(mom20.iloc[-1])
    sv = f"${c:.2f} s200={'N/A' if s200v is None else f'${s200v:.2f}'} 5d={m5:+.1f}% 20d={m20:+.1f}% [{regime}]"
    print(f"  {nm}: {sv}")

v = yf.Ticker('^VIX').history(period='5d', interval='1d')
t = yf.Ticker('^TNX').history(period='5d', interval='1d')
print(f"  VIX={v['Close'].iloc[-1]:.2f} | 10Y TNX={t['Close'].iloc[-1]:.4f}%")

print("\n=== SECTORS ===")
for sym in ['XLK','XLF','XLV','XLY','XLE']:
    h = yf.Ticker(sym).history(period='60d', interval='1d')
    if not h.empty:
        c = h['Close'].iloc[-1]
        m5 = (c / h['Close'].iloc[-6] - 1)*100 if len(h) >= 6 else 0
        m20 = (c / h['Close'].iloc[-21] - 1)*100 if len(h) >= 21 else 0
        print(f"  {sym}: ${c:.2f} 5d={m5:+.1f}% 20d={m20:+.1f}%")

# === TOP CANDIDATES ===
print("\n=== SWING SCAN RESULTS ===")
for sym in ['ADBE', 'ADP', 'CRM', 'MSFT', 'AVGO', 'BKNG']:
    h = yf.Ticker(sym).history(period='1y', interval='1d')
    info = yf.Ticker(sym).info
    if h.empty: continue
    c = h['Close'].iloc[-1]
    prev = h['Close'].iloc[-2] if len(h) > 1 else c
    gap = (c/prev - 1)*100
    s20, s50, s200, macd, signal, rsi, atr, bbu, bbm, bbl, mom5, mom20, l52, h52 = ta(h)
    cur_atr = float(atr.iloc[-1])
    cur_rsi = float(rsi.iloc[-1])
    cur_macd = float(macd.iloc[-1])
    cur_sig = float(signal.iloc[-1])
    cur_hist = cur_macd - cur_sig
    cur_s20 = float(s20.iloc[-1])
    cur_s50 = float(s50.iloc[-1])
    cur_s200v = float(s200.iloc[-1]) if not s200.isna().iloc[-1] else None
    cur_bbu = float(bbu.iloc[-1])
    cur_bbm = float(bbm.iloc[-1])
    cur_bbl = float(bbl.iloc[-1])
    cur_l52 = float(l52.iloc[-1])
    cur_h52 = float(h52.iloc[-1])
    pct52 = (c - cur_l52) / (cur_h52 - cur_l52) * 100
    m5 = float(mom5.iloc[-1])
    m20 = float(mom20.iloc[-1])
    vol_t = int(h['Volume'].iloc[-1])
    vol20 = int(h['Volume'].rolling(20).mean().iloc[-1])
    h5 = float(h['High'].iloc[-5:].max())
    l5 = float(h['Low'].iloc[-5:].min())
    target = info.get('targetMeanPrice', None)
    pe = info.get('trailingPE', None)
    beta = info.get('beta', None)
    rec = info.get('recommendationKey', 'N/A')
    analyst_up = (target/c - 1)*100 if target else 0
    f38 = cur_l52 + 0.382*(cur_h52 - cur_l52)
    f61 = cur_l52 + 0.618*(cur_h52 - cur_l52)
    f78 = cur_l52 + 0.786*(cur_h52 - cur_l52)

    # Stop/target
    stop_dist = cur_atr * 2
    stop = c - stop_dist
    t1 = c + stop_dist * 2
    t2 = c + stop_dist * 3
    rr = (t2 - c) / stop_dist

    above_s20 = c > cur_s20
    above_s50 = c > cur_s50
    above_s200 = cur_s200v and c > cur_s200v

    print(f"\n  {sym}: ${c:.2f} | Gap={gap:+.2f}%")
    print(f"    MA: s20={cur_s20:.2f} s50={cur_s50:.2f} s200={str(round(cur_s200v,2)) if cur_s200v else 'N/A'}")
    print(f"    RSI={cur_rsi:.1f} MACD={cur_macd:.3f} Sig={cur_sig:.3f} Hist={cur_hist:.4f}")
    print(f"    ATR=${cur_atr:.2f} ({(cur_atr/c)*100:.1f}%) | BB: u={cur_bbu:.2f} m={cur_bbm:.2f} l={cur_bbl:.2f}")
    print(f"    52w: {cur_l52:.2f}-{cur_h52:.2f} ({pct52:.0f}%) | Fib: 38={f38:.2f} 62={f61:.2f} 79={f78:.2f}")
    print(f"    5d: ${l5:.2f}-${h5:.2f} | 5d_mom={m5:+.1f}% 20d_mom={m20:+.1f}%")
    print(f"    Vol={vol_t:,} / {vol20:,} ({vol_t/vol20:.2f}x)")
    print(f"    Target=${target} ({analyst_up:+.1f}%) | PE={pe} | Beta={beta} | Rec={rec}")
    print(f"    Above 20/50/200: {above_s20}/{above_s50}/{above_s200}")
    print(f"    >> ENTRY=${c:.2f} | STOP=${stop:.2f} (-{(stop_dist/c)*100:.1f}%) | T1=${t1:.2f} | T2=${t2:.2f} | R/R={rr:.1f}:1")
