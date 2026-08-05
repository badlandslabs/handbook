import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

print(f"=== FULL MARKET DATA — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")

# Indices
indices = ['QQQ', 'SPY', 'IWM', '^VIX']

for ticker in indices:
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period='3mo', interval='1d', timeout=15)
        if len(hist) > 0:
            last = hist.iloc[-1]
            close = last['Close']
            high_20d = hist['High'].tail(20).max()
            low_20d = hist['Low'].tail(20).min()
            sma20 = hist['Close'].tail(20).mean()
            sma50 = hist['Close'].tail(50).mean() if len(hist) >= 50 else close
            sma200 = hist['Close'].tail(200).mean() if len(hist) >= 200 else close
            
            delta = hist['Close'].diff()
            gain = delta.clip(lower=0).ewm(span=14, adjust=False).mean()
            loss = (-delta.clip(upper=0)).ewm(span=14, adjust=False).mean()
            rs = gain / loss
            rsi = (100 - (100 / (1 + rs))).iloc[-1]
            
            high_low = hist['High'] - hist['Low']
            high_close = (hist['High'] - hist['Close'].shift()).abs()
            low_close = (hist['Low'] - hist['Close'].shift()).abs()
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr = tr.tail(14).mean()
            
            mom20 = (close - hist['Close'].iloc[-21]) / hist['Close'].iloc[-21] * 100 if len(hist) > 20 else 0
            
            s50 = f"${sma50:.2f}" if len(hist) >= 50 else "N/A"
            s200 = f"${sma200:.2f}" if len(hist) >= 200 else "N/A"
            
            name = {'QQQ':'QQQ','SPY':'SPY','IWM':'IWM','^VIX':'VIX'}[ticker]
            print(f"[{name}] Price=${close:.2f} | RSI={rsi:.1f} | ATR={atr:.2f}")
            print(f"  20MA=${sma20:.2f} | 50MA={s50} | 200MA={s200}")
            print(f"  20d Hi={high_20d:.2f} | 20d Lo={low_20d:.2f} | 20d Mom={mom20:+.1f}%")
            above = []
            if len(hist) >= 200 and close > sma200: above.append(">200MA")
            if len(hist) >= 50 and close > sma50: above.append(">50MA")
            if close > sma20: above.append(">20MA")
            print(f"  Trend: {', '.join(above) if above else 'BELOW ALL MAs'}")
            print()
    except Exception as e:
        print(f"[{ticker}] ERROR: {e}\n")

print("=" * 60)

# Components
tickers = ['NVDA', 'AAPL', 'MSFT', 'AVGO', 'META', 'AMZN', 'GOOGL', 'AMD', 'TSLA', 'COST', 'NFLX', 'ORLY', 'PANW', 'HON', 'INTU', 'ADP']

for ticker in tickers:
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period='3mo', interval='1d', timeout=15)
        if len(hist) > 0:
            last = hist.iloc[-1]
            close = last['Close']
            high_20d = hist['High'].tail(20).max()
            low_20d = hist['Low'].tail(20).min()
            sma20 = hist['Close'].tail(20).mean()
            sma50 = hist['Close'].tail(50).mean() if len(hist) >= 50 else close
            sma200 = hist['Close'].tail(200).mean() if len(hist) >= 200 else close
            
            delta = hist['Close'].diff()
            gain = delta.clip(lower=0).ewm(span=14, adjust=False).mean()
            loss = (-delta.clip(upper=0)).ewm(span=14, adjust=False).mean()
            rs = gain / loss
            rsi = (100 - (100 / (1 + rs))).iloc[-1]
            
            high_low = hist['High'] - hist['Low']
            high_close = (hist['High'] - hist['Close'].shift()).abs()
            low_close = (hist['Low'] - hist['Close'].shift()).abs()
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr = tr.tail(14).mean()
            
            vol20 = hist['Volume'].tail(20).mean()
            mom10 = (close - hist['Close'].iloc[-11]) / hist['Close'].iloc[-11] * 100 if len(hist) > 10 else 0
            mom20 = (close - hist['Close'].iloc[-21]) / hist['Close'].iloc[-21] * 100 if len(hist) > 20 else 0
            
            # Score
            score = 0
            if close > sma20: score += 1
            if close > sma50: score += 1
            if sma20 > sma50: score += 1
            if 30 < rsi < 70: score += 1
            if mom20 > 0: score += 1
            if mom10 > mom20: score += 1
            
            s200 = f"${sma200:.2f}" if len(hist) >= 200 else "N/A"
            s50 = f"${sma50:.2f}" if len(hist) >= 50 else "N/A"
            
            print(f"[{ticker}] S={score}/6 | ${close:.2f} | RSI={rsi:.1f} | ATR=${atr:.2f}")
            print(f"  20MA=${sma20:.2f} | 50MA={s50} | 200MA={s200}")
            print(f"  10dMom={mom10:+.1f}% | 20dMom={mom20:+.1f}% | Vol={vol20:,.0f}")
            print(f"  20dRange: ${low_20d:.2f}--${high_20d:.2f}")
            print()
        else:
            print(f"[{ticker}] -- No data\n")
    except Exception as e:
        print(f"[{ticker}] -- ERROR: {e}\n")

print("=== DONE ===")
