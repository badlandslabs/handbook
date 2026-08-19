#!/opt/hermes/.venv/bin/python3
import yfinance as yf
import numpy as np

# AAPL
aapl = yf.Ticker("AAPL")
ha = aapl.history(period="3mo", interval="1d")
aapl_close = ha['Close'].iloc[-1]
aapl_rsi = (100 - 100/(1 + ha['Close'].diff().clip(lower=0).rolling(14).mean() / (-ha['Close'].diff().clip(upper=0)).rolling(14).mean())).iloc[-1]
aapl_atr = (ha['High'] - ha['Low']).tail(14).mean()
print(f"AAPL close={aapl_close:.2f} rsi={aapl_rsi:.1f} atr={aapl_atr:.2f}")
print(f"AAPL R:R T2: entry=315.50 stop=305.00 risk=10.50 t2=345.00 reward=29.50 rr={29.50/10.50:.1f}:1")

# AMZN
amzn = yf.Ticker("AMZN")
hm = amzn.history(period="3mo", interval="1d")
amzn_close = hm['Close'].iloc[-1]
amzn_rsi = (100 - 100/(1 + hm['Close'].diff().clip(lower=0).rolling(14).mean() / (-hm['Close'].diff().clip(upper=0)).rolling(14).mean())).iloc[-1]
amzn_atr = (hm['High'] - hm['Low']).tail(14).mean()
print(f"AMZN close={amzn_close:.2f} rsi={amzn_rsi:.1f} atr={amzn_atr:.2f}")
print(f"AMZN R:R T2: entry=258.00 stop=248.00 risk=10.00 t2=282.00 reward=24.00 rr={24.00/10.00:.1f}:1")

# NVDA
nvda = yf.Ticker("NVDA")
hn = nvda.history(period="3mo", interval="1d")
nvda_close = hn['Close'].iloc[-1]
nvda_rsi = (100 - 100/(1 + hn['Close'].diff().clip(lower=0).rolling(14).mean() / (-hn['Close'].diff().clip(upper=0)).rolling(14).mean())).iloc[-1]
nvda_atr = (hn['High'] - hn['Low']).tail(14).mean()
nvda_sma20 = hn['Close'].tail(20).mean()
print(f"NVDA close={nvda_close:.2f} rsi={nvda_rsi:.1f} atr={nvda_atr:.2f} sma20={nvda_sma20:.2f}")
pullback_target = 210.00
nvda_t2_alt = 230.00
nvda_risk_alt = pullback_target - 197.00
nvda_rew_alt = nvda_t2_alt - pullback_target
print(f"NVDA pullback entry at 210: risk=13.00 t2=230 reward=20.00 rr={20.00/13.00:.1f}:1")

# QQQ regime
qqq = yf.Ticker("QQQ")
hq = qqq.history(period="3mo", interval="1d")
qqq_close = hq['Close'].iloc[-1]
qqq_sma200 = hq['Close'].tail(200).mean()
qqq_sma50 = hq['Close'].tail(50).mean()
print(f"QQQ close={qqq_close:.2f} sma200={qqq_sma200:.2f} diff={(qqq_close-qqq_sma200)/qqq_sma200*100:+.2f}%")
print(f"QQQ {'BELOW' if qqq_close < qqq_sma200 else 'ABOVE'} 200-SMA — REGIME: {'BEAR' if qqq_close < qqq_sma200 else 'BULL'}")
print(f"QQQ 50-SMA={qqq_sma50:.2f}")
print(f"Last 5 daily closes:")
for d,c in zip(hq.index[-5:], hq['Close'].tail(5)):
    print(f"  {d.date()}: ${c:.2f}")

# VIX
vix = yf.Ticker("^VIX")
hv = vix.history(period="1mo", interval="1d")
print(f"VIX close={hv['Close'].iloc[-1]:.2f} 20d avg={hv['Close'].tail(20).mean():.2f}")
