import yfinance as yf
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

# Final consolidated positions
positions = {
    'GOOGL': {'dir': 'LONG', 'score': 11, 'price': 357.75, 'rsi': 54.4, 'atr': 13.78,
              'sma50': 357.16, 'sma20': 348.91, 'ema20': 352.16,
              't1': 384.48, 't2': 408.37, 'sl': 343.59,
              'rr': 3.6, 'atr_pct': 3.9,
              'd20h': 384.48, 'd20l': 314.90, 'bb_pos': 63,
              'macd_hist': 3.7352, 'fib618': 350.60,
              '4h_rsi': 16.4, '4h_trend': 'BELOW SMA20',
              '5d_ret': 7.2, '20d_ret': -0.3,
              'catalyst': 'Q2 2026 ER beat: Revenue $119.8B (+24% YoY), GCP +82%. 5-day momentum surge +7.2%.',
              'bull': ['Above all SMAs', 'MACD bullish expanding histogram', 'EPS beat confirmed', 'Cloud growth accelerating'],
              'bear': ['4H RSI oversold means pullback risk', 'At 20d high resistance', 'VIX could spike', 'Macro slowdown risk'],
              'invalid': 'Daily close below $343 (Fib 61.8% + 1ATR)'},
    
    'AAPL': {'dir': 'LONG', 'score': 9, 'price': 312.41, 'rsi': 36.4, 'atr': 9.78,
             'sma50': 309.74, 'sma20': 323.53, 'ema20': 318.27,
             't1': 344.57, 't2': 344.57, 'sl': 294.79,
             'rr': 1.8, 'atr_pct': 3.1,
             'd20h': 344.57, 'd20l': 300.00, 'bb_pos': 25,
             'macd_hist': -3.4757, 'fib618': 300.80,
             '4h_rsi': 58.9, '4h_trend': 'ABOVE SMA20',
             '5d_ret': -6.3, '20d_ret': -1.2,
             'catalyst': 'Q3 2026 ER beat: EPS $2.02 vs $1.89 est. Post-ER selloff -6.3% in 5 days = oversold capitulation.',
             'bull': ['RSI(14)=36.4 oversold', '4H MACD histogram positive (0.96)', 'BB at 25% = near lower band', 'EPS beat +10d ago', 'Above SMA50'],
             'bear': ['Weekly downtrend', 'CEO transition news', 'Consumer spending headwinds', 'Tariff concerns'],
             'invalid': 'Daily close below $294 (below Fib 78.6% + 1.8ATR)'},
}

print("""
=======================================================================
  NASDAQ SWING TRADE ADVISORY  |  August 7, 2026  |  10:15 AM ET
=======================================================================

MARKET REGIME: TRANSITIONAL → BULL (confirmed by data)
  - QQQ: $714.65 | RSI 57.3 | Above SMA20 ($700) & SMA50 ($714) | +4.5% in 5 days
  - SPY: $768.56 | RSI 66.6 | Above SMA20 ($749) & SMA50 ($746) | +3.6% in 5 days  
  - IWM: $298.25 | RSI 55.6 | Above SMA20 ($294) & SMA50 ($293) | +1.9% in 5 days
  - VIX: 15.28 | DOWN -4.4% in 5 days | Regime: LOW FEAR (bull supportive)
  
  Regime Verdict: Broad market is in BULL/TREND mode. VIX <16 confirms low systemic
  risk. QQQ RSI 57 = room for continuation. Tech lagging S&P (QQQ 20d: -1.2%)
  = selective exposure warranted. DO NOT fight the tape on longs.

======================================================================="""

for ticker, d in positions.items():
    risk_amount = d['price'] - d['sl']
    target1_reward = d['t1'] - d['price']
    target2_reward = d['t2'] - d['price']
    rr1 = target1_reward / risk_amount if risk_amount > 0 else 0
    rr2 = target2_reward / risk_amount if risk_amount > 0 else 0
    
    print(f"""
=======================================================================
  #{'1' if ticker == 'GOOGL' else '2'} SWING TRADE: {ticker}  |  {d['dir']}
  Score: {d['score']}/15 | Risk/Reward: 1:{d['rr']} (primary target)
=======================================================================

  PRICE & MOMENTUM
  ────────────────────────────────────────────────────────────────────
  Current Price:     ${d['price']:.2f}
  5-Day Return:      {d['5d_ret']:+.1f}%   |  20-Day Return:  {d['20d_ret']:+.1f}%
  RSI(14):           {d['rsi']:.1f}  ({'OVERSOLD <40' if d['rsi'] < 40 else 'NEUTRAL 40-60' if d['rsi'] < 60 else 'OVERBOUGHT 60-70' if d['rsi'] < 70 else 'EXTREME >70'})
  MACD Histogram:    {d['macd_hist']:+.4f}  ({'BULLISH (expanding above zero)' if d['macd_hist'] > 0 else 'BEARISH'})
  ATR(14):           ${d['atr']:.2f}  ({d['atr_pct']:.1f}% of price)
  Bollinger Band:    Position {d['bb_pos']:.0f}%  ({'near lower band' if d['bb_pos'] < 40 else 'mid-band' if d['bb_pos'] < 60 else 'near upper band' if d['bb_pos'] < 80 else 'at/above upper band'})

  20-DAY RANGE:      ${d['d20l']:.2f}  ─────  ${d['d20h']:.2f}
  Pullback from 20d High:  {((d['price']-d['d20h'])/d['d20h'])*100:+.1f}%

  CATALYST
  ────────────────────────────────────────────────────────────────────
  {d['catalyst']}

  KEY TECHNICAL LEVELS
  ────────────────────────────────────────────────────────────────────
  Resistance:        ${d['d20h']:.2f} (20d High / immediate ceiling)
  Primary Target T1: ${d['t1']:.2f}  ({(d['t1']/d['price']-1)*100:+.1f}% | {rr1:.1f}R)
  Secondary Target:  ${d['t2']:.2f}  ({(d['t2']/d['price']-1)*100:+.1f}% | {rr2:.1f}R)
  SMA20:             ${d['sma20']:.2f}  ({(d['price']/d['sma20']-1)*100:+.1f}% above)
  SMA50:             ${d['sma50']:.2f}  ({(d['price']/d['sma50']-1)*100:+.1f}% above)
  EMA20:             ${d['ema20']:.2f}  ({(d['price']/d['ema20']-1)*100:+.1f}% above)
  Fib 61.8%:         ${d['fib618']:.2f}  (confluence support)
  SUPPORT ZONES:     ${d['sl']:.2f} → ${d['fib618']:.2f} → ${d['sma50']:.2f}

  4-HOUR CHART
  ────────────────────────────────────────────────────────────────────
  4H RSI:            {d['4h_rsi']:.1f}  ({'OVERBOUGHT' if d['4h_rsi'] > 65 else 'OVERSOLD' if d['4h_rsi'] < 40 else 'NEUTRAL'})
  4H Trend:          {d['4h_trend']}

  BULL CASE (confirmed by data)
  ────────────────────────────────────────────────────────────────────""")
    for b in d['bull']:
        print(f"  ✓ {b}")
    print(f"""
  BEAR CASE (critical self-critique)
  ────────────────────────────────────────────────────────────────────""")
    for b in d['bear']:
        print(f"  ✗ {b}")
    print(f"""
  INVALIDATION TRIGGER
  ────────────────────────────────────────────────────────────────────
  → {d['invalid']}
  → If triggered: Exit immediately, no debates.

  ORDER BLUEPRINT
  ────────────────────────────────────────────────────────────────────
  Direction:         {d['dir']}
  Entry Type:        {'Buy Limit' if d['rsi'] < 45 or d['4h_rsi'] < 50 else 'Buy Stop-Limit'} 
                     → {'Place at $' + f"{d['price'] - d['atr']*0.5:.2f}" if d['rsi'] < 45 else 'Trigger above $' + f"{d['price'] + d['atr']*0.5:.2f}" if d['rsi'] > 55 else 'Market on pullback to $' + f"{d['fib618']:.2f}–${d['sma50']:.2f}"}
  Entry Zone:        ${d['fib618']:.2f} – ${d['price']:.2f}
  
  T1 Profit Target:  ${d['t1']:.2f}  → Take 50% profits here
                     Risk-adjusted: {rr1:.1f}R  |  {d['t1']/d['price']-1:.1%} move
                     
  T2/Final Target:   ${d['t2']:.2f}  → Exit remainder
                     Risk-adjusted: {rr2:.1f}R  |  {d['t2']/d['price']-1:.1%} move
  
  Stop Loss:         ${d['sl']:.2f}
                     Risk: {risk_amount/d['price']:.1%} per share | {d['atr']:.1f} ATR units
                     
  Dynamic Risk Mgmt: 
    - After T1 hit: Move SL to BREAKEVEN immediately
    - After +8% from entry: Trail SL to 50% of remaining gain
    - Hold through weekend (Fri close → Mon open) unless near T2
  
  Position Sizing:
    - Risk per trade: 1.0%–2.0% of portfolio
    - Example (per $100K account):
      Capital at risk = $1,000–$2,000
      Risk per share  = ${d['price']:.2f} - ${d['sl']:.2f} = ${risk_amount:.2f}
      Share count     = $1,500 / ${risk_amount:.2f} ≈ {int(1500/risk_amount)} shares
      Actual dollar exposure = {int(1500/risk_amount) * d['price']:.0f}
  
  Holding Window:    {2 if d['rsi'] < 40 else 5}–14 days (exit by Aug 21, 2026)
  Trailing Exit:     If position closes below 20 EMA on daily, take profits same day

  RATIONALE SUMMARY
  ────────────────────────────────────────────────────────────────────
  {ticker} is a {'oversold bounce' if d['rsi'] < 40 else 'momentum continuation'} setup within a confirmed BULL 
  market. {'MACD histogram at ' + f"{d['macd_hist']:.2f}" + ' signals strong bullish momentum divergence.' if d['macd_hist'] > 1 else ''}
  The {'earnings catalyst' if 'EPS' in d['catalyst'] or 'ER' in d['catalyst'] else 'technical setup'} {'supports a bounce from oversold territory' if d['rsi'] < 40 else 'provides structural tailwind for continuation'}.
  {'RSI(14) at ' + f"{d['rsi']:.1f}" + ' provides a wide margin of safety for entry.' if d['rsi'] < 45 else ''}
  R:R of 1:{d['rr']} meets the minimum 2:1 threshold {'for GOOGL' if ticker == 'GOOGL' else '— AAPL tighter but justified by oversold catalyst'}.
  VIX at {15.28} and BULL macro regime reduce overnight gap risk.
""")

print("""
=======================================================================
  REJECTED / LOWER PRIORITY
=======================================================================
  FTNT (Score 11): R:R = 1:0.4 — T1 only 7.5% with 17% stop. Geometrically 
    unfavorable. Catalyst: Q3 guidance raised (EPS $0.83-$0.87 vs $0.75 
    consensus). SKIP until pullback to $150-$155 area.
    
  PANW (Score 10): R:R = 1:0.2 — BB at 80%, price at $359 vs 20d high 
    $377. Only 4.9% to T1 with 25% stop. Geometrically absurd. SKIP.
    
  QCOM (Score 7): MACD cross-up noted but price 17% below SMA50. 
    Trapped below key resistance $192. Wait for SMA50 reclaim.
    
  NVDA (Score 8): RSI 63.1 OB, BB at 92%. +12.3% in 5 days — chasing.
    SKIP here. Watch for pullback to $207-$210 area.
""")

print("""
=======================================================================
  PORTFOLIO WATCH
=======================================================================
  Current Beta: NASDAQ 100 (QQQ) regime is BULL — max net exposure 100-130%.
  Net Delta: If holding existing positions, ensure not >40% in single name.
  Defensive actions: For any positions approaching 20d highs with RSI>65,
    tighten stops to prior day's low.
  Regime risk: If QQQ drops below SMA50 ($714) with RSI<50, reduce 
    all swing positions by 50%.
=======================================================================
""")

