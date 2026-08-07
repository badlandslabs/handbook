import yfinance as yf
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

tickers = ['GOOGL', 'FTNT', 'PANW', 'AMZN', 'NVDA', 'META', 'QCOM', 'AAPL', 'MSFT']

def deep_dive(ticker):
    t = yf.Ticker(ticker)
    
    # Daily
    daily = t.history(period='6mo', interval='1d')
    # 4H
    try:
        hf = t.history(period='3mo', interval='1h')
    except:
        hf = None
    
    close = daily['Close']
    high = daily['High']
    low = daily['Low']
    vol = daily['Volume']
    
    # 20/50 SMAs
    sma20 = close.rolling(20).mean()
    sma50 = close.rolling(50).mean()
    ema20 = close.ewm(span=20).mean()
    
    # RSI
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rsi = 100 - (100 / (1 + gain/loss.replace(0, np.nan)))
    
    # ATR
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    
    # MACD
    macd = close.ewm(span=12).mean() - close.ewm(span=26).mean()
    signal = macd.ewm(span=9).mean()
    macd_hist = macd - signal
    
    # Bollinger Bands
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_upper = bb_mid + 2*bb_std
    bb_lower = bb_mid - 2*bb_std
    bb_pos = (close.iloc[-1] - bb_lower.iloc[-1]) / (bb_upper.iloc[-1] - bb_lower.iloc[-1]) * 100
    
    curr = close.iloc[-1]
    atr_val = atr.iloc[-1]
    
    # Fibonacci retracement from 60d swing
    sl60 = low.tail(60).min()
    sh60 = high.tail(60).max()
    diff60 = sh60 - sl60
    
    fib_382 = sh60 - 0.382 * diff60
    fib_618 = sh60 - 0.618 * diff60
    fib_786 = sh60 - 0.786 * diff60
    
    # Recent support/resistance from last 10 days
    recent_highs = high.tail(10).values
    recent_lows = low.tail(10).values
    
    # VWAP approximation
    typical = (high + low + close) / 3
    vwap = (typical * vol).rolling(20).sum() / vol.rolling(20).sum()
    
    print(f"\n{'='*65}")
    print(f"  {ticker}  |  ${curr:.2f}")
    print(f"{'='*65}")
    print(f"  DAILY:")
    print(f"    SMA20: ${sma20.iloc[-1]:.2f} | SMA50: ${sma50.iloc[-1]:.2f}")
    print(f"    EMA20: ${ema20.iloc[-1]:.2f}")
    print(f"    BB Upper: ${bb_upper.iloc[-1]:.2f} | BB Lower: ${bb_lower.iloc[-1]:.2f} | BB Pos: {bb_pos:.0f}%")
    print(f"    VWAP(20): ${vwap.iloc[-1]:.2f}")
    print(f"    RSI(14): {rsi.iloc[-1]:.1f}")
    print(f"    MACD: {macd.iloc[-1]:.3f} | Signal: {signal.iloc[-1]:.3f} | Hist: {macd_hist.iloc[-1]:.4f}")
    print(f"    ATR(14): ${atr_val:.2f} ({atr_val/curr*100:.1f}%)")
    print(f"  FIBONACCI (60d swing {sl60:.2f}–{sh60:.2f}):")
    print(f"    38.2%: ${fib_382:.2f} | 61.8%: ${fib_618:.2f} | 78.6%: ${fib_786:.2f}")
    print(f"  SUPPORT ZONES:")
    print(f"    Fib 61.8% confluence: ${fib_618:.2f} ({(fib_618/curr-1)*100:+.1f}% from price)")
    print(f"    SMA50: ${sma50.iloc[-1]:.2f} ({(sma50.iloc[-1]/curr-1)*100:+.1f}% from price)")
    print(f"    EMA20: ${ema20.iloc[-1]:.2f} ({(ema20.iloc[-1]/curr-1)*100:+.1f}% from price)")
    print(f"    10d Low: ${recent_lows.min():.2f}")
    print(f"  RESISTANCE ZONES:")
    print(f"    20d High: ${high.tail(20).max():.2f}")
    print(f"    10d High: ${recent_highs.max():.2f}")
    print(f"  SWING TARGETS:")
    # TP: next resistance above
    res_above = sma50.iloc[-1] if sma50.iloc[-1] > curr else sh60
    tp1 = res_above
    tp2 = sh60
    tp3 = sh60 * 1.05  # slight extension
    print(f"    T1: ${tp1:.2f} ({(tp1/curr-1)*100:+.1f}% | {(tp1-curr)/atr_val:.1f}x ATR)")
    print(f"    T2: ${tp2:.2f} ({(tp2/curr-1)*100:+.1f}% | {(tp2-curr)/atr_val:.1f}x ATR)")
    print(f"  RISK:")
    # Stop: below support
    sl = min(fib_618, sma50.iloc[-1]) * 0.98
    risk_pct = (curr - sl) / curr * 100
    rr = (tp1 - curr) / (curr - sl) if sl < curr else 0
    print(f"    SL: ${sl:.2f} ({(sl/curr-1)*100:+.1f}% | {(curr-sl)/atr_val:.1f}x ATR)")
    print(f"    R:R = 1:{rr:.1f}")
    
    # 4H analysis
    if hf is not None and len(hf) > 20:
        hf_close = hf['Close']
        hf_high = hf['High']
        hf_low = hf['Low']
        hf_vol = hf['Volume']
        
        hf_sma20 = hf_close.rolling(20).mean()
        hf_sma50 = hf_close.rolling(50).mean()
        
        # 4H RSI
        hf_delta = hf_close.diff()
        hf_gain = hf_delta.clip(lower=0).rolling(14).mean()
        hf_loss = (-hf_delta.clip(upper=0)).rolling(14).mean()
        hf_rsi = 100 - (100 / (1 + hf_gain/hf_loss.replace(0, np.nan)))
        
        hf_ema12 = hf_close.ewm(span=12).mean()
        hf_ema26 = hf_close.ewm(span=26).mean()
        hf_macd = hf_ema12 - hf_ema26
        hf_signal = hf_macd.ewm(span=9).mean()
        hf_macd_hist = hf_macd - hf_signal
        
        print(f"  4H CHART:")
        print(f"    Price: ${hf_close.iloc[-1]:.2f} | 4H SMA20: ${hf_sma20.iloc[-1]:.2f} | 4H SMA50: ${hf_sma50.iloc[-1]:.2f}")
        print(f"    4H RSI: {hf_rsi.iloc[-1]:.1f} | 4H MACD hist: {hf_macd_hist.iloc[-1]:.4f}")
        trend_4h = 'ABOVE' if hf_close.iloc[-1] > hf_sma20.iloc[-1] else 'BELOW'
        print(f"    4H Trend: {trend_4h} 4H SMA20")

for ticker in tickers:
    try:
        deep_dive(ticker)
    except Exception as e:
        print(f"  ERROR {ticker}: {e}")

# VIX
print(f"\n{'='*65}")
print("  VIX CONTEXT")
print(f"{'='*65}")
try:
    vix = yf.Ticker('^VIX')
    vix_hist = vix.history(period='1mo', interval='1d')
    vix_curr = vix_hist['Close'].iloc[-1]
    vix_high = vix_hist['High'].tail(5).max()
    vix_low = vix_hist['Low'].tail(5).min()
    vix_ret = ((vix_hist['Close'].iloc[-1] / vix_hist['Close'].iloc[-6]) - 1) * 100 if len(vix_hist) > 5 else 0
    print(f"  VIX: {vix_curr:.2f} | 5d High: {vix_high:.2f} | 5d Low: {vix_low:.2f} | 5d change: {vix_ret:+.1f}%")
    regime_vix = 'LOW FEAR (Bull supportive)' if vix_curr < 20 else 'MODERATE' if vix_curr < 30 else 'HIGH FEAR (Bear)'
    print(f"  Regime: {regime_vix}")
except Exception as e:
    print(f"  VIX ERROR: {e}")

