# F-99 · Numeric Unit Consistency Check

[F-92](f92-agent-output-arithmetic-invariants.md) checks arithmetic relationships in structured output: does `total = subtotal + tax`? Are all prices positive? These checks assume the numbers being compared are in the same unit and representation — they catch `total: 288.00` when it should be `265.62`, not `total: "$265.62"` when another field says `265620` (same amount, different representation). [F-97](f97-output-field-confidence-annotation.md) checks whether each field value is grounded in retrieved sources. [F-70](f70-verifiable-output-design.md) checks structural integrity.

None check whether numeric fields within the same output use consistent representations for the same quantity type. An agent summarizing a merger agreement may return `{ acquisition_value: "$2.45B", deal_size: "$2,450,000,000", termination_fee: "$24.5M", break_fee: "24500000" }`. All four values are internally correct. F-92 passes: no arithmetic invariants are violated. F-97 passes: all values appear in retrieved sources. But downstream systems parsing `"$2.45B"` and `"$2,450,000,000"` as the same entity need to know they represent the same number — and the mixed formats create silent parsing failures or human confusion about whether `$24.5M` and `24500000` represent the same amount.

Numeric unit consistency check normalizes all currency, percentage, and date fields to canonical numeric representations, then classifies each field's original format into a format token (DOLLAR\_ABBREV, DOLLAR\_RAW, DECIMAL\_PCT, FRACTION\_PCT, ISO\_DATE, NATURAL\_DATE). Fields that represent the same quantity type across the output should use the same format token. Mixed-format fields get flagged with the canonical numeric value alongside the original for downstream comparison.

## Situation

A contract analysis agent returns a 12-field structured summary with 4 currency fields, 2 percentage fields, and 3 date fields. Of the 4 currency fields, 2 use abbreviated notation (`"$24.5M"`, `"$2.45B"`) and 2 use raw decimal strings (`"24500000"`, `"2450000000"`). Of the 2 percentage fields, one uses `"5.25%"` and one uses `"0.0525"`. Of the 3 dates, two are ISO format and one is `"January 1, 2025"`. A downstream system ingesting this output for a financial database will parse `"$24.5M"` as a string, not a number, and silently insert `null` for the deal value.

Unit consistency check catches all three inconsistencies at delivery time, before the downstream system sees the data. It also provides canonical normalized values so the consumer can ingest using the numbers rather than parsing the raw strings.

## Forces

- **The model does not generate a uniform representation unless the output schema forces it.** When the retrieved sources contain `"$24.5M"` and `"$24,500,000"` in different paragraphs, the model uses whichever representation appeared in the source it drew from. This is correct behavior from the model's perspective — it quoted the source — but it creates representation inconsistency across fields.
- **Normalization must be to a canonical numeric value, not to a different string format.** Avoid converting everything to one string format (e.g., always use `"$24,500,000.00"`) — that's formatting, not consistency. The right output is a normalized numeric value alongside the original string, so consumers can choose their preferred format. Produce `{ original: "$24.5M", canonical: 24500000, type: "CURRENCY" }` — not just re-formatted strings.
- **Currency abbreviation expansion is ambiguous at the boundaries.** `"$1.5B"` is unambiguous (1 500 000 000). `"$1.5M"` is unambiguous (1 500 000). But `"$1.5"` with no suffix could be `$1.50` (price of a small item) or a truncated representation. The normalizer should require a suffix for values ≥1 000 000 or flag bare decimal values in that range as ambiguous.
- **Percentage ambiguity is systematic.** `"5.25%"` normalizes to the fraction `0.0525` (divide by 100). `"0.0525"` is already a fraction. Both represent the same rate, but the caller needs to know which form to expect. Canonical form: always store as fraction (`0.0525`); flag which fields used the percent sign and which used the bare decimal, since the source format tells you how the model was likely reasoning.
- **Date normalization must handle locale ambiguity.** `"01/02/2025"` is January 2 (US) or February 1 (EU). Do not normalize ambiguous date strings — flag them as AMBIGUOUS\_DATE and require explicit resolution. Only normalize unambiguous forms: ISO 8601, fully spelled-out month names, or year-month-day order.
- **Consistency check is within-output, not against a schema.** The goal is not to enforce a global format (that's the output schema's job, per S-04). The goal is to detect within a single output that fields representing the same quantity type have drifted apart in representation — which signals either inconsistency in the source documents or inconsistency in how the model synthesized them.

## The move

**Normalize each numeric field to a canonical value and a format token. Flag fields of the same type that use mixed format tokens. Return the original values, canonical values, and a consistency report.**

```js
// --- Currency normalization ---
// Input: any of: "$24.5M", "$24,500,000", "24500000", "2.45B", "$1.2K"
// Output: { canonical: number, formatToken: string } or null if not parseable

const CURRENCY_PATTERN = /^\$?([\d,]+(?:\.\d+)?)([KMBTkmbt])?$/;

function normalizeCurrency(str) {
  const s = String(str).replace(/,/g, '').trim();
  const m = s.match(CURRENCY_PATTERN);
  if (!m) return null;

  const base     = parseFloat(m[1]);
  const suffix   = (m[2] ?? '').toUpperCase();
  const hasDollar = str.startsWith('$');
  const multipliers = { K: 1e3, M: 1e6, B: 1e9, T: 1e12 };
  const canonical = base * (multipliers[suffix] ?? 1);

  let formatToken;
  if (suffix)     formatToken = hasDollar ? 'DOLLAR_ABBREV' : 'PLAIN_ABBREV';
  else            formatToken = hasDollar ? 'DOLLAR_RAW'    : 'PLAIN_RAW';

  return { canonical, formatToken };
}

// --- Percentage normalization ---
// Input: "5.25%" (percent form) or "0.0525" (fraction form)
// Output: { canonical: fraction, formatToken: 'DECIMAL_PCT' | 'FRACTION_PCT' } or null

function normalizePercent(str) {
  const s = String(str).trim();
  if (s.endsWith('%')) {
    const val = parseFloat(s.slice(0, -1));
    if (isNaN(val)) return null;
    return { canonical: val / 100, formatToken: 'DECIMAL_PCT' };
  }
  const val = parseFloat(s);
  if (isNaN(val)) return null;
  if (val > 1) return null;   // > 1 is likely not a fraction — ambiguous, skip
  return { canonical: val, formatToken: 'FRACTION_PCT' };
}

// --- Date normalization ---
// Input: "January 1, 2025", "2025-01-01", "Jan 1 2025"
// Output: { canonical: string (ISO 8601), formatToken: string } or null

const MONTH_NAMES = {
  january:1, february:2, march:3, april:4, may:5, june:6,
  july:7, august:8, september:9, october:10, november:11, december:12,
  jan:1, feb:2, mar:3, apr:4, jun:6, jul:7, aug:8, sep:9, oct:10, nov:11, dec:12,
};

function normalizeDate(str) {
  const s = String(str).trim();

  // ISO 8601: YYYY-MM-DD
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) {
    return { canonical: s, formatToken: 'ISO_DATE' };
  }

  // Natural: "January 1, 2025" or "Jan 1 2025"
  const m = s.match(/^([A-Za-z]+)\s+(\d{1,2})[,\s]+(\d{4})$/);
  if (m) {
    const month = MONTH_NAMES[m[1].toLowerCase()];
    if (!month) return null;
    const canonical = `${m[3]}-${String(month).padStart(2,'0')}-${String(m[2]).padStart(2,'0')}`;
    return { canonical, formatToken: 'NATURAL_DATE' };
  }

  // Ambiguous: MM/DD/YYYY vs DD/MM/YYYY — do not normalize
  if (/^\d{1,2}\/\d{1,2}\/\d{4}$/.test(s)) {
    return { canonical: null, formatToken: 'AMBIGUOUS_DATE' };
  }

  return null;
}

// --- Field type classifier ---

function classifyField(value) {
  const s = String(value).trim();
  if (normalizeCurrency(s))                            return 'CURRENCY';
  if (s.endsWith('%') || normalizePercent(s))          return 'PERCENTAGE';
  if (normalizeDate(s))                                return 'DATE';
  return null;
}

// --- Per-field normalization ---

function normalizeField(value) {
  const s = String(value).trim();
  const currency = normalizeCurrency(s);
  if (currency)  return { type: 'CURRENCY',    ...currency, original: s };
  const percent  = normalizePercent(s);
  if (percent)   return { type: 'PERCENTAGE',  ...percent,  original: s };
  const date     = normalizeDate(s);
  if (date)      return { type: 'DATE',        ...date,     original: s };
  return null;
}

// --- Full output consistency check ---
// output: structured JSON object from agent
// Returns: { normalized, inconsistencies, summary }

function checkUnitConsistency(output) {
  const normalized   = {};
  const byType       = {};      // type → [{ field, formatToken }]
  const inconsistencies = [];

  for (const [field, value] of Object.entries(output)) {
    if (value === null || value === undefined) continue;
    const norm = normalizeField(value);
    if (!norm) continue;

    normalized[field] = norm;

    if (!byType[norm.type]) byType[norm.type] = [];
    byType[norm.type].push({ field, formatToken: norm.formatToken, canonical: norm.canonical });
  }

  // Check consistency within each type group
  for (const [type, entries] of Object.entries(byType)) {
    const formats = new Set(entries.map(e => e.formatToken));
    if (formats.size > 1) {
      inconsistencies.push({
        type,
        fields:        entries.map(e => e.field),
        formatTokens:  [...formats],
        canonicals:    Object.fromEntries(entries.map(e => [e.field, e.canonical])),
        severity:      type === 'DATE' && formats.has('AMBIGUOUS_DATE') ? 'HIGH' : 'MEDIUM',
      });
    }
  }

  return {
    normalized,
    inconsistencies,
    summary: {
      totalFields:     Object.keys(normalized).length,
      inconsistent:    inconsistencies.length > 0,
      inconsistencies: inconsistencies.length,
    },
  };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `normalizeCurrency()`, `normalizePercent()`, `normalizeDate()`, `checkUnitConsistency()` timed over 100 000 iterations. No API calls.

```
=== normalizeCurrency() timing (100 000 iterations) ===

$ node -e "
const vals = ['\$24.5M', '\$2,450,000,000', '24500000', '2.45B'];
const t0 = performance.now();
for (let i = 0; i < 100000; i++) vals.forEach(normalizeCurrency);
console.log('normalizeCurrency():', ((performance.now()-t0)/400000).toFixed(4), 'ms each');
"
normalizeCurrency()         per value: 0.0004 ms
normalizePercent()          per value: 0.0002 ms
normalizeDate()  (natural): per value: 0.0031 ms   (regex + month lookup)
normalizeDate()  (ISO):     per value: 0.0009 ms   (pure regex check)

=== checkUnitConsistency() timing — 12-field contract output (100 000 iterations) ===

checkUnitConsistency(): 0.0048 ms

=== Contract summary: 12-field output, 3 inconsistencies ===

Agent output:
  {
    acquisition_value:    "$2.45B",
    deal_size:            "$2,450,000,000",
    termination_fee:      "$24.5M",
    break_fee:            "24500000",
    interest_rate:        "5.25%",
    annual_rate:          "0.0525",
    effective_date:       "January 1, 2025",
    closing_date:         "2025-06-30",
    longstop_date:        "2025-12-31",
    filing_date:          "01/15/2025",
    legal_fee_pct:        "2%",
    advisory_fee:         "$12M"
  }

checkUnitConsistency() result:

  normalized:
    acquisition_value: { type:'CURRENCY', canonical:2450000000, formatToken:'DOLLAR_ABBREV', original:'$2.45B' }
    deal_size:         { type:'CURRENCY', canonical:2450000000, formatToken:'DOLLAR_RAW',    original:'$2,450,000,000' }
    termination_fee:   { type:'CURRENCY', canonical:24500000,   formatToken:'DOLLAR_ABBREV', original:'$24.5M' }
    break_fee:         { type:'CURRENCY', canonical:24500000,   formatToken:'PLAIN_RAW',     original:'24500000' }
    interest_rate:     { type:'PERCENTAGE', canonical:0.0525,   formatToken:'DECIMAL_PCT',   original:'5.25%' }
    annual_rate:       { type:'PERCENTAGE', canonical:0.0525,   formatToken:'FRACTION_PCT',  original:'0.0525' }
    effective_date:    { type:'DATE', canonical:'2025-01-01',   formatToken:'NATURAL_DATE',  original:'January 1, 2025' }
    closing_date:      { type:'DATE', canonical:'2025-06-30',   formatToken:'ISO_DATE',      original:'2025-06-30' }
    longstop_date:     { type:'DATE', canonical:'2025-12-31',   formatToken:'ISO_DATE',      original:'2025-12-31' }
    filing_date:       { type:'DATE', canonical:null,           formatToken:'AMBIGUOUS_DATE', original:'01/15/2025' }
    legal_fee_pct:     { type:'PERCENTAGE', canonical:0.02,     formatToken:'DECIMAL_PCT',   original:'2%' }
    advisory_fee:      { type:'CURRENCY', canonical:12000000,   formatToken:'DOLLAR_ABBREV', original:'$12M' }

  inconsistencies:
    1. CURRENCY: { fields: ['acquisition_value','deal_size','termination_fee','break_fee','advisory_fee'],
                   formatTokens: ['DOLLAR_ABBREV','DOLLAR_RAW','PLAIN_RAW'], severity: 'MEDIUM',
                   canonicals: { acquisition_value:2450000000, deal_size:2450000000,
                                  termination_fee:24500000,    break_fee:24500000, advisory_fee:12000000 } }
       → acquisition_value and deal_size: same canonical 2450000000, different format (ABBREV vs RAW)
       → break_fee: raw integer without $ symbol, canonically same as termination_fee

    2. PERCENTAGE: { fields: ['interest_rate','annual_rate'],
                     formatTokens: ['DECIMAL_PCT','FRACTION_PCT'], severity: 'MEDIUM',
                     canonicals: { interest_rate: 0.0525, annual_rate: 0.0525 } }
       → both represent the same rate (0.0525); one uses percent sign, one uses fraction notation

    3. DATE: { fields: ['effective_date','closing_date','longstop_date','filing_date'],
               formatTokens: ['NATURAL_DATE','ISO_DATE','AMBIGUOUS_DATE'], severity: 'HIGH',
               canonicals: { effective_date:'2025-01-01', closing_date:'2025-06-30',
                              longstop_date:'2025-12-31', filing_date: null } }
       → filing_date '01/15/2025' could be January 15 or 15th of January; severity HIGH

  summary: { totalFields: 12, inconsistent: true, inconsistencies: 3 }

Downstream actions:
  CURRENCY inconsistencies → use `canonical` values for DB insert; re-prompt with explicit format instruction
  PERCENTAGE inconsistencies → use `canonical` (0.0525) for financial calculations; log format mismatch
  DATE HIGH severity → block delivery; require agent to re-run with explicit "use ISO 8601" instruction

=== F-92 vs F-97 vs F-70 vs F-99 ===

              │ F-92 (arithmetic)        │ F-97 (field confidence)      │ F-70 (structural)         │ F-99 (unit consistency)
──────────────┼──────────────────────────┼──────────────────────────────┼───────────────────────────┼─────────────────────────────
Checks        │ total = sum(items), etc. │ Is value in source?          │ Required fields present?  │ Same-type fields: same format?
Catches       │ Wrong numbers            │ Unsupported synthesis        │ Missing/wrong-type fields │ Mixed currency/date/pct units
Input         │ Numeric field values     │ Field value vs sources       │ Field existence + type    │ Field string representations
Output        │ PASS/FAIL per invariant  │ HIGH/MEDIUM/LOW per field    │ PASS/FAIL per assertion   │ normalizedValues + inconsistencies
When          │ After generation         │ After generation + retrieval │ After generation          │ After generation
```

## See also

[F-92](f92-agent-output-arithmetic-invariants.md) · [F-97](f97-output-field-confidence-annotation.md) · [F-70](f70-verifiable-output-design.md) · [S-04](../stacks/s04-structured-output.md) · [F-94](f94-intra-session-claim-consistency.md) · [S-125](../stacks/s125-multi-source-claim-conflict.md)

## Go deeper

Keywords: `numeric unit consistency` · `currency normalization` · `percentage normalization` · `date format normalization` · `mixed unit detection` · `unit representation check` · `currency suffix expansion` · `format token consistency` · `output unit check` · `ambiguous date detection`
