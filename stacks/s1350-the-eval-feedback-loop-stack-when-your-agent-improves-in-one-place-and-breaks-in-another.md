# S-1350 · The Eval Feedback Loop Stack

When you change a prompt, swap a model, or add a tool, you have no way to know if you improved or regressed your agent. You ship on vibes and discover the answer when users complain. Every team that skips evaluation shares the same surprise: the change that fixed the obvious problem introduced three subtle ones.

## Forces

- **Agents are non-deterministic** — the same input can yield two valid but different outputs, so "did it pass?" is rarely a binary question
- **Silent failures are the real danger** — an agent can return the right answer via the wrong reasoning path, and pass a shallow eval while hiding a lurking bug
- **Benchmarks lie** — UC Berkeley researchers found all eight major agent benchmarks (SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR-bench) can be gamed to near-perfect scores without solving real tasks; one team gamed 890 tasks with a single character change
- **Synthetic test data has a ceiling** — engineered prompts cover what engineers imagined, while production surfaces the long tail of real user behavior, malformed inputs, and ambiguous phrasings that no one would have invented

## The move

Eval-driven development treats evaluation not as a release gate but as a continuous feedback loop. The core pattern is **Data + Task + Scorers** (Braintrust's framing), applied across four layers:

- **Layer 1 — Outcome:** Did the agent achieve the goal? Check final output correctness, task completion, safety, and policy compliance.
- **Layer 2 — Reasoning:** Did it decompose the problem correctly? Inspect the trajectory — not just the result. A correct answer via a broken process is a silent failure waiting to recur.
- **Layer 3 — Tool use:** Did it call the right tools with the right parameters? Was it efficient? Redundant tool call loops are a common cost and quality killer caught only at this layer.
- **Layer 4 — Efficiency:** How many steps, tokens, and API calls did it take? Cost-per-task and step budget are first-class metrics, not afterthoughts.

**The production-trace loop** is the highest-signal eval data source: every production failure generates a trace, the trace becomes a permanent test case, the test case joins a regression dataset, and the dataset gates every CI run. This loop means coverage grows automatically — you don't have to imagine edge cases, real users hand them to you.

**Three scorer types** cover the quality spectrum:
- **Ground truth** — deterministic assertions for cases where you know the exact correct output
- **LLM-as-judge** — a separate model grades nuanced qualities (helpfulness, coherence, reasoning quality) that have no single right answer
- **Human-in-the-loop** — for high-stakes outputs or novel failure modes, human ratings anchor the eval before automation takes over

**Validate your evaluator.** An eval that doesn't correlate with user value is a sophisticated way to measure the wrong thing. The validation routine: pick the user signal (thumbs up rate, deflection, conversion), run it against your eval scores, and check correlation before treating the eval as authoritative.

## Evidence

- **Google Cloud Blog (Nov 2025):** Outlines the four-layer evaluation stack and silent failure problem — agents can produce correct outputs through incorrect processes. Recommends three data generation strategies: dueling LLMs for synthetic conversations, anonymized production data for golden datasets, and human-in-the-loop trace curation. — [URL](https://cloud.google.com/blog/topics/developers-practitioners/a-methodical-approach-to-agent-evaluation)
- **Agent Factory / Google Cloud (Oct 2025):** Distinguishes agent eval from traditional software testing and LLM eval. The analogy: traditional testing is an exam, LLM testing is a school exam, agent eval is a job performance review — the agent must be assessed on autonomy, reasoning trajectory, tool efficiency, and context retention, not just output correctness. — [URL](https://cloud.google.com/blog/topics/developers-practitioners/agent-factory-recap-a-deep-dive-into-agent-evaluation-practical-tooling-and-multi-agent-systems)
- **Arthur.ai (Jun 2026):** The production-failure-to-regression-dataset loop. "The highest-value regression test dataset for an AI agent is not handcrafted. It comes from production failures." Documents how production traces eliminate dataset drift because evaluation data is always current — edge cases arrive automatically and coverage evolves as the product does. — [URL](https://www.arthur.ai/column/regression-test-datasets-ai-agents-production-failures)
- **Zylos Research (May 2026):** UC Berkeley benchmark analysis finding all eight major agent benchmarks exploitable. Argues static task-completion scores fail to capture what matters in production: reliability, cost efficiency, safety, and long-horizon competence. — [URL](https://zylos.ai/zh/research/2026-05-13-ai-agent-evaluation-benchmarking)
- **Braintrust (May 2026):** The Data + Task + Scorer pattern as the minimal eval unit. Emphasizes that production traces become test cases and evals run ahead of deploys, not after. — [URL](https://www.braintrust.dev/articles/how-to-eval)
- **KDD 2025 Tutorial:** A systematic two-dimensional taxonomy of LLM agent evaluation: evaluation objectives (what to measure) and evaluation process (how to measure). — [URL](https://sap-samples.github.io/llm-agents-eval-tutorial)

## Gotchas

- **Don't benchmark-drive development.** If your team optimizes for benchmark scores rather than user outcomes, you're gaming the metric, not improving the product. Treat benchmarks as one signal among many.
- **Golden datasets go stale.** A dataset created today reflects the product as it was then. Model updates, prompt changes, and new features all shift the target. Production traces stay current; golden datasets require active maintenance.
- **LLM-as-judge has a preference bias.** Models tend to score their own reasoning style higher. Calibrate judge models against human-rated samples before treating their scores as ground truth.
- **Step count and cost are eval signals, not just monitoring metrics.** Many teams track token usage but never assert on it. An agent that solves a task in 3 steps vs. 12 steps is a different product at a different cost — both should be measured and regression-tested.
- **Eval scope must match agent scope.** Evaluating a single LLM call is not the same as evaluating a multi-step agent. Don't substitute component-level eval for end-to-end task eval.
