#!/usr/bin/env python3
"""Supplemental catalyst and deeper analysis for top swing candidates."""
import yfinance as yf
from datetime import datetime, timedelta, timezone
import warnings
warnings.filterwarnings('ignore')

now_et = datetime.now(timezone(timedelta(hours=-5)))
print(f"Analysis time: {now_et.strftime('%Y-%m-%d %H:%M %Z')}")
print()

candidates = ['ORLY', 'BKNG', 'MAR', 'AAPL', 'MSFT', 'CTAS', 'NVDA', 'AMZN', 'META']

for t in candidates:
    print(f"\n{'='*60}")
    print(f"CATALYST SCAN: {t}")
    print(f"{'='*60}")
    try:
        tk = yf.Ticker(t)
        info = tk.info
        
        # Key fundamentals
        print(f"\nFUNDAMENTALS:")
        print(f"  Market Cap:    ${info.get('marketCap', 'N/A'):,.0f}" if isinstance(info.get('marketCap'), (int,float)) else f"  Market Cap:    {info.get('marketCap', 'N/A')}")
        print(f"  P/E (TTM):     {info.get('trailingPE', 'N/A'):.1f}" if isinstance(info.get('trailingPE'), float) else f"  P/E (TTM):     {info.get('trailingPE', 'N/A')}")
        print(f"  EPS (TTM):     {info.get('trailingEps', 'N/A'):.2f}" if isinstance(info.get('trailingEps'), float) else f"  EPS (TTM):     {info.get('trailingEps', 'N/A')}")
        print(f"  EPS (FWD):     {info.get('forwardEps', 'N/A'):.2f}" if isinstance(info.get('forwardEps'), float) else f"  EPS (FWD):     {info.get('forwardEps', 'N/A')}")
        print(f"  PEG:           {info.get('pegRatio', 'N/A'):.2f}" if isinstance(info.get('pegRatio'), float) else f"  PEG:           {info.get('pegRatio', 'N/A')}")
        print(f"  Revenue Grwth: {info.get('revenueGrowth', 'N/A'):.1%}" if isinstance(info.get('revenueGrowth'), float) else f"  Revenue Grwth: {info.get('revenueGrowth', 'N/A')}")
        print(f"  EBITDA:        {info.get('ebitda', 'N/A'):,.0f}" if isinstance(info.get('ebitda'), (int,float)) else f"  EBITDA:        {info.get('ebitda', 'N/A')}")
        print(f"  Div Yield:     {info.get('dividendYield', 'N/A'):.2%}" if isinstance(info.get('dividendYield'), float) else f"  Div Yield:     {info.get('dividendYield', 'N/A')}")
        print(f"  52W Target:    ${info.get('targetMeanPrice', 'N/A'):.2f}" if isinstance(info.get('targetMeanPrice'), float) else f"  52W Target:    {info.get('targetMeanPrice', 'N/A')}")
        print(f"  Analysts:      {info.get('numberOfAnalystOpinions', 'N/A')} ({info.get('recommendationKey', 'N/A')})")
        print(f"  Beta:          {info.get('beta', 'N/A'):.3f}" if isinstance(info.get('beta'), float) else f"  Beta:          {info.get('beta', 'N/A')}")
        print(f"  Short Float:   {info.get('shortPercentOfFloat', 'N/A'):.1%}" if isinstance(info.get('shortPercentOfFloat'), float) else f"  Short Float:   {info.get('shortPercentOfFloat', 'N/A')}")
        print(f"  Avg Volume:   {info.get('averageVolume', 'N/A'):,.0f}" if isinstance(info.get('averageVolume'), (int,float)) else f"  Avg Volume:   {info.get('averageVolume', 'N/A')}")
        print(f"  52W High:     ${info.get('fiftyTwoWeekHigh', 'N/A'):.2f}" if isinstance(info.get('fiftyTwoWeekHigh'), float) else f"  52W High:      {info.get('fiftyTwoWeekHigh', 'N/A')}")
        print(f"  52W Low:      ${info.get('fiftyTwoWeekLow', 'N/A'):.2f}" if isinstance(info.get('fiftyTwoWeekLow'), float) else f"  52W Low:       {info.get('fiftyTwoWeekLow', 'N/A')}")
        
        # Earnings upcoming
        print(f"\nEARNINGS:")
        cal = tk.calendar
        if cal is not None and not cal.empty:
            for col in cal.columns:
                print(f"  {col}: {cal[col].iloc[0] if len(cal) > 0 else 'N/A'}")
        else:
            print(f"  No earnings calendar available")
        
        # Splits/dividends
        splits = tk.splits
        if len(splits) > 0:
            print(f"\nSPLITS (last 5):")
            for dt, v in splits.tail(5).items():
                print(f"  {dt.date()}: {v}")
        
        # Institutional ownership hint
        print(f"\nQUOTE CONTEXT:")
        print(f"  Current Price vs Target: {info.get('currentPrice', 'N/A')} vs {info.get('targetMeanPrice', 'N/A')}")
        
    except Exception as e:
        print(f"Error: {e}")

print()
print("="*60)
print("EARNINGS CALENDAR (next 30 days) — key NASDAQ names")
print("="*60)

# Check upcoming earnings for major tickers
earnings_tickers = ['ORLY', 'BKNG', 'MAR', 'AAPL', 'MSFT', 'NVDA', 'AMZN', 'META', 
                    'TSLA', 'AMD', 'GOOGL', 'NFLX', 'COST', 'AVGO', 'QCOM', 'TXN']
for t in earnings_tickers:
    try:
        tk = yf.Ticker(t)
        cal = tk.calendar
        if cal is not None and not cal.empty:
            print(f"  {t}: Earnings calendar available")
        else:
            # Try earnings_dates
            ed = tk.earnings_dates
            if ed is not None and len(ed) > 0:
                # Filter next 30 days
                now = datetime.now(timezone.utc)
                cutoff = now + timedelta(days=30)
                ed['datetime'] = ed.index
                upcoming = ed[ed['datetime'] >= now]
                if len(upcoming) > 0:
                    for dt, row in upcoming.head(2).iterrows():
                        print(f"  {t}: Earning date = {dt}")
    except:
        pass

print()
print("Scan complete.")
