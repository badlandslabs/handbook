#!/usr/bin/env python3
"""Extract detailed data for swing trade report"""
import yfinance as yf, pandas as pd, numpy as np

def fetch_ta(ticker, period='3mo'):
    try:
        t = yf.Ticker(ticker)
        df = t.history(period=period, interval='1d', auto_adjust=True)
        if df is None or df.empty or len(df) < 30: return None
        c = df['Close']; h = df['High']; l = df['Low']; v = df['Volume']
        ma20 = c.rolling(20).mean(); ma50 = c.rolling(50).mean(); ma200 = c.rolling(200).mean()
        delta = c.diff()
        gain = delta.clip(lower=0).ewm(alpha=1/14, min_periods=14).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1/14, min_periods=14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = (100 - 100/(1+rs)).iloc[-1]
        ema12 = c.ewm(12).mean(); ema26 = c.ewm(26).mean()
        macd_line = ema12 - ema26; macd_sig = macd_line.ewm(9).mean()
        macd_hist = macd_line - macd_sig
        tr = pd.concat([h-l, (h-c.shift(1)).abs(), (l-c.shift(1)).abs()], axis=1).max(axis=1)
        atr = tr.ewm(14).mean().iloc[-1]
        last = c.iloc[-1]; vol20 = v.rolling(20).mean().iloc[-1]
        high52 = h.rolling(252).max().iloc[-1]
        mom20 = (c.iloc[-1]/c.iloc[-20]-1)*100 if len(c)>=20 else 0
        slope20 = (ma20.iloc[-1]/ma20.iloc[-5]-1)*100 if len(ma20)>=5 else 0
        mh = float(macd_hist.iloc[-1]); mh_p = float(macd_hist.iloc[-2])
        vol_ratio = float(v.iloc[-1]/vol20) if vol20 > 0 else 1
        vol5 = float(v.rolling(5).mean().iloc[-1])
        return {
            'last': float(last), 'rsi': float(rsi), 'atr': float(atr),
            'atr_pct': float(atr/last*100),
            'macd_hist': mh, 'macd_hist_prev': mh_p,
            'macd_bull_cross': bool(mh > 0 and mh_p <= 0),
            'macd_hist_pos': mh > 0,
            'above_20': bool(last > float(ma20.iloc[-1])),
            'above_50': bool(last > float(ma50.iloc[-1])),
            'above_200': bool(last > float(ma200.iloc[-1])),
            'ma20': float(ma20.iloc[-1]), 'ma50': float(ma50.iloc[-1]),
            'ma200': float(ma200.iloc[-1]),
            'mom20': float(mom20), 'slope20': float(slope20),
            'vol_ratio': vol_ratio, 'vol5': vol5, 'vol20': float(vol20),
            'high52': float(high52), 'low52': float(l.rolling(252).min().iloc[-1]),
        }
    except: return None

tickers = ['QQQ','SPY','IWM','^VIX','META','AMD','PANW','AAPL','NVDA','NET','NFLX','ORCL','AVGO','AMAT','FTNT','SPGI','COST','TXN','GOOGL','MSFT']
data = {}
for t in tickers:
    data[t] = fetch_ta(t)

# Index data
for sym in ['QQQ','SPY','IWM','^VIX']:
    d = data.get(sym)
    if d:
        print(f"INDEX {sym}: price={d['last']:.4f} rsi={d['rsi']:.2f} atr_pct={d['atr_pct']:.2f} mom20={d['mom20']:.2f} slope20={d['slope20']:.4f} above200={d['above_200']} above50={d['above_50']} macd_hist={d['macd_hist']:.6f} vol={d['vol_ratio']:.2f}")

# Key components for report
print()
for sym in ['META','AMD','PANW','NET','AAPL','NVDA','NFLX','AMAT','FTNT','SPGI']:
    d = data.get(sym)
    if d:
        dist52 = (d['last']/d['high52']-1)*100
        print(f"COMP {sym}: price={d['last']:.4f} rsi={d['rsi']:.2f} atr_pct={d['atr_pct']:.2f} mom20={d['mom20']:.2f} slope20={d['slope20']:.4f} above200={d['above_200']} above50={d['above_50']} above20={d['above_20']} macd_hist={d['macd_hist']:.6f} macd_bull={d['macd_bull_cross']} vol={d['vol_ratio']:.2f} vol5={d['vol5']:.0f} vol20={d['vol20']:.0f} high52={d['high52']:.4f} dist52high={dist52:.2f}")
