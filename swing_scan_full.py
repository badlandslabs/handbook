#!/usr/bin/env python3
"""NASDAQ Swing Trade Scanner — Full Multi-Dimensional Analysis"""
import yfinance as yf, pandas as pd, numpy as np
from datetime import datetime

TODAY = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')

def fetch_ta(ticker, period='3mo'):
    try:
        t = yf.Ticker(ticker)
        df = t.history(period=period, interval='1d', auto_adjust=True)
        if df is None or df.empty or len(df) < 30: return None
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
        atr = tr.ewm(14).mean().iloc[-1]
        last = c.iloc[-1]; vol20 = v.rolling(20).mean().iloc[-1]
        high52 = h.rolling(252).max().iloc[-1]; low52 = l.rolling(252).min().iloc[-1]
        mom20 = (c.iloc[-1]/c.iloc[-20]-1)*100 if len(c)>=20 else 0
        slope20 = (ma20.iloc[-1]/ma20.iloc[-5]-1)*100 if len(ma20)>=5 else 0
        mh = [float(macd_hist.iloc[i]) for i in range(-3, 0)]
        vol_ratio = float(v.iloc[-1]/vol20) if vol20 > 0 else 1
        return {
            'last': float(last), 'rsi': float(rsi), 'atr': float(atr),
            'atr_pct': float(atr/last*100),
            'macd_hist': mh[-1], 'macd_hist_prev': mh[-2], 'macd_hist_prev2': mh[-3],
            'macd_bullish_cross': bool(mh[-1] > 0 and mh[-2] <= 0),
            'macd_bearish_cross': bool(mh[-1] < 0 and mh[-2] >= 0),
            'macd_steepening': bool(mh[-1] > mh[-2]),
            'above_20': bool(last > float(ma20.iloc[-1])) if not pd.isna(ma20.iloc[-1]) else False,
            'above_50': bool(last > float(ma50.iloc[-1])) if not pd.isna(ma50.iloc[-1]) else False,
            'above_200': bool(last > float(ma200.iloc[-1])) if not pd.isna(ma200.iloc[-1]) else False,
            'ma20': float(ma20.iloc[-1]), 'ma50': float(ma50.iloc[-1]),
            'mom20': float(mom20), 'slope20': float(slope20),
            'vol_ratio': vol_ratio,
            'high52': float(high52), 'low52': float(low52),
            'dist_high52': float((last/high52-1)*100),
            'dist_low52': float((last/low52-1)*100),
        }
    except: return None

def score(ta):
    if not ta: return -999, [], []
    s = 0; bull = []; bear = []
    rsi = ta['rsi']
    if ta['above_50']: s += 10
    if ta['above_20']: s += 8
    if ta['above_200']: s += 7
    if ta['slope20'] > 1: s += 5; bull.append('Rising 20d slope')
    elif ta['slope20'] < -2: s -= 5; bear.append('Falling 20d slope')
    if 35 <= rsi < 45: s += 18; bull.append(f'Oversold RSI={rsi:.1f}')
    elif 45 <= rsi <= 58: s += 12; bull.append(f'Neutral RSI={rsi:.1f}')
    elif 58 < rsi <= 65: s += 8; bull.append(f'Strong RSI={rsi:.1f}')
    elif rsi > 70: s -= 8; bear.append(f'Overbought RSI={rsi:.1f}')
    elif rsi < 35: s -= 15; bear.append(f'Severely oversold')
    mom = ta['mom20']
    if mom > 5: s += 8; bull.append(f'Strong 20d mom +{mom:.1f}%')
    elif mom < -5: s -= 8; bear.append(f'Weak mom {mom:.1f}%')
    if ta['macd_bullish_cross']: s += 10; bull.append('MACD bullish cross')
    elif ta['macd_steepening'] and ta['macd_hist'] > 0: s += 5
    elif ta['macd_bearish_cross']: s -= 10; bear.append('MACD bearish cross')
    if ta['vol_ratio'] > 1.8: s += 8; bull.append(f'Volume {ta["vol_ratio"]:.1f}x')
    elif ta['vol_ratio'] > 1.3: s += 4
    elif ta['vol_ratio'] < 0.5: s -= 5
    ap = ta['atr_pct']
    if 2.5 <= ap <= 5.0: s += 8
    elif 1.5 <= ap < 2.5: s += 4
    elif ap > 5.0: s += 6
    elif ap < 1.0: s -= 5
    d52 = ta['dist_high52']
    if -20 < d52 <= -10: s += 8; bull.append(f'Pullback {d52:.1f}% from 52w high')
    elif -30 < d52 <= -20: s += 10; bull.append(f'Deep pullback {d52:.1f}% from high')
    elif d52 > 90: s -= 5; bear.append('Near 52w high')
    return s, bull, bear

# Tickers
idx_tickers = ['QQQ', 'SPY', 'IWM', '^VIX']
comp_tickers = [
    'AAPL','MSFT','NVDA','GOOGL','AMZN','META','TSLA','AMD','AVGO',
    'COST','NFLX','ADBE','CRM','ORCL','QCOM','TXN','INTC','AMAT',
    'MU','LRCX','KLAC','PANW','SNPS','CDNS','MRVL','FTNT','HON',
    'INTU','ADP','GILD','MDLZ','KDP','NXPI','ADI','ON','FSLR',
    'CTAS','PAYX','CPRT','ROST','SBUX','KHC','MELI','DDOG','SNOW',
    'NET','CRWD','ZS','WDAY','TEAM','OKTA','DOCU','MRNA','EXC',
    'AMT','PLD','EQIX','SPGI','CME','ICE'
]
all_tickers = idx_tickers + comp_tickers

# Fetch
data = {}
for t in all_tickers:
    data[t] = fetch_ta(t)
    if data[t]:
        print(f"OK   {t:6s}: ${data[t]['last']:>10.2f} RSI={data[t]['rsi']:>5.1f} ATR%={data[t]['atr_pct']:>4.1f}% mom20={data[t]['mom20']:>+6.1f}%")
    else:
        print(f"FAIL {t}")

# Regime
q = data.get('QQQ', {}); s = data.get('SPY', {}); i_d = data.get('IWM', {}); v = data.get('^VIX', {})
vix_val = v.get('last', 20); vix_mom = v.get('mom20', 0)
bull_cnt = sum([q.get('above_200',False), q.get('above_50',False),
                 s.get('above_200',False), s.get('above_50',False),
                 i_d.get('above_50',False)])
if vix_val < 15 and bull_cnt >= 4 and q.get('mom20',0) > 0:
    regime = 'BULL'
elif vix_val > 25 or (bull_cnt <= 1 and q.get('mom20',0) < -3):
    regime = 'BEAR'
else:
    regime = 'TRANSITIONAL'

# Score components
scored = []
for t in comp_tickers:
    ta = data.get(t)
    if ta:
        sc, bull, bear = score(ta)
        scored.append({'symbol': t, 'score': sc, 'ta': ta, 'bull': bull, 'bear': bear})
scored.sort(key=lambda x: x['score'], reverse=True)
longs = [r for r in scored if r['score'] > 0][:5]
shorts = [r for r in scored if r['score'] < -10][:3]

print(f"\n{'='*70}")
print(f"MARKET REGIME: {regime}")
print(f"{'='*70}")
print(f"QQQ: ${q.get('last','N/A')} | RSI={q.get('rsi','N/A'):.1f} | ATR%={q.get('atr_pct','N/A'):.1f}% | mom20={q.get('mom20',0):+.1f}% | above200={q.get('above_200')}")
print(f"SPY: ${s.get('last','N/A')} | RSI={s.get('rsi','N/A'):.1f} | ATR%={s.get('atr_pct','N/A'):.1f}% | mom20={s.get('mom20',0):+.1f}% | above200={s.get('above_200')}")
print(f"IWM: ${i_d.get('last','N/A')} | RSI={i_d.get('rsi','N/A'):.1f} | ATR%={i_d.get('atr_pct','N/A'):.1f}% | mom20={i_d.get('mom20',0):+.1f}%")
print(f"VIX: ${v.get('last','N/A')} | RSI={v.get('rsi','N/A'):.1f} | mom20={v.get('mom20',0):+.1f}%")
print(f"\nTOP 5 LONG SETUPS:")
for r in scored[:5]:
    t = r['ta']
    print(f"  {r['symbol']:6s} Score={r['score']:+.0f} Price=${t['last']:.2f} RSI={t['rsi']:.1f} ATR%={t['atr_pct']:.1f}% mom20={t['mom20']:+.1f}% vol={t['vol_ratio']:.1f}x d52={t['dist_high52']:+.1f}%")

# Build advisories
print(f"\n{'='*70}")
print("DETAILED ADVISORIES (Top 3)")
print(f"{'='*70}")

advisories = []
for r in longs[:3]:
    ta = r['ta']
    price = ta['last']; atr = ta['atr']; atr_pct = ta['atr_pct']
    sl = price - (atr * 1.5); risk = atr * 1.5
    t1 = price + risk * 2.0; t2 = price + risk * 3.0
    t3 = ta['high52']
    if ta['rsi'] < 45:
        entry_px = price; entry_type = "BUY LIMIT at current (RSI oversold)"
    elif ta['macd_bullish_cross']:
        entry_px = price * 1.01; entry_type = "BUY STOP-LIMIT 1% above (MACD cross)"
    else:
        entry_px = price * 0.985; entry_type = "BUY LIMIT 1.5% below (pullback)"
    risk_pct = 2.0 if regime == 'TRANSITIONAL' else (2.5 if regime == 'BULL' else 1.0)
    shares = int((100000 * risk_pct / 100) / risk)
    adv = {'symbol': r['symbol'], 'score': r['score'], 'regime': regime,
           'price': price, 'entry_px': entry_px, 'entry_type': entry_type,
           'sl': sl, 't1': t1, 't2': t2, 't3': t3,
           'atr': atr, 'atr_pct': atr_pct, 'risk': risk,
           'rr_t1': 2.0, 'rr_t2': 3.0,
           'risk_pct': risk_pct, 'shares': shares,
           'bull': r['bull'], 'bear': r['bear'], 'ta': ta}
    advisories.append(adv)
    print(f"\n{r['symbol']} | Score={r['score']:+.0f} | Regime={regime}")
    print(f"  Entry: {entry_type}")
    print(f"  SL: ${sl:.2f} | T1: ${t1:.2f} | T2: ${t2:.2f} | T3: ${t3:.2f}")
    print(f"  Shares: {shares} @ ${entry_px:.2f} | Risk ${shares*risk:.0f} ({risk_pct}%)")
    print(f"  Bull: {', '.join(r['bull'][:5])}")
    print(f"  Bear: {', '.join(r['bear'][:5])}")

# Bearish
print(f"\nBEARISH SCANS:")
for r in shorts[:3]:
    ta = r['ta']
    price = ta['last']; atr = ta['atr']
    ts = price + atr * 1.5; ss = price - atr * 1.0
    print(f"  SHORT {r['symbol']} Score={r['score']:+.0f} ${price:.2f} SL=${ss:.2f} TP=${ts:.2f}")
    print(f"    Bears: {', '.join(r['bear'][:3])}")

# Summary
print(f"\n{'='*70}")
print(f"ADVISORY SUMMARY  |  {TODAY}")
print(f"{'='*70}")
print(f"{'SYM':6s} {'PRICE':>8s} {'ENTRY':>8s} {'SL':>8s} {'T1':>8s} {'T2':>8s} {'R:R1':>5s} {'R:R2':>5s} {'SHRS':>5s}")
print(f"{'-'*70}")
for adv in advisories:
    print(f"{adv['symbol']:6s} ${adv['price']:>7.2f} ${adv['entry_px']:>7.2f} ${adv['sl']:>7.2f} ${adv['t1']:>7.2f} ${adv['t2']:>7.2f} 1:{adv['rr_t1']:.0f}   1:{adv['rr_t2']:.0f}   {adv['shares']:>5d}")

print(f"\nREGIME: {regime} | Risk sizing: {advisories[0]['risk_pct'] if advisories else 'N/A'}% per trade")
print(f"Trailing: After T1, move SL to breakeven + 0.5%")
print(f"Time stop: Exit if no T1 progress in 10 trading days")

# Save
lines = [f"{'='*70}", f"  NASDAQ SWING TRADE ADVISORY  |  {TODAY}", f"{'='*70}", "",
         f"MARKET REGIME: {regime}", "",
         f"QQQ: ${q.get('last','N/A')} | RSI={q.get('rsi',0):.1f} | ATR%={q.get('atr_pct',0):.1f}% | mom20={q.get('mom20',0):+.1f}%",
         f"SPY: ${s.get('last','N/A')} | RSI={s.get('rsi',0):.1f} | ATR%={s.get('atr_pct',0):.1f}% | mom20={s.get('mom20',0):+.1f}%",
         f"IWM: ${i_d.get('last','N/A')} | RSI={i_d.get('rsi',0):.1f} | ATR%={i_d.get('atr_pct',0):.1f}% | mom20={i_d.get('mom20',0):+.1f}%",
         f"VIX: ${v.get('last','N/A')} | RSI={v.get('rsi',0):.1f} | mom20={v.get('mom20',0):+.1f}%", ""]
for adv in advisories:
    lines += [f"{'='*60}", f"  {adv['symbol']} | Score={adv['score']:+.0f} | Regime={regime}",
              f"{'='*60}",
              f"  Price: ${adv['price']:.2f} | ATR: ${adv['atr']:.2f} ({adv['atr_pct']:.1f}%)",
              f"  Entry: {adv['entry_type']}",
              f"  SL: ${adv['sl']:.2f} | T1: ${adv['t1']:.2f} | T2: ${adv['t2']:.2f}",
              f"  R:R: 1:{adv['rr_t1']:.0f} / 1:{adv['rr_t2']:.0f}",
              f"  Shares: {adv['shares']} | Risk: {adv['risk_pct']}%",
              f"  Bull: {', '.join(adv['bull'][:5])}",
              f"  Bear: {', '.join(adv['bear'][:5])}", ""]
with open('/opt/data/handbook/swing_advisory_live.txt', 'w') as f:
    f.write('\n'.join(lines))
print("\nSaved: /opt/data/handbook/swing_advisory_live.txt")
