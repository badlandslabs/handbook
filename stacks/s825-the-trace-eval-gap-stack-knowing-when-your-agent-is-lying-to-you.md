# S-825 · The Trace-Eval Gap Stack — Knowing When Your Agent Is Lying to You

Your agent scores 0.91 on CI. Forty-seven scenarios, four rubrics, three sprints green. In production it quotes refund amounts off by an order of magnitude, contradicts itself across turns, and hands users another customer's order. Every failing conversation passed per-turn faithfulness rubric. Individual steps looked right; the outcome was wrong. This is the trace-eval gap: your evaluation set is a frozen snapshot, but production is a living system, and the two diverge by design.

## Forces

- **Per-step success ≠ end-to-end success** — per-step accuracy of 95% across 8 steps compounds to 66% end-to-end. Standard benchmarks measure neither the compounding nor the trajectory quality.
- **Eval sets freeze; production doesn't** — eval sets capture a hypothesis about user behavior, tool behavior, prompts, and retrieval at a single point in time. Production changes continuously across all of those dimensions.
- **LLM-as-judge has systematic blind spots** — single-model judges disagree with human majority votes 31% of the time on complex tasks, and their assessments of intermediate reasoning steps are especially unreliable.
- **The benchmark trap** — public benchmarks (MMLU-Pro, SWE-bench, AgentBench) tell you which model is generally smarter; they don't tell you whether your copilot stops fabricating policy numbers in production.

## The Move

Evaluate at three distinct layers. Treat each as a separate problem with separate tooling and separate release gates.

### Layer 1 — Final-Answer Score
- Run deterministic pass/fail on structured outputs (JSON schema validity, tool-call correctness, exact-match on closed-domain queries)
- Use domain-specific benchmarks: τ-bench for customer service agents (multi-turn, dynamic; measures `pass^k` — reliability across k trials), SWE-bench Verified for coding agents
- Gate: must exceed threshold (e.g., 0.85) before promotion; single number doesn't close the loop but filters the obvious regressions

### Layer 2 — Trajectory Quality
- Score the full execution path: reasoning steps, tool calls, retries, recovery attempts
- A correct final answer reached via policy violations, excessive tool calls, or circular reasoning is a failing trajectory
- Agent-as-a-judge outperforms LLM-as-judge here: a second agent that can check intermediate code compilation, requirement adherence, and attempt counts achieves near-parity with human evaluators (0.3% disagreement vs. 31% for single-model judges on complex tasks)
- Gate: trajectory score is a release gate, not optional — a passing final answer with a failing trajectory blocks promotion

### Layer 3 — Per-Turn Production Classifier
- Deploy a lightweight classifier (<90ms latency) on every production turn
- Labels: jailbreaks, prompt injections, PII leakage, policy violations, user frustration signals
- Feeds fine-tuning data, RL reward signals, and alerts
- This is where silent failures live — they are invisible to both final-answer and trajectory evals because each individual turn looks acceptable

### The Three-Tier Evaluation Architecture
- **Offline regression suite**: curated test cases, versioned, run on every commit; catches obvious regressions
- **Shadow evaluation**: live production traffic evaluated in parallel without user-facing impact; catches drift before users do
- **Human calibration anchors**: 5–10% of production turns manually reviewed; trains and validates the per-turn classifier; catches what automation systematically misses

### The Five Drift Watchdogs
- **Dataset drift**: eval set doesn't cover new user intents that production has already surfaced
- **Tool-API drift**: mocked tool returns stale shapes; vendor changed schema, error codes, or rate limits
- **Prompt drift**: rubric frozen at prompt v3; prompt is now at v17
- **Retrieval-corpus drift**: index frozen at eval-build time; re-indexing introduced new chunks for the same query
- **Agent-step compounding**: structural, not fixable by more evals — requires architectural changes (circuit breakers, step budgets, rollback triggers)

## Evidence

- **Blog post (Future AGI, 2026):** Detailed case study — customer-support agent scored 0.91 on CI (47 scenarios, four rubrics, three sprints green) but in production was quoting wrong refund amounts, contradicting itself, and exposing customer data. Root cause: per-turn faithfulness rubric passed individual steps while the outcome was catastrophically wrong. Six drift modes documented with real production failure patterns. — [futureagi.com/blog/agent-passes-evals-fails-production-2026](https://futureagi.com/blog/agent-passes-evals-fails-production-2026)

- **Company engineering post (Sierra AI, 2024):** τ-bench introduced to address the gap between single-turn benchmarks and real multi-turn agent conversations. `pass^k` metric — whether the same task completes successfully across k trials — revealed that single-run success rates are a misleading proxy for production reliability. Existing benchmarks (WebArena, SWE-bench, AgentBench) only evaluate a single exchange round, not dynamic multi-turn gathering. — [sierra.ai/blog/benchmarking-ai-agents](https://sierra.ai/blog/benchmarking-ai-agents)

- **Research paper (arXiv 2508.02994, 2024):** Agent-as-a-judge (a second agent evaluating the primary agent's trajectory) dramatically outperformed single-model LLM-as-judge on code tasks. Agent judge decisions differed from human-majority vote by only 0.3%; single-model judges disagreed 31% of the time. Cost-effective while achieving parity with human evaluators because it can check intermediate compilation states and requirement adherence, not just final outputs. — [arxiv.org/html/2508.02994v1](https://arxiv.org/html/2508.02994v1)

- **Article (Galileo AI, 2026):** Enterprise deployments show 60% single-run success dropping to 25% across eight runs. 40%+ of agentic AI projects projected to cancel by end of 2027 (Gartner, 2025). Three-tier rubrics with 7 dimensions → 25 sub-dimensions → 130 rubric items recommended for systematic evaluation. LLM-as-judge requires 0.80+ Spearman correlation with human judgment before deployment as a gate. — [galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks](https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks)

- **Blog post (Big Data Boutique, 2026):** Layered evaluation architecture: offline regression suites, online/shadow evaluation, human calibration anchors. Task metrics (exact match, structured-output validity, tool-call correctness), trajectory metrics (step efficiency, recovery, policy adherence), and operational metrics (cost per task, latency, token efficiency) map to business risk. Public benchmarks are necessary but insufficient — they measure general model capability, not copilot-specific fabrication rates. — [bigdataboutique.com/blog/llm-evaluation-frameworks-metrics-best-practices](https://bigdataboutique.com/blog/llm-evaluation-frameworks-metrics-best-practices)

- **InfoQ article (March 2026):** "An agent that works perfectly in a sandbox but silently misreports a failed refund in production hasn't passed any evaluation that counts." Hybrid evaluation (LLM-as-judge + trace analysis + human judgment) is non-negotiable. Operational constraints — latency, cost per task, token efficiency, tool reliability, policy compliance — are first-class evaluation targets, not afterthoughts. — [infoq.com/articles/evaluating-ai-agents-lessons-learned](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned)

## Gotchas

- **"Our benchmark score went up, ship it"** — benchmark improvements don't translate to production improvement when the benchmark measures the wrong thing (single-turn vs. multi-turn, or final-answer vs. trajectory)
- **Rubric staleness** — rubrics drift from prompts and tools faster than teams realize; treat rubric versioning like code versioning, with explicit re-validation on every prompt or tool change
- **LLM-as-judge correlation drift** — a judge model calibrated against human labels at launch degrades as the judge model itself is updated; re-calibrate before using judge scores as release gates
- **Tool mocking in evals** — mocked tool returns are the most common source of false confidence; if possible, use a staging environment with real (rate-limited, erroring) tool APIs for a subset of eval cases
- **Measuring trajectory but not acting on it** — many teams compute trajectory scores but use only final-answer scores for promotion decisions, making trajectory evaluation theater
