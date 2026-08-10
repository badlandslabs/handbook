#!/opt/hermes/.venv/bin/python3
import yfinance as yf
import pandas as pd

def get_ohlcv(ticker_sym, period='3mo', interval='1d'):
    h = yf.download(ticker_sym, period=period, interval=interval, progress=False)
    if h.empty:
        return None, None
    # Flatten multi-index columns if present
    if isinstance(h.columns, pd.MultiIndex):
        h.columns = h.columns.get_level_values(0)
    close = h['Close'].dropna()
    high = h['High'] if 'High' in h.columns else close
    low = h['Low'] if 'Low' in h.columns else close
    vol = h['Volume'] if 'Volume' in h.columns else None
    return close, (high, low, vol)

tickers = ['QQQ','SPY','IWM','^VIX','^TNX','HYG']
results = []
for t in tickers:
    try:
        close, ohlcv = get_ohlcv(t)
        if close is None or close.empty:
            results.append(f'{t}:NO_DATA')
            continue
        c = close.iloc[-1]
        s20 = close.rolling(20).mean().iloc[-1]
        s50 = close.rolling(50).mean().iloc[-1]
        s200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else None
        r1 = float((close.iloc[-1]/close.iloc[-2]-1)*100) if len(close)>=2 else 0.0
        r5 = float((close.iloc[-1]/close.iloc[-6]-1)*100) if len(close)>=6 else 0.0
        r1m = float((close.iloc[-1]/close.iloc[-22]-1)*100) if len(close)>=22 else 0.0
        high52 = float(ohlcv[0].max()) if ohlcv and ohlcv[0] is not None else c
        low52 = float(ohlcv[1].min()) if ohlcv and ohlcv[1] is not None else c
        above200 = ("YES" if s200 is not None and c>s200 else "NO" if s200 is not None else "N/A")
        trend = "UP" if s20>s50 else "DOWN"
        results.append(f'{t}: price={c:.2f} 20sma={s20:.2f} 50sma={s50:.2f} 200sma={f"{s200:.2f}" if s200 else "N/A"} above200={above200} trend={trend} 1d={r1:+.2f}% 5d={r5:+.2f}% 1m={r1m:+.2f}% 52wh={high52:.2f} 52wl={low52:.2f}')
    except Exception as e:
        results.append(f'{t}:ERROR {e}')

for r in results:
    print(r)

print("\n--- NASDAQ 100 TOP COMPONENTS ---")
# Top liquid NASDAQ-100 components with high relative volume / catalysts
nasdaq100 = ['NVDA','AAPL','MSFT','GOOGL','AMZN','META','AVGO','TSLA','AMD','CRM','ORCL','PANW','NFLX','MU','INTU','AMAT','LRCX','KLAC','SNPS','CDNS','ADSK','QCOM','TXN','NXPI','INTC']
for t in nasdaq100:
    try:
        close, ohlcv = get_ohlcv(t)
        if close is None or close.empty:
            continue
        c = close.iloc[-1]
        s20 = close.rolling(20).mean().iloc[-1]
        s50 = close.rolling(50).mean().iloc[-1]
        s200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else None
        r1 = float((close.iloc[-1]/close.iloc[-2]-1)*100) if len(close)>=2 else 0.0
        r5 = float((close.iloc[-1]/close.iloc[-6]-1)*100) if len(close)>=6 else 0.0
        r1m = float((close.iloc[-1]/close.iloc[-22]-1)*100) if len(close)>=22 else 0.0
        vol_col = ohlcv[2] if ohlcv and ohlcv[2] is not None else None
        avgvol20 = float(vol_col.rolling(20).mean().iloc[-1]) if vol_col is not None and len(vol_col)>=20 else 0
        curvol = float(vol_col.iloc[-1]) if vol_col is not None and len(vol_col)>0 else 0
        vol_ratio = curvol/avgvol20 if avgvol20 > 0 else 0
        high52 = float(ohlcv[0].max()) if ohlcv and ohlcv[0] is not None else c
        low52 = float(ohlcv[1].min()) if ohlcv and ohlcv[1] is not None else c
        above200 = ("YES" if s200 is not None and c>s200 else "NO" if s200 is not None else "N/A")
        trend = "UP" if s20>s50 else "DOWN"
        # ATR approximation
        high_arr = ohlcv[0] if ohlcv and ohlcv[0] is not None else close
        low_arr = ohlcv[1] if ohlcv and ohlcv[1] is not None else close
        tr1 = high_arr - low_arr
        tr2 = abs(high_arr - close.shift(1))
        tr3 = abs(low_arr - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr14 = float(tr.rolling(14).mean().iloc[-1])
        atr_pct = atr14/c*100 if c > 0 else 0
        pct_52w = (c - low52)/(high52 - low52)*100 if high52 > low52 else 0
        results.append(f'{t}: price={c:.2f} 20sma={s20:.2f} 50sma={s50:.2f} above200={above200} trend={trend} 1d={r1:+.2f}% 5d={r5:+.2f}% 1m={r1m:+.2f}% 52wpos={pct_52w:.0f}% volratio={vol_ratio:.1f}x atr={atr14:.2f}({atr_pct:.1f}%)')
    except Exception as e:
        pass

for r in results[len(nasdaq100):]:
    print(r)
