import yfinance as yf
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

def get_ohlcv(ticker, period='6mo', interval='1d'):
    df = yf.download(ticker, period=period, interval=interval, progress=False)
    if df.empty:
        return None, None, None, None, None
    # Handle multi-level columns from yfinance
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    close = df['Close'].values.flatten()
    high = df['High'].values.flatten()
    low = df['Low'].values.flatten()
    vol = df['Volume'].values.flatten()
    dates = df.index
    return close, high, low, vol, dates

def calc_rsi(close, period=14):
    delta = np.diff(close, prepend=close[0])
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    # EMA
    alpha = 2 / (period + 1)
    ema_gain = gain[0]
    ema_loss = loss[0]
    for i in range(1, len(gain)):
        ema_gain = alpha * gain[i] + (1 - alpha) * ema_gain
        ema_loss = alpha * loss[i] + (1 - alpha) * ema_loss
    rs = ema_gain / ema_loss if ema_loss != 0 else 100
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calc_atr(high, low, close, period=14):
    tr1 = high - low
    tr2 = np.abs(high - np.roll(close, 1))
    tr3 = np.abs(low - np.roll(close, 1))
    tr2[0] = tr1[0]
    tr3[0] = tr1[0]
    tr = np.maximum.reduce([tr1, tr2, tr3])
    # SMA ATR
    atr = np.mean(tr[-period:])
    return atr

def calc_sma(close, period):
    if len(close) < period:
        return np.nan
    return np.mean(close[-period:])

print("=== MACRO REGIME ===")
for sym in ['SPY', 'QQQ', 'IWM', '^VIX']:
    close, high, low, vol, dates = get_ohlcv(sym, '1y')
    if close is None:
        print(f"{sym}: No data")
        continue
    latest = close[-1]
    sma20 = calc_sma(close, 20)
    sma50 = calc_sma(close, 50)
    sma200 = calc_sma(close, 200)
    rsi = calc_rsi(close)
    atr = calc_atr(high, low, close)
    pct_52w = ((latest - np.min(low)) / (np.max(low) - np.min(low))) * 100 if np.max(low) > np.min(low) else 50
    print(f"{sym}: ${latest:.2f} | SMA20={sma20:.2f} | SMA50={sma50:.2f} | SMA200={sma200:.2f} | RSI={rsi:.1f} | ATR={atr:.2f} | Above200={latest>sma200} | 52wPos={pct_52w:.0f}%")

print("\n=== TOP CANDIDATE DEEP DIVE ===")
candidates = ['CRWD', 'PANW', 'NVDA', 'AMAT', 'FAST', 'TSLA', 'AAPL', 'META', 'AVGO', 'AMD']

for sym in candidates:
    close, high, low, vol, dates = get_ohlcv(sym, '3mo')
    if close is None or len(close) < 30:
        print(f"{sym}: No data")
        continue
    
    latest = close[-1]
    prev5 = close[-6] if len(close) > 5 else close[0]
    prev10 = close[-11] if len(close) > 10 else close[0]
    prev20 = close[-21] if len(close) > 20 else close[0]
    
    sma20 = calc_sma(close, 20)
    sma50 = calc_sma(close, 50)
    sma200 = calc_sma(close, 200) if len(close) >= 200 else np.nan
    rsi = calc_rsi(close)
    atr = calc_atr(high, low, close)
    
    # EMA for MACD
    ema12 = close[-1]
    ema26 = close[-1]
    alpha12 = 2/13
    alpha26 = 2/27
    for i in range(min(50, len(close)-1), -1, -1):
        if i == min(50, len(close)-1):
            ema12 = close[i]
            ema26 = close[i]
        else:
            ema12 = alpha12 * close[i] + (1-alpha12) * ema12
            ema26 = alpha26 * close[i] + (1-alpha26) * ema26
    # Recalc properly from start
    ema12_arr = []
    ema26_arr = []
    for i in range(len(close)):
        if i == 0:
            ema12_arr.append(close[0])
            ema26_arr.append(close[0])
        else:
            ema12_arr.append(alpha12 * close[i] + (1-alpha12) * ema12_arr[-1])
            ema26_arr.append(alpha26 * close[i] + (1-alpha26) * ema26_arr[-1])
    macd_line = ema12_arr[-1] - ema26_arr[-1]
    macd_prev = ema12_arr[-2] - ema26_arr[-2]
    # Signal = 9-period EMA of MACD
    macd_vals = np.array(ema12_arr) - np.array(ema26_arr)
    alpha9 = 2/10
    macd_sig = macd_vals[-1]
    for i in range(-10, -1):
        macd_sig = alpha9 * macd_vals[i] + (1-alpha9) * macd_sig
    
    # Bollinger
    bb_mid = sma20
    bb_std = np.std(close[-20:])
    bb_upper = bb_mid + 2*bb_std
    bb_lower = bb_mid - 2*bb_std
    bb_pos = (latest - bb_lower) / (bb_upper - bb_lower) if bb_upper > bb_lower else 0.5
    
    # Recent swing highs/lows (lookback 20 days)
    swing_highs = []
    swing_lows = []
    for i in range(2, min(len(high)-2, 22)):
        if high[i] > high[i-1] and high[i] > high[i+1] and high[i] > high[i-2] and high[i] > high[i+2]:
            swing_highs.append(high[i])
        if low[i] < low[i-1] and low[i] < low[i+1] and low[i] < low[i-2] and low[i] < low[i+2]:
            swing_lows.append(low[i])
    
    # Recent support = max of recent lows below price
    nearest_support = max([l for l in swing_lows if l < latest], default=latest*0.95)
    nearest_resistance = min([h for h in swing_highs if h > latest], default=latest*1.05)
    
    ret_5d = (latest/prev5 - 1)*100
    ret_10d = (latest/prev10 - 1)*100
    ret_20d = (latest/prev20 - 1)*100 if len(close) > 20 else 0
    
    print(f"\n{sym}: ${latest:.2f}")
    print(f"  RSI={rsi:.1f} | ATR14={atr:.2f} ({(atr/latest)*100:.1f}% of price)")
    sma200_str = f"{sma200:.2f}" if not np.isnan(sma200) else "N/A"
    print(f"  SMA20={sma20:.2f} | SMA50={sma50:.2f} | SMA200={sma200_str}")
    print(f"  BB: Lower={bb_lower:.2f} Upper={bb_upper:.2f} Pos={bb_pos*100:.0f}%")
    print(f"  MACD={macd_line:.3f} Signal={macd_sig:.3f} | {'BULL+' if macd_line > macd_sig else 'BEAR-'}")
    print(f"  Returns: 5d={ret_5d:+.1f}% | 10d={ret_10d:+.1f}% | 20d={ret_20d:+.1f}%")
    print(f"  Nearest S: ${nearest_support:.2f} | Nearest R: ${nearest_resistance:.2f}")
    print(f"  Swing Highs (recent): {sorted(swing_highs, reverse=True)[:3]}")
    print(f"  Swing Lows (recent): {sorted(swing_lows)[:3]}")
    above_200 = "N/A" if np.isnan(sma200) else (latest > sma200)
    print(f"  Above SMA20: {latest > sma20} | Above SMA50: {latest > sma50} | Above SMA200: {above_200}")
    
    # Earnings
    try:
        t = yf.Ticker(sym)
        try:
            cal = t.calendar
            if cal is not None:
                print(f"  Earnings cal: {cal}")
        except:
            pass
    except:
        pass

print("\n=== SECTOR ROTATION ===")
sector_etfs = {'XLK':'Tech', 'XLF':'Financials', 'XLV':'Healthcare', 'XLY':'Consumer Disc',
               'XLP':'Staples', 'XLE':'Energy', 'XLC':'Comm', 'XLI':'Industrials', 'XLB':'Materials', 'XLRE':'Real Estate'}
for etf, name in sector_etfs.items():
    close, _, _, _, _ = get_ohlcv(etf, '20d')
    spy_close, _, _, _, _ = get_ohlcv('SPY', '20d')
    if close is not None and spy_close is not None and len(close) > 2 and len(spy_close) > 2:
        etf_ret = (close[-1]/close[0] - 1)*100
        spy_ret = (spy_close[-1]/spy_close[0] - 1)*100
        rel = etf_ret - spy_ret
        print(f"  {etf} ({name}): {etf_ret:+.2f}% | vs SPY: {rel:+.2f}%")

print("\n=== SCAN COMPLETE ===")
