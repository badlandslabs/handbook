#!/usr/bin/env python3
import json
d = json.load(open('/opt/data/handbook/scan_deep.json'))
WATCHLIST = [
    'QQQ','SPY','IWM','^VIX',
    'AAPL','MSFT','NVDA','AMZN','META','GOOGL','GOOG','TSLA','AVGO',
    'AMD','AMAT','LRCX','KLAC','MU','INTC','QCOM','TXN','NXPI','MRVL','ADI','ON','MCHP','ASML','SNPS','CDNS',
    'PANW','CRWD','ZS','NET','DDOG','NOW','VEEV','SNOW','CRM','INTU','ADSK',
    'ADP','HON','GEHC','PYPL','SQ','COIN',
]
stock_tickers = [s for s in WATCHLIST if s not in ['QQQ','SPY','IWM','^VIX']]
top = d['top_long']
for i, r in enumerate(top):
    sym = stock_tickers[i] if i < len(stock_tickers) else f"X{i}"
    sc = r.get('score',0)
    c = r.get('close',0)
    rsi = r.get('rsi',0)
    ap = r.get('atr_pct',0)
    r5 = r.get('ret5',0)
    r20 = r.get('ret20',0)
    rp = r.get('range_pos',0)
    a20 = r.get('above_20',False)
    a50 = r.get('above_50',False)
    a200 = r.get('above_200',False)
    print(f"{sym:6s}|{sc:2d}|{c:>10.2f}|RSI={rsi:5.1f}|ATR%={ap:4.1f}|5d={r5:>+5.1f}|20d={r20:>+6.1f}|RP={rp:.2f}|20={'Y' if a20 else 'N'}50={'Y' if a50 else 'N'}200={'Y' if a200 else 'N'}")
