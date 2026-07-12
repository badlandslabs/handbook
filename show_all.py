#!/usr/bin/env python3
import json, sys
d = json.load(open('/opt/data/handbook/scan_deep.json'))
WATCHLIST = [
    'AAPL','MSFT','NVDA','AMZN','META','GOOGL','GOOG','TSLA','AVGO',
    'AMD','AMAT','LRCX','KLAC','MU','INTC','QCOM','TXN','NXPI','MRVL','ADI','ON','MCHP','ASML','SNPS','CDNS',
    'PANW','CRWD','ZS','NET','DDOG','NOW','VEEV','SNOW','CRM','INTU','ADSK',
    'ADP','HON','GEHC','PYPL','SQ','COIN',
]
top = d['top_long']
lines = []
for i, r in enumerate(top):
    sym = WATCHLIST[i] if i < len(WATCHLIST) else f"UNK{i}"
    sc = int(r.get('score', 0))
    c = float(r.get('close', 0))
    rsi = float(r.get('rsi', 0))
    ap = float(r.get('atr_pct', 0))
    r5 = float(r.get('ret5', 0))
    r20 = float(r.get('ret20', 0))
    rp = float(r.get('range_pos', 0))
    a20 = r.get('above_20', False)
    a50 = r.get('above_50', False)
    a200 = r.get('above_200', False)
    atr = float(r.get('atr', 0))
    macd = float(r.get('macd', 0))
    low = float(r.get('low20', 0))
    high = float(r.get('high20', 0))
    vr5 = float(r.get('vol_ratio_5', 0))
    lines.append((sc, sym, c, rsi, ap, r5, r20, rp, a20, a50, a200, atr, macd, low, high, vr5))

lines.sort(key=lambda x: x[0], reverse=True)
for x in lines:
    sc, sym, c, rsi, ap, r5, r20, rp, a20, a50, a200, atr, macd, low, high, vr5 = x
    sys.stdout.write(f"{sym}|{sc}|{c:.2f}|{rsi:.1f}|{ap:.1f}|{r5:.1f}|{r20:.1f}|{rp:.2f}|{'Y' if a20 else 'N'}|{'Y' if a50 else 'N'}|{'Y' if a200 else 'N'}|{atr:.2f}|{macd:.2f}|{low:.2f}|{high:.2f}|{vr5:.2f}\n")
