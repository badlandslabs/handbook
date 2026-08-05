#!/usr/bin/env python3
import yfinance as yf
import pandas as pd
import numpy as np

def fetch(ticker, period='6mo'):
    df = yf.download(ticker, period=period, progress=False)
    if df.empty: return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    return df.dropna(subset=['Close'])

def compute_ta(close, high, low):
    out = {}
    out['ema9']   = close.ewm(span=9).mean()
    out['ema20']  = close.ewm(span=20).mean()
    out['sma50']  = close.rolling(50).mean()
    out['sma200'] = close.rolling(200).mean()
    tr1 = high - low
    tr2 = np.abs(high - close.shift(1))
    tr3 = np.abs(low  - close.shift(1))
    tr  = pd.concat([tr1,tr2,tr3], axis=1).max(axis=1)
    out['atr14'] = tr.rolling(14).mean()
    out['atr20'] = tr.rolling(20).mean()
    d = close.diff()
    g = d.clip(lower=0).rolling(14).mean()
    l = (-d.clip(upper=0)).rolling(14).mean()
    out['rsi14'] = 100 - (100 / (1 + g/(l+1e-10)))
    d2 = close.diff()
    g2 = d2.clip(lower=0).rolling(2).mean()
    l2 = (-d2.clip(upper=0)).rolling(2).mean()
    out['rsi2']  = 100 - (100 / (1 + g2/(l2+1e-10)))
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    macd  = ema12 - ema26
    signal = macd.ewm(span=9).mean()
    out['macd_line']  = macd
    out['macd_signal'] = signal
    out['macd_hist']   = macd - signal
    out['vol_ma20'] = close.rolling(20).mean()  # placeholder
    out['bb_mid']   = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    out['bb_upper'] = out['bb_mid'] + 2*bb_std
    out['bb_lower'] = out['bb_mid'] - 2*bb_std
    return out

targets = ['MSFT','CRM','EXPE','SNPS','RIVN']
print("="*70)
print("DEEP DIVE: TOP 5 SWING SETUPS")
print("="*70)

for ticker in targets:
    df = fetch(ticker, period='6mo')
    if df.empty: continue

    c = df['Close']; v = df['Volume']; h = df['High']; lo = df['Low']
    ta = compute_ta(c, h, lo)

    p    = float(c.iloc[-1])
    e9   = float(ta['ema9'].iloc[-1])
    e9_5 = float(ta['ema9'].dropna().iloc[-6]) if len(ta['ema9'].dropna())>=6 else e9
    e20  = float(ta['ema20'].iloc[-1])
    e20_5= float(ta['ema20'].dropna().iloc[-6]) if len(ta['ema20'].dropna())>=6 else e20
    s50  = float(ta['sma50'].iloc[-1])
    s200 = float(ta['sma200'].iloc[-1]) if len(df)>=200 else np.nan
    atr14= float(ta['atr14'].iloc[-1])
    atr20= float(ta['atr20'].iloc[-1])
    r14  = float(ta['rsi14'].iloc[-1])
    r2   = float(ta['rsi2'].iloc[-1])
    mh   = float(ta['macd_hist'].iloc[-1])
    ml   = float(ta['macd_line'].iloc[-1])
    ms   = float(ta['macd_signal'].iloc[-1])
    bbu  = float(ta['bb_upper'].iloc[-1])
    bbl  = float(ta['bb_lower'].iloc[-1])
    bbw  = (bbu - bbl) / p * 100
    va   = float(v.rolling(20).mean().iloc[-1])
    vt   = float(v.iloc[-1])
    vr   = vt / va if va > 0 else 0

    h52  = float(c.iloc[-252:].max()) if len(c)>=252 else float(h.max())
    l52  = float(c.iloc[-252:].min()) if len(c)>=252 else float(lo.min())

    r5d  = float((c.iloc[-1]/c.iloc[-6]-1)*100) if len(c)>=6 else 0
    r20d = float((c.iloc[-1]/c.iloc[-21]-1)*100) if len(c)>=21 else 0

    res20  = float(h.iloc[-20:].max())
    sup20  = float(lo.iloc[-20:].min())
    s10_lo = float(lo.iloc[-10:].min())
    s5_lo  = float(lo.iloc[-5:].min())
    pullback = (p - res20) / res20 * 100

    bull_stack = (not np.isnan(s200) and e20 > s50 > s200) or (np.isnan(s200) and e20 > s50)

    print(f"\n{'='*30} {ticker} {'='*30}")
    print(f"  PRICE: ${p:.2f} | ATR14=${atr14:.2f}({atr14/p*100:.2f}%) | ATR20=${atr20:.2f}")
    print(f"  20d Range: High=${res20:.2f}({pullback:+.1f}%) | Low=${sup20:.2f} | 10dLow=${s10_lo:.2f} | 5dLow=${s5_lo:.2f}")
    print(f"  52w High=${h52:.2f}({(p/h52-1)*100:.1f}%) | 52w Low=${l52:.2f}({(p/l52-1)*100:.1f}%)")
    print(f"  EMA9=${e9:.2f}({(e9-e9_5)/e9_5*100:+.1f}%) | EMA20=${e20:.2f}({(e20-e20_5)/e20_5*100:+.1f}%)")
    print(f"  SMA50=${s50:.2f}({(p/s50-1)*100:+.1f}%)")
    if not np.isnan(s200): print(f"  SMA200=${s200:.2f}({(p/s200-1)*100:+.1f}%)")
    print(f"  EMA_BULL_STACK={bull_stack} | EMA9>EMA20={e9>e20}")
    print(f"  RSI14={r14:.1f} | RSI2={r2:.1f}")
    print(f"  MACD: line={ml:.3f} signal={ms:.3f} hist={mh:.3f}")
    print(f"  BB: Upper=${bbu:.2f} Lower=${bbl:.2f} Width={bbw:.1f}%")
    print(f"  Vol: today={vt:,.0f} avg20d={va:,.0f} ratio={vr:.1f}x")
    print(f"  Returns: 5d={r5d:+.1f}% | 20d={r20d:+.1f}%")

# Macro
print("\n" + "="*70)
print("MACRO REGIME")
print("="*70)
for ticker in ['SPY', 'IWM']:
    df = fetch(ticker, period='1y')
    if df.empty: continue
    c = df['Close']
    p = float(c.iloc[-1])
    ta = compute_ta(c, df['High'], df['Low'])
    r14 = float(ta['rsi14'].iloc[-1])
    atr14 = float(ta['atr14'].iloc[-1])
    s200 = float(ta['sma200'].iloc[-1]) if len(df)>=200 else np.nan
    s200_slope = np.nan
    if len(df)>=220:
        s200_now  = float(ta['sma200'].iloc[-1])
        s200_then = float(ta['sma200'].iloc[-20])
        s200_slope = (s200_now - s200_then)/s200_then*100
    regime = "BULL" if (p > s200 and s200_slope > 0) else \
             "BEAR" if (p < s200 and s200_slope < 0) else "TRANSITIONAL"
    print(f"  {ticker}: ${p:.2f} | RSI={r14:.1f} | ATR={atr14:.2f} | SMA200={s200:.2f}({(p/s200-1)*100:+.1f}%) | slope={s200_slope:+.2f}% | {regime}")

print("\n[COMPLETE]")
