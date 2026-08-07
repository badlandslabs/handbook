import yfinance as yf
import warnings
import json
warnings.filterwarnings('ignore')

# Fetch key indices
tickers = ['QQQ', 'SPY', 'IWM']
index_data = {}
for t in tickers:
    try:
        tk = yf.Ticker(t)
        hist = tk.history(period='6mo', interval='1d')
        if len(hist) > 0:
            cur = hist['Close'].iloc[-1]
            prev = hist['Close'].iloc[-2] if len(hist) > 1 else cur
            chg = ((cur - prev) / prev) * 100
            sma20 = hist['Close'].rolling(20).mean().iloc[-1]
            sma50 = hist['Close'].rolling(50).mean().iloc[-1]
            sma200 = hist['Close'].rolling(200).mean().iloc[-1] if len(hist) >= 200 else None
            high52 = hist['High'].max()
            low52 = hist['Low'].min()
            vol20 = hist['Volume'].iloc[-20:].mean()
            index_data[t] = {
                'price': cur, 'chg': chg, 'sma20': sma20, 'sma50': sma50, 'sma200': sma200,
                'high52': high52, 'low52': low52, 'vol20': vol20
            }
    except Exception as e:
        index_data[t] = {'error': str(e)}

# Top NASDAQ 100 components
nasdaq100 = ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'TSLA', 'AVGO', 'ORCL', 'AMD',
             'ADBE', 'CRM', 'NFLX', 'QCOM', 'TXN', 'INTC', 'AMAT', 'LRCX', 'MU', 'PANW']

results = []
for t in nasdaq100:
    try:
        tk = yf.Ticker(t)
        hist = tk.history(period='6mo', interval='1d')
        if len(hist) > 5:
            cur = hist['Close'].iloc[-1]
            prev = hist['Close'].iloc[-2] if len(hist) > 1 else cur
            chg = ((cur - prev) / prev) * 100
            sma20 = hist['Close'].rolling(20).mean().iloc[-1]
            sma50 = hist['Close'].rolling(50).mean().iloc[-1]
            high52 = hist['High'].max()
            low52 = hist['Low'].min()
            vol20 = hist['Volume'].iloc[-20:].mean()
            # ATR
            tr = []
            for i in range(1, min(15, len(hist))):
                hi = hist['High'].iloc[-i]
                lo = hist['Low'].iloc[-i]
                pc = hist['Close'].iloc[-i-1] if i < len(hist)-1 else hist['Close'].iloc[-i]
                tr.append(max(hi-lo, abs(hi-pc), abs(lo-pc)))
            atr = sum(tr)/len(tr) if tr else 0
            # RSI(14)
            deltas = hist['Close'].diff()
            gain = deltas.where(deltas > 0, 0).rolling(14).mean().iloc[-1]
            loss = (-deltas.where(deltas < 0, 0)).rolling(14).mean().iloc[-1]
            rs = gain/loss if loss != 0 else 100
            rsi = 100 - (100/(1+rs))
            
            above_sma20 = cur > sma20
            above_sma50 = cur > sma50
            near_52w_high = cur >= 0.97 * high52
            pct_from_52w_high = (cur / high52 - 1) * 100
            pct_from_52w_low = (cur / low52 - 1) * 100
            pct_from_sma20 = (cur / sma20 - 1) * 100

            # MACD
            ema12 = hist['Close'].ewm(span=12).mean().iloc[-1]
            ema26 = hist['Close'].ewm(span=26).mean().iloc[-1]
            macd_line = ema12 - ema26
            macd_signal = hist['Close'].ewm(span=9).mean().iloc[-1] - hist['Close'].ewm(span=9).mean().iloc[-1]  # approximate
            macd_hist = macd_line - (ema12 - ema26)  # simplified

            results.append({
                'ticker': t, 'price': cur, 'chg': chg, 'sma20': sma20, 'sma50': sma50,
                'high52': high52, 'low52': low52, 'vol20': vol20, 'atr': atr,
                'rsi': rsi, 'above_sma20': above_sma20, 'above_sma50': above_sma50,
                'near_52w_high': near_52w_high,
                'pct_from_52w_high': pct_from_52w_high, 'pct_from_52w_low': pct_from_52w_low,
                'pct_from_sma20': pct_from_sma20, 'macd_line': macd_line
            })
    except Exception as e:
        pass

# Score setups
scored = []
for r in results:
    score = 0
    if r['above_sma20']: score += 1
    if r['above_sma50']: score += 1
    if r['near_52w_high']: score += 2
    if 40 <= r['rsi'] <= 68: score += 2
    if r['rsi'] < 35: score += 3
    if r['chg'] > 0: score += 1
    if r['pct_from_sma20'] > 0: score += 1
    scored.append((r['ticker'], score, r))
    
scored.sort(key=lambda x: x[1], reverse=True)

# Write JSON output
output = {
    'timestamp': str(__import__('datetime').datetime.now()),
    'indices': index_data,
    'rankings': [{'ticker': t, 'score': s, 'details': r} for t, s, r in scored],
    'top3': []
}

for ticker, score, r in scored[:3]:
    stop_distance = r['atr'] * 1.5
    stop_price = r['price'] - stop_distance
    target1 = r['price'] + stop_distance * 2
    target2 = r['price'] + stop_distance * 3
    position_size = 1000 / stop_distance  # $1K risk on $100K acct
    output['top3'].append({
        'ticker': ticker, 'score': score,
        'entry': r['price'], 'stop': stop_price, 't1': target1, 't2': target2,
        'atr': r['atr'], 'atr_pct': r['atr']/r['price']*100,
        'rsi': r['rsi'], 'sma20': r['sma20'], 'sma50': r['sma50'],
        'high52': r['high52'], 'low52': r['low52'],
        'pct_from_52w_high': r['pct_from_52w_high'],
        'position_size_shares': position_size,
        'above_sma20': r['above_sma20'], 'above_sma50': r['above_sma50'],
        'chg': r['chg'], 'vol20': r['vol20']
    })

with open('/opt/data/handbook/scan_results.json', 'w') as f:
    json.dump(output, f, indent=2, default=str)

print("DONE")
for t, s, r in scored[:10]:
    print(f"  {t}: score={s} | RSI={r['rsi']:.1f} | ${r['price']:.2f} | 52w_high={r['pct_from_52w_high']:+.1f}%")
