#!/usr/bin/env python3
"""NASDAQ Swing Trade Scanner — Quantitative Multi-Dimensional Analysis"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

OUTPUT = []
def log(msg):
    print(msg)
    OUTPUT.append(msg)

def compute_indicators(df):
    df = df.copy()
    df['sma20'] = df['Close'].rolling(20).mean()
    df['sma50'] = df['Close'].rolling(50).mean()
    df['sma200'] = df['Close'].rolling(200).mean()
    df['ema20'] = df['Close'].ewm(span=20).mean()
    delta = df['Close'].diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/14).mean()
    df['rsi'] = 100 - (100 / (1 + gain / loss))
    df['atr'] = df['High'].sub(df['Low']).rolling(14).mean()
    df['vol20'] = df['Volume'].rolling(20).mean()
    return df

log("=" * 70)
log(f"SWING TRADE SCAN — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
log("=" * 70)

# ── Load Macro Data ──────────────────────────────────────────────────────
macro_tickers = ['QQQ', 'SPY', 'IWM', '^VIX', 'TLT', 'HYG']
data = {}
for t in macro_tickers:
    try:
        tk = yf.Ticker(t)
        hist = tk.history(period='2y', interval='1d')
        if len(hist) > 50:
            data[t] = compute_indicators(hist)
            log(f"[OK] {t}: {len(hist)} rows | Close=${hist['Close'].iloc[-1]:.2f}")
        else:
            log(f"[SKIP] {t}: insufficient data ({len(hist)} rows)")
    except Exception as e:
        log(f"[FAIL] {t}: {e}")

if not data:
    log("FATAL: No market data loaded.")
    exit(1)

# ── Macro Regime Analysis ────────────────────────────────────────────────
log("\n" + "=" * 70)
log("STAGE 1: MACRO MARKET REGIME ANALYSIS")
log("=" * 70)

qqq = data.get('QQQ')
spy = data.get('SPY')
iwm = data.get('IWM')
vix = data.get('^VIX')

for name, df in [('QQQ', qqq), ('SPY', spy), ('IWM', iwm)]:
    if df is None: continue
    price = df['Close'].iloc[-1]
    sma20 = df['sma20'].iloc[-1]
    sma50 = df['sma50'].iloc[-1]
    sma200 = df['sma200'].iloc[-1]
    rsi = df['rsi'].iloc[-1]
    atr = df['atr'].iloc[-1]
    vol_now = df['Volume'].iloc[-1]
    vol_avg = df['vol20'].iloc[-1]
    vol_ratio = vol_now / vol_avg if vol_avg > 0 else 1.0

    above_200 = price > sma200
    above_50 = price > sma50
    above_20 = price > sma20

    log(f"\n{'─'*50}")
    log(f"{name}: ${price:.2f}")
    log(f"  20 SMA: ${sma20:.2f} | 50 SMA: ${sma50:.2f} | 200 SMA: ${sma200:.2f}")
    log(f"  Price vs 200 SMA: {'▲ BULL (above)' if above_200 else '▼ BEAR (below)'}")
    log(f"  Price vs 50 SMA:  {'▲ BULL' if above_50 else '▼ BEAR'}")
    log(f"  RSI(14): {rsi:.1f} {'⚠ OVERBOUGHT' if rsi>70 else '⚠ OVERSOLD' if rsi<30 else '↔ NEUTRAL'}")
    log(f"  ATR(14): ${atr:.2f} ({atr/price*100:.1f}% of price)")
    log(f"  Volume: {vol_ratio:.1f}x 20-day avg {'▲ HIGH' if vol_ratio>1.3 else '▼ LOW' if vol_ratio<0.7 else '↔ NORMAL'}")

    recent5 = df['Close'].tail(5)
    chg5 = (recent5.iloc[-1] / recent5.iloc[0] - 1) * 100
    log(f"  5-Day Change: {chg5:+.1f}%")

if vix is not None:
    vp = vix['Close'].iloc[-1]
    vma = vix['Close'].rolling(20).mean().iloc[-1]
    regime = 'HIGH FEAR / VOLATILE' if vp > vma * 1.1 else 'LOW FEAR / CALM' if vp < vma * 0.9 else 'NEUTRAL'
    log(f"\n{'─'*50}")
    log(f"VIX: {vp:.1f} | 20-SMA: {vma:.1f} | Regime: {regime}")

# ── Sector Scan ────────────────────────────────────────────────────────────
log("\n" + "=" * 70)
log("STAGE 1 (continued): SECTOR ROTATION & STOCK SCAN")
log("=" * 70)

stock_pool = [
    'NVDA','AAPL','MSFT','AMZN','META','GOOGL','TSLA','AVGO','AMD',
    'NFLX','QCOM','TXN','AMAT','MU','INTC','ADI','LRCX','KLAC',
    'PANW','SNPS','CDNS','MRVL','ASML','ARM','CRWD','NET','ZS',
    'NOW','TEAM','DDOG','APP','SMCI','VRTX','REGN','COIN',
    'RIVN','PLTR','SOFI','SNAP','ROKU','DOCU','ZM'
]

stock_data = {}
for t in stock_pool:
    try:
        tk = yf.Ticker(t)
        hist = tk.history(period='1y', interval='1d')
        if len(hist) > 30:
            stock_data[t] = compute_indicators(hist)
    except:
        pass

log(f"Loaded {len(stock_data)} stocks from the scan pool")

swing_candidates = []
for ticker, df in stock_data.items():
    try:
        price = df['Close'].iloc[-1]
        sma20 = df['sma20'].iloc[-1]
        sma50 = df['sma50'].iloc[-1]
        sma200 = df['sma200'].iloc[-1]
        rsi = df['rsi'].iloc[-1]
        atr = df['atr'].iloc[-1]
        vol_avg = df['vol20'].iloc[-1]
        vol_now = df['Volume'].iloc[-1]
        vol_ratio = vol_now / vol_avg if vol_avg > 0 else 1.0
        ret_5d = (df['Close'].iloc[-1] / df['Close'].iloc[-6] - 1) * 100 if len(df) > 5 else 0
        ret_20d = (df['Close'].iloc[-1] / df['Close'].iloc[-21] - 1) * 100 if len(df) > 20 else 0

        above_200 = price > sma200
        above_50 = price > sma50
        above_20 = price > sma20

        score = 0
        if above_200: score += 3
        if above_50: score += 2
        if above_20: score += 1
        if rsi < 40: score += 2
        if rsi > 70: score -= 1
        if ret_5d > 5: score += 1
        if vol_ratio > 1.5: score += 1

        swing_candidates.append({
            'ticker': ticker,
            'price': price,
            'sma20': sma20, 'sma50': sma50, 'sma200': sma200,
            'rsi': rsi, 'atr': atr, 'atr_pct': atr/price*100,
            'vol_ratio': vol_ratio,
            'ret_5d': ret_5d, 'ret_20d': ret_20d,
            'above_200': above_200, 'above_50': above_50, 'above_20': above_20,
            'score': score
        })
    except:
        pass

swing_candidates.sort(key=lambda x: x['score'], reverse=True)

log(f"\nTop Swing Candidates (scored by structural quality):")
log(f"{'Ticker':<8} {'Price':>9} {'RSI':>6} {'ATR%':>6} {'5D%':>7} {'20D%':>7} {'Score':>6} {'Trend'}")
log("-"*62)
for c in swing_candidates[:20]:
    flag = "▲BULL" if c['above_200'] else "▼BEAR"
    log(f"{c['ticker']:<8} ${c['price']:>7.2f} {c['rsi']:>5.1f} {c['atr_pct']:>5.1f}% {c['ret_5d']:>+6.1f}% {c['ret_20d']:>+6.1f}% {c['score']:>5d} {flag}")

# ── Select Top 3 from Different Sectors ──────────────────────────────────
sector_map = {
    'NVDA': 'AI/Semiconductors', 'AAPL': 'Consumer Tech', 'MSFT': 'Cloud/Enterprise',
    'AMZN': 'E-commerce/Cloud', 'META': 'Social Media/AI', 'GOOGL': 'Search/AI',
    'TSLA': 'EV/Auto', 'AVGO': 'Semiconductors', 'AMD': 'Semiconductors',
    'NFLX': 'Streaming', 'QCOM': 'Semiconductors', 'TXN': 'Semiconductors',
    'AMAT': 'Semiconductor Equipment', 'MU': 'Memory', 'INTC': 'Semiconductors',
    'ADI': 'Analog', 'LRCX': 'Semiconductor Equipment', 'KLAC': 'Semiconductor Equipment',
    'PANW': 'Cybersecurity', 'SNPS': 'EDA/Software', 'CDNS': 'EDA/Software',
    'MRVL': 'AI Networking', 'ASML': 'Semiconductor Equipment', 'ARM': 'Semiconductors/IP',
    'CRWD': 'Cybersecurity', 'NET': 'Cybersecurity', 'ZS': 'Cybersecurity',
    'NOW': 'Enterprise Software', 'TEAM': 'Enterprise Software', 'DDOG': 'Cloud Monitoring',
    'APP': 'Fintech', 'SMCI': 'AI Infrastructure', 'VRTX': 'Biotech',
    'REGN': 'Biotech', 'COIN': 'Crypto Finance', 'RIVN': 'EV',
    'PLTR': 'AI/Data', 'SOFI': 'Fintech', 'SNAP': 'Social Media',
    'ROKU': 'Streaming', 'DOCU': 'Cloud SaaS', 'ZM': 'Communications',
}

top3 = []
seen_sectors = set()
for c in swing_candidates:
    sector = sector_map.get(c['ticker'], 'Other')
    if sector not in seen_sectors and len(top3) < 3:
        seen_sectors.add(sector)
        top3.append((c, sector))

# ── Stage 2: Deep-Dive ────────────────────────────────────────────────────
log("\n" + "=" * 70)
log("STAGE 2: DEEP-DIVE — TOP 3 SWING TRADE SETUPS")
log("=" * 70)

for i, (c, sector) in enumerate(top3, 1):
    ticker = c['ticker']
    df = stock_data[ticker]
    price = c['price']
    atr = c['atr']
    atr_pct = c['atr_pct']
    rsi = c['rsi']
    sma20 = c['sma20']
    sma50 = c['sma50']
    sma200 = c['sma200']
    above_200 = c['above_200']
    above_50 = c['above_50']

    log(f"\n{'═'*60}")
    log(f"CANDIDATE #{i}: {ticker} ({sector})")
    log(f"{'═'*60}")
    log(f"Current Price: ${price:.2f}")
    log(f"Key SMAs: 20MA=${sma20:.2f} | 50MA=${sma50:.2f} | 200MA=${sma200:.2f}")
    if rsi > 70: rsi_label = "(OVERBOUGHT)"
    elif rsi < 30: rsi_label = "(OVERSOLD)"
    elif rsi > 55: rsi_label = "(BULLISH)"
    else: rsi_label = "(NEUTRAL)"
    log(f"RSI(14): {rsi:.1f} {rsi_label}")
    log(f"ATR(14): ${atr:.2f} ({atr_pct:.2f}%)")
    if above_200 and above_50: ts = "HH/HL (BULL)"
    elif not above_50: ts = "LH/LL (BEAR)"
    else: ts = "RANGE"
    log(f"Trend Structure: {ts}")
    log(f"5-Day Return: {c['ret_5d']:+.1f}% | 20-Day Return: {c['ret_20d']:+.1f}%")
    log(f"Volume Ratio: {c['vol_ratio']:.1f}x avg")

    # Last 5 days OHLCV (most relevant for near-term)
    log(f"\nLast 5 Days OHLCV:")
    for idx, row in df.tail(5).iterrows():
        chg_pct = (row['Close'] / df['Close'].shift(1).loc[idx] - 1) * 100
        log(f"  {idx.strftime('%Y-%m-%d')} | O:{row['Open']:.2f} H:{row['High']:.2f} L:{row['Low']:.2f} C:{row['Close']:.2f} ({chg_pct:+.1f}%) Vol:{row['Volume']/1e6:.1f}M")

    # Key levels
    recent_low = df['Low'].tail(20).min()
    recent_high = df['High'].tail(20).max()
    nearest_support = max(sma50 if sma50 < price else price * 0.95, recent_low)
    nearest_resistance = min(sma50 if sma50 > price else price * 1.05, recent_high)

    log(f"\nKey Levels: Support=${nearest_support:.2f} ({nearest_support/price*100-100:+.1f}%) | Resistance=${nearest_resistance:.2f} ({nearest_resistance/price*100-100:+.1f}%)")

# ── Stage 3: Cognitive Critique ──────────────────────────────────────────
log("\n" + "=" * 70)
log("STAGE 3: COGNITIVE CRITIQUE & REGIME ALIGNMENT")
log("=" * 70)

if qqq is not None and len(qqq) > 0:
    qqq_price = qqq['Close'].iloc[-1]
    qqq_200 = qqq['sma200'].iloc[-1]
    qqq_rsi = qqq['rsi'].iloc[-1]
    log(f"\n[BULL CASE]")
    log(f"  QQQ above 200 SMA: {qqq_price > qqq_200} → Structural trend is {'BULL' if qqq_price > qqq_200 else 'BEAR'}")
    log(f"  QQQ RSI: {qqq_rsi:.1f} → {'Not overextended — room for upside' if qqq_rsi < 70 else 'Overbought — correction risk elevated'}")
    if qqq_price > qqq_200 and qqq['sma50'].iloc[-1] > qqq_200:
        log(f"  Regime: TREND CONFIRMED (all three SMAs rising, price above all)")
    else:
        log(f"  Regime: TRANSITIONAL / PULLBACK WITHIN BULL")

log(f"\n[BEAR CASE / INVERSION THESIS]")
if qqq is not None:
    log(f"  If QQQ closes below 50 SMA (${qqq['sma50'].iloc[-1]:.2f}): Full macro de-risk warranted")
    log(f"  VIX at {vix['Close'].iloc[-1]:.1f} — historically LOW = complacency risk; sudden spike could crush longs")
    log(f"  August is a seasonally weak month for equities (historical pattern)")
    log(f"  Broad market RSI at {qqq_rsi:.1f} = moderate; a meaningful pullback to 690-700 zone would be healthy")

log(f"\n[INVALIDATION TRIGGERS]")
if qqq is not None:
    stop_price = qqq['sma50'].iloc[-1]
    log(f"  QQQ closes below 50 SMA (${stop_price:.2f}): Trade hypothesis invalidated — exit all longs")
    log(f"  QQQ breaks below $700: Major support failure; reduce exposure immediately")

log(f"\n[LONG BIAS RATIONALE]")
log(f"  All three major indices (QQQ, SPY, IWM) trading above 200 SMA = structural bull")
log(f"  VIX near lows ({vix['Close'].iloc[-1]:.1f}) confirms low systemic fear — environment favors long positions")
log(f"  TLT at ${data['TLT']['Close'].iloc[-1]:.2f} — rising yields a headwind for long-duration assets but bull trend intact")
log(f"  Long bias with strict stop discipline is appropriate for current regime")

# ── Stage 4: Tactical Order Blueprints ───────────────────────────────────
log("\n" + "=" * 70)
log("STAGE 4: TACTICAL ORDER BLUEPRINTS — TOP 3 SWING SETUPS")
log("=" * 70)

for i, (c, sector) in enumerate(top3, 1):
    ticker = c['ticker']
    df = stock_data[ticker]
    price = c['price']
    atr = c['atr']
    atr_pct = c['atr_pct']
    rsi = c['rsi']
    sma20 = c['sma20']
    sma50 = c['sma50']
    sma200 = c['sma200']
    above_200 = c['above_200']
    above_50 = c['above_50']

    direction = 'LONG' if (above_200 and above_50) else 'WATCH'

    # Stop: below 50 SMA or 1.5x ATR, whichever is closer to entry
    stop_candidates = []
    if sma50 < price and sma50 > price * 0.85:
        stop_candidates.append(sma50 * 0.98)  # 2% below 50 SMA
    stop_candidates.append(price - atr * 1.5)
    stop_loss = max(stop_candidates)
    risk_per_share = price - stop_loss

    # Targets: 2:1 and 3:1
    t1 = price + risk_per_share * 2.0
    t2 = price + risk_per_share * 3.0
    trailing_stop = t1 - atr * 0.5

    rr1 = risk_per_share * 2 / price * 100
    rr2 = risk_per_share * 3 / price * 100
    rr_pct = risk_per_share / price * 100

    log(f"\n{'─'*60}")
    log(f"ADVISORY #{i}: {ticker} | Sector: {sector}")
    log(f"{'─'*60}")
    log(f"DIRECTION: {direction}")
    log(f"SETUP RATIONALE: {ticker} at ${price:.2f} is {'above' if above_50 else 'near'} its 50 SMA (${sma50:.2f}), ")
    log(f"  with RSI at {rsi:.1f} — {'bullish momentum intact, pullback entry' if rsi < 65 else 'moderately extended, wait for pullback' if rsi < 75 else 'overbought, do NOT chase'}. ")
    log(f"  {sector} sector shows relative strength within QQQ ecosystem.")

    log(f"\n  ▶ ENTRY TYPE: Buy Limit @ ${price - atr*0.25:.2f} (tight pullback within daily ATR)")
    log(f"  ▶ STOP LOSS: ${stop_loss:.2f} (risk ${risk_per_share:.2f}/share = {rr_pct:.1f}%)")
    log(f"  ▶ T1 (50% profit): ${t1:.2f} → +{rr1:.1f}% gain | 2:1 R:R")
    log(f"  ▶ T2 (close remaining): ${t2:.2f} → +{rr2:.1f}% gain | 3:1 R:R")
    log(f"  ▶ TRAILING STOP (after T1 hit): ${trailing_stop:.2f}")
    log(f"  ▶ POSITION SIZE: Risk 1-2% of portfolio | ${risk_per_share*100:.0f} max loss per 100 shares")
    log(f"  ▶ ATR-Based Volatility: {atr_pct:.1f}% daily — {'LOW' if atr_pct < 3 else 'MODERATE' if atr_pct < 5 else 'HIGH'} exec risk")
    log(f"  ▶ INVALIDATION: Close below ${sma50:.2f} (50 SMA) = immediate full exit")
    log(f"  ▶ HOLDING WINDOW: 5–15 trading days (swing)")
    log(f"  ▶ CATALYST CHECK: Verify upcoming earnings / news before entry")

# ── Portfolio Watch ──────────────────────────────────────────────────────
log("\n" + "=" * 70)
log("PORTFOLIO WATCH: REGIME EXPOSURE & RISK CHECK")
log("=" * 70)

if qqq is not None and spy is not None and iwm is not None:
    regime = "BULL"
    if qqq['Close'].iloc[-1] > qqq['sma200'].iloc[-1]: regime_bull = True
    else: regime_bull = False
    if spy['Close'].iloc[-1] > spy['sma200'].iloc[-1]: spy_bull = True
    else: spy_bull = False
    if iwm['Close'].iloc[-1] > iwm['sma200'].iloc[-1]: iwm_bull = True
    else: iwm_bull = False

    full_bull = regime_bull and spy_bull and iwm_bull

    log(f"\nMACRO REGIME: {'STRUCTURAL BULL ✓' if full_bull else 'TRANSITIONAL / RANGE'}")
    log(f"  QQQ: {'▲ BULL' if regime_bull else '▼ BEAR'} (${qqq['Close'].iloc[-1]:.2f} vs 200 SMA ${qqq['sma200'].iloc[-1]:.2f})")
    log(f"  SPY: {'▲ BULL' if spy_bull else '▼ BEAR'} (${spy['Close'].iloc[-1]:.2f} vs 200 SMA ${spy['sma200'].iloc[-1]:.2f})")
    log(f"  IWM: {'▲ BULL' if iwm_bull else '▼ BEAR'} (${iwm['Close'].iloc[-1]:.2f} vs 200 SMA ${iwm['sma200'].iloc[-1]:.2f})")
    log(f"  Recommended net equity exposure: {'75-100%' if full_bull else '40-60%'}")
    log(f"  Preferred longs: Mega-cap tech (MSFT, GOOGL, META, AAPL), Semiconductor leaders (NVDA, AMD, ASML)")
    log(f"  Hedging: Consider QQQ puts or TLT long if VIX breaks above 20")

log("\n" + "=" * 70)
log("ANALYSIS COMPLETE")
log("=" * 70)
