#!/opt/hermes/.venv/bin/python3
import yfinance as yf
import pandas as pd

def get_data(ticker_sym, period='6mo', interval='1d'):
    h = yf.download(ticker_sym, period=period, interval=interval, progress=False, auto_adjust=True)
    if h.empty:
        return None
    if isinstance(h.columns, pd.MultiIndex):
        h.columns = h.columns.get_level_values(0)
    return h

def analyze(ticker_sym):
    h = get_data(ticker_sym)
    if h is None or 'Close' not in h.columns or h['Close'].dropna().empty:
        return f'{ticker_sym}:NO_DATA'
    close = h['Close'].dropna()
    high = h['High'] if 'High' in h.columns else close
    low = h['Low'] if 'Low' in h.columns else close
    vol = h['Volume'] if 'Volume' in h.columns else None

    c = float(close.iloc[-1])
    s20 = float(close.rolling(20).mean().iloc[-1])
    s50 = float(close.rolling(50).mean().iloc[-1])
    s200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None
    e20 = float(close.ewm(span=20).mean().iloc[-1])

    r1 = float((close.iloc[-1]/close.iloc[-2]-1)*100) if len(close)>=2 else 0.0
    r5 = float((close.iloc[-1]/close.iloc[-6]-1)*100) if len(close)>=6 else 0.0
    r1m = float((close.iloc[-1]/close.iloc[-22]-1)*100) if len(close)>=22 else 0.0
    r3m = float((close.iloc[-1]/close.iloc[-63]-1)*100) if len(close)>=63 else 0.0

    high52 = float(h['High'].max()) if 'High' in h.columns else c
    low52 = float(h['Low'].min()) if 'Low' in h.columns else c

    # ATR
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr14 = float(tr.rolling(14).mean().iloc[-1])
    atr_pct = atr14/c*100 if c > 0 else 0

    # RSI(14)
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.rolling(14).mean().iloc[-1]
    avg_loss = loss.rolling(14).mean().iloc[-1]
    rs = avg_gain / avg_loss if avg_loss != 0 else 100
    rsi14 = 100 - (100/(1+rs)) if avg_loss != 0 else 100

    # Vol ratio
    if vol is not None and len(vol) >= 20:
        avgvol = float(vol.rolling(20).mean().iloc[-1])
        curvol = float(vol.iloc[-1])
        vol_ratio = curvol/avgvol if avgvol > 0 else 0
    else:
        vol_ratio = 0

    pct_52w = (c - low52)/(high52 - low52)*100 if high52 > low52 else 0

    # MACD
    ema12 = float(close.ewm(span=12).mean().iloc[-1])
    ema26 = float(close.ewm(span=26).mean().iloc[-1])
    macd_line = ema12 - ema26
    # MACD signal
    macd_hist = macd_line  # simplified

    # Market structure
    above20 = c > s20
    above50 = c > s50
    above200 = s200 is not None and c > s200
    ema_bull = e20 > s50

    trend = "UP" if s20 > s50 else "DOWN"

    return f'{ticker_sym}: price={c:.2f} 20sma={s20:.2f} 50sma={s50:.2f} 200sma={f"{s200:.2f}" if s200 else "N/A"} 20ema={e20:.2f} above200={above200} trend={trend} ema_bull={ema_bull} rsi14={rsi14:.1f} macd={macd_line:.2f} 1d={r1:+.2f}% 5d={r5:+.2f}% 1m={r1m:+.2f}% 3m={r3m:+.2f}% 52wpos={pct_52w:.0f}% volratio={vol_ratio:.1f}x atr={atr14:.2f}({atr_pct:.1f}%)'

tickers = ['QQQ','SPY','IWM','^VIX','^TNX','HYG',
           'NVDA','AAPL','MSFT','GOOGL','AMZN','META','AVGO','TSLA',
           'AMD','CRM','ORCL','PANW','NFLX','MU','INTU','AMAT',
           'LRCX','KLAC','SNPS','CDNS','ADSK','QCOM','TXN','NXPI',
           'INTC','CSCO','ADP','ADI','EXC','FANG','GEHC','HON',
           'ISRG','KDP','MCHP','MDLZ','MRVL','NXPI','ON','PANW']

results = []
for t in tickers:
    r = analyze(t)
    results.append(r)

for r in results:
    print(r)
