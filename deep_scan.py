#!/opt/hermes/.venv/bin/python3
import yfinance as yf
import pandas as pd

def get_deep(ticker_sym, period='3mo', interval='1d'):
    h = yf.download(ticker_sym, period=period, interval=interval, progress=False, auto_adjust=True)
    if h.empty:
        return None
    if isinstance(h.columns, pd.MultiIndex):
        h.columns = h.columns.get_level_values(0)
    return h

def deep_analysis(ticker):
    h = get_deep(ticker)
    if h is None: return f'{ticker}: NO_DATA'
    close = h['Close'].dropna()
    high = h['High']
    low = h['Low']
    vol = h['Volume'] if 'Volume' in h.columns else None
    c = float(close.iloc[-1])
    s8 = float(close.rolling(8).mean().iloc[-1])
    s20 = float(close.rolling(20).mean().iloc[-1])
    s50 = float(close.rolling(50).mean().iloc[-1])
    e20 = float(close.ewm(span=20).mean().iloc[-1])
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr14 = float(tr.rolling(14).mean().iloc[-1])
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = float(gain.rolling(14).mean().iloc[-1])
    avg_loss = float(loss.rolling(14).mean().iloc[-1])
    rs = avg_gain / avg_loss if avg_loss != 0 else 100
    rsi14 = 100 - (100/(1+rs)) if avg_loss != 0 else 100
    sma20_series = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    bb_upper = float((sma20_series + 2*std20).iloc[-1])
    bb_lower = float((sma20_series - 2*std20).iloc[-1])
    bb_pct = (c - bb_lower)/(bb_upper - bb_lower)*100 if bb_upper != bb_lower else 50
    ret_5d = float((close.iloc[-1]/close.iloc[-6]-1)*100) if len(close)>=6 else 0
    ret_10d = float((close.iloc[-1]/close.iloc[-11]-1)*100) if len(close)>=11 else 0
    vol_ratio = 0
    if vol is not None and len(vol) >= 20:
        avgvol = float(vol.rolling(20).mean().iloc[-1])
        curvol = float(vol.iloc[-1])
        vol_ratio = curvol/avgvol if avgvol > 0 else 0
    h52 = float(h['High'].max())
    l52 = float(h['Low'].min())
    swing_high_20 = float(high.rolling(20).max().iloc[-1])
    swing_low_20 = float(low.rolling(20).min().iloc[-1])
    pct_52w = (c - l52)/(h52 - l52)*100 if h52 > l52 else 0
    # MACD
    ema12 = float(close.ewm(span=12).mean().iloc[-1])
    ema26 = float(close.ewm(span=26).mean().iloc[-1])
    macd = ema12 - ema26
    macd_sig = float(pd.Series([ema12-ema26]).ewm(span=9).mean().iloc[-1])
    # Stoch K
    low14 = low.rolling(14).min().iloc[-1]
    high14 = high.rolling(14).max().iloc[-1]
    stoch_k = 100*(c - low14)/(high14 - low14) if high14 != low14 else 50
    lines = []
    lines.append(f'{ticker}: price={c:.2f}')
    lines.append(f'  8sma={s8:.2f} 20sma={s20:.2f} 50sma={s50:.2f} 20ema={e20:.2f}')
    lines.append(f'  rsi14={rsi14:.1f} stoch_k={stoch_k:.1f}')
    lines.append(f'  macd={macd:.2f} macd_sig={macd_sig:.2f}')
    lines.append(f'  bb_upper={bb_upper:.2f} bb_lower={bb_lower:.2f} bb_pct={bb_pct:.0f}')
    lines.append(f'  5d={ret_5d:+.2f}% 10d={ret_10d:+.2f}%')
    lines.append(f'  swing20_hi={swing_high_20:.2f} swing20_lo={swing_low_20:.2f}')
    lines.append(f'  52wh={h52:.2f} 52wl={l52:.2f} 52wpos={pct_52w:.0f}%')
    lines.append(f'  atr14={atr14:.2f}({atr14/c*100:.1f}%) volratio={vol_ratio:.1f}x')
    return '\n'.join(lines)

for t in ['PANW','AAPL','NXPI','TSLA','NVDA','ADSK','MSFT','AMZN','QCOM','INTC']:
    print(deep_analysis(t))
    print()
