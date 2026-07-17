#!/usr/bin/env python3
import yfinance as yf, pandas as pd, numpy as np
def ta(ticker):
    try:
        df = yf.Ticker(ticker).history(period='1y', interval='1d', auto_adjust=True)
        if df is None or df.empty or len(df) < 60: return None
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
        atr = tr.ewm(14).mean().iloc[-1]; last = c.iloc[-1]
        vol20 = v.rolling(20).mean().iloc[-1]
        high1y = h.rolling(252).max().iloc[-1]
        mom20 = (c.iloc[-1]/c.iloc[-20]-1)*100 if len(c)>=20 else 0
        slope20 = (ma20.iloc[-1]/ma20.iloc[-5]-1)*100 if len(ma20)>=5 else 0
        mh = float(macd_hist.iloc[-1]); mh_p = float(macd_hist.iloc[-2])
        vol_r = float(v.iloc[-1]/vol20)
        dist = float((last/high1y-1)*100)
        ma200_val = float(ma200.iloc[-1]) if not pd.isna(ma200.iloc[-1]) else 0
        ma50_val = float(ma50.iloc[-1])
        ma20_val = float(ma20.iloc[-1])
        return f'{ticker:6s} price={last:.2f} rsi={rsi:.1f} atr%={atr/last*100:.1f} mom20={mom20:+.1f}% slope20={slope20:+.2f}% macd_hist={mh:+.3f} bull_cross={mh>0 and mh_p<=0} vol={vol_r:.1f}x above200={last>ma200_val} above50={last>ma50_val} above20={last>ma20_val} high1y={high1y:.2f} dist1y={dist:+.1f}%'
    except Exception as e:
        return f'{ticker}: ERR {e}'
for s in ['NFLX','AMAT','FTNT','AVGO','SPGI','TXN','COST','GOOGL','MSFT','QCOM','INTC','KLAC','LRCX']:
    print(ta(s))
