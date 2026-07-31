import yfinance as yf
import json

tickers = ['^VIX', 'TLT', 'HYG', 'NBIS']
data = {}

for t in tickers:
    try:
        tk = yf.Ticker(t)
        hist = tk.history(period='5d', interval='1d')
        info = tk.info
        data[t] = {
            'price': info.get('currentPrice') or info.get('regularMarketPrice') or (hist['Close'].iloc[-1] if len(hist) > 0 else None),
            'sma50': info.get('fiftyDayAverage'),
            'sma200': info.get('twoHundredDayAverage'),
            'closes': [round(x,2) for x in hist['Close'].tolist()] if len(hist) > 0 else [],
            'highs': [round(x,2) for x in hist['High'].tolist()] if len(hist) > 0 else [],
            'lows': [round(x,2) for x in hist['Low'].tolist()] if len(hist) > 0 else [],
            'dates': [str(d.date()) for d in hist.index] if len(hist) > 0 else [],
        }
    except Exception as e:
        data[t] = {'error': str(e)}

print(json.dumps(data, indent=2, default=str))
