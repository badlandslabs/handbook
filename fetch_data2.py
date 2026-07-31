import yfinance as yf
import json

tickers = ['MSFT', 'META', 'NBIS', '^VIX', 'TLT', 'HYG']
data = {}

for t in tickers:
    try:
        tk = yf.Ticker(t)
        hist = tk.history(period='10d', interval='1d')
        info = tk.info
        data[t] = {
            'price': info.get('currentPrice') or info.get('regularMarketPrice') or (hist['Close'].iloc[-1] if len(hist) > 0 else None),
            'sma50': info.get('fiftyDayAverage'),
            'sma200': info.get('twoHundredDayAverage'),
            '52w_high': info.get('fiftyTwoWeekHigh'),
            '52w_low': info.get('fiftyTwoWeekLow'),
            'volume_avg': info.get('averageVolume'),
            'beta': info.get('beta'),
            'pe': info.get('trailingPE'),
            'closes': [round(x,2) for x in hist['Close'].tolist()] if len(hist) > 0 else [],
            'highs': [round(x,2) for x in hist['High'].tolist()] if len(hist) > 0 else [],
            'lows': [round(x,2) for x in hist['Low'].tolist()] if len(hist) > 0 else [],
        }
    except Exception as e:
        data[t] = {'error': str(e)}

print(json.dumps(data, indent=2, default=str))
