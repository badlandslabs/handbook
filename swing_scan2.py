import yfinance as yf
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

today = pd.Timestamp.today(tz='America/New_York')
print(f"Scan Date: {today}")
print("="*70)

# Fetch with longer period to get 200 SMA
indices = {'QQQ': None, 'SPY': None, 'IWM': None}
stocks = ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'META', 'AMZN', 'TSLA', 'AVGO',
          'AMD', 'NFLX', 'ORCL', 'CRM', 'ADBE', 'INTU', 'QCOM', 'TXN',
          'MU', 'AMAT', 'LRCX', 'KLAC', 'PANW', 'SNPS', 'CDNS', 'AMAT',
          'MRVL', 'ON', 'CSCO', 'NXPI', 'FTNT', 'MAR', 'FAST', 'PAYX']

all_tickers = list(indices.keys()) + stocks

def analyze(ticker):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period='6mo', interval='1d', timeout=15)
        if hist.empty or len(hist) < 120:
            return None
        close = hist['Close']
        high = hist['High']
        low = hist['Low']
        volume = hist['Volume']
        
        sma20 = close.rolling(20).mean()
        sma50 = close.rolling(50).mean()
        sma200 = close.rolling(200).mean()
        ema9 = close.ewm(span=9).mean()
        ema20 = close.ewm(span=20).mean()
        
        # RSI(14)
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        
        # ATR(14)
        tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(14).mean()
        
        curr = close.iloc[-1]
        
        # MACD
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        macd_hist = macd - signal
        
        # Momentum score components
        above_20sma = 1 if curr > sma20.iloc[-1] else 0
        above_50sma = 1 if curr > sma50.iloc[-1] else 0
        above_200sma = 1 if pd.notna(sma200.iloc[-1]) and curr > sma200.iloc[-1] else 0
        above_ema20 = 1 if curr > ema20.iloc[-1] else 0
        rsi_ok = 1 if 35 < rsi.iloc[-1] < 70 else 0
        rsi_oversold = 1 if rsi.iloc[-1] < 40 else 0
        rsi_overbought = 1 if rsi.iloc[-1] > 65 else 0
        macd_bullish = 1 if macd.iloc[-1] > signal.iloc[-1] else 0
        macd_cross_up = 1 if macd.iloc[-2] < signal.iloc[-2] and macd.iloc[-1] > signal.iloc[-1] else 0
        macd_cross_down = 1 if macd.iloc[-2] > signal.iloc[-2] and macd.iloc[-1] < signal.iloc[-1] else 0
        
        # Retracement from 20d high
        d20h = high.tail(20).max()
        d20l = low.tail(20).min()
        pullback_pct = ((curr - d20h) / d20h) * 100
        
        # Gap analysis
        gap_up = 1 if len(close) > 1 and close.iloc[-2] > 0 and (high.iloc[-1] > low.iloc[-2] and low.iloc[-1] > high.iloc[-2]) else 0
        
        # 5d / 20d momentum
        ret_5d = ((close.iloc[-1] / close.iloc[-6]) - 1) * 100 if len(close) > 5 else 0
        ret_10d = ((close.iloc[-1] / close.iloc[-11]) - 1) * 100 if len(close) > 10 else 0
        ret_20d = ((close.iloc[-1] / close.iloc[-21]) - 1) * 100 if len(close) > 20 else 0
        
        atr_pct = (atr.iloc[-1] / curr) * 100
        vol_ratio = volume.iloc[-1] / volume.tail(20).mean() if volume.tail(20).mean() > 0 else 0
        
        # Distance from key levels
        dist_50sma = ((curr - sma50.iloc[-1]) / sma50.iloc[-1]) * 100
        
        # Volume trend
        vol_10_avg = volume.tail(10).mean()
        vol_10_prior = volume.tail(20).head(10).mean()
        vol_trend = vol_10_avg / vol_10_prior if vol_10_prior > 0 else 1
        
        return {
            'ticker': ticker,
            'price': curr,
            'sma20': sma20.iloc[-1],
            'sma50': sma50.iloc[-1],
            'sma200': sma200.iloc[-1],
            'ema20': ema20.iloc[-1],
            'rsi14': rsi.iloc[-1],
            'atr14': atr.iloc[-1],
            'atr_pct': atr_pct,
            'dist_50sma': dist_50sma,
            'dist_200sma': ((curr - sma200.iloc[-1]) / sma200.iloc[-1]) * 100 if pd.notna(sma200.iloc[-1]) else np.nan,
            'above_20sma': above_20sma,
            'above_50sma': above_50sma,
            'above_200sma': above_200sma,
            'above_ema20': above_ema20,
            'rsi_ok': rsi_ok,
            'rsi_oversold': rsi_oversold,
            'rsi_overbought': rsi_overbought,
            'macd_bullish': macd_bullish,
            'macd_cross_up': macd_cross_up,
            'macd_cross_down': macd_cross_down,
            'pullback_pct': pullback_pct,
            'ret_5d': ret_5d,
            'ret_10d': ret_10d,
            'ret_20d': ret_20d,
            'vol_ratio': vol_ratio,
            'vol_trend': vol_trend,
            'd20h': d20h,
            'd20l': d20l,
            'swing_low': low.tail(60).min(),
            'swing_high': high.tail(60).max(),
            'macd': macd.iloc[-1],
            'macd_signal': signal.iloc[-1],
            'macd_hist': macd_hist.iloc[-1],
            'close_series': close.tail(10).values,
        }
    except Exception as e:
        return {'ticker': ticker, 'error': str(e)}

print("Fetching data for all tickers...")
data = {}
for t in all_tickers:
    res = analyze(t)
    if res:
        data[t] = res
    else:
        print(f"  SKIP {t}: insufficient data")

print(f"\nFetched: {len(data)} tickers")

# Score each ticker
print("\n" + "="*70)
print("SCAN RESULTS — SORTED BY SWING SCORE")
print("="*70)

def swing_score(d):
    if 'error' in d:
        return -999
    score = 0
    # Bullish factors
    if d['above_50sma']: score += 2
    if d['above_20sma']: score += 1
    if d['above_ema20']: score += 1
    if d['macd_bullish']: score += 2
    if d['macd_cross_up']: score += 3
    if 35 < d['rsi14'] < 60: score += 2  # Sweet spot
    if d['rsi14'] < 40: score += 3  # Oversold bounce setup
    if d['dist_50sma'] > -3: score += 1  # Near/above 50 SMA
    if d['pullback_pct'] < -5: score += 1  # Pulled back from highs
    if d['ret_5d'] > 0: score += 1
    # Bearish factors (reduce score)
    if d['macd_cross_down']: score -= 3
    if d['rsi_overbought']: score -= 2
    if d['dist_50sma'] < -10: score -= 2
    return score

ranked = []
for ticker, d in data.items():
    if 'error' not in d:
        d['score'] = swing_score(d)
        ranked.append((ticker, d))

ranked.sort(key=lambda x: x[1]['score'], reverse=True)

for ticker, d in ranked:
    print(f"\n{ticker} | Score: {d['score']} | Price: ${d['price']:.2f}")
    print(f"  RSI: {d['rsi14']:.1f} | ATR: {d['atr14']:.2f} ({d['atr_pct']:.1f}%)")
    print(f"  SMA20: ${d['sma20']:.2f} | SMA50: ${d['sma50']:.2f} | SMA200: ${d['sma200']:.2f if pd.notna(d['sma200']) else float('nan'):.2f}")
    print(f"  vs SMA50: {d['dist_50sma']:+.1f}% | vs SMA200: {d['dist_200sma']:+.1f}%")
    print(f"  5d: {d['ret_5d']:+.1f}% | 10d: {d['ret_10d']:+.1f}% | 20d: {d['ret_20d']:+.1f}%")
    print(f"  20d Range: ${d['d20l']:.2f} – ${d['d20h']:.2f} | Pullback: {d['pullback_pct']:.1f}%")
    print(f"  MACD: {d['macd']:.3f} | Signal: {d['macd_signal']:.3f} | Hist: {d['macd_hist']:.3f}")
    print(f"  Vol Ratio: {d['vol_ratio']:.1f}x | Vol Trend: {d['vol_trend']:.2f}")
    bull_flags = [k for k in ['above_50sma','above_20sma','above_ema20','macd_bullish','macd_cross_up','rsi_ok','rsi_oversold'] if d.get(k, 0) == 1]
    print(f"  Bullish flags: {bull_flags}")

# Top 3 setups for detailed analysis
print("\n" + "="*70)
print("TOP 3 SWING SETUPS — DETAILED ANALYSIS")
print("="*70)

for ticker, d in ranked[:3]:
    print(f"\n{'='*30} {ticker} @ ${d['price']:.2f} {'='*30}")
    print(f"20d High: ${d['d20h']:.2f} | 20d Low: ${d['d20l']:.2f}")
    print(f"60d Swing Low: ${d['swing_low']:.2f} | Swing High: ${d['swing_high']:.2f}")
    print(f"MACD Histogram: {d['macd_hist']:.4f} ({'BULLISH' if d['macd_hist'] > 0 else 'BEARISH'})")
    print(f"RSI zone: {'OVERSOLD' if d['rsi14'] < 40 else 'NEUTRAL' if d['rsi14'] < 60 else 'OVERBOUGHT' if d['rsi14'] < 70 else 'EXTREME'}")

