import json, urllib.request

def fetch_yf(symbol, interval="1d", range_="3mo"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={range_}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

def sma(data, n):
    valid = [x for x in data if x is not None]
    if len(valid) < n: return None
    return sum(valid[-n:]) / n

def rsi_calc(prices, period=14):
    valid = [x for x in prices if x is not None]
    if len(valid) < period + 1: return None
    deltas = [valid[i] - valid[i-1] for i in range(1, len(valid))]
    gains = [d if d > 0 else 0 for d in deltas[-period:]]
    losses = [-d if d < 0 else 0 for d in deltas[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0: return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def atr_calc(highs, lows, closes, period=14):
    valid = [(h, l, c) for h, l, c in zip(highs, lows, closes) if h is not None and l is not None and c is not None]
    if len(valid) < period + 1: return None
    trs = []
    for i in range(1, len(valid)):
        h, l, c_prev = valid[i][0], valid[i][1], valid[i-1][2]
        tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
        trs.append(tr)
    return sum(trs[-period:]) / period

def macd_signal(prices, fast=12, slow=26, signal=9):
    valid = [x for x in prices if x is not None]
    if len(valid) < slow + signal: return None, None, None
    def ema(data, n):
        k = 2/(n+1)
        ema_val = data[0]
        for v in data[1:]:
            ema_val = v * k + ema_val * (1-k)
        return ema_val
    ema_fast = ema(valid, fast)
    ema_slow = ema(valid, slow)
    macd_line = ema_fast - ema_slow
    macd_series = []
    for i in range(slow, len(valid)):
        ef = ema(valid[:i+1], fast)
        es = ema(valid[:i+1], slow)
        macd_series.append(ef - es)
    signal_line = ema(macd_series, signal) if len(macd_series) >= signal else None
    return macd_line, signal_line, macd_line - signal_line if signal_line else None

# Deep dive on top candidates
candidates = ["NVDA", "AMZN", "GOOGL", "ADBE", "CRM", "AVGO", "NFLX", "PYPL", "INTC", "META"]

for sym in candidates:
    try:
        d = fetch_yf(sym)
        res = d["chart"]["result"][0]
        meta = res["meta"]
        closes = res["indicators"]["quote"][0]["close"]
        highs = res["indicators"]["quote"][0]["high"]
        lows = res["indicators"]["quote"][0]["low"]
        volumes = res["indicators"]["quote"][0]["volume"]
        
        c = meta.get('regularMarketPrice')
        h52 = meta.get('fiftyTwoWeekHigh')
        l52 = meta.get('fiftyTwoWeekLow')
        vol = meta.get('regularMarketVolume', 0)
        
        sma20 = sma(closes, 20)
        sma50 = sma(closes, 50)
        sma200 = sma(closes, 200)
        
        n = len(closes)
        rsi14 = rsi_calc(closes)
        atr14 = atr_calc(highs, lows, closes)
        macd_line, signal_line, histogram = macd_signal(closes)
        
        # Recent swing analysis
        last10_closes = [closes[i] for i in range(n-10, n) if closes[i] is not None]
        recent_high = max(last10_closes)
        recent_low = min(last10_closes)
        
        # Distance from 52w high
        dist_from_52w_high = ((c - h52) / h52 * 100) if h52 else 0
        
        # Volume trend
        avg_vol_20 = sum([v for v in volumes[-20:] if v]) / 20 if len([v for v in volumes[-20:] if v]) >= 20 else 0
        recent_vol_ratio = vol / avg_vol_20 if avg_vol_20 else 0
        
        print(f"\n{'='*50}")
        print(f"=== {sym} ===")
        print(f"Price: ${c} | 52w H: ${h52} | 52w L: ${l52}")
        print(f"Distance from 52w High: {dist_from_52w_high:.1f}%")
        print(f"Recent Vol (M): {vol/1e6:.1f}M | 20d Avg Vol: {avg_vol_20/1e6:.1f}M | Ratio: {recent_vol_ratio:.2f}x")
        print(f"SMA20: ${sma20:.2f} | SMA50: ${sma50:.2f} | SMA200: ${sma200:.2f if sma200 else 'N/A'}")
        print(f"RSI(14): {rsi14:.1f}")
        print(f"ATR(14): ${atr14:.2f}")
        macd_h = f"{histogram:.3f}" if histogram else "N/A"
        macd_l = f"{macd_line:.3f}" if macd_line else "N/A"
        sig_l = f"{signal_line:.3f}" if signal_line else "N/A"
        print(f"MACD: {macd_l} | Signal: {sig_l} | Histogram: {macd_h}")
        print(f"Recent 10d Range: ${recent_low:.2f} - ${recent_high:.2f}")
        print(f"Last 5 closes: {[round(closes[i],2) for i in range(n-5,n) if closes[i] is not None]}")
        
        # Volume profile last 5 days
        last5_vols = [v/1e6 for v in volumes[-5:] if v]
        print(f"Last 5 Vols (M): {[round(v,1) for v in last5_vols]}")
        
        # Pullback or breakout classification
        above_20 = c > sma20 if sma20 else False
        above_50 = c > sma50 if sma50 else False
        above_200 = c > sma200 if sma200 else False
        
        if above_50 and above_20:
            setup_type = "BULLISH BREAKOUT"
        elif above_50 and not above_20:
            setup_type = "PULLBACK TO 20SMA"
        elif above_20 and not above_50:
            setup_type = "RECOVERY ATTEMPT"
        else:
            setup_type = "BEARISH / WEAK"
        
        # Distance to key levels
        print(f"Above 20SMA: {above_20} | Above 50SMA: {above_50} | Above 200SMA: {above_200}")
        print(f"Setup Type: {setup_type}")
        
    except Exception as e:
        print(f"Error fetching {sym}: {e}")

# Also fetch 4h data for QQQ to check intraday structure
print("\n\n=== QQQ 4H CHART CONTEXT ===")
try:
    d = fetch_yf("QQQ", interval="1h", range_="5d")
    res = d["chart"]["result"][0]
    closes_h = res["indicators"]["quote"][0]["close"]
    highs_h = res["indicators"]["quote"][0]["high"]
    lows_h = res["indicators"]["quote"][0]["low"]
    print(f"Last 5 hourly closes: {[round(c,2) for c in closes_h[-5:] if c is not None]}")
    print(f"4H ATR: ${atr_calc(highs_h, lows_h, closes_h, 14):.2f}" if atr_calc(highs_h, lows_h, closes_h, 14) else "4H ATR: N/A")
except Exception as e:
    print(f"Error: {e}")
