#!/usr/bin/env python3
import json
d = json.load(open('/opt/data/handbook/scan_live_new.json'))
print("=== INDICES FULL ===")
for k, v in d['indices'].items():
    print(f"\n{k}:")
    for mk, mv in v.items():
        if mv is not None:
            print(f"  {mk}: {mv}")

print("\n=== ALL SCANNED STOCKS ===")
for r in d['top_long']:
    print(f"{r['sym']:6s} Score={r['score']:2d} ${r['close']:>10.2f} RSI={r['rsi']:5.1f} ATR%={r['atr_pct']:4.1f}% 20d={r['ret20']:>+6.1f}% VolR={r['vol_ratio']:.2f} RangePos={r['range_pos']:.2f}")
