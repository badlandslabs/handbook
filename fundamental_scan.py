import yfinance as yf
from datetime import datetime

today = datetime.now()
print(f"Date: {today.strftime('%Y-%m-%d %A')}")

earnings_watch = {
    'NVDA': '2026-08-28', 'AVGO': '2026-09-05', 'ORCL': '2026-09-10',
    'ADBE': '2026-09-11', 'CRM': '2026-09-11', 'AMD': '2026-10-28',
    'META': '2026-10-29', 'GOOGL': '2026-10-29', 'AMZN': '2026-10-30',
    'AAPL': '2026-10-30', 'MSFT': '2026-10-29', 'NFLX': '2026-10-15',
    'INTC': '2026-10-23', 'QCOM': '2026-11-05', 'INTU': '2026-11-19'
}

print("\nUpcoming Earnings (next 21 days):")
for ticker, edate in earnings_watch.items():
    d = datetime.strptime(edate, '%Y-%m-%d')
    days_out = (d - today).days
    if 0 <= days_out <= 21:
        try:
            tk = yf.Ticker(ticker)
            h = tk.history(period='3d')
            price = float(h['Close'].iloc[-1]) if not h.empty else None
            if price:
                print(f"  {ticker}: {edate} ({days_out} days) @ ${price:.2f}")
            else:
                print(f"  {ticker}: {edate} ({days_out} days)")
        except Exception as e:
            print(f"  {ticker}: {edate} ({days_out} days) [price error]")

print("\nMacro Events (Aug-Sep 2026):")
print("  Aug 20-21: FOMC Meeting")
print("  Aug 28:    Q2 GDP")
print("  Sep 3:     JOLTS Job Openings")
print("  Sep 10:    CPI (August data)")
print("  Sep 16-17: FOMC Meeting")
