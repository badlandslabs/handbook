import yfinance as yf
import pandas as pd

tickers = ['QQQ', 'MSFT', 'META', 'SOFI', 'NBIS']

for t in tickers:
    try:
        tk = yf.Ticker(t)
        hist = tk.history(period='14d', interval='1d')
        if len(hist) >= 14:
            high = hist['High']
            low = hist['Low']
            close = hist['Close'].shift(1)
            tr1 = high - low
            tr2 = abs(high - close)
            tr3 = abs(low - close)
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr14 = tr.mean()
            last_close = hist['Close'].iloc[-1]
            print(f"{t}: ATR(14) = {atr14:.2f}, Close = {last_close:.2f}, ATR% = {atr14/last_close*100:.1f}%")
    except Exception as e:
        print(f"{t}: error {e}")
