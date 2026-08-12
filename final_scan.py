import yfinance as yf
import warnings
warnings.filterwarnings('ignore')

def compute_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def compute_atr(df, period=14):
    high = df['High']
    low = df['Low']
    close = df['Close']
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = tr1.combine(tr2, max).combine(tr3, max)
    return tr.rolling(window=period).mean()

def full_analysis(ticker):
    t = yf.Ticker(ticker)
    d = t.history(period='6mo')
    intraday = t.history(period='5d', interval='30m')

    last = d['Close'].iloc[-1]
    atr14 = compute_atr(d, 14).iloc[-1]
    rsi14 = compute_rsi(d['Close'], 14).iloc[-1]

    # Nearest resistance levels (rolling max of last 60 days)
    resist = sorted(d['High'].tail(60).nlargest(5).values)
    support = sorted(d['Low'].tail(60).nsmallest(5).values)

    # Recent pullback: % from 20d high
    h20 = d['High'].tail(20).max()
    l20 = d['Low'].tail(20).min()
    chg_from_high = (last - h20) / h20 * 100

    # 20d volatility compression (ATR % of price trending)
    atr_trend = compute_atr(d, 14).tail(10).mean()
    atr_trend_pct = atr_trend / last * 100

    # 20-day range width as % of price
    range_pct = (h20 - l20) / last * 100

    # Volume profile: avg vol on up days vs down days
    up_days = d[d['Close'].diff() > 0]
    dn_days = d[d['Close'].diff() < 0]
    up_vol = up_days['Volume'].mean() if len(up_days) > 0 else 0
    dn_vol = dn_days['Volume'].mean() if len(dn_days) > 0 else 0
    vol_breadth = up_vol / dn_vol if dn_vol > 0 else 0

    # RSI divergence check (current RSI vs 5 days ago)
    rsi5d_ago = compute_rsi(d['Close'], 14).iloc[-6]
    rsi_trend = rsi14 - rsi5d_ago

    # MACD crossover check
    ema12 = d['Close'].ewm(span=12, adjust=False).mean()
    ema26 = d['Close'].ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    macd_signal = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = macd_line - macd_signal
    macd_cross_ago = (macd_line.iloc[-3] < macd_signal.iloc[-3]) and (macd_line.iloc[-1] > macd_signal.iloc[-1])

    # Intraday structure (last 5 days, 30-min close proximity to 20EMA)
    d20ema = d['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
    intra_last = intraday['Close'].iloc[-1] if len(intraday) > 0 else last

    # Support/Resistance proximity
    near_resist = min([r for r in resist if r >= last], default=max(resist))
    near_support = max([s for s in support if s <= last], default=min(support))
    dist_to_resist = (near_resist - last) / last * 100
    dist_to_support = (last - near_support) / last * 100

    # 4H EMA cross analysis
    h4 = t.history(period='5d', interval='1h')
    h4_ema8 = h4['Close'].ewm(span=8, adjust=False).mean().iloc[-1]
    h4_ema20 = h4['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
    h4_ema50 = h4['Close'].ewm(span=50, adjust=False).mean().iloc[-1]

    print(f"\n{'='*65}")
    print(f"  {ticker} | ${last:.2f} | RSI={rsi14:.1f} | ATR=${atr14:.2f}")
    print(f"{'='*65}")
    print(f"  [STRUCTURE]")
    print(f"  Near Resistance:  ${near_resist:.2f} ({dist_to_resist:+.1f}% above price)")
    print(f"  Near Support:    ${near_support:.2f} ({dist_to_support:+.1f}% below price)")
    print(f"  20d High:        ${h20:.2f} | 20d Low: ${l20:.2f} | Range: {range_pct:.1f}%")
    print(f"  Pullback from 20d High: {chg_from_high:.1f}%")
    print(f"  ATR volatility:  {atr_trend_pct:.1f}% ({'CONTRACTION' if atr_trend_pct < 4 else 'EXPANDING'})")
    print(f"  Volume Breadth:  {vol_breadth:.2f}x (up-day vol / down-day vol)")
    print(f"  200SMA:          ${d['Close'].ewm(span=200, adjust=False).mean().iloc[-1] if len(d)>=200 else 'N/A'}")
    print(f"  [MOMENTUM]")
    print(f"  RSI(14):         {rsi14:.1f} | 5d delta: {rsi_trend:+.1f} ({'Rising' if rsi_trend>0 else 'Falling'})")
    print(f"  MACD Histogram:  {macd_hist.iloc[-1]:.3f} | 5d ago: {macd_hist.iloc[-6]:.3f}")
    print(f"  MACD Hist delta: {macd_hist.iloc[-1]-macd_hist.iloc[-6]:+.3f} ({'Expanding' if abs(macd_hist.iloc[-1])>abs(macd_hist.iloc[-6]) else 'Contracting'})")
    print(f"  MACD Cross Rec:  {'YES (BUY SIGNAL)' if macd_cross_ago else 'No recent cross'}")
    print(f"  [4H INTRADAY]")
    print(f"  4H Price:        ${h4['Close'].iloc[-1]:.2f}")
    print(f"  4H 8EMA:         ${h4_ema8:.2f} | {('ABOVE' if h4['Close'].iloc[-1]>h4_ema8 else 'BELOW')} | Delta: {abs((h4['Close'].iloc[-1]-h4_ema8)/h4_ema8*100):.2f}%")
    print(f"  4H 20EMA:        ${h4_ema20:.2f} | {('ABOVE' if h4['Close'].iloc[-1]>h4_ema20 else 'BELOW')} | Delta: {abs((h4['Close'].iloc[-1]-h4_ema20)/h4_ema20*100):.2f}%")
    print(f"  4H 50EMA:        ${h4_ema50:.2f} | {('ABOVE' if h4['Close'].iloc[-1]>h4_ema50 else 'BELOW')}")

    # Key levels summary
    print(f"  [KEY LEVELS]")
    print(f"  R1: ${near_resist:.2f} | S1: ${near_support:.2f}")
    print(f"  Stop zone:     ${near_support - atr14*1.5:.2f}–${near_support - atr14*0.5:.2f}")
    print(f"  Entry range:   ${near_resist - atr14*0.5:.2f}–${near_resist:.2f}")
    print(f"  T1: ${near_resist + atr14*1.5:.2f} ({atr14*1.5/last*100:.1f}%) | T2: ${near_resist + atr14*3:.2f} ({atr14*3/last*100:.1f}%)")
    print(f"  R:R T1: {(near_resist - (near_support - atr14*1.5)) / (near_resist - (near_support - atr14*1.5) - (near_support - atr14*1.5 - (near_resist - atr14*1.5))) if False else (atr14*1.5) / (atr14*1.5):.1f}x")

    return {
        'ticker': ticker, 'price': last, 'atr': atr14, 'rsi': rsi14,
        'near_r': near_resist, 'near_s': near_support,
        'dist_resist': dist_to_resist, 'dist_support': dist_to_support,
        'chg_from_h20': chg_from_high, 'range_pct': range_pct,
        'vol_breadth': vol_breadth, 'macd_hist': macd_hist.iloc[-1],
        'macd_cross': macd_cross_ago, 'h4_ema8': h4_ema8, 'h4_ema20': h4_ema20,
        'atr_pct': atr_trend_pct, 'h4_price': h4['Close'].iloc[-1]
    }

candidates = ['PANW', 'ADBE', 'NVDA', 'AMD', 'AMZN']
results = {}
for t in candidates:
    try:
        results[t] = full_analysis(t)
    except Exception as e:
        print(f"  {t}: ERROR {e}")

print("\n\n=== SWING SCORE RANKING ===")
# Score each: 0-3 scale
def score(r):
    s = 0
    # RSI in sweet spot (40-70 for longs): +2
    if 40 <= r['rsi'] <= 70: s += 2
    elif r['rsi'] < 40: s += 1  # oversold = potential
    # Within 5% of resistance: +2
    if r['dist_resist'] <= 5: s += 2
    elif r['dist_resist'] <= 10: s += 1
    # Pullback quality: within 5% of 20d high: +2
    if r['chg_from_h20'] >= -5: s += 2
    elif r['chg_from_h20'] >= -10: s += 1
    # MACD positive: +2
    if r['macd_hist'] > 0: s += 2
    # Volume breadth > 1.1: +1
    if r['vol_breadth'] > 1.1: s += 1
    # 4H above 20EMA: +2
    if r['h4_price'] > r['h4_ema20']: s += 2
    return s

scored = [(t, r, score(r)) for t, r in results.items()]
scored.sort(key=lambda x: x[2], reverse=True)

print(f"{'Rank':<6} {'Ticker':<8} {'Score':>6} {'Price':>8} {'RSI':>5} {'%Resist':>8} {'Chg20dH':>8} {'MACD':>7} {'4H>EMA20':>10}")
for rank, (t, r, s) in enumerate(scored, 1):
    print(f"  {rank:<4} {t:<8} {s:>6} ${r['price']:>7.2f} {r['rsi']:>5.1f} {r['dist_resist']:>+8.1f} {r['chg_from_h20']:>+8.1f} {r['macd_hist']:>7.3f} {str(r['h4_price']>r['h4_ema20']):>10}")
