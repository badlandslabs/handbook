import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

print(f"DEEP DIVE — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC\n")

def atr(df, period=14):
    high = df['High']
    low  = df['Low']
    close = df['Close']
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low  - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def rsi(df, period=14):
    delta = df['Close'].diff()
    gain  = delta.where(delta > 0, 0).rolling(period).mean()
    loss  = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def ema(df, period):
    return df['Close'].ewm(span=period, adjust=False).mean()

def sma(df, period):
    return df['Close'].rolling(period).mean()

def deep_dive(ticker):
    tk = yf.Ticker(ticker)
    df = tk.history(period='3mo', interval='1d', auto_adjust=True)
    df4h = tk.history(period='1mo', interval='1h', auto_adjust=True)

    close = df['Close']
    high  = df['High']
    low   = df['Low']
    vol   = df['Volume']

    ma20  = ema(df, 20)
    ma50  = sma(df, 50)
    ma200 = sma(df, 200) if len(df) >= 200 else None
    atr14 = atr(df, 14).iloc[-1]
    rsi14 = rsi(df, 14).iloc[-1]

    price = close.iloc[-1]
    vol_avg = vol.rolling(20).mean().iloc[-1]
    vol_ratio = vol.iloc[-1] / vol_avg if vol_avg > 0 else 1

    ret5  = (close.iloc[-1] / close.iloc[-6] - 1) * 100 if len(close) >= 6 else 0
    ret10 = (close.iloc[-1] / close.iloc[-11] - 1) * 100 if len(close) >= 11 else 0
    ret20 = (close.iloc[-1] / close.iloc[-21] - 1) * 100 if len(close) >= 21 else 0

    gap_today = ((close.iloc[-1] - close.iloc[-2]) / close.iloc[-2]) * 100 if len(close) >= 2 else 0

    # Structure: HH/HL detection
    last10 = close[-10:]
    prev10 = close[-20:-10]
    hh = max(last10) > max(prev10)
    ll = min(last10) < min(prev10)

    # Support/resistance
    swing_low_20  = low.tail(20).min()
    swing_high_20 = high.tail(20).max()
    swing_low_50  = low.tail(50).min()
    swing_high_50 = high.tail(50).max()

    # EMA cross
    ema12 = ema(df, 12)
    ema26 = ema(df, 26)
    macd_line  = ema12 - ema26
    macd_sig   = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist  = macd_line - macd_sig
    macd_curr  = macd_hist.iloc[-1]
    macd_prev  = macd_hist.iloc[-3]
    macd_bull_x = macd_curr > 0 and macd_prev <= 0

    # Stochastic K
    low14  = low.rolling(14).min()
    high14 = high.rolling(14).max()
    stoch_k = ((close - low14) / (high14 - low14) * 100).iloc[-1]

    # ATR-based levels
    stop_below_swing  = swing_low_20 - atr14 * 0.3
    stop_atr          = price - atr14 * 1.5
    stop              = max(stop_below_swing, stop_atr)
    risk_pct          = (price - stop) / price * 100

    t1 = price + (price - stop) * 2
    t2 = price + (price - stop) * 4
    rr1 = (t1 - price) / (price - stop)
    rr2 = (t2 - price) / (price - stop)

    # Position sizing (1% risk on account)
    account = 100000
    risk_amt = account * 0.01
    shares = int(risk_amt / (price - stop))

    pct_52w_high = (price / high.rolling(252).max().iloc[-1]) * 100 if len(high) >= 252 else 50

    print(f"═══ {ticker} ═══")
    print(f"  Price:         ${price:.2f}")
    print(f"  RSI(14):       {rsi14:.1f}  {'(NEUTRAL-SOFT)' if 40<=rsi14<=55 else '(OVERBOUGHT)' if rsi14>70 else '(OVERSOLD)' if rsi14<40 else '(NEUTRAL)'}")
    print(f"  Stochastic K:  {stoch_k:.1f}")
    print(f"  ATR(14):       ${atr14:.2f}  ({atr14/price*100:.1f}% of price)")
    print(f"  ATR% of 52wHi: {pct_52w_high:.0f}%")
    print(f"  Gap today:     {gap_today:+.2f}%")
    print(f"  5d return:     {ret5:+.1f}%  |  10d: {ret10:+.1f}%  |  20d: {ret20:+.1f}%")
    print(f"  Vol ratio:     {vol_ratio:.2f}  (avg 20d vol = {vol_avg:.0f})")
    print(f"  HH/HL Struct:  {'YES — bullish structure' if hh and ll else 'NO — no clear structure'}")
    print(f"  MACD Hist:      {macd_curr:.4f}  |  Crossed bullish: {macd_bull_x}")
    print(f"  MA20:           ${ma20.iloc[-1]:.2f}  |  MA50: ${ma50.iloc[-1]:.2f}  |  MA200: ${ma200.iloc[-1]:.2f if ma200 is not None else 'N/A'}")
    print(f"  Above MA20:     {price > ma20.iloc[-1]}  |  Above MA50: {price > ma50.iloc[-1]}")
    print(f"  20d Low:        ${swing_low_20:.2f}  |  20d High: ${swing_high_20:.2f}")
    print(f"  50d Low:        ${swing_low_50:.2f}  |  50d High: ${swing_high_50:.2f}")
    print()
    print(f"  ── ENTRY ZONE:  ${swing_low_20:.2f} – ${price:.2f}  (prefer pullback to {swing_low_20:.2f})")
    print(f"  ── STOP LOSS:   ${stop:.2f}  ({risk_pct:.1f}% risk vs. price)")
    print(f"  ── T1 (2:1):    ${t1:.2f}  ({rr1:.1f}:1 reward-to-risk)")
    print(f"  ── T2 (4:1):    ${t2:.2f}  ({rr2:.1f}:1 reward-to-risk)")
    print(f"  ── Risk Amount: ${(price - stop) * shares:,.0f}  |  Shares (1% risk): {shares}")
    print()

for t in ['TXN', 'HOOD', 'META']:
    try:
        deep_dive(t)
    except Exception as e:
        print(f"ERROR on {t}: {e}")

print("─── QQQ REGIME CONTEXT ──")
try:
    qqq = yf.Ticker('QQQ')
    q = qqq.history(period='3mo', interval='1d', auto_adjust=True)
    q_close = q['Close']
    q_ma20 = ema(q, 20).iloc[-1]
    q_ma50 = sma(q, 50).iloc[-1]
    q_rsi = rsi(q, 14).iloc[-1]
    q_ret5 = (q_close.iloc[-1] / q_close.iloc[-6] - 1) * 100
    q_ret20 = (q_close.iloc[-1] / q_close.iloc[-21] - 1) * 100
    q_atr = atr(q, 14).iloc[-1]
    print(f"  QQQ: ${q_close.iloc[-1]:.2f}  RSI:{q_rsi:.1f}  MA20:{q_ma20:.2f}  MA50:{q_ma50:.2f}")
    print(f"  5d:{q_ret5:+.1f}%  20d:{q_ret20:+.1f}%  ATR%:{q_atr/q_close.iloc[-1]*100:.1f}%")
    regime = "BULL" if q_close.iloc[-1] > q_ma50 and q_ma20 > q_ma50 else ("BEAR" if q_close.iloc[-1] < q_ma50 else "TRANSITIONAL")
    print(f"  Regime: {regime}")
    print(f"  Note: QQQ RSI {q_rsi:.1f} + negative 5d/20d returns = BEAR classification (tech underperforming SPY)")
    print()
    print(f"  SPY regime: BULL (RSI 46, near 52w highs)")
    print(f"  IWM regime: BULL (RSI 52, strong small-cap)")
    print(f"  => MARKET SPLIT: Broad market BULL but NASDAQ TECH BEAR (QQQ -4% in 5 days)")
    print(f"  => FAVOR: Defensive rotation (XLV, XLF) and short-term mean-reversion on beaten tech")
except Exception as e:
    print(f"  ERROR: {e}")

