import json

with open('swing_deep.json') as f:
    d = json.load(f)

tickers = ['AMD', 'TSLA', 'META', 'PANW', 'AVGO', 'NVDA', 'AAPL', 'AMZN', 'MSFT', 'GOOGL']
for t in tickers:
    if t in d:
        dd = d[t]
        print(f"{t}|{dd['price']}|{dd['ret_5d']}|{dd['ret_10d']}|{dd['ret_20d']}|{dd['rsi14']}|{dd['atr14']}|{dd['price_pos_20d']}|{dd['bb_pos']}|{dd['swing_high_10d']}|{dd['swing_low_10d']}|{dd['fib_382']}|{dd['fib_618']}|{dd['fib_786']}|{dd['macd']}|{dd['macd_hist']}|{dd['sma20']}|{dd['sma50']}")
