import yfinance as yf
import pandas as pd

tickers = ['QQQ', 'SPY', 'IWM', 'NVDA', 'AAPL', 'MSFT', 'AMZN', 'GOOGL', 'META', 'TSLA', 'AMD', 'AVGO', '^VIX']

rows = []
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
    ret5 = (close.iloc[-1] / close.iloc[-6] - 1) * 100 if len(close) >= 6 else 0
    ret10 = (close.iloc[-1] / close.iloc[-11] - 1) * 100 if len(close) >= 11 else 0
    ret20 = (close.iloc[-1] / close.iloc[-21] - 1) * 100 if len(close) >= 21 else 0
    h52 = info.get('fiftyTwoWeekHigh')
    l52 = info.get('fiftyTwoWeekLow')
    rows.append({
        'T': t,
        'Px': round(price, 2),
        'Prev': round(prev, 2),
        'Gap': round(gap, 2),
        'SMA20': round(sma20, 2),
        'SMA50': round(sma50, 2),
        'ATR': round(atr14, 2),
        'RSI': round(rsi14, 1),
        'MHist': round(macd_hist, 3),
        'R5d': round(ret5, 2),
        'R10d': round(ret10, 2),
        'R1m': round(ret20, 2),
        'H52': h52,
        'L52': l52,
        'PctHi': round((price - h52)/h52*100, 1) if h52 else None,
        'PctLo': round((price - l52)/l52*100, 1) if l52 else None,
        'Vol': info.get('averageVolume'),
        'Rate': info.get('recommendationKey'),
        'Tgt': info.get('targetMeanPrice'),
        'FwdPE': round(info.get('forwardPE'), 1) if info.get('forwardPE') else None,
        'Sector': info.get('sector'),
        'Name': (info.get('shortName') or t)[:30],
    })

df = pd.DataFrame(rows)
cols = ['T','Name','Px','Prev','Gap','SMA20','SMA50','ATR','RSI','MHist','R5d','R10d','R1m','H52','L52','PctHi','PctLo','Vol','Rate','Tgt','FwdPE','Sector']
df = df[cols]
print(df.to_string(index=False))
