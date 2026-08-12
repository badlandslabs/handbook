import yfinance as yf
from datetime import datetime, timezone, timedelta
import numpy as np

candidates = ['NVDA', 'AVGO', 'ISRG', 'PLTR', 'PANW', 'NET', 'ZS', 'CRWD', 'AMD', 'AMAT', 'KLAC']
print('ANALYST DATA:')
for t in candidates:
    tk = yf.Ticker(t)
    info = tk.info
    price = info.get('currentPrice', info.get('regularMarketPrice', None))
    median = info.get('targetMeanPrice', None)
    high = info.get('targetHighPrice', None)
    low = info.get('targetLowPrice', None)
    rec = info.get('recommendationKey', '?')
    num_analysts = info.get('numberOfAnalystOpinions', 0)
    rev_growth = info.get('revenueGrowth', None)
    earn_growth = info.get('earningsGrowth', None)
    sector = info.get('sector', '?')
    beta = info.get('beta', None)
    if price and median:
        try:
            upside = (float(median) - float(price)) / float(price) * 100
            print(f"{t}: P={price:.2f} MedianTgt={median:.2f} High={high:.2f} Low={low:.2f} Up={upside:+.1f}% Rec={rec} Analysts={num_analysts}")
        except:
            print(f"{t}: P={price} MedianTgt={median}")
    else:
        print(f"{t}: P={price} No target data")
    rg = f"{rev_growth:.1%}" if isinstance(rev_growth, float) else str(rev_growth)
    eg = f"{earn_growth:.1%}" if isinstance(earn_growth, float) else str(earn_growth)
    print(f"    Sector={sector} RevGrowth={rg} EarnGrowth={eg} Beta={beta}")

print()
print('NVDA earnings dates:')
tk = yf.Ticker('NVDA')
try:
    ed = tk.earnings_dates
    if ed is not None:
        df = ed()
        if df is not None and not df.empty:
            now = datetime.now(timezone.utc)
            print(df.tail(4).to_string())
except Exception as e:
    print(f"Error: {e}")

print()
print('AVGO key financials:')
tk = yf.Ticker('AVGO')
info = tk.info
for k in ['profitMargins','operatingMargins','forwardEps','trailingEps','marketCap','totalDebt','totalCash']:
    v = info.get(k,'?')
    if isinstance(v, float) and v > 1e9:
        print(f"  {k}: {v/1e9:.2f}B")
    elif isinstance(v, float):
        print(f"  {k}: {v:.2%}" if 0 < v < 1 else f"  {k}: {v:.2f}")
    else:
        print(f"  {k}: {v}")

print()
print('ISRG key financials:')
tk = yf.Ticker('ISRG')
info = tk.info
for k in ['profitMargins','operatingMargins','forwardEps','trailingEps','marketCap','beta']:
    v = info.get(k,'?')
    if isinstance(v, float) and v > 1e9:
        print(f"  {k}: {v/1e9:.2f}B")
    elif isinstance(v, float):
        print(f"  {k}: {v:.2%}" if 0 < v < 1 else f"  {k}: {v:.2f}")
    else:
        print(f"  {k}: {v}")
