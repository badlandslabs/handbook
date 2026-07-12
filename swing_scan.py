#!/usr/bin/env python3
"""NASDAQ Swing Trade Scanner — Quantitative Multi-Dimensional Analysis"""
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

OUT = []

def log(msg):
    print(msg)
    OUT.append(msg)

def calc_rsi(series, period=14):
    """Standard RSI using exponential moving average."""
    delta = series.diff()
    gain  = delta.where(delta > 0, 0.0)
    loss  = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs  = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1])

def calc_atr(high, low, close, period=14):
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs()
    ], axis=1).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])

log("=" * 80)
log(f"NASDAQ SWING TRADE SCAN — {datetime.now().strftime('%Y-%m-%d %H:%M ET')}")
log("=" * 80)

# ─── STAGE 1: MACRO REGIME ───────────────────────────────────────────────────
log("\n[STAGE 1] MACRO REGIME ANALYSIS")
log("-" * 60)

tickers_macro = {
    'SPY':  'S&P 500 ETF',
    'QQQ':  'Nasdaq 100 ETF',
    'IWM':  'Russell 2000 ETF',
    '^VIX': 'Volatility Index',
    '^TNX': '10Y Treasury Yield',
}

macro_data = {}
for ticker, name in tickers_macro.items():
    try:
        t_obj  = yf.Ticker(ticker)
        hist   = t_obj.history(period='6mo', interval='1d', auto_adjust=True)
        if hist.empty:
            log(f"  [WARN] No data for {ticker}")
            continue
        macro_data[ticker] = hist
        closes = hist['Close']
        last   = float(closes.iloc[-1])
        sma20  = float(closes.rolling(20).mean().iloc[-1])
        sma50  = float(closes.rolling(50).mean().iloc[-1])
        sma200 = float(closes.rolling(200).mean().iloc[-1]) if len(closes) >= 200 else None
        rsi14  = calc_rsi(closes, 14)
        atr14  = calc_atr(hist['High'], hist['Low'], closes)

        pct_above_200sma = float((closes.iloc[-20:] > sma200).mean() * 100) if sma200 else 0

        if sma200:
            if last > sma50 and sma50 > sma200:
                regime = "BULL"
            elif last < sma50 and sma50 < sma200:
                regime = "BEAR"
            else:
                regime = "TRANSITIONAL"
        else:
            regime = "UNKNOWN"

        log(f"  {ticker} ({name})")
        log(f"    Price: ${last:.2f}  SMA20: ${sma20:.2f}  SMA50: ${sma50:.2f}  SMA200: ${sma200:.2f}")
        log(f"    Above 200SMA (last 20d): {pct_above_200sma:.0f}%  |  RSI(14): {rsi14:.1f}  |  ATR(14): ${atr14:.2f}")
        log(f"    Regime: {regime}")
        log("")
    except Exception as e:
        log(f"  [ERR] {ticker}: {e}")

# ─── DETERMINE MARKET REGIME ─────────────────────────────────────────────────
qqq = macro_data.get('QQQ')
spy = macro_data.get('SPY')
vix = macro_data.get('^VIX')
tnx = macro_data.get('^TNX')

regime_override = "TRANSITIONAL"
if qqq is not None and spy is not None:
    qqq_last  = float(qqq['Close'].iloc[-1])
    spy_last  = float(spy['Close'].iloc[-1])
    qqq_sma50 = float(qqq['Close'].rolling(50).mean().iloc[-1])
    spy_sma50 = float(spy['Close'].rolling(50).mean().iloc[-1])
    vix_val   = float(vix['Close'].iloc[-1]) if vix is not None else None
    tnx_val   = float(tnx['Close'].iloc[-1]) if tnx is not None else None

    qqq_bull = qqq_last > qqq_sma50
    spy_bull = spy_last > spy_sma50

    if qqq_bull and spy_bull:
        regime_override = "BULL"
    elif not qqq_bull and not spy_bull:
        regime_override = "BEAR"
    else:
        regime_override = "TRANSITIONAL"

    log(f">>> MARKET REGIME CLASSIFICATION: {regime_override}")
    log(f"    QQQ: ${qqq_last:.2f} vs SMA50 ${qqq_sma50:.2f} → {'ABOVE' if qqq_bull else 'BELOW'}")
    log(f"    SPY: ${spy_last:.2f} vs SMA50 ${spy_sma50:.2f} → {'ABOVE' if spy_bull else 'BELOW'}")
    if vix_val:
        vix_label = 'LOW FEAR' if vix_val < 20 else 'HIGH FEAR' if vix_val > 30 else 'MODERATE'
        log(f"    VIX: {vix_val:.2f} ({vix_label})")
    if tnx_val:
        log(f"    10Y Yield: {tnx_val:.2f}%")
    log("")

# ─── STAGE 2: COMPONENT SCAN ─────────────────────────────────────────────────
log("\n[STAGE 2] NASDAQ 100 COMPONENT SCAN")
log("-" * 60)

scan_tickers = [
    'NVDA','AMD','MSFT','GOOGL','META','AMZN','AAPL','TSLA','AVGO',
    'NFLX','CRM','ADBE','ORCL','INTC','QCOM','TXN','AMAT','LRCX',
    'MU','PYPL','SNPS','CDNS','KLAC','MCHP','ADI','PANW','CRWD',
    'NET','ZS','DDOG','SNOW','APP','TEAM','NOW','WDAY',
]
scan_tickers = list(dict.fromkeys(scan_tickers))

results = []
for ticker in scan_tickers:
    try:
        t_obj = yf.Ticker(ticker)
        d = t_obj.history(period='6mo',  interval='1d',  auto_adjust=True)
        w = t_obj.history(period='2y',   interval='1wk', auto_adjust=True)
        if d.empty or len(d) < 60:
            continue

        c  = d['Close']
        h  = d['High']
        l  = d['Low']
        v  = d['Volume']

        last     = float(c.iloc[-1])
        prev     = float(c.iloc[-2]) if len(c) > 1 else last
        chg_pct  = (last - prev) / prev * 100

        sma20    = float(c.rolling(20).mean().iloc[-1])
        sma50    = float(c.rolling(50).mean().iloc[-1])
        sma200   = float(c.rolling(200).mean().iloc[-1]) if len(c) >= 200 else None
        ema9     = float(c.ewm(span=9).mean().iloc[-1])

        rsi14    = calc_rsi(c, 14)
        rsi7     = calc_rsi(c, 7)

        ema12    = float(c.ewm(span=12).mean().iloc[-1])
        ema26    = float(c.ewm(span=26).mean().iloc[-1])
        macd     = ema12 - ema26
        macd_sig = float(pd.Series(macd).ewm(span=9).mean().iloc[-1])
        macd_hist= macd - macd_sig

        atr14    = calc_atr(h, l, c)

        avg_vol  = float(v.rolling(20).mean().iloc[-1])
        vol_ratio= float(v.iloc[-1]) / avg_vol if avg_vol > 0 else 1.0

        high52   = float(h.iloc[-252:].max()) if len(h) >= 252 else float(h.max())
        low52    = float(l.iloc[-252:].min()) if len(l) >= 252 else float(l.min())
        pct_52wk = (last - low52) / (high52 - low52) * 100 if (high52 - low52) > 0 else 50

        dist_50sma = (last - sma50) / sma50 * 100
        dist_20sma = (last - sma20) / sma20 * 100

        highs_20 = h.iloc[-20:]
        lows_20  = l.iloc[-20:]
        hh_count = sum(1 for i in range(1, len(highs_20)) if highs_20.iloc[i] > highs_20.iloc[i-1])
        hl_count = sum(1 for i in range(1, len(lows_20))  if lows_20.iloc[i]  > lows_20.iloc[i-1])

        wc     = w['Close']
        wsma50 = float(wc.rolling(50).mean().iloc[-1]) if len(wc) >= 50 else None
        w_rsi14 = calc_rsi(wc, 14)

        results.append({
            'ticker': ticker, 'price': last, 'chg_pct': chg_pct,
            'sma20': sma20, 'sma50': sma50, 'sma200': sma200, 'ema9': ema9,
            'rsi14': rsi14, 'rsi7': rsi7,
            'macd': macd, 'macd_sig': macd_sig, 'macd_hist': macd_hist,
            'atr14': atr14, 'avg_vol': avg_vol, 'vol_ratio': vol_ratio,
            'high52': high52, 'low52': low52, 'pct_52wk': pct_52wk,
            'dist_50sma': dist_50sma, 'dist_20sma': dist_20sma,
            'hh_count': hh_count, 'hl_count': hl_count,
            'wsma50': wsma50, 'w_rsi14': w_rsi14,
        })
    except Exception as e:
        pass

log(f"  Scanned {len(results)} tickers successfully.\n")

# ─── SCORING ──────────────────────────────────────────────────────────────────
scores = []
for r in results:
    s = 0

    if r['price'] > r['sma50']:  s += 2
    if r['price'] > r['sma20']:  s += 1
    if r['sma20'] > r['sma50']:  s += 2

    if 40 <= r['rsi14'] <= 65:   s += 3
    elif r['rsi14'] < 40:        s += 1
    elif r['rsi14'] > 80:        s -= 2

    if r['macd_hist'] > 0:       s += 2
    if r['macd'] > r['macd_sig']: s += 1

    if r['vol_ratio'] > 1.5:     s += 2
    elif r['vol_ratio'] > 1.2:  s += 1

    if 30 <= r['pct_52wk'] <= 80: s += 2
    elif r['pct_52wk'] < 20:     s += 1

    atr_pct = r['atr14'] / r['price'] * 100
    if 1.5 <= atr_pct <= 6:      s += 2
    elif atr_pct > 6:            s += 1

    if r['chg_pct'] > 2:         s += 2
    elif r['chg_pct'] > 0:       s += 1

    r['score'] = s
    scores.append(r)

scores.sort(key=lambda x: x['score'], reverse=True)

log("TOP 10 SCORED SWING CANDIDATES (LONG bias in current regime):")
log("-" * 80)
log(f"{'Ticker':<8} {'Price':>8} {'%Chg':>6} {'RSI14':>6} {'RSI7':>5} {'MACD_H':>7} {'VolR':>5} "
    f"{'52wk%':>5} {'ATR%':>5} {'Score':>6}")
log("-" * 80)

for r in scores[:10]:
    atr_pct = r['atr14'] / r['price'] * 100
    log(f"{r['ticker']:<8} ${r['price']:>7.2f} {r['chg_pct']:>+5.1f}% {r['rsi14']:>6.1f} "
        f"{r['rsi7']:>5.1f} {r['macd_hist']:>+7.3f} {r['vol_ratio']:>5.2f} "
        f"{r['pct_52wk']:>5.0f}% {atr_pct:>5.1f}% {r['score']:>6}")

# ─── TOP 3 DEEP DIVE ──────────────────────────────────────────────────────────
log("\n[STAGE 3] TOP 3 SWING SETUPS — DEEP DIVE")
log("=" * 80)

top3 = scores[:3]
advisories = []

for i, r in enumerate(top3, 1):
    ticker = r['ticker']
    log(f"\n{'─'*60}")
    log(f"SETUP #{i}: {ticker}")
    log(f"{'─'*60}")

    try:
        t_obj = yf.Ticker(ticker)
        info  = t_obj.info
        recs  = info.get('recommendationKey', 'N/A')
        tgt   = info.get('targetMeanPrice', None)
        pe    = info.get('trailingPE', None)
        fwd_pe= info.get('forwardPE', None)
        eps_next = info.get('forwardEps', None)
        eps_ttm  = info.get('trailingEps', None)
        mkt_cap  = info.get('marketCap', None)
        beta     = info.get('beta', None)
        short_pct= info.get('shortPercentOfFloat', None)
        div_yld  = info.get('dividendYield', 0) or 0

        if mkt_cap:
            log(f"  Market Cap: ${mkt_cap/1e9:.1f}B")
        if pe and fwd_pe:
            log(f"  P/E (TTM/Fwd): {pe:.1f} / {fwd_pe:.1f}")
        if eps_ttm and eps_next:
            log(f"  EPS (TTM/Fwd): ${eps_ttm:.2f} / ${eps_next:.2f}")
        if tgt:
            log(f"  Analyst Rec: {recs} | Target: ${tgt:.2f} | Upside: {((tgt-r['price'])/r['price'])*100:+.1f}%")
        if beta:
            log(f"  Beta: {beta:.2f}")
        if short_pct:
            log(f"  Short %: {short_pct*100:.1f}%")
        if div_yld:
            log(f"  Div Yield: {div_yld*100:.2f}%")
    except Exception as e:
        log(f"  [INFO pull error: {e}]")

    log(f"\n  TECHNICAL PROFILE:")
    log(f"    Price:         ${r['price']:.2f}")
    log(f"    SMA20:         ${r['sma20']:.2f}  |  Distance: {r['dist_20sma']:+.1f}%")
    log(f"    SMA50:         ${r['sma50']:.2f}  |  Distance: {r['dist_50sma']:+.1f}%")
    if r['sma200']:
        log(f"    SMA200:        ${r['sma200']:.2f}")
    log(f"    EMA9:          ${r['ema9']:.2f}")
    rsi_label = 'OVERBOUGHT' if r['rsi14']>70 else 'OVERSOLD' if r['rsi14']<40 else 'NEUTRAL'
    log(f"    RSI(14):       {r['rsi14']:.1f}  ({rsi_label})")
    log(f"    RSI(7):        {r['rsi7']:.1f}")
    log(f"    MACD:          {r['macd']:.4f}  |  Signal: {r['macd_sig']:.4f}  |  Hist: {r['macd_hist']:+.4f}")
    log(f"    ATR(14):       ${r['atr14']:.2f}  ({r['atr14']/r['price']*100:.1f}% of price)")
    log(f"    Vol Ratio:     {r['vol_ratio']:.2f}x 20-day avg")
    log(f"    52wk High/Low: ${r['high52']:.2f} / ${r['low52']:.2f}  ({r['pct_52wk']:.0f}% of range)")
    log(f"    HH/HL (20d):   {r['hh_count']} Higher Highs / {r['hl_count']} Higher Lows")
    if r['wsma50']:
        log(f"    Weekly SMA50: ${r['wsma50']:.2f}  |  Weekly RSI(14): {r['w_rsi14']:.1f}")

    price     = r['price']
    atr       = r['atr14']
    stop_loss = price - 2.0 * atr
    t1        = price + 1.5 * atr
    t2        = price + 3.0 * atr
    rr        = (t2 - price) / (price - stop_loss) if price > stop_loss else 0

    log(f"\n  SWING TRADE PARAMETERS:")
    log(f"    Long Entry:    ${price:.2f} (current)")
    log(f"    Stop Loss:     ${stop_loss:.2f}  ({2.0}ATR / ${2*atr:.2f} risk)")
    log(f"    T1 (Partial):  ${t1:.2f}  (+{(t1-price)/price*100:.1f}% / {(t1-price)/atr:.1f}ATR)")
    log(f"    T2 (Full):     ${t2:.2f}  (+{(t2-price)/price*100:.1f}% / {(t2-price)/atr:.1f}ATR)")
    log(f"    Reward/Risk:   {rr:.1f}:1")
    log(f"    Hold Window:   2–15 days (ATR-based)")

    advisories.append({
        'rank': i, 'ticker': ticker, 'price': price, 'atr': atr,
        'stop': stop_loss, 't1': t1, 't2': t2, 'rr': rr,
        'rsi14': r['rsi14'], 'macd_hist': r['macd_hist'],
        'vol_ratio': r['vol_ratio'], 'score': r['score'],
    })

# ─── FINAL ADVISORY ───────────────────────────────────────────────────────────
log("\n" + "=" * 80)
log("FINAL ACTIONABLE SWING TRADE ADVISORIES")
log("=" * 80)

for adv in advisories:
    log(f"""
┌─ SETUP #{adv['rank']}: {adv['ticker']} ─────────────────────────────────
│  Entry:         ${adv['price']:.2f}  (buy on pullback to ${adv['price']-adv['atr']*0.5:.2f}–${adv['price']:.2f})
│  Stop Loss:     ${adv['stop']:.2f}  (risk ${adv['price']-adv['stop']:.2f} / {((adv['price']-adv['stop'])/adv['price'])*100:.1f}%)
│  T1 (Partial):  ${adv['t1']:.2f}  → sell 50% of position at open
│  T2 (Full):     ${adv['t2']:.2f}  → exit remaining
│  R:R Ratio:     {adv['rr']:.1f}:1  |  ATR risk: ${adv['atr']*2:.2f}
│  Key Flags:     RSI={adv['rsi14']:.0f} | MACD_H={adv['macd_hist']:+.3f} | Vol={adv['vol_ratio']:.1f}x | Score={adv['score']}
│  Hold:          2–15 trading days
│  Position Size: Risk 1–2% of portfolio capital per setup
└──────────────────────────────────────────────────────────────────
""")

log("\n[DISCIPLINE] RISK MANAGEMENT RULES:")
log("  1. Never risk more than 2% of total capital on a single setup")
log("  2. Maximum 3 concurrent swing positions (6% gross exposure)")
log("  3. Move stop to breakeven after T1 is hit")
log("  4. Exit immediately on weekly close below SMA50")
log("  5. Skip if macro regime shifts to BEAR on SPY/QQQ")

print("\n[DONE]")
