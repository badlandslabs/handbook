import yfinance as yf
import json
import pandas as pd

tickers = ['QQQ', 'SPY', 'IWM', 'NVDA', 'AAPL', 'MSFT', 'AMZN', 'GOOGL', 'META', 'TSLA', 'AMD', 'AVGO', '^VIX']

results = []
for t in tickers:
    tk = yf.Ticker(t)
    info = tk.info
    hist = tk.history(period='6mo', interval='1d')
    close = hist['Close']
    high = hist['High']
    low = hist['Low']
    price = info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose')
    prev = info.get('previousClose') or info.get('regularMarketPreviousClose')
    
    sma20 = close.rolling(20).mean().iloc[-1]
    sma50 = close.rolling(50).mean().iloc[-1]
    ema9 = close.ewm(span=9).mean().iloc[-1]
    
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr14 = tr.rolling(14).mean().iloc[-1]
    
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi14 = 100 - (100 / (1 + rs)).iloc[-1]
    
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    macd_line = ema12 - ema26
    signal = macd_line.ewm(span=9).mean()
    macd_hist = (macd_line - signal).iloc[-1]
    
    gap = (price - prev) / prev * 100 if prev else 0
    ret5 = (close.iloc[-1] / close.iloc[-6] - 1) * 100 if len(close) >= 6 else None
    ret10 = (close.iloc[-1] / close.iloc[-11] - 1) * 100 if len(close) >= 11 else None
    ret20 = (close.iloc[-1] / close.iloc[-21] - 1) * 100 if len(close) >= 21 else None
    
    h52 = info.get('fiftyTwoWeekHigh')
    l52 = info.get('fiftyTwoWeekLow')
    
    results.append({
        'Ticker': t,
        'Price': round(price, 2),
        'Prev': round(prev, 2),
        'Gap%': round(gap, 2),
        'SMA20': round(sma20, 2),
        'SMA50': round(sma50, 2),
        'EMA9': round(ema9, 2),
        'ATR14': round(atr14, 2),
        'RSI14': round(rsi14, 1),
        'MACD_Hist': round(macd_hist, 3),
        'Ret5d': round(ret5, 2) if ret5 else None,
        'Ret10d': round(ret10, 2) if ret10 else None,
        'Ret1m': round(ret20, 2) if ret20 else None,
        '52WHigh': h52,
        '52WLow': l52,
        'PctHigh': round((price - h52)/h52*100, 1) if h52 else None,
        'PctLow': round((price - l52)/l52*100, 1) if l52 else None,
        'AvgVol': info.get('averageVolume'),
        'Rating': info.get('recommendationKey'),
        'Target': info.get('targetMeanPrice'),
        'FwdPE': round(info.get('forwardPE'), 1) if info.get('forwardPE') else None,
        'Sector': info.get('sector'),
        'Name': info.get('shortName') or t,
        '5Closes': [round(x, 2) for x in close.tail(5).values],
        '5Lows': [round(x, 2) for x in low.tail(5).values],
    })

for r in results:
    print("=" * 80)
    print(f"{r['Ticker']} ({r['Name']})")
    print(f"  Price=${r['Price']} | Prev=${r['Prev']} | Gap={r['Gap%']}%")
    print(f"  SMA20=${r['SMA20']} | SMA50=${r['SMA50']} | EMA9=${r['EMA9']}")
    print(f"  ATR14=${r['ATR14']} | RSI14={r['RSI14']} | MACD_Hist={r['MACD_Hist']}")
    print(f"  Ret5d={r['Ret5d']}% | Ret10d={r['Ret10d']}% | Ret1m={r['Ret1m']}%")
    print(f"  52W: High={r['52WHigh']} ({r['PctHigh']}%) | Low={r['52WLow']} ({r['PctLow']}%)")
    print(f"  AvgVol={r['AvgVol']:,} | Rating={r['Rating']} | Target=${r['Target']} | FwdPE={r['FwdPE']}")
    print(f"  Sector: {r['Sector']}")
    print(f"  5-Day Closes: {r['5Closes']}")
    print(f"  5-Day Lows:   {r['5Lows']}")
