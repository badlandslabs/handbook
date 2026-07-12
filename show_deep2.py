#!/usr/bin/env python3
import json
d = json.load(open('/opt/data/handbook/scan_deep.json'))
# indices
print("=== INDICES ===")
idx = d['indices']
for k in ['QQQ','SPY','IWM','^VIX']:
    v = idx.get(k, {})
    if v:
        print(f"{k:6s} ${v.get('close',0):>10.2f} | RSI={v.get('rsi',0):5.1f} | ATR%={v.get('atr_pct',0):4.1f}% | 20d={v.get('ret20',0):>+6.1f}% | 200MA={'Y' if v.get('above_200') else 'N'}")
print()
# stocks from the list in the JSON (they're stored as dict entries, key = sym)
print("=== TOP STOCKS ===")
all_items = [(k, v) for k, v in d['top_long']]
for item in all_items:
    r = item
    sym = r.get('sym', '?')
    if sym == '?':
        # Try finding sym in the data differently
        for key in ['symbol', 'ticker', 'name']:
            if key in r:
                sym = r[key]
                break
    close = r.get('close', 0)
    score = r.get('score', 0)
    rsi = r.get('rsi', 0)
    atr_pct = r.get('atr_pct', 0)
    ret5 = r.get('ret5', 0)
    ret20 = r.get('ret20', 0)
    vr5 = r.get('vol_ratio_5', 0)
    rp = r.get('range_pos', 0)
    a20 = 'Y' if r.get('above_20') else 'N'
    a50 = 'Y' if r.get('above_50') else 'N'
    a200 = 'Y' if r.get('above_200') else 'N'
    low = r.get('low20', 0)
    high = r.get('high20', 0)
    macd = r.get('macd', 0)
    atr = r.get('atr', 0)
    print(f"?? S={score:2d} | ${close:>10.2f} | RSI={rsi:5.1f} | ATR%={atr_pct:4.1f}% | 5d={ret5:>+5.1f}% | 20d={ret20:>+6.1f}% | Vol5R={vr5:.2f} | RngPos={rp:.2f} | 20={a20} 50={a50} 200={a200}")
    print(f"    Range: ${low:.2f} → ${high:.2f} | MACD={macd:.2f} | ATR=${atr:.2f}")
