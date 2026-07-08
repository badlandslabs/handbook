import yfinance as yf

syms = ['AMD', 'AMAT', 'GOOGL', 'FTNT', 'CRWD', 'TSLA']
for sym in syms:
    t = yf.Ticker(sym)
    h = t.history(period='6mo', interval='1d')
    c = h['Close']
    v = h['Volume']
    recent = c.tail(60)
    highs = recent.nlargest(3)
    lows = recent.nsmallest(3)
    print(f'=== {sym} ===')
    print(f'  Current: ${c.iloc[-1]:.2f}')
    print(f'  3 Recent Swing Highs: {list(highs.round(2))}')
    print(f'  3 Recent Swing Lows: {list(lows.round(2))}')
    atr14 = sum(max(h['High'].iloc[-i]-h['Low'].iloc[-i], abs(h['High'].iloc[-i]-c.iloc[-i-1] if i < len(c)-1 else 0), abs(h['Low'].iloc[-i]-c.iloc[-i-1] if i < len(c)-1 else 0)) for i in range(1,15))/14
    print(f'  ATR(14): ${atr14:.2f}')
    l52 = h['Low'].min()
    h52 = h['High'].max()
    for fib in [0.236, 0.382, 0.5, 0.618, 0.786]:
        level = l52 + (h52 - l52) * fib
        print(f'  Fib {fib*100:.1f}%: ${level:.2f}')
    vol_avg = v.tail(20).mean()
    vol_days = v.tail(20)
    above_avg_days = (vol_days > vol_avg).sum()
    print(f'  Vol: {above_avg_days}/20 days above 20D avg')
    # More recent swings
    h20 = c.tail(20)
    swing_h = h20.max()
    swing_l = h20.min()
    print(f'  20D High: ${swing_h:.2f}  20D Low: ${swing_l:.2f}')
    print()
