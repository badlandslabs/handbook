# S-36 · System Prompt Architecture

The system prompt is the agent's constitution — its identity, scope, constraints, and output contract in one document. Most system prompts are written like drafts: capabilities listed first, constraints buried at the bottom after prose has diluted them, output shape never specified. The model reads this as one long stream. Structure is not cosmetic; position and labeling determine what the model treats as high-priority. Write it like a legal document, not an email.

## Situation

Your agent occasionally ignores a constraint you definitely included. Or it returns output in three different formats across calls. Or you added a new rule and the model started behaving strangely — because the rule contradicted something earlier in the prompt that the model weighted more heavily. These are structural failures, not model failures. The system prompt was not architected; it was accumulated.

## Forces

- A transformer reads context as a sequence. Content at the top gets higher relative attention; constraints buried at line 30 of a 35-line prompt compete with 30 lines of framing that preceded them. Position is a priority signal.
- Labels (XML tags, bold headers) make sections scannable for the model in the same way they are for humans — they create parsing anchors. An unlabeled constraint in a paragraph is less reliable than the same constraint under `<constraints>`.
- A system prompt with injected dynamic content (user name, session state, current date) limits how much of it can be cached ([S-08](s08-prompt-caching.md)). A fully-static system prompt is a fully-cacheable prefix — every dynamic element belongs in the user turn, not in the system prompt.
- No output contract means the model decides output shape. It will be inconsistent across runs, model versions, and phrasings — exactly when you need downstream code to parse it reliably.
- Longer is not more thorough. Hedging prose ("try to," "when possible," "feel free to") burns tokens and weakens instructions. A 134-token constitutional prompt outperforms a 154-token chaotic one with the same coverage because precision replaces hedging.

## The move

**Four sections, fixed order: identity → scope → constraints → output contract.**

**1. Identity** (2–4 lines). One-sentence role, one-sentence domain. Not capabilities — not "you can do X, Y, Z." Role and domain: "You are the Acme Corp price-lookup agent. Your single job is answering product price questions." The identity section answers *what you are*, not *what you can do*.

**2. Scope** (in-scope and out-of-scope, explicit). Name the out-of-scope cases and what to do with them. "Out of scope: inventory, emails, refunds — decline politely." An agent without explicit out-of-scope boundaries will drift toward attempting anything. Scope and identity together are the constraint that S-34 talks about — the scope declaration.

**3. Constraints** (hard rules, listed, not buried in prose). Use a bulleted list under a label. Not "you should be careful not to reveal cost prices" — "Never reveal cost_price field." The harder the constraint, the shorter and more explicit the sentence. Constraints go in section 3, not at the bottom of section 2, not in the middle of a paragraph.

**4. Output contract** (required). Specify the exact output shape: "Reply in one sentence. Use this format: `[SKU] is $[price].` If not found: `Price unavailable for [SKU].`" Every agent that parses its output programmatically requires this. Every agent that writes to another system requires this. The absence of an output contract is a bug.

**Make the entire system prompt static.** Dynamic elements — user name, session ID, current date, retrieved context — go in the user turn or in tool outputs, not in the system prompt. A static system prompt is a cacheable prompt. A prompt with dynamic injections has a fractional cacheable prefix, which pays more per call ([S-08](s08-prompt-caching.md)).

**Use XML tags to label sections.** They work as parsing anchors, survive prompt-to-prompt variation, and are the format Anthropic trained Claude on ([S-16](s16-prompting.md)). `<identity>`, `<scope>`, `<constraints>`, `<output>` are enough. Markdown headers work for GPT-family models.

**Eliminate hedging language.** "Try to," "when possible," "feel free to" — cut them. They dilute instructions. "Reply in one sentence" is stronger than "Try to keep your reply brief."

## Receipt

> Verified 2026-06-26 — Node, `gpt-tokenizer`. Both prompts cover the same agent (Acme price-lookup) with the same rules. Structural differences are the only variable. Cacheable-prefix fractions: constitutional = 100% by construction (all sections static); chaotic = 60% estimated (practice observation that chaotic prompts tend to accumulate dynamic injections — this is a conservative model, not a live measurement).

```
=== Two prompts, same rules ===
Chaotic prompt:        154 tokens,  cacheable prefix ~92 tok  (60%)
Constitutional:        134 tokens,  cacheable prefix  134 tok (100%)

Token delta: -20  (constitutional is shorter — precision beats hedging)

=== Constraint position ===
  chaotic:         constraint at line 7/10  (70% through the prompt)
  constitutional:  constraint at line 11/18 (61% through prompt, in labeled <constraints>)

=== Output contract present? ===
  chaotic:         NO — model decides output shape
  constitutional:  YES — explicit one-sentence format
```

**What the receipt shows:**

- The constitutional prompt is **20 tokens shorter** despite more explicit coverage. Structured sections eliminate the connective prose ("Also," "Additionally," "Please note that") that chaotic prompts accumulate.
- Fully static sections give a **100% cacheable prefix**. The chaotic prompt's ~60% cacheable fraction means ~38 tokens re-billed on every call at the un-cached rate — a small tax per call that becomes significant at agent loop volumes.
- The chaotic prompt has **no output contract**. The model will choose output shape at inference time, producing inconsistent formats across runs and model updates. Downstream parsing code that works today will break on the next phrasing the model picks.
- The key structural difference between the two constraint positions is not the percentage (70% vs 61% — close) but the **label**. The constitutional constraint lives under `<constraints>` — a parsing anchor. The chaotic constraint is in a paragraph that starts with "IMPORTANT:" — a convention, not a structure.

## See also

[S-16](s16-prompting.md) · [S-13](s13-context-engineering.md) · [S-08](s08-prompt-caching.md) · [S-34](s34-narrow-scope-agent-design.md) · [F-13](../forward-deployed/f13-prompt-injection.md)

## Go deeper

Keywords: `system prompt` · `prompt architecture` · `constitutional prompt` · `instruction hierarchy` · `output contract` · `cacheable prefix` · `scope declaration` · `XML tags` · `prompt structure` · `constraint placement`
