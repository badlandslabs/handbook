# S-1817 · The Agent Evaluation Stack — How Teams Measure Whether Their Agents Are Actually Working

You shipped the agent three months ago. It passes your test suite. It answers politely. But you have no idea whether it completes tasks, whether it's getting better or worse, or whether it's quietly failing in ways users haven't complained about yet. Task completion rate, tool-call accuracy, trajectory quality, and recovery behavior are invisible unless you build the instrumentation to see them.

Standard LLM benchmarks (BLEU, ROUGE, MMLU) don't apply — they score single prompt-response pairs. Agents plan, call tools, maintain state across turns, and recover from failures. A bad decision in step two corrupts step three, then step four, until the final output looks reasonable but misses the point. Endpoint accuracy hides trajectory quality. You need evaluation that looks at the whole run.

## Forces

- **Agents are systems, not models.** Single-turn metrics miss the failure modes that matter in production — wrong tool sequence, silent policy violations, lucky recoveries that mask real problems.
- **Offline evals go stale.** Curated test sets drift from production traffic. What you test against at release is not what users actually ask. A supermajority of YC agent builders report that offline evaluation under-delivers because keeping test sets current is nearly impossible.
- **Non-determinism makes regression invisible.** Run the same input twice and the agent may take different tool-call paths. Without trajectory-level comparison, regressions only surface when users complain.
- **The benchmark crisis.** UC Berkeley researchers found that all eight prominent agent benchmarks (SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR-bench) can be exploited to achieve near-perfect scores without genuine capability — meaning benchmark performance does not reliably predict production performance.

## The Move

**Evaluate agents across three dimensions simultaneously: system efficiency, session-level outcomes, and node-level precision.**

### 1. Task Completion Rate (the north star)
Measure end-to-end success on defined tasks — did the agent accomplish what the user asked? Typical healthy bands: 92%–97% on curated eval sets, 78%–88% on noisy live traffic. This is your signal for whether the agent is working at all.

### 2. Tool Call Accuracy and Invocation Accuracy
Two distinct things: (a) did the agent choose the correct tool from the available set, and (b) did it decide correctly whether to call a tool at all? A third metric — retrieval accuracy — measures whether the agent can retrieve the right tool from a large repository given a natural-language description. Tool-call errors compound: wrong tool → wrong output → corrupted downstream steps.

### 3. Trajectory Evaluation (not just endpoint)
Score the entire run: which tools were called, in what order, with what arguments, and whether each step satisfied policy. A run can reach the right answer through the wrong path — and that path is a liability. Replay harnesses let you re-run captured traces against a new model or policy without re-hitting production systems. Minimum viable setup: 50–200 real examples, per-step rubrics, 10+ runs per example, and a held-out set you never tune against.

### 4. LLM-as-Judge for Subjective Quality
Deterministic checks work for tool correctness and exact outputs. For anything requiring judgment — response tone, contextual appropriateness, whether a partial success is acceptable — use an LLM judge. Best practice: large proprietary judges (GPT-4o, Claude 3.7 Sonnet) for high-stakes verification; small distilled judges for low-latency, high-volume checks. Segment reported 90% alignment between LLM judges and human reviewers, with 89%→92% improvement in scores when using Chain-of-Thought prompting on the judge.

### 5. Online Production Monitoring (not just offline testing)
Offline eval catches regressions before deploy. Online monitoring catches drift in live traffic. Configure: which traces to evaluate (all, sampled 10–20%, or filtered subsets), what criteria to score, and thresholds that trigger alerts. Topic tagging on production queries gives visibility into what users are actually asking — which often diverges from what you built the agent to do. Combine automated scoring with periodic human review to keep the judge calibrated.

### 6. Failure Recovery Measurement
Don't just count failures — measure whether the agent recovers gracefully. An agent that fails silently is worse than one that fails loudly with a clear error. Track: how often does a failed tool call lead to a retry with corrected parameters? How often does the agent self-correct after an error? Recovery quality is a separate metric from task completion rate.

## Evidence

- **arXiv (ICML 2026):** First systematic MAP study (Measuring Agents in Production) — 20 in-depth interviews + 86 deployed systems practitioners across 26 industries. Key finding: 54% of evaluated agents use tool-calling accuracy as a primary metric, 53% use task completion, 39% use human preference scoring. Only 35% use trajectory-level evaluation. A supermajority of agent teams now use LLM-as-judge for runtime quality gating. — [arXiv:2512.04123](https://arxiv.org/abs/2512.04123)

- **Zylos Research / UC Berkeley:** Benchmark analysis across 8 prominent agent benchmarks found all 8 exploitable for near-perfect scores without genuine capability. Gap between benchmark performance and real-world deployment estimated at 37%. — [Zylos Research](https://zylos.ai/zh/research/2026-05-13-ai-agent-evaluation-benchmarking/), [arXiv:2507.21504](https://arxiv.org/html/2507.21504v1)

- **Polystreak (2026):** Production metrics reference bands — Task completion: 92%–97% curated, 78%–88% live. Tool call error rate: <3% threshold. Token efficiency tracked as cost-per-task. Human review: 5%–10% of traces reviewed monthly. — [Polystreak](https://polystreak.com/blog/evaluating-ai-agents-production)

## Gotchas

- **Endpoint eval is a false comfort.** Scoring only the final answer misses wrong-path-successes — the agent reached a correct answer through a risky trajectory that won't always work. Build per-step rubrics and trajectory scoring into your eval suite.
- **Offline test sets rot fast.** Production traffic diverges from curated eval sets within weeks. Curate continuously: mine production failures, add them to the eval set, run regression on every release. Without this loop, your eval suite becomes an increasingly inaccurate picture of real-world performance.
- **LLM-as-Judge has its own failure modes.** Judges exhibit positional bias (preferring responses in certain positions), self-preference bias (favoring responses similar to their own outputs), and can be gamed by verbosity. Calibrate judges against human ratings and re-calibrate after model updates. Chain-of-Thought prompting on the judge improves alignment by ~3 percentage points.
- **Non-determinism requires statistical rigor.** Run each eval example multiple times (10+ recommended) and track distribution, not just pass/fail rate. An agent that succeeds 95% of the time with high variance is a different reliability proposition than one that succeeds 87% of the time consistently.
