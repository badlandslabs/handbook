#!/usr/bin/env python3
import json
d = json.load(open('/opt/data/handbook/scan_deep.json'))
print(f"Scan: {d['scan_time']}")
print()
print("=== INDICES ===")
for k, v in d['indices'].items():
    print(f"{k:6s} ${v['close']:>10.2f} | RSI={v['rsi']:5.1f} | ATR%={v['atr_pct']:4.1f}% | 20d={v['ret20']:>+6.1f}% | 200MA={'Y' if v.get('above_200') else 'N'}")
print()
print("=== ALL STOCKS (sorted by score) ===")
for r in d['top_long']:
    sym = r.get('sym', '?')
    print(f"{sym:6s} S={r['score']:2d} | ${r['close']:>10.2f} | RSI={r['rsi']:5.1f} | ATR%={r['atr_pct']:4.1f}% | 5d={r['ret5']:>+5.1f}% | 20d={r['ret20']:>+6.1f}% | Vol5R={r['vol_ratio_5']:.2f} | RngPos={r['range_pos']:.2f} | 20={'Y' if r['above_20'] else 'N'} 50={'Y' if r['above_50'] else 'N'} 200={'Y' if r['above_200'] else 'N'}")
    print(f"       Range: ${r['low20']:.2f} → ${r['high20']:.2f} | MACD={r['macd']:.2f} | ATR=${r['atr']:.2f}")
