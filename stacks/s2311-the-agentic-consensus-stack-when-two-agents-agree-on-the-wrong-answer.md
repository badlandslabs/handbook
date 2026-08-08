# S-2311 · The Agentic Consensus Stack — When Two Agents Agree on the Wrong Answer

Your two specialist agents reviewed the contract. Both returned "no material risk." Your investment committee approved. Three weeks later, the counterparty's force-majeure clause triggered a $2.3M loss — and both agents had missed the same subclause. This is not a model quality problem. This is a consensus architecture problem. Multiple agents don't guarantee correctness; they guarantee correlated confidence. [S-29](s29-false-consensus.md) covers why agreement isn't truth. This entry covers what to build instead.

## Forces

- **Same-model agents share blind spots.** A classifier and a summarizer built on the same base model fail on the same inputs the same way. Majority vote amplifies this, not cancels it — you get the illusion of independence you didn't buy.
- **Disagreement is information, not noise.** When two agents disagree, the system now knows the answer is non-obvious. Most teams paper over disagreement with a third vote instead of surfacing it for escalation or deeper analysis.
- **Consensus without independence is theater.** Agents that see each other's outputs before voting are no longer independent verifiers — they are a chorus harmonizing on the same pitch.
- **The cost of consensus scales superlinearly.** A 3-agent jury is 3× the cost and 3× the token budget. A 5-agent jury is 5×. Teams routinely underprice this and then cut corners at the worst moment.
- **Safety-critical decisions demand the highest confidence, not the fastest vote.** The fastest path to consensus is one agent making the call. The safest path is expensive. Most systems choose speed at design time and regret it at incident time.

## The move

**Three patterns, ordered by increasing cost and confidence:**

### Pattern 1 — Independent Parallel (minimum bar)

Each agent generates its answer without seeing others' outputs. Classic blind vote.

```
Agent A: "Risk rating: LOW"     → blind
Agent B: "Risk rating: LOW"     → blind
Agent C: "Risk rating: LOW"     → blind
→ Majority: LOW (but all same model = correlated failure)
```

**When to use:** Style differences, format synthesis, anything where wrong answers are cheap.

**Critical constraint:** Agents MUST NOT see each other's outputs before committing. Enforce this architecturally — not via a prompt instruction.

### Pattern 2 — Adversarial Debate (elevated confidence)

Agents see each other's answers and must argue against the weakest position. A moderator judges.

```
Agent A → position
Agent B → position
If A ≠ B: expose both positions, each must critique the other
Moderator (or Agent C) → selects winner + rationale
```

Tian Pan (tianpan.co, Apr 2026): debate patterns reveal disagreement that parallel voting hides. When agents must defend their answer against a live critique, incorrect positions often self-collapse. The survivors carry higher confidence.

**Implementation:** Use a separate "arbiter" agent that never generates the primary answer — only judges. Keep the arbiter model-diverse from the debaters if possible.

**When to use:** Research synthesis, risk analysis, code review where a wrong answer is expensive but not catastrophic.

### Pattern 3 — Jury with Independence Guarantee (maximum confidence)

Inspired by AgentMarketCap's consensus taxonomy (Apr 2026). Requirements for genuine independence:

- **Model diversity:** Use different base models across jury members. Claude + GPT + Gemini on the same task = genuine blind-spot diversity.
- **Prompt diversity:** Slight variations in system prompts produce meaningfully different sampling paths.
- **Context slicing:** Each agent sees a different chunk of the evidence. No agent has the complete picture until the verdict.
- **No cross-visibility:** Architecture enforces that Agent A's output never appears in Agent B's context window until voting closes.

```
Jury[Claude, GPT, Gemini]
  for each juror:
    generate(position, evidence_slice_juror)
  collect(all positions)
  if unanimous_wrong: escalate_to_human()  ← the failure mode no pattern catches
  else if majority:
    return majority_position
  else:
    escalate()  ← disagreement = non-obvious case
```

The `escalate_to_human()` on unanimous wrong answers is the pattern most consensus systems miss. You cannot solve this architecturally — identical models on identical evidence produce identical blind spots. The only defense is human review of unanimous verdicts above a materiality threshold.

## Cost / Confidence Tradeoffs

| Pattern | Extra Cost | Confidence Gain | When It Wins |
|---------|-----------|-----------------|--------------|
| Independent Parallel | 2–3× base | Marginal — same blind spots | Style, formatting, cheap errors |
| Adversarial Debate | 2.5–4× base | Significant — weak positions collapse | Non-critical risk analysis |
| Jury w/ Independence | 3–5× base | Highest — genuine diversity | Safety-critical, legal, financial |

## The Consensus Failure Mode Nobody Catches

The unanimous-wrong verdict. Every pattern above handles disagreement. None handles the case where the jury is perfectly confident and perfectly wrong. For safety-critical decisions:

```python
def execute_with_consensus_verdict(agents, task, materiality_threshold):
    positions = [a.execute(task) for a in agents]
    verdict = resolve(positions)

    if all_identical(positions) and verdict_confidence(verdict) < 0.7:
        # Uniform high confidence on non-obvious task = suspicious
        # Blind spots may be aligning, not agreeing
        return escalate_to_human(task, reason="unanimous_concerning")

    if all_identical(positions) and materiality(task) > materiality_threshold:
        return escalate_to_human(task, reason="unanimous_material")

    return verdict
```

The key insight from S-29 (False Consensus): the moment the first agent's answer is visible, independence is gone. Implement consensus *architecture* — not consensus *prompts*.

## See also
- [S-29 · False Consensus](s29-false-consensus.md) — agreement isn't truth; vote only over independent samples
- [S-23 · Self-Consistency](s23-self-consistency.md) — sampling multiple reasoning paths from one model
- [S-41 · Agent Handoff Patterns](s41-agent-handoff-patterns.md) — structured information transfer between agents
- [S-1013 · The Multi-Agent Boundary Stack](s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — state disagreement in shared-context workflows
- [S-2211 · The Scaffold Effect Stack](s2211-the-scaffold-effect-stack-when-your-model-isnt-the-problem-and-the-harness-is.md) — how evaluation infrastructure shapes what agents produce
