# S-29 · False Consensus

Multi-agent "debate" and "review" are sold as **independent verification** — a panel catches what one agent misses. But agreement isn't truth. If the reviewers share a blind spot or see each other's answers, the panel ratifies the mistake with high, false confidence. The dark twin of [S-24](s24-self-consistency.md): voting helps *only* when the votes are genuinely independent.

## Forces
- The whole pitch for a panel is "two heads beat one" — but if they share a head, you paid for a chorus
- Agents on the **same base model** share correlated blind spots: they fail on the same inputs, the same way, so a vote *confirms* the shared error
- The moment one agent's answer is visible, independence is gone — LLMs can tilt toward a stated majority (conformity/sycophancy)
- Handoffs compress context; agents reconstruct from a lossy summary and can drift together, away from ground truth
- A panel that *looks* unanimous gets treated as ground truth downstream — false confidence is the worst thing to ship

## The move
- **Don't vote over a discussion.** Voting helps only over *independent* samples ([S-24](s24-self-consistency.md)). The moment agents read each other first, you've destroyed the independence that made the vote worth anything.
- **Diverse base models for verification.** Same model twice is one model twice — it shares its own blind spots. A checker on a different family/size breaks the correlation.
- **Keep the verifier blind.** The checker sees the problem and the work, not the proposer's verdict — review the work, not the answer.
- **Force dissent before discussion.** If agents must confer, make each commit an independent verdict *first*, then aggregate. Post-hoc "we discussed and agreed" is consensus laundering.
- **Prefer an objective verifier** — tests, schema, a deterministic tool ([R-07](../frontier/r07-post-training-rlvr.md), [S-25](s25-reflection.md)). No amount of agent agreement beats one passing test.

## Receipt
> Verified 2026-06-26 — a "panel" of 10 independent agents, all the **same base model** (llama3.2 via Ollama, localhost:11435), on a trap riddle: "A farmer has 17 sheep. All but 9 die. How many are left?" Correct = **9** (all *except* 9 die). Each agent answered independently; we then majority-vote.

```
panel answers: [8, 8, 9, 8, 8, 8, 9, 9, 8, 8]
tally: { "8": 7, "9": 3 }
majority vote: 8  (7/10)  -> WRONG   (correct is 9)
=> 70% consensus on the WRONG answer
```

Three agents read the trap correctly; the majority fell for `17 − 9 = 8` and **outvoted them**. A "7 of 10 reviewers agree" signal would have shipped the wrong answer with high confidence — because the agents share one model's blind spot, the vote laundered a correlated failure into false consensus. This is exactly when [S-24](s24-self-consistency.md) *inverts*: majority vote rescues you when the model is usually right (it suppresses outliers), but **confirms the error** when the model is usually wrong. (The other mechanism — conformity to a stated majority — is documented but model-dependent: in a separate test, llama3.2 *resisted* a fake "3 reviewers said $0.10" prompt on the bat-and-ball problem, holding the correct answer 10/10. Correlated failure is structural; conformity is variable. Don't rely on either being absent.)

## See also
[S-24](s24-self-consistency.md) · [S-05](s05-multi-agent-patterns.md) · [S-25](s25-reflection.md) · [F-12](../forward-deployed/f12-llm-as-a-judge.md) · [F-11](../forward-deployed/f11-agent-reliability.md)

## Go deeper
Keywords: `false consensus` · `multi-agent debate` · `correlated failure` · `sycophancy` · `conformity` · `independent verification` · `LLM-as-judge` · `ensemble diversity` · `self-consistency`
