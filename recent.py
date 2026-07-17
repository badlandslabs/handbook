#!/opt/data/handbook/venv/bin/python3
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

today = datetime.now().strftime('%Y-%m-%d')
start = (datetime.now() - timedelta(days=200)).strftime('%Y-%m-%d')

# Get recent 5-day data for QQQ to see today's move
print("=== QQQ RECENT DATA ===")
qqq = yf.download('QQQ', start=start, end=today, progress=False, auto_adjust=True)
print(qqq.tail(10).to_string())
print()

# Also get today's date in the series
print(f"\nLast 3 dates: {list(qqq.index[-3:])}")
print(f"Today is: {today}")

# Check if we have today's data
if qqq.index[-1].strftime('%Y-%m-%d') == today:
    print("Today's QQQ data is available!")
else:
    print(f"Last available: {qqq.index[-1].strftime('%Y-%m-%d')}")
