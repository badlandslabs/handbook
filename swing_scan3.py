import yfinance as yf
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

today = pd.Timestamp.today(tz='America/New_York')
print(f"Scan Date: {today}")
print("="*70)

stocks = ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'META', 'AMZN', 'TSLA', 'AVGO',
          'AMD', 'NFLX', 'ORCL', 'CRM', 'ADBE', 'INTU', 'QCOM', 'TXN',
          'MU', 'AMAT', 'LRCX', 'KLAC', 'PANW', 'SNPS', 'CDNS', 'MRVL',
          'ON', 'CSCO', 'NXPI', 'FTNT', 'MAR', 'FAST', 'PAYX', 'ORLY',
          'ADI', 'MDLZ', 'ROST', 'CMCSA', 'GFS', 'MELI', 'TEAM', 'DDOG']

def safe(v):
    return float('nan') if pd.isna(v) else v

def fmt(v, fmt='.2f'):
    return format(safe(v), fmt)

def analyze(ticker):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period='6mo', interval='1d', timeout=15)
        if hist.empty or len(hist) < 100:
            return None
        close = hist['Close']
        high = hist['High']
        low = hist['Low']
        volume = hist['Volume']
        
        sma20 = close.rolling(20).mean()
        sma50 = close.rolling(50).mean()
        sma200 = close.rolling(200).mean()
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
        
        sma200_val = safe(sma200.iloc[-1])
        dist_200sma = ((curr - sma200_val) / sma200_val) * 100 if not np.isnan(sma200_val) else np.nan
        dist_50sma = ((curr - safe(sma50.iloc[-1])) / safe(sma50.iloc[-1])) * 100
        
        above_20sma = curr > safe(sma20.iloc[-1])
        above_50sma = curr > safe(sma50.iloc[-1])
        above_200sma = not np.isnan(sma200_val) and curr > sma200_val
        above_ema20 = curr > safe(ema20.iloc[-1])
        
        rsi_val = safe(rsi.iloc[-1])
        macd_val = safe(macd.iloc[-1])
        sig_val = safe(signal.iloc[-1])
        macd_hist_val = safe(macd_hist.iloc[-1])
        
        macd_bullish = macd_val > sig_val
        macd_cross_up = safe(macd.iloc[-2]) < safe(signal.iloc[-2]) and macd_val > sig_val
        macd_cross_down = safe(macd.iloc[-2]) > safe(signal.iloc[-2]) and macd_val < sig_val
        
        d20h = safe(high.tail(20).max())
        d20l = safe(low.tail(20).min())
        pullback_pct = ((curr - d20h) / d20h) * 100
        
        ret_5d = ((close.iloc[-1] / close.iloc[-6]) - 1) * 100 if len(close) > 5 else 0
        ret_10d = ((close.iloc[-1] / close.iloc[-11]) - 1) * 100 if len(close) > 10 else 0
        ret_20d = ((close.iloc[-1] / close.iloc[-21]) - 1) * 100 if len(close) > 20 else 0
        
        atr_pct = (safe(atr.iloc[-1]) / curr) * 100
        vol_ratio = volume.iloc[-1] / safe(volume.tail(20).mean()) if safe(volume.tail(20).mean()) > 0 else 0
        
        vol_10_avg = safe(volume.tail(10).mean())
        vol_10_prior = safe(volume.tail(20).head(10).mean())
        vol_trend = vol_10_avg / vol_10_prior if vol_10_prior > 0 else 1
        
        return {
            'ticker': ticker, 'price': curr,
            'sma20': safe(sma20.iloc[-1]), 'sma50': safe(sma50.iloc[-1]),
            'sma200': sma200_val,
            'ema20': safe(ema20.iloc[-1]),
            'rsi14': rsi_val, 'atr14': safe(atr.iloc[-1]), 'atr_pct': atr_pct,
            'dist_50sma': dist_50sma, 'dist_200sma': dist_200sma,
            'above_20sma': above_20sma, 'above_50sma': above_50sma,
            'above_200sma': above_200sma, 'above_ema20': above_ema20,
            'macd_bullish': macd_bullish, 'macd_cross_up': macd_cross_up,
            'macd_cross_down': macd_cross_down, 'macd_hist': macd_hist_val,
            'pullback_pct': pullback_pct,
            'ret_5d': ret_5d, 'ret_10d': ret_10d, 'ret_20d': ret_20d,
            'vol_ratio': vol_ratio, 'vol_trend': vol_trend,
            'd20h': d20h, 'd20l': d20l,
            'swing_low': safe(low.tail(60).min()),
            'swing_high': safe(high.tail(60).max()),
        }
    except Exception as e:
        return {'ticker': ticker, 'error': str(e)}

print("Fetching data...")
data = {}
for t in stocks:
    res = analyze(t)
    if res and 'error' not in res:
        data[t] = res
    else:
        print(f"  SKIP/ERR {t}: {res.get('error', 'no data') if res else 'none'}")

print(f"Fetched: {len(data)} tickers")

# Also get market indices
idx_data = {}
for idx in ['QQQ', 'SPY', 'IWM']:
    res = analyze(idx)
    if res and 'error' not in res:
        idx_data[idx] = res

for ticker, d in idx_data.items():
    print(f"\n{ticker}: ${d['price']:.2f} | RSI: {d['rsi14']:.1f} | 5d: {d['ret_5d']:+.1f}% | 20d: {d['ret_20d']:+.1f}% | vs SMA50: {d['dist_50sma']:+.1f}%")
    print(f"  SMA20: {d['sma20']:.2f} | SMA50: {d['sma50']:.2f} | SMA200: {d['sma200']:.2f if not np.isnan(d['sma200']) else 0:.2f}")

# Score each
def swing_score(d):
    score = 0
    if d['above_50sma']: score += 2
    if d['above_20sma']: score += 1
    if d['above_ema20']: score += 1
    if d['macd_bullish']: score += 2
    if d['macd_cross_up']: score += 3
    if 35 < d['rsi14'] < 60: score += 2
    if d['rsi14'] < 40: score += 3
    if d['dist_50sma'] > -3: score += 1
    if d['pullback_pct'] < -5: score += 1
    if d['ret_5d'] > 0: score += 1
    if d['macd_cross_down']: score -= 3
    if d['rsi14'] > 65: score -= 2
    if d['dist_50sma'] < -10: score -= 2
    return score

ranked = [(t, d) for t, d in data.items()]
for t, d in ranked:
    d['score'] = swing_score(d)
ranked.sort(key=lambda x: x[1]['score'], reverse=True)

print("\n" + "="*70)
print("RANKED SCAN RESULTS")
print("="*70)
for ticker, d in ranked:
    rsi_zone = 'OS' if d['rsi14'] < 40 else 'N' if d['rsi14'] < 60 else 'OB' if d['rsi14'] < 70 else 'EXT'
    macd_zone = 'BULL' if d['macd_hist'] > 0 else 'BEAR'
    print(f"{ticker:6s} | Sc:{d['score']:2d} | ${d['price']:.2f} | RSI:{d['rsi14']:5.1f}({rsi_zone}) | ATR:{d['atr_pct']:.1f}% | SMA50:{d['dist_50sma']:+.1f}% | SMA200:{d['dist_200sma']:+.1f}% | 5d:{d['ret_5d']:+.1f}% | MACD:{macd_zone}")

print("\n" + "="*70)
print("TOP 3 SWING SETUPS — DETAILED")
print("="*70)
for ticker, d in ranked[:3]:
    sl_60 = d['swing_low']
    sh_60 = d['swing_high']
    r = (sh_60 - sl_60) / sl_60 * 100
    print(f"\n{'='*35}")
    print(f"  {ticker} @ ${d['price']:.2f}  |  Score: {d['score']}")
    print(f"{'='*35}")
    print(f"  Price vs: SMA20 {((d['price']-d['sma20'])/d['sma20']*100):+.1f}% | SMA50 {d['dist_50sma']:+.1f}% | SMA200 {d['dist_200sma']:+.1f}%")
    print(f"  RSI(14): {d['rsi14']:.1f} ({'OVERSOLD' if d['rsi14']<40 else 'NEUTRAL' if d['rsi14']<60 else 'OVERBOUGHT' if d['rsi14']<70 else 'EXTREME'})")
    print(f"  MACD Hist: {d['macd_hist']:.4f} | {'BULLISH (above signal)' if d['macd_hist']>0 else 'BEARISH (below signal)'}")
    print(f"  MACD Cross: {'UP (RECENT)' if d['macd_cross_up'] else 'DOWN (RECENT)' if d['macd_cross_down'] else 'NONE'}")
    print(f"  20d Range: ${d['d20l']:.2f} – ${d['d20h']:.2f} | Pullback from 20d high: {d['pullback_pct']:.1f}%")
    print(f"  60d Swing: ${sl_60:.2f} – ${sh_60:.2f} ({r:.1f}% range)")
    print(f"  ATR(14): ${d['atr14']:.2f} ({d['atr_pct']:.1f}% of price)")
    print(f"  Momentum: 5d {d['ret_5d']:+.1f}% | 10d {d['ret_10d']:+.1f}% | 20d {d['ret_20d']:+.1f}%")
    print(f"  Volume: {d['vol_ratio']:.1f}x avg | Vol trend: {d['vol_trend']:.2f}")
    print(f"  Bullish: {'ABOVE_50SMA ' if d['above_50sma'] else ''}{'ABOVE_EMA20 ' if d['above_ema20'] else ''}{'MACD_BULL ' if d['macd_bullish'] else ''}{'MACD_XUP ' if d['macd_cross_up'] else ''}")

