#!/usr/bin/env python3
"""Full swing trade scan for NASDAQ QQQ + top components — August 11, 2026."""
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
import warnings
warnings.filterwarnings('ignore')

now_et = datetime.now(timezone(timedelta(hours=-5)))
print(f"=== SCAN RUN: {now_et.strftime('%Y-%m-%d %H:%M %Z')} ===\n")

# ── INDEX DATA ──────────────────────────────────────────────────────────────
indices = {
    'QQQ': {'name': 'Nasdaq 100 ETF'},
    'SPY': {'name': 'S&P 500 ETF'},
    'IWM': {'name': 'Russell 2000 ETF'},
}

# VIX is fetched separately with ^VIX
hist_d = {t: yf.Ticker(t).history(period='3mo', interval='1d') for t in indices}
hist_d['VIX'] = yf.Ticker('^VIX').history(period='3mo')
hist_h = {t: yf.Ticker(t).history(period='10d', interval='1h') for t in ['QQQ', 'SPY', 'IWM']}

# 1yr history for SMA200
hist_1yr = {t: yf.Ticker(t).history(period='1y', interval='1d') for t in ['QQQ', 'SPY', 'IWM']}

def calc_atr(hist, n=14):
    tr1 = hist['High'] - hist['Low']
    tr2 = abs(hist['High'] - hist['Close'].shift(1))
    tr3 = abs(hist['Low'] - hist['Close'].shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(n).mean().iloc[-1]

def rsi(prices, n=14):
    delta = prices.diff()
    gain = delta.clip(lower=0).rolling(n).mean()
    loss = (-delta.clip(upper=0)).rolling(n).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def macd(prices, f=12, s=26, sig=9):
    ema_f = prices.ewm(span=f).mean()
    ema_s = prices.ewm(span=s).mean()
    m = ema_f - ema_s
    sig_m = m.ewm(span=sig).mean()
    return m.iloc[-1], sig_m.iloc[-1], m.iloc[-1] - sig_m.iloc[-1]

print("=== INDEX SNAPSHOT ===")
regime = "TRANSITIONAL"
for t in ['QQQ', 'SPY', 'IWM']:
    h = hist_d[t]
    h1 = hist_1yr[t]
    c = h['Close'].iloc[-1]
    c20 = h['Close'].iloc[-20:]
    sma20 = c20.mean()
    sma50 = h['Close'].rolling(50).mean().iloc[-1]
    sma200 = h1['Close'].rolling(200).mean().iloc[-1]
    rsi14 = rsi(h['Close']).iloc[-1]
    atr = calc_atr(h)
    m, ms, mh = macd(h['Close'])
    ret5 = (c / h['Close'].iloc[-6] - 1) * 100
    ret20 = (c / h['Close'].iloc[-21] - 1) * 100
    above20 = c > sma20
    above50 = c > sma50
    above200 = c > sma200
    vol_r = h['Volume'].iloc[-5:].mean() / h['Volume'].rolling(20).mean().iloc[-1]
    print(f"\n{t}: ${c:.2f}  RSI={rsi14:.1f}  ATR={atr:.2f} ({atr/c*100:.1f}%)")
    print(f"     5d={ret5:+.1f}%  20d={ret20:+.1f}%  VolRatio={vol_r:.2f}x")
    print(f"     SMA20=${sma20:.2f} SMA50=${sma50:.2f} SMA200=${sma200:.2f}")
    print(f"     Above20={above20} Above50={above50} Above200={above200}")
    print(f"     MACD={m:.2f} Signal={ms:.2f} Hist={mh:.2f}")
    indices[t]['close'] = c
    indices[t]['sma20'] = sma20
    indices[t]['sma50'] = sma50
    indices[t]['sma200'] = sma200
    indices[t]['rsi'] = rsi14
    indices[t]['atr'] = atr
    indices[t]['atr_pct'] = atr/c*100
    indices[t]['ret5'] = ret5
    indices[t]['ret20'] = ret20
    indices[t]['macd_hist'] = mh
    indices[t]['above20'] = above20
    indices[t]['above50'] = above50
    indices[t]['above200'] = above200

# VIX
vix = hist_d['VIX']
vix_c = vix['Close'].iloc[-1]
vix_rsi = rsi(vix['Close']).iloc[-1]
vix20 = (vix['Close'].iloc[-20:].mean())
print(f"\nVIX: ${vix_c:.2f}  RSI={vix_rsi:.1f}  20d_avg={vix20:.2f}")
vix_rsi_actual = vix_rsi

# ── NASDAQ-100 COMPONENT SCAN ────────────────────────────────────────────────
# Top-tier candidates with known catalysts / strong setups
nasdaq_candidates = [
    'NVDA', 'AAPL', 'MSFT', 'META', 'AMZN', 'GOOGL', 'AVGO',
    'COST', 'AMD', 'CRM', 'NFLX', 'NOW', 'PANW', 'ORLY',
    'BKNG', 'ISRG', 'INTU', 'ADP', 'MDLZ', 'REGN', 'AMAT',
    'KLAC', 'LRCX', 'MU', 'INTC', 'QCOM', 'TXN', 'HON',
    'ADI', 'MRVL', 'SNPS', 'CDNS', 'PANW', 'FTNT', 'ZS',
    'CRWD', 'NET', 'DDOG', 'SNOW', 'TEAM', 'WDAY', 'PLTR',
    'SMCI', 'SOFI', 'RIVN', 'PLTR', 'COIN', 'MSTR'
]

results = []
for t in nasdaq_candidates:
    try:
        tk = yf.Ticker(t)
        h = tk.history(period='3mo', interval='1d')
        if len(h) < 60:
            continue
        c = h['Close'].iloc[-1]
        prev = h['Close'].iloc[-2]
        sma20 = h['Close'].rolling(20).mean().iloc[-1]
        sma50 = h['Close'].rolling(50).mean().iloc[-1]
        sma200 = np.nan
        if len(h) >= 200:
            sma200 = h['Close'].iloc[-200:].mean()
        rsi14 = rsi(h['Close']).iloc[-1]
        atr = calc_atr(h)
        m, ms, mh = macd(h['Close'])
        ret5 = (c / h['Close'].iloc[-6] - 1) * 100
        ret20 = (c / h['Close'].iloc[-21] - 1) * 100
        ret60 = (c / h['Close'].iloc[-61] - 1) * 100
        vol20 = h['Volume'].rolling(20).mean().iloc[-1]
        vol_last = h['Volume'].iloc[-5:].mean()
        vol_r = vol_last / vol20 if vol20 > 0 else 0
        hh52 = h['High'].max()
        ll52 = h['Low'].min()
        range_pos = (c - ll52) / (hh52 - ll52) if (hh52 - ll52) > 0 else 0.5
        bb_upper = sma20 + 2 * h['Close'].rolling(20).std().iloc[-1]
        bb_lower = sma20 - 2 * h['Close'].rolling(20).std().iloc[-1]
        bb_pos = (c - bb_lower) / (bb_upper - bb_lower) if (bb_upper - bb_lower) > 0 else 0.5

        # Score: higher = better long candidate
        score = 0
        if rsi14 > 40 and rsi14 < 75: score += 2
        if above20 := c > sma20: score += 2
        if c > sma50: score += 2
        if vol_r > 1.3: score += 2
        if mh > 0: score += 2  # MACD bullish
        if ret5 > 0: score += 1
        if range_pos < 0.8: score += 1
        if bb_pos < 0.90: score += 1
        if atr / c < 0.05: score += 1  # lower vol = tighter stops possible

        results.append({
            'Symbol': t, 'Price': c, 'PrevClose': prev,
            'RSI': rsi14, 'ATR14': atr, 'ATR%': atr/c*100,
            'MACD_Hist': mh, 'SMA20': sma20, 'SMA50': sma50, 'SMA200': sma200,
            'Above_SMA20': c > sma20, 'Above_SMA50': c > sma50, 'Above_SMA200': c > sma200,
            'Ret_5d': ret5, 'Ret_20d': ret20, 'Ret_60d': ret60,
            'High_52w': hh52, 'Low_52w': ll52, 'Pct_52w': range_pos,
            'BB_Pos': bb_pos, 'VolRatio': vol_r,
            'AvgVol': vol20, 'Score': score
        })
    except Exception as e:
        pass

df = pd.DataFrame(results).sort_values('Score', ascending=False)

print("\n\n=== TOP SWING CANDIDATES (Top 20 by Score) ===")
print(f"{'Sym':6} {'Price':>8} {'RSI':>5} {'ATR%':>5} {'5d%':>6} {'20d%':>7} {'Score':>5} {'Ab20':>4} {'Ab50':>4} {'VolR':>5} {'BBP':>5}")
for _, r in df.head(20).iterrows():
    print(f"{r['Symbol']:6} ${r['Price']:>7.2f} {r['RSI']:>5.1f} {r['ATR%']*100:>4.1f}% {r['Ret_5d']:>+6.1f}% {r['Ret_20d']:>+7.1f}% {r['Score']:>5.0f}  {str(r['Above_SMA20']):>4} {str(r['Above_SMA50']):>4} {r['VolRatio']:>5.2f} {r['BB_Pos']:>5.2f}")

# Save full results
df.to_csv('/opt/data/handbook/swing_live_results.csv', index=False)

# ── DEEP DIVE: TOP 3 SETUPS ──────────────────────────────────────────────────
print("\n\n" + "="*70)
print("TOP 3 SWING SETUP DEEP DIVE")
print("="*70)

top3 = df.head(3)
for _, r in top3.iterrows():
    t = r['Symbol']
    tk = yf.Ticker(t)
    info = tk.info
    h = tk.history(period='6mo', interval='1d')
    c = r['Price']
    atr = r['ATR14']

    # Stop & targets
    stop = c - atr * 1.5
    t1 = c + atr * 1.5 * 2
    t2 = c + atr * 1.5 * 3
    rr = (t1 - c) / (c - stop) if (c - stop) > 0 else 0

    print(f"\n{'─'*60}")
    print(f"SYMBOL: {t}")
    print(f"  Price:    ${c:.2f}")
    print(f"  Entry:    Buy on pullback to ${c - atr*0.3:.2f} or breakout above ${c + atr*0.2:.2f}")
    print(f"  Stop:     ${stop:.2f}  ({(1-stop/c)*100:.1f}% risk = {atr*1.5:.2f} pts)")
    print(f"  T1:       ${t1:.2f}  ({rr:.1f}:1 R:R)")
    print(f"  T2:       ${t2:.2f}  ({((t2-c)/(c-stop)):.1f}:1 R:R)")
    print(f"  ATR:      ${atr:.2f} ({r['ATR%']*100:.1f}%)")
    print(f"  RSI:      {r['RSI']:.1f}")
    print(f"  MACD:     {r['MACD_Hist']:.2f}")
    print(f"  5d Ret:   {r['Ret_5d']:+.1f}%")
    print(f"  20d Ret:  {r['Ret_20d']:+.1f}%")
    print(f"  52w Range: {r['Pct_52w']*100:.0f}% (L={r['Low_52w']:.2f} H={r['High_52w']:.2f})")
    print(f"  Volume:   {r['VolRatio']:.2f}x 20d avg")
    print(f"  Score:    {r['Score']:.0f}")

    # News / fundamental
    try:
        print(f"  Market Cap: ${info.get('marketCap', 0)/1e9:.1f}B")
        print(f"  P/E TTM:    {info.get('trailingPE', 'N/A')}")
        print(f"  Fwd P/E:    {info.get('forwardPE', 'N/A')}")
        print(f"  EPS TTM:    {info.get('trailingEps', 'N/A')}")
        print(f"  EPS Fwd:    {info.get('forwardEps', 'N/A')}")
    except:
        pass

    # Recent earnings
    try:
        cal = tk.calendar
        if cal is not None and not cal.empty:
            print(f"  Earnings Cal: {cal}")
    except:
        pass

    # Recent news
    try:
        news = tk.news(limit=3)
        if news:
            print(f"  Recent News ({len(news)} items):")
            for n in news[:3]:
                print(f"    - [{n.get('provider','')}] {n.get('title','')[:80]}")
    except:
        pass

print("\n\n=== REGIME SUMMARY ===")
bull_count = sum([
    indices['QQQ']['above20'] and indices['QQQ']['above50'],
    indices['SPY']['above20'] and indices['SPY']['above50'],
    indices['IWM']['above20'] and indices['IWM']['above50'],
])
print(f"QQQ: ${indices['QQQ']['close']:.2f} | RSI={indices['QQQ']['rsi']:.1f} | 5d={indices['QQQ']['ret5']:+.1f}% | ATR%={indices['QQQ']['atr_pct']*100:.1f}% | Above SMA20={indices['QQQ']['above20']} | Above SMA50={indices['QQQ']['above50']}")
print(f"SPY: ${indices['SPY']['close']:.2f} | RSI={indices['SPY']['rsi']:.1f} | 5d={indices['SPY']['ret5']:+.1f}% | ATR%={indices['SPY']['atr_pct']*100:.1f}% | Above SMA20={indices['SPY']['above20']} | Above SMA50={indices['SPY']['above50']}")
print(f"IWM: ${indices['IWM']['close']:.2f} | RSI={indices['IWM']['rsi']:.1f} | 5d={indices['IWM']['ret5']:+.1f}% | ATR%={indices['IWM']['atr_pct']*100:.1f}% | Above SMA20={indices['IWM']['above20']} | Above SMA50={indices['IWM']['above50']}")
print(f"VIX: ${vix_c:.2f} | RSI={vix_rsi:.1f} | {'LOW FEAR (bull supportive)' if vix_c < 18 else 'ELEVATED (caution)'}")
print(f"Bull confirm signals: {bull_count}/3 indices above 20+50 SMA")

regime_text = "BULL" if bull_count >= 2 and vix_c < 18 else ("BEAR" if bull_count <= 1 else "TRANSITIONAL")
print(f"REGIME: {regime_text}")

# Save regime
with open('/opt/data/handbook/regime_data.txt', 'w') as f:
    f.write(f"QQQ: {indices['QQQ']['close']:.2f}|{indices['QQQ']['rsi']:.1f}|{indices['QQQ']['atr_pct']*100:.1f}|{indices['QQQ']['ret5']:.1f}|{indices['QQQ']['above20']}|{indices['QQQ']['above50']}\n")
    f.write(f"SPY: {indices['SPY']['close']:.2f}|{indices['SPY']['rsi']:.1f}|{indices['SPY']['atr_pct']*100:.1f}|{indices['SPY']['ret5']:.1f}|{indices['SPY']['above20']}|{indices['SPY']['above50']}\n")
    f.write(f"IWM: {indices['IWM']['close']:.2f}|{indices['IWM']['rsi']:.1f}|{indices['IWM']['atr_pct']*100:.1f}|{indices['IWM']['ret5']:.1f}|{indices['IWM']['above20']}|{indices['IWM']['above50']}\n")
    f.write(f"VIX: {vix_c:.2f}|{vix_rsi:.1f}\n")
    f.write(f"REGIME: {regime_text}|BULL_COUNT={bull_count}\n")

print("\nDONE")
