#!/opt/data/handbook/venv/bin/python3
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

today = datetime.now().strftime('%Y-%m-%d')
start = (datetime.now() - timedelta(days=200)).strftime('%Y-%m-%d')

candidates = ['AAPL', 'NVDA', 'MSFT', 'AMD', 'META', 'AVGO', 'INTU']

for ticker in candidates:
    print(f"\n{'='*60}")
    print(f"{ticker}")
    print(f"{'='*60}")
    try:
        data = yf.download(ticker, start=start, end=today, progress=False, auto_adjust=True)
        close = data['Close'].squeeze()
        high = data['High'].squeeze()
        low = data['Low'].squeeze()
        vol = data['Volume'].squeeze()
        
        ma20 = close.rolling(20).mean()
        ma50 = close.rolling(50).mean()
        ma10 = close.rolling(10).mean()
        
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
        bb_pct = ((close - bb_lower) / (bb_upper - bb_lower)) * 100
        
        swing_h = high.rolling(20).max().shift(1)
        swing_l = low.rolling(20).min().shift(1)
        vol_sma = vol.rolling(20).mean()
        vol_ratio = vol / vol_sma
        
        def fv(x):
            v = float(x)
            return v if pd.notna(v) else 0.0
        
        c = fv(close.iloc[-1])
        c5 = fv(close.iloc[-5])
        c10 = fv(close.iloc[-10])
        c20 = fv(close.iloc[-20])
        rsi_v = fv(rsi.iloc[-1])
        macd_h = fv(macd_hist.iloc[-1])
        macd_v = fv(macd.iloc[-1])
        sig_v = fv(signal.iloc[-1])
        atr_v = fv(atr14.iloc[-1])
        bbu_v = fv(bb_upper.iloc[-1])
        bbl_v = fv(bb_lower.iloc[-1])
        bbp_v = fv(bb_pct.iloc[-1])
        sh_v = fv(swing_h.iloc[-1])
        sl_v = fv(swing_l.iloc[-1])
        m20_v = fv(ma20.iloc[-1])
        m50_v = fv(ma50.iloc[-1])
        m10_v = fv(ma10.iloc[-1])
        vr_v = fv(vol_ratio.iloc[-1])
        
        print(f"Price: ${c:.2f} | 5d: {((c-c5)/c5)*100:+.1f}% | 10d: {((c-c10)/c10)*100:+.1f}% | 20d: {((c-c20)/c20)*100:+.1f}%")
        print(f"MA10: ${m10_v:.2f} | MA20: ${m20_v:.2f} | MA50: ${m50_v:.2f}")
        print(f"RSI: {rsi_v:.1f} | MACD Hist: {macd_h:.4f} | MACD: {macd_v:.4f} | Signal: {sig_v:.4f}")
        print(f"ATR14: ${atr_v:.2f} ({atr_v/c*100:.2f}%)")
        print(f"BB Upper: ${bbu_v:.2f} | BB Lower: ${bbl_v:.2f} | BB%: {bbp_v:.0f}")
        print(f"Swing High: ${sh_v:.2f} ({((sh_v-c)/c)*100:.1f}% above) | Swing Low: ${sl_v:.2f} ({((c-sl_v)/c)*100:.1f}% below)")
        print(f"Vol Ratio: {vr_v:.2f}x")
        print(f"Last 5 closes: {[f'${fv(x):.2f}' for x in close.iloc[-5:].values]}")
        print(f"Last 5 highs: {[f'${fv(x):.2f}' for x in high.iloc[-5:].values]}")
        print(f"Last 5 lows: {[f'${fv(x):.2f}' for x in low.iloc[-5:].values]}")
        
    except Exception as e:
        import traceback
        print(f"ERROR: {e}")
        traceback.print_exc()
