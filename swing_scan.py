import yfinance as yf
import pandas as pd
import json
from datetime import datetime, timedelta

now = datetime.now()
print(f"Data fetch time: {now.strftime('%Y-%m-%d %H:%M:%S')}")

tickers = {
    'QQQ': 'Nasdaq 100 ETF',
    'SPY': 'S&P 500 ETF',
    'IWM': 'Russell 2000 ETF',
    'AAPL': 'Apple',
    'MSFT': 'Microsoft',
    'NVDA': 'Nvidia',
    'GOOGL': 'Alphabet',
    'AMZN': 'Amazon',
    'META': 'Meta',
    'TSLA': 'Tesla',
    'AMD': 'AMD',
    'AVGO': 'Broadcom',
    'CRM': 'Salesforce',
    'ADBE': 'Adobe',
    'NFLX': 'Netflix',
    'QCOM': 'Qualcomm',
    'TXN': 'Texas Instruments',
    'AMAT': 'Applied Materials',
    'MU': 'Micron Technology',
}

results = {}
for sym, name in tickers.items():
    try:
        t = yf.Ticker(sym)
        hist = t.history(period='3mo', interval='1d')
        info = t.info
        if hist.empty:
            results[sym] = {'error': 'No data', 'name': name}
            continue
        
        close = hist['Close']
        high = hist['High']
        low = hist['Low']
        vol = hist['Volume']
        
        sma20 = close.rolling(20).mean()
        sma50 = close.rolling(50).mean()
        sma200 = close.rolling(200).mean()
        ema20 = close.ewm(span=20).mean()
        
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        tr1 = high - low
        tr2 = (high - close.shift(1).abs())
        tr3 = (low - close.shift(1).abs())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(14).mean()
        
        macd_fast = close.ewm(span=12).mean()
        macd_slow = close.ewm(span=26).mean()
        macd_line = macd_fast - macd_slow
        signal = macd_line.ewm(span=9).mean()
        macd_hist = macd_line - signal
        
        last_close = float(close.iloc[-1])
        prev_close = float(close.iloc[-2])
        pct_chg = (last_close - prev_close) / prev_close * 100
        
        high52 = float(high.max())
        low52 = float(low.min())
        
        # Recent price action - last 5 days
        last5_pct = (float(close.iloc[-1]) - float(close.iloc[-6])) / float(close.iloc[-6]) * 100 if len(close) >= 6 else 0
        
        results[sym] = {
            'name': name,
            'last_close': round(last_close, 2),
            'pct_chg_today': round(pct_chg, 2),
            'last5_pct': round(last5_pct, 2),
            'sma20': round(float(sma20.iloc[-1]), 2) if not sma20.isna().iloc[-1] else None,
            'sma50': round(float(sma50.iloc[-1]), 2) if not sma50.isna().iloc[-1] else None,
            'sma200': round(float(sma200.iloc[-1]), 2) if not sma200.isna().iloc[-1] else None,
            'ema20': round(float(ema20.iloc[-1]), 2) if not ema20.isna().iloc[-1] else None,
            'rsi_14': round(float(rsi.iloc[-1]), 1) if not rsi.isna().iloc[-1] else None,
            'atr_14': round(float(atr.iloc[-1]), 2) if not atr.isna().iloc[-1] else None,
            'macd_histogram': round(float(macd_hist.iloc[-1]), 3) if not macd_hist.isna().iloc[-1] else None,
            'macd_histogram_prev': round(float(macd_hist.iloc[-2]), 3) if len(macd_hist) > 2 and not macd_hist.isna().iloc[-2] else None,
            'volume_20_avg': round(float(vol.rolling(20).mean().iloc[-1]), 0),
            'volume_today': int(vol.iloc[-1]),
            'high_52wk': round(high52, 2),
            'low_52wk': round(low52, 2),
            'price_vs_sma20': round((last_close / float(sma20.iloc[-1]) - 1) * 100, 1) if not sma20.isna().iloc[-1] else None,
            'price_vs_sma50': round((last_close / float(sma50.iloc[-1]) - 1) * 100, 1) if not sma50.isna().iloc[-1] else None,
            'price_vs_sma200': round((last_close / float(sma200.iloc[-1]) - 1) * 100, 1) if not sma200.isna().iloc[-1] else None,
            'above_sma200': last_close > float(sma200.iloc[-1]) if not sma200.isna().iloc[-1] else None,
            'sector': info.get('sector', 'N/A'),
            'market_cap': info.get('marketCap', 'N/A'),
            'pe_ratio': round(info.get('trailingPE', 0), 1) if info.get('trailingPE') else None,
            'fifty_two_wk_change': round(info.get('52WeekChange', 0) * 100, 1) if isinstance(info.get('52WeekChange'), (int, float)) else None,
        }
        
    except Exception as e:
        results[sym] = {'error': str(e), 'name': name}

print(json.dumps(results, indent=2))
