#!/usr/bin/env python3
import json
d = json.load(open('/opt/data/handbook/scan_deep.json'))

# Reconstruct the order from the scan loop
WATCHLIST = [
    'QQQ','SPY','IWM','^VIX',
    'AAPL','MSFT','NVDA','AMZN','META','GOOGL','GOOG','TSLA','AVGO',
    'AMD','AMAT','LRCX','KLAC','MU','INTC','QCOM','TXN','NXPI','MRVL','ADI','ON','MCHP','ASML','SNPS','CDNS',
    'PANW','CRWD','ZS','NET','DDOG','NOW','VEEV','SNOW','CRM','INTU','ADSK',
    'ADP','HON','GEHC','PYPL','SQ','COIN',
]
# skip indices
stock_tickers = [s for s in WATCHLIST if s not in ['QQQ','SPY','IWM','^VIX']]

idx = d['indices']
print(f"DEEP SCAN — {d['scan_time']}")
print()
print("=== INDEX SUMMARY ===")
for k in ['QQQ','SPY','IWM','^VIX']:
    v = idx.get(k, {})
    print(f"  {k:6s} ${v.get('close',0):>10.2f} | RSI={v.get('rsi',0):5.1f} | ATR%={v.get('atr_pct',0):4.1f}% | 5d={v.get('ret5',0):>+5.1f}% | 20d={v.get('ret20',0):>+6.1f}% | 200MA={'Y' if v.get('above_200') else 'N'}")

print()
print("=== STOCK SCAN (Top 20 by Score) ===")
top = d['top_long']
# The JSON top_long order matches stock_tickers order
for i, r in enumerate(top):
    if i < len(stock_tickers):
        sym = stock_tickers[i]
    else:
        sym = f"UNK_{i}"
    close = r.get('close',0)
    score = r.get('score',0)
    rsi = r.get('rsi',0)
    atr_pct = r.get('atr_pct',0)
    ret5 = r.get('ret5',0)
    ret20 = r.get('ret20',0)
    vr5 = r.get('vol_ratio_5',0)
    rp = r.get('range_pos',0)
    a20 = 'Y' if r.get('above_20') else 'N'
    a50 = 'Y' if r.get('above_50') else 'N'
    a200 = 'Y' if r.get('above_200') else 'N'
    low = r.get('low20',0)
    high = r.get('high20',0)
    macd = r.get('macd',0)
    atr = r.get('atr',0)
    print(f"  {sym:6s} S={score:2d} | ${close:>10.2f} | RSI={rsi:5.1f} | ATR%={atr_pct:4.1f}% | 5d={ret5:>+5.1f}% | 20d={ret20:>+6.1f}% | Vol5R={vr5:.2f} | RngPos={rp:.2f} | 20={a20} 50={a50} 200={a200}")
    print(f"         Range: ${low:.2f} → ${high:.2f} | MACD={macd:.2f} | ATR=${atr:.2f}")
