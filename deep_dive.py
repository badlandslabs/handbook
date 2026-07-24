import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

CANDIDATES = ['AAPL', 'NVDA', 'META', 'AMD', 'AMZN', 'ORCL', 'MSFT', 'QQQ', 'SPY']

def analyze_deep(ticker):
    print("\n" + "="*70)
    print(f"  {ticker}  -- DEEP DIVE")
    print("="*70)

    df = yf.Ticker(ticker).history(period='6mo', auto_adjust=True)
    if df is None or len(df) < 60:
        print("  Insufficient data")
        return None

    price = float(df['Close'].iloc[-1])

    # SMAs
    sma20 = df['Close'].rolling(20).mean()
    sma50 = df['Close'].rolling(50).mean()
    sma200 = df['Close'].rolling(200).mean()

    # RSI
    delta = df['Close'].diff()
    gain = delta.clip(lower=0).ewm(alpha=2/14).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=2/14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    # MACD
    ema12 = df['Close'].ewm(span=12).mean()
    ema26 = df['Close'].ewm(span=26).mean()
    macd = ema12 - ema26
    macd_sig = macd.ewm(span=9).mean()
    macd_hist = macd - macd_sig

    # ATR
    atr14 = (df['High'] - df['Low']).rolling(14).mean()

    # Volume
    vol_avg = df['Volume'].rolling(20).mean()

    # Fibonacci
    lookback = min(60, len(df)-1)
    swing_high = float(df['High'].tail(lookback).max())
    swing_low = float(df['Low'].tail(lookback).min())
    diff = swing_high - swing_low

    # S/R from recent highs/lows
    highs = list(df['High'].tail(20).nlargest(3))
    lows = list(df['Low'].tail(20).nsmallest(3))
    closes = df['Close'].tail(20)

    # Bollinger Bands
    bb_mid = df['Close'].rolling(20).mean()
    bb_std = df['Close'].rolling(20).std()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std

    # Key values
    cur_rsi = float(rsi.iloc[-1])
    cur_macd = float(macd.iloc[-1])
    cur_macd_sig = float(macd_sig.iloc[-1])
    cur_macd_hist = float(macd_hist.iloc[-1])
    cur_atr = float(atr14.iloc[-1])
    cur_vol = float(df['Volume'].iloc[-1])
    vol_ratio = cur_vol / float(vol_avg.iloc[-1])
    bb_low_val = float(bb_lower.iloc[-1])
    bb_up_val = float(bb_upper.iloc[-1])

    # 5d/10d/20d returns
    ret_5d = (price / float(df['Close'].iloc[-6]) - 1) * 100 if len(df) > 5 else 0.0
    ret_10d = (price / float(df['Close'].iloc[-11]) - 1) * 100 if len(df) > 10 else 0.0
    ret_20d = (price / float(df['Close'].iloc[-21]) - 1) * 100 if len(df) > 20 else 0.0

    print(f"  PRICE: ${price:.2f}")
    print(f"  5D: {ret_5d:+.1f}%   10D: {ret_10d:+.1f}%   20D: {ret_20d:+.1f}%")
    print(f"  SMA20: ${float(sma20.iloc[-1]):.2f}  {'ABOVE' if price > float(sma20.iloc[-1]) else 'BELOW'}")
    print(f"  SMA50: ${float(sma50.iloc[-1]):.2f}  {'ABOVE' if price > float(sma50.iloc[-1]) else 'BELOW'}")
    sma200_val = float(sma200.iloc[-1]) if not pd.isna(sma200.iloc[-1]) else None
    if sma200_val:
        print(f"  SMA200: ${sma200_val:.2f}  {'ABOVE' if price > sma200_val else 'BELOW'}")
    else:
        print(f"  SMA200: N/A")
    print(f"  RSI(14): {cur_rsi:.1f}  {'OVERBOUGHT' if cur_rsi > 70 else 'OVERSOLD' if cur_rsi < 30 else 'NEUTRAL'}")
    print(f"  MACD: {cur_macd:.3f}  signal: {cur_macd_sig:.3f}  hist: {cur_macd_hist:.3f}  {'BULLISH' if cur_macd > cur_macd_sig else 'BEARISH'}")
    print(f"  ATR(14): ${cur_atr:.2f}  ({cur_atr/price*100:.1f}% of price)")
    print(f"  VOL RATIO: {vol_ratio:.2f}x avg")
    print(f"  BB Lower: ${bb_low_val:.2f}  BB Upper: ${bb_up_val:.2f}")
    bb_pct = (price - bb_low_val)/(bb_up_val - bb_low_val)*100
    print(f"  Position in BB range: {bb_pct:.0f}% {'(near lower band)' if bb_pct < 25 else '(near upper band)' if bb_pct > 75 else ''}")
    print()
    print(f"  FIBONACCI (swing: ${swing_low:.2f} -- ${swing_high:.2f}):")
    print(f"    23.6%: ${swing_low + diff*0.236:.2f}")
    print(f"    38.2%: ${swing_low + diff*0.382:.2f}")
    print(f"    50.0%: ${swing_low + diff*0.500:.2f}")
    print(f"    61.8%: ${swing_low + diff*0.618:.2f}")
    print(f"    78.6%: ${swing_low + diff*0.786:.2f}")
    print()
    print(f"  RESISTANCE levels (nearest 3): {[f'${h:.2f}' for h in sorted([x for x in highs if x > price])[:3]]}")
    print(f"  SUPPORT levels (nearest 3):    {[f'${l:.2f}' for l in sorted([x for x in lows if x < price], reverse=True)[:3]]}")

    # News
    try:
        t = yf.Ticker(ticker)
        news = t.news
        if news and len(news) > 0:
            print(f"\n  RECENT NEWS:")
            for n in news[:3]:
                title = str(n.get('title', 'N/A'))[:80]
                pub = str(n.get('pubDate', 'N/A'))[:10]
                print(f"    [{pub}] {title}")
    except:
        pass

    return {
        'ticker': ticker,
        'price': price,
        'rsi': cur_rsi,
        'macd': cur_macd,
        'macd_signal': cur_macd_sig,
        'macd_hist': cur_macd_hist,
        'atr': cur_atr,
        'atr_pct': cur_atr/price*100,
        'vol_ratio': vol_ratio,
        'bb_lower': bb_low_val,
        'bb_upper': bb_up_val,
        'bb_pct': bb_pct,
        'sma20': float(sma20.iloc[-1]),
        'sma50': float(sma50.iloc[-1]),
        'sma200': sma200_val,
        'swing_high': swing_high,
        'swing_low': swing_low,
        'resistance': sorted([x for x in highs if x > price])[:3],
        'support': sorted([x for x in lows if x < price], reverse=True)[:3],
        'ret_5d': ret_5d,
        'ret_10d': ret_10d,
        'ret_20d': ret_20d,
    }

results = {}
for t_sym in CANDIDATES:
    r = analyze_deep(t_sym)
    if r:
        results[t_sym] = r
