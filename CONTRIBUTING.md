# Contributing to The AI Agent Handbook

The handbook is open. Fork it, improve it, submit a PR. Here is what makes a contribution land.

---

## The one hard rule

**No fabrication.** Every technique, every example, every run log must come from reality. If you haven't run it, mark it `Receipt pending — [date]`. Do not invent output. Do not round numbers. A fabricated receipt is grounds for rejection, not a style note.

---

## Entry format

Every entry follows this skeleton:

```markdown
# [Code] · [Name]

[One-sentence situation — where this bites, when you reach for it]

## Forces
- [tension 1]
- [tension 2]
- [what makes this non-obvious]

## The move
[The technique. Key points only — no paragraph blobs. If complex, give keywords.]

```language
[Minimal working example]
```

## Receipt
> Verified [date] — [what was actually run, actual output trimmed to signal]

## See also
[S-02](stacks/s02-context-budget.md) · [W-03](workspace/w03-local-models-ollama.md)

## Go deeper
Keywords: `[term1]` · `[term2]` · `[term3]`
```

---

## What makes a good entry

- Solves one problem, not three
- Usable by a student and a principal engineer (different depths, same words)
- Has a receipt, or is honest that it doesn't
- Short. If you need more than 400 words, split it into two entries
- Links to 2–5 siblings

---

## Codes

| Prefix | Book |
|---|---|
| `S-NN` | Book of Stacks |
| `W-NN` | Book of the Workspace |
| `F-NN` | Book of the Forward-Deployed Engineer |
| `R-NN` | Book of the Frontier |

Take the next available number in the sequence. Don't reuse numbers.

---

## Raising an issue

Use the issue templates:
- **Entry request** — suggest a topic that belongs in the handbook
- **Correction** — something is wrong, stale, or fabricated

---

## Law amendments

Amending a Law requires: a written reason, the entry that exposed the flaw, and consensus in the PR. Laws move rarely.
