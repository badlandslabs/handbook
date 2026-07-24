# S-1588 · The Agent Eval Calibration Stack — When Your Test Suite Says Pass and Your Users Say Fail

Your agent hits 94% on your internal eval. Your users are leaving. Your QA team can't explain the gap — the unit tests pass, the regression suite is green, and the LLM judge gives everything a 4/5. The agent is technically correct on every measurable axis and behaviorally wrong on the ones that matter: it takes too long, it explains things nobody asked for, it gets the right answer by reasoning that falls apart on edge cases, and it won't recover gracefully when it fails. Your eval is measuring the wrong thing, or measuring it right but at the wrong granularity, or measuring it at the right granularity but with a judge that has its own biases. This is the calibration problem: closing the gap between what your eval says and what your users experience.

## Forces

- Agent behavior is non-deterministic — a single trial is not a measurement; it's one draw from a distribution
- Defining success criteria for agents is harder than implementing them — "did the agent do the right thing" resists simple assertions
- Deterministic assertions (exact match, regex) cover happy paths but miss the emergent failure modes that define real agent quality
- LLM-as-judge introduces its own systematic biases — verbosity inflation (~15% score bonus for longer outputs), position preference in pairwise comparison, self-preference when the judge model is the same family
- A passing eval means nothing if it doesn't correlate with user outcomes
- Building evals after the agent exists means you're testing post-hoc, not defining behavior — teams that write evals first encode expected behavior explicitly and catch regressions faster
- Grading the final output misses the trajectory — an agent can reach the right answer through the wrong reasoning and still score high on outcome-only evaluation

## The move

**The core principle: eval before you build, grade the trajectory, and trust assertions over judges for things you can assert.**

### 1. Define the eval hierarchy first

Build a layered grading stack, not a single judge call:

- **L0 — Assertions:** Deterministic checks for things you can verify programmatically. Tool was called? API returned 200? File exists? Output matches a schema? These are fast, unambiguous, and don't hallucinate. Cover everything you can with assertions; use LLM grading only for what's left.
- **L1 — Golden transcript comparison:** Record a correct agent run as ground truth. Compare subsequent runs against it — tool call sequence, state changes, output structure. Catch regressions in the "how" not just the "what."
- **L2 — LLM-assisted grading:** Use a judge model for subjective quality signals that assertions can't cover — did the explanation make sense? Was the error message helpful? Did the agent recover appropriately? Keep the rubric narrow and concrete.
- **L3 — LLM-as-judge for trajectory:** Score the full reasoning path, not just the output. An agent that reaches the right answer via broken logic is a failure even if the outcome passes.

### 2. Run multiple trials

Agent output is non-deterministic. A single run is one data point, not a measurement. Anthropic's Claude Code team runs 3-5 trials per task and reports the distribution, not just the mean. A 70% pass rate across 5 trials with variance of ±15% means something different than a flat 70% with no variance — the former reveals instability, the latter hides it.

### 3. Calibrate your judge for systematic biases

LLM judges have well-documented failure modes. Before trusting judge scores:

- **Verbosity bias correction:** Score a known-good short answer against a known-good long answer. If the judge systematically rates longer answers higher, normalize scores or switch judges. Impact: ~15% score inflation for responses over 400 words (AgentMarketCap, 2026).
- **Position preference:** In pairwise comparisons, judges tend to prefer the first or second option depending on model family. Randomize order and run each comparison twice with reversed positions.
- **Self-preference:** A judge from the same model family as the agent may score it higher. Use a different model family for the judge — e.g., a Claude judge for a GPT-agent, or a distilled judge (Prometheus 2 7B, Patronus Lynx 8B) for cost efficiency at 0.88–0.95 accuracy vs. GPT-4o.
- **Reference anchor:** Always provide the judge with a concrete rubric and 2–3 scored examples (anchor calibration). Unanchored judges show higher variance and stronger position bias.

### 4. Place judges at the right boundaries — not everywhere

Per-step judging adds latency, cost, and noise. Strategic placement:

- **Before user output:** Gate what the user sees. This is the highest-value judgment point.
- **Before irreversible tool execution:** Verify the tool call is appropriate before it executes a destructive or costly action.
- **On memory writes:** Validate that the agent is correctly recording state before persisting it.
- **Skip inline judging on every intermediate step:** It doubles token cost and introduces decision fatigue for the judge.

### 5. Make eval data a first-class artifact

Store every eval run as a versioned dataset. SMOLTRACE (Hugging Face, 2026) writes 4 versioned datasets per eval run — input, reference, output, and scores — so every eval is reproducible and queryable. This matters because eval results without traces are unverifiable; traces without versioning are uncomparably.

### 6. Relate evals to user outcomes

If your eval score and your user satisfaction score aren't correlated, your eval is measuring the wrong thing. Track both. A common failure: the agent passes all internal evals but NPS drops — the eval missed a behavioral dimension (verbosity, tone, recovery behavior) that users care about but the rubric didn't capture.

## Evidence

- **Company engineering post (Anthropic, Jan 2026):** Claude Code and enterprise deployments with companies like Descript, Bolt AI, Stripe, and Shopify used the task/trial/grader model; recommended building evals before the agent and using assertions for everything deterministic. — https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
- **Research synthesis (AgentMarketCap, Apr 2026):** Documented three scoring variants (pointwise, reference-based, pairwise); quantified LLM-as-judge cost at $0.001–$0.05/eval vs. $0.10–$3.00 for human annotation ($150 vs. $15,000 for 10,000 cases); quantified verbosity bias at ~15% score inflation for responses over 400 words. — https://agentmarketcap.ai/blog/2026/04/11/llm-as-judge-agent-output-evaluation-2026
- **HN comment / post:** Practitioner documented that benchmark-style eval approaches fail in production — agents pass deterministic tests but miss behavioral failure modes; recommended combining deterministic assertions with trajectory-level evaluation. — https://news.ycombinator.com/item?id=47416033
- **Research synthesis (Zylos Research, Apr–May 2026):** Small distilled judges (Luna-2 3B–8B, Prometheus 2 7B, Patronus Lynx 8B) deliver 97% cost reduction at 0.88–0.95 accuracy vs. GPT-4o; intrinsic self-correction without external grounding degrades performance; 57%+ of production agent teams use judge LLMs at runtime. — https://zylos.ai/en/research/2026-04-10-llm-as-judge-production-agent-verification-2026/, https://zylos.ai/en/research/2026-05-26-llm-as-judge-agent-evaluation-patterns/

## Gotchas

- **Don't judge every turn.** Inline per-step LLM judging doubles your token cost and introduces judge noise that compounds. Gate at boundaries, not steps.
- **Ungrounded self-correction backfires.** Reflexion-style "check your work" loops without external grounding degrade performance on reasoning tasks — the model reinforces its own errors. Self-correction only helps when grounded to an external reference (retrieved docs, tool outputs, memory state).
- **Correlation doesn't prove causation on eval improvement.** A higher eval score after a change could mean the agent improved, the judge became more lenient, the test cases got easier, or the sample shifted. Track judge version, test case version, and sample composition alongside scores.
- **Outcome-only grading misses the trajectory.** An agent that reaches the right answer through broken reasoning is a failure waiting to happen on the next edge case. Grade the path, not just the destination.
