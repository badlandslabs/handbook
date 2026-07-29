import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

print("="*70)
print(f"NASDAQ SWING TRADE SCAN — {datetime.now().strftime('%Y-%m-%d %I:%M %p ET')}")
print("="*70)

# ── Stage 1: Macro Index Data ────────────────────────────────────────────────
indices = {
    "QQQ": yf.Ticker("QQQ"),
    "SPY": yf.Ticker("SPY"),
    "IWM": yf.Ticker("IWM"),
    "^VIX": yf.Ticker("^VIX"),
}

hist_range = "3mo"
d1 = "1d"

def fetch_index(ticker, period=hist_range, interval=d1):
    try:
        df = ticker.history(period=period, interval=interval)
        return df
    except:
        return pd.DataFrame()

print("\n[1] FETCHING MACRO INDEX DATA...")
index_data = {}
for name, ticker in indices.items():
    df = fetch_index(ticker)
    if len(df) > 0:
        index_data[name] = df
        last = df['Close'].iloc[-1]
        prev = df['Close'].iloc[-2] if len(df) > 1 else last
        chg_pct = (last - prev) / prev * 100
        print(f"  {name}: ${last:.2f} ({chg_pct:+.2f}%)")
    else:
        print(f"  {name}: FAILED TO FETCH")

# ── Technical helper functions ───────────────────────────────────────────────
def sma(series, n): return series.rolling(n).mean()
def ema(series, n): return series.ewm(span=n).mean()
def calc_atr(df, n=14):
    high = df['High']
    low = df['Low']
    close = df['Close']
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def calc_rsi(series, n=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).ewm(alpha=1/n, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/n, adjust=False).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def analyze_index(name, df):
    close = df['Close']
    rsi = calc_rsi(close)
    atr14 = calc_atr(df)

    last_close = close.iloc[-1]
    last_ma20 = ema(close, 20).iloc[-1]
    last_ma50 = sma(close, 50).iloc[-1]
    try:
        last_ma200 = sma(close, 200).iloc[-1]
    except:
        last_ma200 = np.nan
    last_rsi = rsi.iloc[-1]
    last_atr = atr14.iloc[-1]

    # Regime
    if last_close > last_ma200 and not np.isnan(last_ma200):
        if len(close) > 10 and last_ma200 > sma(close, 200).shift(5).iloc[-1]:
            regime = "BULL"
        else:
            regime = "TRANSITIONAL"
    elif last_close < last_ma200 and not np.isnan(last_ma200):
        if len(close) > 10 and last_ma200 < sma(close, 200).shift(5).iloc[-1]:
            regime = "BEAR"
        else:
            regime = "TRANSITIONAL"
    else:
        regime = "TRANSITIONAL"

    high20 = close.tail(20).max()
    low20 = close.tail(20).min()
    pct_high = (last_close - high20) / high20 * 100
    pct_low = (last_close - low20) / low20 * 100

    return {
        "name": name,
        "close": last_close,
        "ma20": last_ma20,
        "ma50": last_ma50,
        "ma200": last_ma200,
        "rsi": last_rsi,
        "atr": last_atr,
        "regime": regime,
        "high20": high20,
        "low20": low20,
        "pct_to_high20": pct_high,
        "pct_to_low20": pct_low,
    }

results = {}
for name, df in index_data.items():
    if len(df) > 30:
        results[name] = analyze_index(name, df)

print("\n[2] INDEX ANALYSIS:")
for name, r in results.items():
    regime_mark = "🔴" if r['regime'] == "BEAR" else ("🟢" if r['regime'] == "BULL" else "🟡")
    print(f"\n  {regime_mark} {name}  |  Close: ${r['close']:.2f}  |  Regime: {r['regime']}")
    print(f"  MA20: ${r['ma20']:.2f}  |  MA50: ${r['ma50']:.2f}  |  MA200: ${r['ma200']:.2f}" if not np.isnan(r['ma200']) else f"  MA20: ${r['ma20']:.2f}  |  MA50: ${r['ma50']:.2f}  |  MA200: N/A")
    print(f"  RSI(14): {r['rsi']:.1f}  |  ATR(14): ${r['atr']:.2f}")
    print(f"  20d High: ${r['high20']:.2f} ({r['pct_to_high20']:+.1f}%)  |  20d Low: ${r['low20']:.2f} ({r['pct_to_low20']:+.1f}%)")

# ── Stage 2: NASDAQ 100 Component Scan ─────────────────────────────────────
print("\n\n[3] SCANNING NASDAQ 100 COMPONENTS...")

tickers_to_scan = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AMD",
    "AVGO", "ORCL", "CRM", "NFLX", "ADBE", "QCOM", "TXN", "INTU",
    "AMAT", "MU", "LRCX", "KLAC", "PANW", "SNPS", "CDNS", "ADI",
    "NXPI", "ON", "MRVL", "INTC", "CSCO", "PEP", "COST", "APP",
    "DDOG", "CRWD", "NET", "TEAM", "WDAY", "NOW", "ZS", "PLTR",
]

scanned = {}
for sym in tickers_to_scan:
    try:
        t = yf.Ticker(sym)
        df = t.history(period=hist_range, interval=d1)
        if len(df) < 60:
            print(f"  {sym}: INSUFFICIENT DATA ({len(df)} rows)")
            continue

        close = df['Close']
        high20 = close.tail(20).max()
        low20 = close.tail(20).min()
        last_close = close.iloc[-1]

        rsi_vals = calc_rsi(close)
        rsi = rsi_vals.iloc[-1]

        ma20 = ema(close, 20).iloc[-1]
        ma50 = sma(close, 50).iloc[-1]
        try:
            ma200 = sma(close, 200).iloc[-1]
        except:
            ma200 = np.nan

        atr14 = calc_atr(df).iloc[-1]

        vol20 = df['Volume'].tail(20).mean()
        vol_today = df['Volume'].iloc[-1]

        pct_to_high = (last_close - high20) / high20 * 100
        pct_to_low = (last_close - low20) / low20 * 100
        mom5 = (close.iloc[-1] - close.iloc[-6]) / close.iloc[-6] * 100 if len(close) >= 6 else 0
        mom20 = (close.iloc[-1] - close.iloc[-21]) / close.iloc[-21] * 100 if len(close) >= 21 else 0

        score = 0
        if last_close > ma20: score += 1
        if last_close > ma50: score += 1
        if not np.isnan(ma200) and last_close > ma200: score += 1
        if pct_to_high > -5: score += 1
        if pct_to_high > -2: score += 1
        if 35 < rsi < 68: score += 1
        if mom5 > 0: score += 1
        if mom20 > 0: score += 1
        if mom20 > 5: score += 1

        bear_score = 0
        if last_close < ma20: bear_score += 1
        if last_close < ma50: bear_score += 1
        if not np.isnan(ma200) and last_close < ma200: bear_score += 1
        if pct_to_low < 5: bear_score += 1
        if rsi < 42: bear_score += 1
        if mom5 < -2: bear_score += 1
        if mom20 < -8: bear_score += 1

        vol_ratio = vol_today / vol20 if vol20 > 0 else 0

        scanned[sym] = {
            "close": last_close,
            "rsi": rsi,
            "ma20": ma20,
            "ma50": ma50,
            "ma200": ma200,
            "atr14": atr14,
            "pct_to_high20": pct_to_high,
            "pct_to_low20": pct_to_low,
            "mom5": mom5,
            "mom20": mom20,
            "vol_ratio": vol_ratio,
            "score": score,
            "bear_score": bear_score,
            "above_ma20": last_close > ma20,
            "above_ma50": last_close > ma50,
            "above_ma200": not np.isnan(ma200) and last_close > ma200,
        }
        print(f"  {sym}: ${last_close:.2f} | RSI:{rsi:.0f} | 20dHi:{pct_to_high:+.1f}% | 5d:{mom5:+.1f}% | 20d:{mom20:+.1f}% | LongScore:{score} | ShortScore:{bear_score}")
    except Exception as e:
        print(f"  {sym}: ERROR — {e}")

# ── Stage 3: Identify top setups ─────────────────────────────────────────────
print("\n\n[4] TOP SWING TRADE SETUPS (LONG):")
longs = sorted([(k,v) for k,v in scanned.items() if v['score'] >= 6 and v['above_ma20'] and v['above_ma50']], key=lambda x: x[1]['score'], reverse=True)
for sym, d in longs[:5]:
    print(f"  {sym}: Score={d['score']} | Close=${d['close']:.2f} | RSI={d['rsi']:.0f} | ATR=${d['atr14']:.2f} | 20dHi={d['pct_to_high20']:+.1f}% | Mom5={d['mom5']:+.1f}%")

print("\n[5] TOP SWING TRADE SETUPS (SHORT):")
shorts = sorted([(k,v) for k,v in scanned.items() if v['bear_score'] >= 5 and not v['above_ma20'] and not v['above_ma50']], key=lambda x: x[1]['bear_score'], reverse=True)
for sym, d in shorts[:5]:
    print(f"  {sym}: BearScore={d['bear_score']} | Close=${d['close']:.2f} | RSI={d['rsi']:.0f} | ATR=${d['atr14']:.2f} | 20dLow={d['pct_to_low20']:+.1f}% | Mom5={d['mom5']:+.1f}%")

# ── Stage 4: Deep dive on top 3 candidates ───────────────────────────────────
print("\n\n[6] DEEP DIVE — TOP 3 LONG CANDIDATES:")
top_long = longs[:3] if longs else []

for sym, base in top_long:
    print(f"\n  {'='*55}")
    print(f"  {sym} — DETAILED ANALYSIS")
    print(f"  {'='*55}")
    try:
        t = yf.Ticker(sym)
        df = t.history(period=hist_range, interval=d1)
        df_4h = t.history(period="1mo", interval="1h") if False else None  # skip 4h for speed

        close = df['Close']
        high20 = close.tail(20).max()
        low20 = close.tail(20).min()
        low50 = close.tail(50).min()

        rsi_vals = calc_rsi(close)
        rsi = rsi_vals.iloc[-1]
        rsi_5ago = rsi_vals.iloc[-6] if len(rsi_vals) >= 6 else rsi_vals.iloc[0]

        ma20 = ema(close, 20).iloc[-1]
        ma50 = sma(close, 50).iloc[-1]
        try:
            ma200 = sma(close, 200).iloc[-1]
        except:
            ma200 = np.nan

        atr14 = calc_atr(df).iloc[-1]

        # Recent 5-day structure
        last5 = close.tail(5)
        last10 = close.tail(10)

        pct_to_high = (base['close'] - high20) / high20 * 100
        pct_to_low = (base['close'] - low20) / low20 * 100

        # Volume analysis
        vol_avg = df['Volume'].tail(20).mean()
        vol_today = df['Volume'].iloc[-1]
        vol_surge = vol_today / vol_avg if vol_avg > 0 else 1

        # Position sizing基准
        risk_dollar = atr14 * 2.5  # 2.5 ATR risk
        # assume $50K portfolio, 2% risk
        portfolio_risk = 1000
        shares = int(portfolio_risk / risk_dollar)
        dollar_exp = shares * base['close']

        # Support/resistance
        print(f"  Close: ${base['close']:.2f} | ATR(14): ${atr14:.2f}")
        print(f"  MA20: ${ma20:.2f} | MA50: ${ma50:.2f} | MA200: ${ma200:.2f}" if not np.isnan(ma200) else f"  MA20: ${ma20:.2f} | MA50: ${ma50:.2f} | MA200: N/A")
        print(f"  RSI: {rsi:.1f} (5d ago: {rsi_5ago:.1f})")
        print(f"  20d High: ${high20:.2f} ({pct_to_high:+.1f}% away)")
        print(f"  20d Low: ${low20:.2f} ({pct_to_low:+.1f}% away)")
        print(f"  50d Low: ${low50:.2f}")
        print(f"  5d Momentum: {base['mom5']:+.1f}% | 20d Momentum: {base['mom20']:+.1f}%")
        print(f"  Volume (today vs 20d avg): {vol_surge:.2f}x")
        print(f"  --- RISK PARAMETERS ---")
        print(f"  Stop Loss: ${base['close'] - atr14*2:.2f} (2 ATR, ${atr14*2:.2f} risk)")
        print(f"  T1 (1.5R): ${base['close'] + atr14*3:.2f}")
        print(f"  T2 (2.5R): ${base['close'] + atr14*6.25:.2f}")
        print(f"  Risk/Reward: 1:2.5 minimum")
        print(f"  Approx shares (2% risk on $50K): {shares} (~${dollar_exp:.0f} exposure)")

    except Exception as e:
        print(f"  Error: {e}")

print("\n\n[7] DEEP DIVE — TOP 3 SHORT CANDIDATES:")
top_short = shorts[:3] if shorts else []

for sym, base in top_short:
    print(f"\n  {'='*55}")
    print(f"  {sym} — DETAILED ANALYSIS")
    print(f"  {'='*55}")
    try:
        t = yf.Ticker(sym)
        df = t.history(period=hist_range, interval=d1)

        close = df['Close']
        high20 = close.tail(20).max()
        low20 = close.tail(20).min()
        high50 = close.tail(50).max()

        rsi_vals = calc_rsi(close)
        rsi = rsi_vals.iloc[-1]

        ma20 = ema(close, 20).iloc[-1]
        ma50 = sma(close, 50).iloc[-1]
        try:
            ma200 = sma(close, 200).iloc[-1]
        except:
            ma200 = np.nan

        atr14 = calc_atr(df).iloc[-1]

        pct_to_high = (base['close'] - high20) / high20 * 100
        pct_to_low = (base['close'] - low20) / low20 * 100

        vol_avg = df['Volume'].tail(20).mean()
        vol_today = df['Volume'].iloc[-1]
        vol_surge = vol_today / vol_avg if vol_avg > 0 else 1

        print(f"  Close: ${base['close']:.2f} | ATR(14): ${atr14:.2f}")
        print(f"  MA20: ${ma20:.2f} | MA50: ${ma50:.2f} | MA200: ${ma200:.2f}" if not np.isnan(ma200) else f"  MA20: ${ma20:.2f} | MA50: ${ma50:.2f}")
        print(f"  RSI: {rsi:.1f}")
        print(f"  20d High: ${high20:.2f} ({pct_to_high:+.1f}% away)")
        print(f"  20d Low: ${low20:.2f} ({pct_to_low:+.1f}% away)")
        print(f"  5d Momentum: {base['mom5']:+.1f}% | 20d Momentum: {base['mom20']:+.1f}%")
        print(f"  Volume (today vs 20d avg): {vol_surge:.2f}x")
        print(f"  --- SHORT RISK PARAMETERS ---")
        print(f"  Stop Loss (above {atr14*2:.2f} ATR): ${base['close'] + atr14*2:.2f}")
        print(f"  T1 (1.5R): ${base['close'] - atr14*3:.2f}")
        print(f"  T2 (2.5R): ${base['close'] - atr14*6.25:.2f}")
        print(f"  Risk/Reward: 1:2.5 minimum")

    except Exception as e:
        print(f"  Error: {e}")

# ── Macro regime summary ─────────────────────────────────────────────────────
macro_regime = "TRANSITIONAL"
if "QQQ" in results:
    qqq_r = results["QQQ"]
    if qqq_r['close'] > qqq_r['ma200']:
        macro_regime = "BULL"
    elif qqq_r['close'] < qqq_r['ma200']:
        macro_regime = "BEAR"
    else:
        macro_regime = "TRANSITIONAL"

print("\n\n" + "="*70)
print(f"MACRO REGIME DETERMINATION: {macro_regime}")
print("="*70)
print(f"  QQQ Close: ${results.get('QQQ',{}).get('close','N/A')} | Regime: {results.get('QQQ',{}).get('regime','N/A')}")
print(f"  SPY Close: ${results.get('SPY',{}).get('close','N/A')} | Regime: {results.get('SPY',{}).get('regime','N/A')}")
print(f"  IWM Close: ${results.get('IWM',{}).get('close','N/A')} | Regime: {results.get('IWM',{}).get('regime','N/A')}")
print(f"  VIX: ${results.get('^VIX',{}).get('close','N/A')}")

# ── Final recommendations summary ────────────────────────────────────────────
print("\n\n" + "="*70)
print("FINAL RECOMMENDATIONS SUMMARY")
print("="*70)
print(f"\n  Macro Regime: {macro_regime}")
print(f"  Long Candidates Found: {len(longs)}")
print(f"  Short Candidates Found: {len(shorts)}")

if longs:
    print(f"\n  TOP LONG SETUP: {longs[0][0]}")
    d = longs[0][1]
    print(f"    Score: {d['score']} | Close: ${d['close']:.2f} | RSI: {d['rsi']:.0f}")
    print(f"    Entry: ${d['close']:.2f} | Stop: ${d['close'] - d['atr14']*2:.2f} | T1: ${d['close'] + d['atr14']*3:.2f} | T2: ${d['close'] + d['atr14']*6.25:.2f}")
if len(longs) > 1:
    print(f"\n  RUNNER-UP LONG: {longs[1][0]}")
    d = longs[1][1]
    print(f"    Score: {d['score']} | Close: ${d['close']:.2f} | RSI: {d['rsi']:.0f}")
    print(f"    Entry: ${d['close']:.2f} | Stop: ${d['close'] - d['atr14']*2:.2f} | T1: ${d['close'] + d['atr14']*3:.2f} | T2: ${d['close'] + d['atr14']*6.25:.2f}")
if shorts:
    print(f"\n  TOP SHORT SETUP: {shorts[0][0]}")
    d = shorts[0][1]
    print(f"    BearScore: {d['bear_score']} | Close: ${d['close']:.2f} | RSI: {d['rsi']:.0f}")
    print(f"    Entry: ${d['close']:.2f} | Stop: ${d['close'] + d['atr14']*2:.2f} | T1: ${d['close'] - d['atr14']*3:.2f} | T2: ${d['close'] - d['atr14']*6.25:.2f}")

print("\n" + "="*70)
print("SCAN COMPLETE")
print("="*70)
