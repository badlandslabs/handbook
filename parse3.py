#!/usr/bin/env python3
import json
d = json.load(open('/opt/data/handbook/scan_live_new.json'))
all_results = d.get('all_results', d['top_long'])
print(f"Total stocks scanned: {len(all_results)}")
for r in all_results:
    print(f"{r['sym']:6s} ${r['close']:>10.2f} | RSI={r['rsi']:5.1f} | ATR%={r['atr_pct']:4.1f}% | 20d={r['ret20']:>+6.1f}% | Score={r['score']}")
