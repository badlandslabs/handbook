# S-1832 · The Consensus Trap Stack — When Your Majority-Voted Multi-Agent System Tips Into Catastrophic Failure

Your multi-agent reasoning pipeline uses majority voting across five agents to surface the most reliable answer. Your adversarial-content filter catches the obvious attacks. The prompt injection detection layer flags the loud attempts. And yet your system still outputs confidently wrong answers at scale — because a corrupted agent that passes every filter, when embedded in a majority-voted system, doesn't need to break the guardrails. It just needs to outvote them. This is the consensus trap: the security of majority voting depends on the integrity of every voter, and integrity is not checked by a vote.

## Forces

- **Majority voting is blind to intermediate logic.** A corrupted agent can produce a perfectly fluent, high-confidence answer that is wrong at the reasoning level — and if it's in the majority, the system returns it as correct. Voting aggregates conclusions, not reasoning chains. The flaw is architectural, not statistical.
- **Stealthy corruption outruns detection.** Prompt injection filters catch explicit attacks ("Ignore previous instructions"). They do not catch contextual corruption — a poisoned document that subtly shifts an agent's framing of a question, or an agent fine-tuned to produce persuasive distractors. These agents pass every capability check and every safety check, but their outputs are systematically wrong when acting in concert.
- **The corruption threshold is 50%.** With response-level aggregation, a corrupted minority can do nothing. A corrupted majority flips the system. The transition from safe to dangerous is binary and invisible — there is no graceful degradation, no warning shot, no degraded-but-functional state.
- **Multi-agent reasoning adoption is accelerating.** Majority-voted ensembles are now standard in production pipelines for code generation, document analysis, and financial reasoning. The vulnerability surface is large and growing.

## The move

**Detect before you vote.** Replace response-level aggregation with token-level round-robin collaboration:

```
Agent A generates  → [TOKEN BATCH]
Agent B sees A's tokens → generates continuation
Agent C sees A+B → generates continuation
Final output = joint generation with traceable reasoning

# Instead of:
Agent A → answer
Agent B → answer
Agent C → answer
Majority vote → output  (blind to reasoning)
```

**The key structural change:** agents see each other's *tokens as they are generated*, not after the fact. Agent B's generation is conditioned on Agent A's actual reasoning, not on a polished answer. Flawed intermediate logic is visible in the generation stream and can be detected by downstream agents before conclusions solidify.

**Detection layer (if you must keep voting):** Run a lightweight logic-provenance check on each agent's response before aggregating — does the conclusion follow from the stated premises? Even a simple chain-of-thought consistency scorer catches the corruption signal before the vote.

**Corruption resistance scaling:** The paper shows token-level RR maintains accuracy even at 70% corruption (vs. majority voting accuracy collapsing at 50%). Design for the corruption scenario, not the nominal case.

## Receipt

> Verified — arXiv:2604.17139 (Liu, Du, Du, Guo, Conitzer, Apr 2026): majority voting collapses at 50% corrupted agents; token-level round-robin maintains robust accuracy through 70% corruption. Empirical results across GSM8K, MATH, and CommonsenseQA. Stealthy corruption types characterized (advisory vs. imperative). No existing handbook entry covers this failure mode. S-1052 (cascade) covers content propagation; S-1827 covers emergent adversarial behavior — neither addresses the aggregation-layer vulnerability in majority-voted reasoning systems.

## See also

- [S-1052 · The Cascade Stack](s1052-the-cascade-stack-when-one-wrong-answer-infects-your-entire-multi-agent-pipeline.md) — false claim propagation through multi-agent pipelines
- [S-1827 · The Emergent Adversarial Multi-Agent Stack](s1827-the-emergent-adversarial-multi-agent-stack-when-your-agents-dont-compete-but-they-do-anyway.md) — adversarial convergence in shared resource environments
- [S-1831 · The Agent Trajectory Evaluation Stack](s1831-the-agent-trajectory-evaluation-stack-when-your-agent-passes-all-checks-and-still-fails-in-production.md) — evaluating the reasoning path, not just the output
