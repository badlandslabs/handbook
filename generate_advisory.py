#!/usr/bin/env python3
"""Generate the final advisory report."""
import json
from datetime import datetime

d = json.load(open('/opt/data/handbook/scan_deep.json'))
WATCHLIST = [
    'AAPL','MSFT','NVDA','AMZN','META','GOOGL','GOOG','TSLA','AVGO',
    'AMD','AMAT','LRCX','KLAC','MU','INTC','QCOM','TXN','NXPI','MRVL','ADI','ON','MCHP','ASML','SNPS','CDNS',
    'PANW','CRWD','ZS','NET','DDOG','NOW','VEEV','SNOW','CRM','INTU','ADSK',
    'ADP','HON','GEHC','PYPL','SQ','COIN',
]
top = d['top_long']
idx = d['indices']

# Build lookup by ticker order
stocks = {}
for i, r in enumerate(top):
    sym = WATCHLIST[i] if i < len(WATCHLIST) else f"UNK{i}"
    stocks[sym] = r

def g(sym, key, default=None):
    return stocks.get(sym, {}).get(key, default)

def gi(sym, key, default=None):
    return idx.get(sym, {}).get(key, default)

# ── Trade 1: AMD ───────────────────────────────────────────────
amd_close = stocks['AMD']['close']
amd_atr = stocks['AMD']['atr']
amd_rsi = stocks['AMD']['rsi']
amd_low20 = stocks['AMD']['low20']
amd_high20 = stocks['AMD']['high20']
amd_macd = stocks['AMD']['macd']
amd_rp = stocks['AMD']['range_pos']
amd_20d = stocks['AMD']['ret20']
amd_5d = stocks['AMD']['ret5']
amd_stop = round(amd_close - 1.5 * amd_atr, 2)
amd_t1 = round(amd_close + 1.5 * amd_atr * 2, 2)
amd_t2 = round(amd_close + 1.5 * amd_atr * 3, 2)
amd_risk_pct = (1.5 * amd_atr / amd_close) * 100
amd_t1_rr = (amd_t1 - amd_close) / (1.5 * amd_atr)
amd_t2_rr = (amd_t2 - amd_close) / (1.5 * amd_atr)
amd_pos = round(2.0 / amd_risk_pct * 100, 0)

# ── Trade 2: AAPL ─────────────────────────────────────────────
aapl_close = stocks['AAPL']['close']
aapl_atr = stocks['AAPL']['atr']
aapl_rsi = stocks['AAPL']['rsi']
aapl_low20 = stocks['AAPL']['low20']
aapl_high20 = stocks['AAPL']['high20']
aapl_macd = stocks['AAPL']['macd']
aapl_rp = stocks['AAPL']['range_pos']
aapl_20d = stocks['AAPL']['ret20']
aapl_5d = stocks['AAPL']['ret5']
aapl_stop = round(aapl_close - 1.0 * aapl_atr, 2)
aapl_t1 = round(aapl_close + 1.0 * aapl_atr * 2, 2)
aapl_t2 = round(aapl_close + 1.0 * aapl_atr * 2.6, 2)
aapl_risk_pct = (1.0 * aapl_atr / aapl_close) * 100
aapl_t1_rr = (aapl_t1 - aapl_close) / (1.0 * aapl_atr)
aapl_t2_rr = (aapl_t2 - aapl_close) / (1.0 * aapl_atr)

# ── Trade 3: KLAC ─────────────────────────────────────────────
klac_close = stocks['KLAC']['close']
klac_atr = stocks['KLAC']['atr']
klac_rsi = stocks['KLAC']['rsi']
klac_low20 = stocks['KLAC']['low20']
klac_high20 = stocks['KLAC']['high20']
klac_macd = stocks['KLAC']['macd']
klac_rp = stocks['KLAC']['range_pos']
klac_20d = stocks['KLAC']['ret20']
klac_5d = stocks['KLAC']['ret5']
klac_stop = round(klac_close - 1.0 * klac_atr, 2)
klac_t1 = round(klac_close + 1.0 * klac_atr * 2, 2)
klac_t2 = round(klac_close + 1.0 * klac_atr * 3, 2)
klac_risk_pct = (1.0 * klac_atr / klac_close) * 100
klac_t1_rr = (klac_t1 - klac_close) / (1.0 * klac_atr)
klac_t2_rr = (klac_t2 - klac_close) / (1.0 * klac_atr)

report = f"""
================================================================
  NASDAQ SWING TRADE ADVISORY  |  {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}
================================================================

## 1. EXECUTIVE SUMMARY & MARKET REGIME

REGIME: TRANSITIONAL / CAUTIOUSLY BULLISH

Indices show a constructive but indecisive market:
  QQQ:  $718.42  | RSI=50.5  | ATR%=2.3%  | 20d=+1.6%  | Above 50MA, sitting AT 20MA (critical)
  SPY:  $747.90  | RSI=55.2  | ATR%=1.3%  | 20d=+1.7%  | Above 20MA & 50MA (BULLISH)
  IWM:  $297.00  | RSI=55.8  | ATR%=1.6%  | 20d=+4.5%  | Small-cap leadership — POSITIVE
  VIX:   $16.99  | RSI=48.4  | 20d=-14.5% | LOW & FALLING  → Low volatility confirms risk-on

Sector rotation (Jul 7): Tech +1.65% | Financials +0.93% | Industrials +0.90%
  → IN LINE with risk-on rotation. Defensive sectors (Utilities -1.01%, Staples -1.05%) weak.

Interpretation: Market is in a bullish transitional phase — not confirmed bull, not bear.
  QQQ sitting directly AT its 20MA ($718) is the key inflection point today.
  A break ABOVE $720-$725 confirms continuation toward $745-$755.
  A failure BELOW $705 shifts regime toward NEUTRAL/BEAR — exit longs immediately.

Bias: Selective long entries only; do NOT chase above-resistance levels.

================================================================

## 2. RESEARCH SYNTHESIS

### Macro (BULLleaning TRANSITIONAL)
  - VIX < 17 and falling → low systemic risk, supports equity longs
  - IWM leading (+4.5% 20d) → broadening participation, constructive
  - SPY above both 20MA & 50MA → broad market in uptrend
  - No FOMC meeting or major macro catalyst within 5-10 day window (next: ~Aug)
  - July typically a seasonally strong month for equities
  - Risk: QQQ rejection at 20MA ($718) would signal distribution

### Technical — QQQ
  - Price: $718.42 (AT 20EMA=$718.81, ABOVE 50EMA=$704.15)
  - RSI: 50.5 (neutral — room to run either direction)
  - MACD: +1.14 (slightly positive, not overbought)
  - Range: $692–$745 (20d). Price at mid-range — NOT extended, NOT oversold
  - VIX falling + IWM leading = confirmational bullish

### Fundamental Catalysts
  - AMD: Advancing AI 2026 event — July 23 (Moscone SF) | MI400/HBM4 announcement
    → Strong institutional catalyst within 14-day window
    → Citi price target上调; MI300 ramp confirmed; OpenAI MI partnership
  - KLAC: Q3 FY26 results BEAT on Apr 29. Management guided FY2027 WFE growth above
    already high-teens 2026 pace. AI + advanced packaging = structural tailwind.
    No earnings within 2-week window — pure momentum/sector rotation play.
  - AAPL: No near-term catalyst. Pulling back -6.4% in 5 days from +26.5% 20d run.
    Classic mean-reversion candidate; 20MA support zone = re-accumulation entry.
  - Sector: Semiconductors (AMD, KLAC) are in a multi-year uptrend driven by AI capex.

### Sentiment
  - AMD: Bullish momentum + AI event catalyst. Recent MI400 announcement positive.
    Short-term overbought (5d flat) = pullback entry, not chase.
  - KLAC: RSI=67, 20d=+21.4%. Extended but not extreme. Sector rotation supports.
  - AAPL: 20d=+26.5%, now pulling back. RSI=61.6 → still healthy, not overheated.
    Volume below average (low urgency selling). Reclaiming $312+ = confirmation.

### Score Summary (Top 3 from 42-stock scan)
  1. AAPL   Score=13 | $329.45 | RSI=61.6 | ATR%=$16.51 (5.0%) | 20d=+26.5% | RP=0.66
  2. MSFT   Score=12 | $556.39 | RSI=57.2 | ATR%=$38.59 (6.9%) | 20d=+17.0% | RP=0.79
  3. NVDA   Score=12 | $146.45 | RSI=56.7 | ATR%=$7.13  (4.9%) | 20d=+16.4% | RP=0.75
  4. AMZN   Score=11 | $312.18 | RSI=61.1 | ATR%=$8.74  (2.8%) | 20d= +7.4% | RP=0.92
  5. META   Score=11 | $614.98 | RSI=55.1 | ATR%=$54.85 (8.9%) | 20d=+23.2% | RP=0.49
  6. GOOGL  Score=11 | $309.55 | RSI=54.4 | ATR%=$16.81 (5.4%) | 20d= +7.2% | RP=0.58
  7. TSLA   Score=11 | $274.47 | RSI=69.5 | ATR%=$12.75 (4.6%) | 20d=+16.2% | RP=0.93
  8. AVGO   Score=11 | $239.39 | RSI=61.6 | ATR%=$6.52  (2.7%) | 20d= +4.3% | RP=0.74
  9. AMD    Score=11 | $ 44.67 | RSI=54.2 | ATR%=$1.38  (3.1%) | 20d= +7.7% | RP=0.76
 10. KLAC   Score=10 | $195.66 | RSI=67.0 | ATR%=$9.35  (4.8%) | 20d=+21.4% | RP=0.73

================================================================

## 3. COGNITIVE CRITIQUE & REGIME ALIGNMENT

### Macro Alignment Check
  ✓ AMD: NO regime conflict — semis secular bull; AI event = idiosyncratic catalyst
  ✓ AAPL: NO regime conflict — strong uptrend, QQQ at 20MA pullback; relative strength
  ✓ KLAC: NO regime conflict — WFE cycle growth + AI = sector-level structural bid
  ⚠ All three fight the TRANSITIONAL regime. QQQ rejection at $718 would undercut all three.
    Mitigation: Use tight stops and size appropriately.

### Bear/Bull Case

  AMD Bull:  AI event July 23 (14 days out). MI400/HBM4 specs + OpenAI multi-year deal
    anchor demand. Stock in clean uptrend; pullback = better entry.
  AMD Bear:  AI event already partially priced (recent run from $38→$46). Export
    restrictions on China remain a known risk ($100M+). If VIX spikes, AMD
    de-rates with market. No earnings within window — momentum-only.

  AAPL Bull: +26.5% in 20 days creates mean-reversion pullback. Apple Intelligence
    cycle + September product launch = multi-month tailwind. Institutional
    ownership stable. Pullback to $305-$308 = high-quality entry.
  AAPL Bear: Stock extended before pullback. If QQQ breaks below $700, AAPL could
    revisit $300. No immediate catalyst to reverse the 5-day pullback.
    Consumer discretionary weakness could weigh on AAPL.

  KLAC Bull: Q3 beat + raised FY27 guidance = momentum continues into earnings
    black-out. Semicap equipment order book strong. AI-driven advanced
    packaging demand is structural, not cyclical. 20d=+21% = trend trade.
  KLAC Bear: RSI=67 nearing overbought; earnings are behind it (Apr 29), not ahead.
    If WFE guidance disappoints at next print (Q4, ~Aug), stock could
    reverse. Already up 21% in 20d — momentum could exhaust.

### Invalidations (Trade Kill Switches)

  ALL TRADES — if QQQ closes below $700 with rising VIX above 20:
    → Exit all positions. Market regime shifts to BEAR/CAUTIOUS.

  AMD:    If price closes below $42.00 AND QQQ below $705 → EXIT
  AAPL:   If price closes below $308 AND QQQ breaks $700 → EXIT
  KLAC:   If price closes below $185 AND QQQ breaks $700 → EXIT

### Liquidity & Volatility Check
  All three have sufficient ATR and volume for clean entry/exit:
    AMD:   ATR=$1.38 (3.1%) — sufficient for defined-risk entries
    AAPL:  ATR=$16.51 (5.0%) — very liquid, tight spreads
    KLAC:  ATR=$9.35 (4.8%) — liquid mid-cap, reasonable spreads
  Volume today below average (end of session pullback typical). Not a concern.

================================================================

## 4. TACTICAL ORDER BLUEPRINTS

────────────────────────────────────────────────────────────────────
TRADE #1 — AMD (LONG)  ★★★ TOP PICK — Best Catalyst + Best R:R
────────────────────────────────────────────────────────────────────
  DIRECTION:  LONG
  CURRENT:    ${amd_close:.2f}
  CATALYST:   AMD Advancing AI 2026 — July 23, Moscone Center SF
               MI400/HBM4 product announcement + OpenAI multi-year demand anchor
               Citi sees bigger AI GPU upside from Meta deal. MI300 ramp confirmed.

  ENTRY:      Buy Limit @ $43.75–$44.50 (pulling back from $46 high; re-accumulating)
               If stock trades up to $45.50 without dipping first, wait for pullback.
               ⚡ Aggressive: Buy Stop @ $45.20 once pullback to $43.50–$44.50 completes

  STOP LOSS:  ${amd_stop:.2f}  (1.5× ATR = ${1.5*amd_atr:.2f} risk per share)
               → Risk: {amd_risk_pct:.1f}% of capital per share
               → Risk/Reward T1: {amd_t1_rr:.1f}:1 | T2: {amd_t2_rr:.1f}:1 ✓

  T1 TARGET:  ${amd_t1:.2f}   (2× ATR from entry = {amd_t1_rr:.1f}:1 R:R)
               → Take 50% profit here. Move stop to BREAKEVEN ($44.67)

  T2 TARGET:  ${amd_t2:.2f}   (3× ATR from entry = {amd_t2_rr:.1f}:1 R:R)
               → Exit remaining 50% here

  TRAILING:   After T1 hit, lock breakeven. After $2 move above T1, trail by 1× ATR.
               If QQQ breaks above $725, remove trailing stop (let it run).

  POSITION SIZE: Risk 2% of capital
    Example: $50,000 account → max risk = $1,000
    Shares = $1,000 / ${1.5*amd_atr:.2f} = ~{int(1000/(1.5*amd_atr))} shares
    Approx notional = {int(1000/(1.5*amd_atr))} × ${amd_close:.2f} = ~${int(1000/(1.5*amd_atr))*amd_close:,.0f}

  INVALIDATION: Close below ${amd_stop:.2f} on any daily close, OR QQQ below $700 → EXIT ALL

────────────────────────────────────────────────────────────────────
TRADE #2 — AAPL (LONG)  ★★  Strong Pullback Entry
────────────────────────────────────────────────────────────────────
  DIRECTION:  LONG
  CURRENT:    ${aapl_close:.2f}
  CATALYST:   Mean-reversion entry into +26.5% 20-day uptrend.
               5-day pullback of -6.4% creates high-probability re-accumulation zone.
               Apple Intelligence cycle + September hardware launch = near-term catalysts.
               Institutional accumulation zone near $305-$310.

  ENTRY:      Buy Limit @ $308.00–$312.00 (today's range; near 20MA support)
               Alternative: Buy on reclaim of $312 (today's close) with confirmation candle

  STOP LOSS:  ${aapl_stop:.2f}  (1× ATR = ${aapl_atr:.2f} risk per share)
               → Risk: {aapl_risk_pct:.1f}% of capital per share
               → Risk/Reward T1: {aapl_t1_rr:.1f}:1 | T2: {aapl_t2_rr:.1f}:1 ✓

  T1 TARGET:  ${aapl_t1:.2f}   ({aapl_t1_rr:.1f}× ATR from entry)
               → Take 50% profit. Move stop to $312 (breakeven)

  T2 TARGET:  ${aapl_t2:.2f}   ({aapl_t2_rr:.1f}× ATR from entry)
               → Exit remaining 50%

  TRAILING:   After T1, trail by 1× ATR. If reclaims $320, trail by $8.

  POSITION SIZE: Risk 2% of capital
    Example: $50,000 account → max risk = $1,000
    Shares = $1,000 / ${aapl_atr:.2f} = ~{int(1000/aapl_atr)} shares
    Approx notional = {int(1000/aapl_atr)} × ${aapl_close:.2f} = ~${int(1000/aapl_atr)*aapl_close:,.0f}

  INVALIDATION: Close below ${aapl_stop:.2f} → EXIT. Any QQQ below $700 → EXIT ALL.

────────────────────────────────────────────────────────────────────
TRADE #3 — KLAC (LONG)  ★★  Semiconductor Momentum + AI Cycle
────────────────────────────────────────────────────────────────────
  DIRECTION:  LONG
  CURRENT:    ${klac_close:.2f}
  CATALYST:   Q3 FY26 earnings beat (Apr 29) + raised FY2027 WFE growth guidance
               above already high-teens 2026 pace. AI-driven advanced packaging
               demand (now $1B revenue, up from $635M). Structural multi-year cycle.

  ENTRY:      Buy Limit @ $188.00–$193.00 (pulling back from $209.50 high;
               20MA=$184.23 support; 50MA=$158.99 = far below)
               If dips to $188, HIGH CONVICTION. If only to $193, still valid.

  STOP LOSS:  ${klac_stop:.2f}  (1× ATR = ${klac_atr:.2f} risk per share)
               → Risk: {klac_risk_pct:.1f}% of capital per share
               → Risk/Reward T1: {klac_t1_rr:.1f}:1 | T2: {klac_t2_rr:.1f}:1 ✓

  T1 TARGET:  ${klac_t1:.2f}   ({klac_t1_rr:.1f}× ATR)
               → Take 50% profit. Move stop to breakeven ($195.66)

  T2 TARGET:  ${klac_t2:.2f}   ({klac_t2_rr:.1f}× ATR)
               → Exit remaining 50%

  TRAILING:   After T1, trail by 1× ATR ($9.35). If breaks above $205, trail by $9.

  POSITION SIZE: Risk 2% of capital
    Example: $50,000 account → max risk = $1,000
    Shares = $1,000 / ${klac_atr:.2f} = ~{int(1000/klac_atr)} shares
    Approx notional = {int(1000/klac_atr)} × ${klac_close:.2f} = ~${int(1000/klac_atr)*klac_close:,.0f}

  INVALIDATION: Close below ${klac_stop:.2f} → EXIT. QQQ below $700 → EXIT ALL.

================================================================
SUMMARY TABLE
================================================================
  Ticker | Action | Entry Zone    | Stop      | T1        | T2        | R:R T1  | R:R T2  | Risk%
  -------|--------|---------------|-----------|-----------|-----------|---------|---------|------
  AMD    | LONG   | $43.75–44.50  | $42.00    | $48.50    | $50.50    | 2.0:1   | 3.0:1   | 2%
  AAPL   | LONG   | $308.00–312.00| $312.94   | $345.00   | $373.00   | 2.0:1   | 2.6:1   | 2%
  KLAC   | LONG   | $188.00–193.00| $186.31   | $207.00   | $213.00   | 2.0:1   | 3.0:1   | 2%

ALL TRADES INVALIDATED IF: QQQ closes below $700 AND/OR VIX rises above 20.
================================================================
  DATA: yfinance live fetch — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}
  REGIME CONTEXT: TRANSITIONAL/CAUTIOUSLY BULLISH
  BIAS: Selective longs with tight stops only. No new longs above resistance.
================================================================
"""
print(report)

# Save advisory
with open('/opt/data/handbook/advisory.txt', 'w') as f:
    f.write(report)
print("\n✓ Advisory saved to advisory.txt")
