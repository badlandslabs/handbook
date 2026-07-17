import csv

print("=" * 90)
print("ALL STOCKS — swing_scan_results.csv")
print("=" * 90)
with open('/opt/data/handbook/swing_scan_results.csv') as f:
    rows = list(csv.DictReader(f))

for r in rows:
    p = float(r['Price'])
    atr = float(r['ATR14'])
    stop = p - atr * 1.5
    t1 = p + atr * 1.5 * 2
    t2 = p + atr * 1.5 * 3
    rr = (t1 - p) / (p - stop) if (p - stop) > 0 else 0
    print(f"{r['Symbol']:8} P=${p:>8.2f} RSI={float(r['RSI']):>5.1f} ATR={atr:>6.2f} "
          f"5D={float(r['Ret_5d']):>+7.2f}% 20D={float(r['Ret_20d']):>+8.2f}% "
          f"Sc={float(r['Score']):>3.0f} Ab50={r['Above_SMA50']} Ab20={r['Above_SMA20']} "
          f"T1={t1:.2f}({rr:.1f}:1) T2={t2:.2f} VolR={float(r['VolRatio']):.2f}x BB={float(r['BB_Pos']):.2f}")

print()
print("=" * 90)
print("scan_results_live.csv — TOP SCORED")
print("=" * 90)
with open('/opt/data/handbook/scan_results_live.csv') as f:
    rows2 = list(csv.DictReader(f))

rows2.sort(key=lambda x: float(x['score']), reverse=True)
for r in rows2[:20]:
    p = float(r['close'])
    atr = float(r['atr'])
    chg5d = float(r['chg5d'])
    chg20d = float(r['chg20d'])
    rsi = float(r['rsi'])
    stop = p - atr * 1.5
    t1 = p + atr * 1.5 * 2
    t2 = p + atr * 1.5 * 3
    rr = (t1 - p) / (p - stop) if (p - stop) > 0 else 0
    range_pos = float(r['range_pos'])
    vol_ratio = float(r['vol_ratio'])
    print(f"{r['sym']:8} P=${p:>8.2f} RSI={rsi:>5.1f} ATR={atr:>6.2f} "
          f"5D={chg5d:>+7.2f}% 20D={chg20d:>+8.2f}% Sc={r['score']:>3} "
          f"T1={t1:.2f}({rr:.1f}:1) T2={t2:.2f} VolR={vol_ratio:.2f}x "
          f"RangePos={range_pos:.2f}")
