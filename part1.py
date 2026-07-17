#!/opt/data/handbook/venv/bin/python3
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def compute_indicators(df):
    close = df['Close']
    high = df['High']
    low = df['Low']
    volume = df['Volume']
    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()
    ema20 = close.ewm(span=20).mean()
    ema50 = close.ewm(span=50).mean()
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9).mean()
    macd_hist = macd - signal
    tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    atr14 = tr.rolling(14).mean()
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std
    swing_high_20 = high.rolling(20).max().shift(1)
    swing_low_20 = low.rolling(20).min().shift(1)
    vol_sma20 = volume.rolling(20).mean()
    vol_ratio = volume / vol_sma20
    return pd.DataFrame({
        'Close': close, 'High': high, 'Low': low, 'Volume': volume,
        'MA20': ma20, 'MA50': ma50, 'EMA20': ema20, 'EMA50': ema50,
        'RSI14': rsi, 'MACD': macd, 'MACD_Signal': signal, 'MACD_Hist': macd_hist,
        'ATR14': atr14, 'BB_Upper': bb_upper, 'BB_Lower': bb_lower,
        'SwingHigh20': swing_high_20, 'SwingLow20': swing_low_20,
        'VolSMA20': vol_sma20, 'VolRatio': vol_ratio
    })

def scan_setup(ticker, df):
    close = df['Close'].iloc[-1]
    prev_close = df['Close'].iloc[-2]
    rsi = df['RSI14'].iloc[-1]
    macd_hist = df['MACD_Hist'].iloc[-1]
    prev_macd_hist = df['MACD_Hist'].iloc[-2]
    atr14 = df['ATR14'].iloc[-1]
    vol_ratio = df['VolRatio'].iloc[-1]
    bb_upper = df['BB_Upper'].iloc[-1]
    bb_lower = df['BB_Lower'].iloc[-1]
    swing_low = df['SwingLow20'].iloc[-1]
    swing_high = df['SwingHigh20'].iloc[-1]
    ma20 = df['MA20'].iloc[-1]
    ma50 = df['MA50'].iloc[-1]
    pct_change = ((close - prev_close) / prev_close) * 100
    score = 0
    signals = []
    if close > ma20:
        score += 2
        signals.append('Above MA20')
    if close > ma50:
        score += 2
        signals.append('Above MA50')
    if ma20 > ma50:
        score += 1
        signals.append('MA20>MA50')
    if 40 <= rsi <= 65:
        score += 2
        signals.append(f'RSI {rsi:.0f}')
    elif rsi < 30:
        score += 1
        signals.append(f'RSI ovrSld {rsi:.0f}')
    elif rsi > 70:
        score -= 1
        signals.append(f'RSI ovrBgt {rsi:.0f}')
    if macd_hist > 0 and prev_macd_hist <= 0:
        score += 3
        signals.append('MACD XOVER')
    elif macd_hist > 0 and macd_hist > prev_macd_hist:
        score += 1
        signals.append('MACD expand')
    elif macd_hist < 0:
        score -= 1
        signals.append('MACD bear')
    if vol_ratio.iloc[-1] > 1.5:
        score += 2
        signals.append(f'Vol {vol_ratio.iloc[-1]:.1f}x')
    elif vol_ratio.iloc[-1] > 1.0:
        score += 1
        signals.append(f'Vol {vol_ratio.iloc[-1]:.1f}x')
    dist_to_high = ((swing_high - close) / close) * 100 if pd.notna(swing_high) else None
    dist_to_low = ((close - swing_low) / close) * 100 if pd.notna(swing_low) else None
    bb_pct = ((close - bb_lower) / (bb_upper - bb_lower)) * 100 if pd.notna(bb_upper) else 50
    return {
        'ticker': ticker, 'close': close, 'pct_change': pct_change,
        'rsi': rsi, 'macd_hist': macd_hist, 'atr14': atr14, 'atr_pct': (atr14 / close) * 100,
        'vol_ratio': vol_ratio.iloc[-1],
        'bb_upper': bb_upper, 'bb_lower': bb_lower, 'bb_pct': bb_pct,
        'swing_low': swing_low, 'swing_high': swing_high,
        'dist_to_resistance': dist_to_high, 'dist_to_support': dist_to_low,
        'ma20': ma20, 'ma50': ma50,
        'score': score, 'signals': signals,
    }

today = datetime.now().strftime('%Y-%m-%d')
start = (datetime.now() - timedelta(days=200)).strftime('%Y-%m-%d')

ndaq100 = ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'TSLA', 'AVGO', 'ORCL', 'AMD',
           'NFLX', 'CRM', 'ADBE', 'INTU', 'TXN', 'QCOM', 'AMAT', 'MU', 'LRCX', 'KLAC']

print("Fetching data...")
ndx_data = yf.download(ndaq100, start=start, end=today, progress=False, auto_adjust=True)
results = []
for ticker in ndaq100:
    try:
        close_s = ndx_data['Close'][ticker].dropna()
        if len(close_s) < 50:
            continue
        high_s = ndx_data['High'][ticker].dropna()
        low_s = ndx_data['Low'][ticker].dropna()
        vol_s = ndx_data['Volume'][ticker].dropna()
        common = close_s.index.intersection(high_s.index).intersection(low_s.index).intersection(vol_s.index)
        df_full = pd.DataFrame({'Close': close_s, 'High': high_s, 'Low': low_s, 'Volume': vol_s}).loc[common]
        ind = compute_indicators(df_full)
        setup = scan_setup(ticker, ind)
        results.append(setup)
    except Exception as e:
        pass

results.sort(key=lambda x: x['score'], reverse=True)

# Print just the table
for r in results:
    print(f"{r['ticker']}: close={r['close']:.2f} rsi={r['rsi']:.1f} macdh={r['macd_hist']:.4f} atr%={r['atr_pct']:.2f} vol={r['vol_ratio']:.2f} bb%={r['bb_pct']:.0f} sh={r['swing_high']:.2f if pd.notna(r['swing_high']) else 0:.2f} sl={r['swing_low']:.2f if pd.notna(r['swing_low']) else 0:.2f} distR={r['dist_to_resistance']:.1f if r['dist_to_resistance'] else 0:.1f}% distS={r['dist_to_support']:.1f if r['dist_to_support'] else 0:.1f}% score={r['score']} signals={','.join(r['signals'])}")
