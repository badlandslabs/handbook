#!/opt/data/handbook/venv/bin/python3
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

today = datetime.now().strftime('%Y-%m-%d')
start = (datetime.now() - timedelta(days=200)).strftime('%Y-%m-%d')

# Try downloading single ticker first
test = yf.download('AAPL', start=start, end=today, progress=False, auto_adjust=True)
print(f"AAPL shape: {test.shape}")
print(f"AAPL cols: {list(test.columns)}")
print(test.tail(3))
print()

# Try multi-ticker
tickers = ['AAPL', 'MSFT', 'NVDA']
multi = yf.download(tickers, start=start, end=today, progress=False, auto_adjust=True)
print(f"Multi shape: {multi.shape}")
print(f"Multi cols: {list(multi.columns)}")
print(multi.tail(3))
