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

candidates = ["NVDA", "AMZN", "GOOGL", "ADBE", "CRM", "AVGO", "NFLX", "PYPL", "INTC", "META"]

for sym in candidates:
    try:
        d = fetch_yf(sym)
        res = d["chart"]["result"][0]
        meta = res["meta"]
        closes_all = res["indicators"]["quote"][0]["close"]
        highs_all = res["indicators"]["quote"][0]["high"]
        lows_all = res["indicators"]["quote"][0]["low"]
        volumes_all = res["indicators"]["quote"][0]["volume"]
        
        c = meta.get('regularMarketPrice')
        h52 = meta.get('fiftyTwoWeekHigh')
        l52 = meta.get('fiftyTwoWeekLow')
        vol = meta.get('regularMarketVolume', 0)
        
        closes = [x for x in closes_all if x is not None]
        highs = [x for x in highs_all if x is not None]
        lows = [x for x in lows_all if x is not None]
        volumes = [x for x in volumes_all if x is not None]
        
        sma20 = sma(closes_all, 20)
        sma50 = sma(closes_all, 50)
        sma200 = sma(closes_all, 200)
        
        n = len(closes)
        rsi14 = rsi_calc(closes_all)
        atr14 = atr_calc(highs_all, lows_all, closes_all)
        macd_line, signal_line, histogram = macd_signal(closes_all)
        
        last10_closes = closes[-10:] if len(closes) >= 10 else closes
        recent_high = max(last10_closes)
        recent_low = min(last10_closes)
        
        dist_from_52w_high = ((c - h52) / h52 * 100) if h52 else 0
        
        avg_vol_20 = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else 0
        recent_vol_ratio = vol / avg_vol_20 if avg_vol_20 else 0
        
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
        
        rsi_str = f"{rsi14:.1f}" if rsi14 else "N/A"
        atr_str = f"${atr14:.2f}" if atr14 else "N/A"
        sma20_str = f"${sma20:.2f}" if sma20 else "N/A"
        sma50_str = f"${sma50:.2f}" if sma50 else "N/A"
        sma200_str = f"${sma200:.2f}" if sma200 else "N/A"
        macd_str = f"{macd_line:.3f}" if macd_line else "N/A"
        sig_str = f"{signal_line:.3f}" if signal_line else "N/A"
        hist_str = f"{histogram:.3f}" if histogram else "N/A"
        
        print(f"\n{'='*50}")
        print(f"=== {sym} ===")
        print(f"Price: ${c} | 52w H: ${h52} | 52w L: ${l52}")
        print(f"Distance from 52w High: {dist_from_52w_high:.1f}%")
        print(f"Recent Vol (M): {vol/1e6:.1f}M | 20d Avg: {avg_vol_20/1e6:.1f}M | Ratio: {recent_vol_ratio:.2f}x")
        print(f"SMA20: {sma20_str} | SMA50: {sma50_str} | SMA200: {sma200_str}")
        print(f"RSI(14): {rsi_str}")
        print(f"ATR(14): {atr_str}")
        print(f"MACD: {macd_str} | Signal: {sig_str} | Histogram: {hist_str}")
        print(f"Recent 10d Range: ${recent_low:.2f} - ${recent_high:.2f}")
        last5 = [round(x, 2) for x in closes[-5:]]
        print(f"Last 5 closes: {last5}")
        last5_vols = [round(v/1e6, 1) for v in volumes[-5:]]
        print(f"Last 5 Vols (M): {last5_vols}")
        print(f"Above 20SMA: {above_20} | Above 50SMA: {above_50} | Above 200SMA: {above_200}")
        print(f"Setup Type: {setup_type}")
        
    except Exception as e:
        print(f"Error fetching {sym}: {e}")

print("\n\n=== QQQ 4H CONTEXT ===")
try:
    d = fetch_yf("QQQ", interval="1h", range_="5d")
    res = d["chart"]["result"][0]
    closes_h = res["indicators"]["quote"][0]["close"]
    highs_h = res["indicators"]["quote"][0]["high"]
    lows_h = res["indicators"]["quote"][0]["low"]
    closes_hv = [x for x in closes_h if x is not None]
    last5h = [round(x, 2) for x in closes_hv[-5:]]
    print(f"Last 5 hourly closes: {last5h}")
    atr4h = atr_calc(highs_h, lows_h, closes_h, 14)
    print(f"4H ATR(14): ${atr4h:.2f}" if atr4h else "4H ATR: N/A")
except Exception as e:
    print(f"Error: {e}")

# VIX context
print("\n\n=== VIX / VOLATILITY CONTEXT ===")
try:
    d = fetch_yf("^VIX")
    meta = d["chart"]["result"][0]["meta"]
    closes_vix = [x for x in d["chart"]["result"][0]["indicators"]["quote"][0]["close"] if x is not None]
    rsi_v = rsi_calc(d["chart"]["result"][0]["indicators"]["quote"][0]["close"])
    print(f"VIX: ${meta.get('regularMarketPrice')}")
    print(f"VIX 52w Range: ${meta.get('fiftyTwoWeekLow')} - ${meta.get('fiftyTwoWeekHigh')}")
    print(f"VIX RSI(14): {rsi_v:.1f}" if rsi_v else "N/A")
    print(f"VIX Last 5: {[round(x,2) for x in closes_vix[-5:]]}")
except Exception as e:
    print(f"VIX Error: {e}")

# TNX (10yr yield)
print("\n\n=== 10Y YIELD CONTEXT ===")
try:
    d = fetch_yf("^TNX")
    meta = d["chart"]["result"][0]["meta"]
    closes_tnx = [x for x in d["chart"]["result"][0]["indicators"]["quote"][0]["close"] if x is not None]
    print(f"10Y Yield: {meta.get('regularMarketPrice')}%")
    print(f"Last 5: {[round(x,2) for x in closes_tnx[-5:]]}")
except Exception as e:
    print(f"TNX Error: {e}")
