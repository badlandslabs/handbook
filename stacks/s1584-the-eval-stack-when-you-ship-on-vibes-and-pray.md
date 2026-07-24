# S-1584 · The Eval Stack: When You Ship on Vibes and Pray

You deployed a customer-service agent. Task completion is "good." Latency is fine. Cost is within budget. But you have no idea if the agent is hallucinating answers, looping on edge cases, or drifting off-policy on regulated topics. Your eval strategy is a held-out set of 20 questions your PM wrote last quarter. This is the eval stack — the measurement system that separates production-grade agents from demos that happen to work.

## Forces

- **Standard benchmarks lie.** UC Berkeley found all eight major agent benchmarks (SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR-bench) could be gamed to near-perfect scores without solving the underlying task. A team gamed 890 tasks with a single character change.
- **Final-answer pass/fail hides path failure.** An agent can reach the right answer via a catastrophic trajectory — 47 tool calls, three policy violations, and a hallucination corrected by luck. That run scores 100% on standard evals.
- **Golden datasets go stale.** A curated eval set captures the agent as it was when built, not as it operates after prompt edits, model swaps, and RAG updates. Graders keep reporting pass against inputs that no longer reflect live behavior.
- **95% of AI projects fail** (MIT, via Forbes/Thoughtworks). The primary cause is not bad models — it is teams that cannot measure whether the system is working.

## The Move

Build a three-layer eval stack and close the production trace loop:

**Layer 1 — Final-answer eval:** Did the task complete? Check the resulting database or system state, not just the final text. tau-bench sets the standard here — it verifies both the answer and the resulting state.

**Layer 2 — Trajectory eval:** Was the path efficient? Count steps, tool calls, retries, and handoffs. Detect looping (same tool called 3+ times with no progress) and excessive wandering (steps exceeding 1.5× the expected trajectory length). This is where efficiency and recovery are measured.

**Layer 3 — Per-turn eval:** Was each individual step correct? Classify each turn as on-policy or off-policy, grounded or hallucinated, safe or policy-violating. Use deterministic checks for tool selection correctness (schema validation) and LLM-as-judge for groundedness and policy alignment.

**The trace flywheel:** Capture production traces → analyze to find failure patterns → build regression datasets from real traffic → run evals before every deploy → feed production failures back into the dataset. LangChain's framing: traces document the agent the way code documents a traditional app. Microsoft Foundry uses intelligent sampling (MinHash deduplication + diversity weighting) to auto-select high-value traces from raw production noise, skipping single-character inputs and low-intent traffic.

**Golden dataset hygiene:** Curate a base set, then continuously supplement it with production failures. Never let the dataset age beyond one sprint without a refresh. When a grader flips from pass to fail, the trace carries the evidence for root-cause analysis.

**LLM-as-judge guardrails:** The judge must be strictly smarter than the agent under test (Anthropic's best practice). Watch for position bias (judge prefers first position), verbosity bias (judge rewards longer outputs), and self-preference bias (judge favors outputs from its own model family). Use pair comparison with randomized ordering and calibrate with known-good and known-bad reference cases.

## Evidence

- **Research paper:** "Evaluation and Benchmarking of LLM Agents: A Survey" (arXiv:2507.21504, July 2025) — documents invocation accuracy, tool selection accuracy, retrieval accuracy, and trajectory-level metrics as distinct measurement dimensions. — https://arxiv.org/abs/2507.21504
- **Engineering blog:** LangChain's "The agent improvement loop starts with a trace" (March 2026) — describes the three-layer eval + trace flywheel approach, emphasizing that production traces feed regression datasets that drive CI/CD gates. — https://www.langchain.com/blog/traces-start-agent-improvement-loop
- **Engineering blog:** Microsoft Foundry's trace-to-dataset pipeline (2026) — intelligent sampling with MinHash deduplication converts production traces into curated eval datasets without manual cleanup, closing the observability loop. — https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/traces-to-dataset
- **Company postmortem:** Anthropic's routing bug postmortem (2025) — 0.8–16% of Sonnet 4 requests misrouted for weeks; evaluations "simply didn't capture the degradation use cases" that production traffic surfaced. Direct evidence that static eval sets miss what live traces catch. — https://www.anthropic.com/engineering/a-postmortem-of-three-recent-issues
- **Company postmortem:** Tessary analysis of the same Anthropic incident — argues production traces eliminate dataset drift because evaluation data is always current; golden datasets decay unless continuously supplemented from live traffic. — https://tessary.ai/blog/production-traces-vs-golden-datasets-llm-evals
- **Company blog:** Thoughtworks "Evaluating AI agents in production" (June 2026) — 95% AI project failure rate linked to inability to measure success; recommends unit evals, persona-based testing, and production observability layered together. — https://www.thoughtworks.com/insights/blog/machine-learning-and-ai/Evaluating-AI-agents-in-production
- **Benchmark critique:** Zylos Research "AI Agent Evaluation and Benchmarking" (May 2026) — UC Berkeley's finding that all eight prominent agent benchmarks are gameable, with quantitative evidence (890 tasks gamed with one character). — https://zylos.ai/zh/research/2026-05-13-ai-agent-evaluation-benchmarking

## Gotchas

- **Holding a final-answer pass as a quality signal.** The answer can be right and the trajectory disastrous. Always evaluate at layer 2 and 3, not just layer 1.
- **Using the same LLM as judge and agent.** The judge will systematically favor outputs from its own model family. Use a strictly stronger or orthogonal model as judge.
- **Letting golden datasets age.** After two sprints without a refresh, your eval is measuring the agent you had, not the one you have. Set a recurring calendar reminder to sample from production and add failures to the dataset.
- **Optimizing a single metric.** Task completion rate can be high while cost-per-completion explodes or policy violations triple. Track all six: task completion, tool-call accuracy, step efficiency, groundedness, safety/compliance, and cost/latency.
