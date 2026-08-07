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

def f2(v):
    try:
        return f"{v:.2f}"
    except:
        return "N/A"

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
        
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        
        tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(14).mean()
        
        curr = close.iloc[-1]
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        macd_hist = macd - signal
        
        sma200_val = safe(sma200.iloc[-1])
        dist_200sma = ((curr - sma200_val) / sma200_val) * 100 if not np.isnan(sma200_val) else np.nan
        dist_50sma = ((curr - safe(sma50.iloc[-1])) / safe(sma50.iloc[-1])) * 100
        
        rsi_val = safe(rsi.iloc[-1])
        macd_val = safe(macd.iloc[-1])
        sig_val = safe(signal.iloc[-1])
        
        return {
            'ticker': ticker, 'price': curr,
            'sma20': safe(sma20.iloc[-1]), 'sma50': safe(sma50.iloc[-1]),
            'sma200': sma200_val,
            'ema20': safe(ema20.iloc[-1]),
            'rsi14': rsi_val, 'atr14': safe(atr.iloc[-1]),
            'atr_pct': safe(atr.iloc[-1]) / curr * 100,
            'dist_50sma': dist_50sma, 'dist_200sma': dist_200sma,
            'above_20sma': curr > safe(sma20.iloc[-1]),
            'above_50sma': curr > safe(sma50.iloc[-1]),
            'above_200sma': not np.isnan(sma200_val) and curr > sma200_val,
            'above_ema20': curr > safe(ema20.iloc[-1]),
            'macd_bullish': macd_val > sig_val,
            'macd_cross_up': safe(macd.iloc[-2]) < safe(signal.iloc[-2]) and macd_val > sig_val,
            'macd_cross_down': safe(macd.iloc[-2]) > safe(signal.iloc[-2]) and macd_val < sig_val,
            'macd_hist': safe(macd_hist.iloc[-1]),
            'pullback_pct': ((curr - safe(high.tail(20).max())) / safe(high.tail(20).max())) * 100,
            'ret_5d': ((close.iloc[-1] / close.iloc[-6]) - 1) * 100 if len(close) > 5 else 0,
            'ret_10d': ((close.iloc[-1] / close.iloc[-11]) - 1) * 100 if len(close) > 10 else 0,
            'ret_20d': ((close.iloc[-1] / close.iloc[-21]) - 1) * 100 if len(close) > 20 else 0,
            'vol_ratio': volume.iloc[-1] / safe(volume.tail(20).mean()) if safe(volume.tail(20).mean()) > 0 else 0,
            'vol_trend': safe(volume.tail(10).mean()) / safe(volume.tail(20).head(10).mean()) if safe(volume.tail(20).head(10).mean()) > 0 else 1,
            'd20h': safe(high.tail(20).max()), 'd20l': safe(low.tail(20).min()),
            'swing_low': safe(low.tail(60).min()), 'swing_high': safe(high.tail(60).max()),
            'close_5ago': close.iloc[-6] if len(close) > 5 else curr,
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
        print(f"  SKIP/ERR {t}: {res.get('error','?') if res else '?'}")

print(f"Fetched {len(data)} stock tickers")

idx_data = {}
for idx in ['QQQ', 'SPY', 'IWM']:
    res = analyze(idx)
    if res and 'error' not in res:
        idx_data[idx] = res

print(f"\n{'='*70}")
print("INDEX CONTEXT")
print(f"{'='*70}")
for ticker, d in idx_data.items():
    regime = "BULL" if d['above_50sma'] and d['above_20sma'] else "BEAR" if not d['above_50sma'] and not d['above_20sma'] else "TRANSITIONAL"
    print(f"  {ticker}: ${d['price']} | RSI:{d['rsi14']:.1f} | {regime} | 5d:{d['ret_5d']:+.1f}% | 20d:{d['ret_20d']:+.1f}%")
    print(f"    SMA20:{f2(d['sma20'])} SMA50:{f2(d['sma50'])} SMA200:{f2(d['sma200'])}")

def swing_score(d):
    s = 0
    if d['above_50sma']: s += 2
    if d['above_20sma']: s += 1
    if d['above_ema20']: s += 1
    if d['macd_bullish']: s += 2
    if d['macd_cross_up']: s += 3
    if 35 < d['rsi14'] < 60: s += 2
    if d['rsi14'] < 40: s += 3
    if d['dist_50sma'] > -3: s += 1
    if d['pullback_pct'] < -5: s += 1
    if d['ret_5d'] > 0: s += 1
    if d['macd_cross_down']: s -= 3
    if d['rsi14'] > 65: s -= 2
    if d['dist_50sma'] < -10: s -= 2
    return s

ranked = [(t, d) for t, d in data.items()]
for t, d in ranked:
    d['score'] = swing_score(d)
ranked.sort(key=lambda x: x[1]['score'], reverse=True)

print(f"\n{'='*70}")
print("RANKED SCAN RESULTS")
print(f"{'='*70}")
for ticker, d in ranked:
    rsi_z = 'OS' if d['rsi14']<40 else 'N' if d['rsi14']<60 else 'OB' if d['rsi14']<70 else 'EX'
    mc = 'UP' if d['macd_cross_up'] else 'DN' if d['macd_cross_down'] else ('+' if d['macd_bullish'] else '-')
    print(f"  {ticker:6s} Sc:{d['score']:2d} ${d['price']:.2f} RSI:{d['rsi14']:5.1f}({rsi_z}) ATR:{d['atr_pct']:.1f}% "
          f"SMA50:{d['dist_50sma']:+6.1f}% SMA200:{d['dist_200sma']:+6.1f}% "
          f"5d:{d['ret_5d']:+6.1f}% MACD:{mc}")

print(f"\n{'='*70}")
print("TOP 3 SWING SETUPS — FULL ANALYSIS")
print(f"{'='*70}")
for i, (ticker, d) in enumerate(ranked[:3], 1):
    sl60 = d['swing_low']
    sh60 = d['swing_high']
    r60 = (sh60 - sl60) / sl60 * 100
    zone = 'OVERSOLD' if d['rsi14'] < 40 else 'NEUTRAL' if d['rsi14'] < 60 else 'OVERBOUGHT' if d['rsi14'] < 70 else 'EXTREME'
    
    print(f"\n{'='*65}")
    print(f"  #{i} {ticker}  |  Score: {d['score']}  |  ${d['price']}")
    print(f"{'='*65}")
    print(f"  KEY LEVELS:")
    print(f"    SMA20: ${f2(d['sma20'])} | SMA50: ${f2(d['sma50'])} | SMA200: ${f2(d['sma200'])}")
    print(f"    EMA20: ${f2(d['ema20'])}")
    print(f"    20d Range: ${f2(d['d20l'])} – ${f2(d['d20h'])} | Pullback: {d['pullback_pct']:.1f}% from 20d high")
    print(f"    60d Swing: ${f2(sl60)} – ${f2(sh60)} ({r60:.1f}% range)")
    print(f"  MOMENTUM:")
    print(f"    RSI(14): {d['rsi14']:.1f} → {zone}")
    print(f"    MACD: hist={d['macd_hist']:.4f} | {'BULLISH' if d['macd_hist']>0 else 'BEARISH'} | "
          f"{'RECENT CROSS UP' if d['macd_cross_up'] else 'RECENT CROSS DOWN' if d['macd_cross_down'] else 'STABLE'}")
    print(f"    Momentum: 5d {d['ret_5d']:+.1f}% | 10d {d['ret_10d']:+.1f}% | 20d {d['ret_20d']:+.1f}%")
    print(f"  STRUCTURE:")
    print(f"    ATR(14): ${f2(d['atr14'])} ({d['atr_pct']:.1f}% of price)")
    print(f"    Volume: {d['vol_ratio']:.1f}x avg | Vol trend: {d['vol_trend']:.2f}")
    flags = []
    if d['above_50sma']: flags.append('>SMA50')
    if d['above_20sma']: flags.append('>SMA20')
    if d['above_200sma']: flags.append('>SMA200')
    if d['above_ema20']: flags.append('>EMA20')
    if d['macd_cross_up']: flags.append('MACD_XUP')
    if d['macd_bullish']: flags.append('MACD_POS')
    if d['rsi14'] < 40: flags.append('RSI_OS')
    print(f"    Active: {' | '.join(flags)}")

