#!/usr/bin/env python3
import json

d = json.load(open('/opt/data/handbook/scan_live_new.json'))
print('SCAN TIME:', d['scan_time'])
print()
print('=== INDICES ===')
for k, v in d['indices'].items():
    print(f"{k}: ${v['close']:.2f} | RSI={v['rsi']:.1f} | ATR%={v['atr_pct']:.1f}% | Regime={v['regime']} | 20d={v['ret20']:+.1f}%")
print()
print('=== TOP 20 STOCKS BY SCORE ===')
for r in d['top_long'][:20]:
    print(f"{r['sym']:6s} ${r['close']:>10.2f} | RSI={r['rsi']:5.1f} | ATR%={r['atr_pct']:4.1f}% | 20d={r['ret20']:>+6.1f}% | VolR={r['vol_ratio']:.2f} | Score={r['score']} | 20MA={r['above_20']} 50MA={r['above_50']} 200MA={r['above_200']}")
    print(f"       Range: ${r['low20']:.2f} - ${r['high20']:.2f} | RangePos={r['range_pos']:.2f} | MACD={r['macd']:.2f}")
