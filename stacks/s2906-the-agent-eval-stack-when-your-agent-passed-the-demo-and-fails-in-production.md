# S-2906 · The Agent Eval Stack — When Your Agent Passed the Demo and Fails in Production

The demo worked. The stakeholder meeting worked. The first ten users loved it. Then it went to production and started hallucinating confident failures, looping on rate-limited APIs, taking 47 tool calls to accomplish what a simple script could do in two — and nobody noticed until a customer complained. The fix is not a better model. It is an evaluation architecture that makes the agent's behavior visible before it reaches users.

## Forces

- **Trajectory is invisible in single-turn metrics.** BLEU, ROUGE, and exact-match scores measure output quality on one-shot tasks. Agents plan, call tools, fail, recover, and branch — and all of that happens off-screen of output-only evaluation. A 95% task success rate that costs 50 API calls and 30 seconds per task is not a working agent.
- **The golden dataset rots.** Static test suites built from yesterday's user queries go stale the moment you ship an update. The cases that mattered last quarter aren't the cases that will break next quarter. Without a pipeline to refresh test cases from production, your regression suite becomes a false confidence engine.
- **LLM-as-judge is powerful but requires calibration.** Using a model to score agent outputs works at scale but introduces its own failure modes: positional bias, verbosity bias, self-preference. An uncalibrated judge will rate its own reasoning style higher and fail to catch subtle trajectory errors.
- **Operational metrics are first-class citizens.** Latency, token cost, and tool-call count are not secondary to accuracy — they are co-equal constraints. An agent that achieves 98% accuracy but requires $2.40 per conversation is not production-ready regardless of its benchmark score.
- **Human evaluation does not scale but automation does not replace it.** Automated evaluators catch regressions, enforce consistency, and run thousands of trials per day. Human reviewers catch tone failures, contextual misreads, and trust violations that no rubric captures. The teams that ship reliably use both — but not on the same axes.

## The move

Build a three-layer evaluation architecture that treats system efficiency, session-level outcomes, and node-level tool precision as independent measurement surfaces, governed by a continuously-refreshed golden dataset with both automated and human scoring on different dimensions.

### Core structure

- **Layer 1 — System Efficiency (operational, automated):** Measure latency (p50/p95/p99), tokens per session, tool-call count, and cost per task. These are deterministic; instrument them directly, not through LLM judgment. A CI gate on cost-per-task or p95 latency catches regressions before they compound.

- **Layer 2 — Session-Level Outcomes (task success, automated + human):** Did the agent accomplish the goal? Outcome-based: the customer's question was answered. Process-based: all required workflow steps completed. Quality-based: the output satisfies a domain-specific rubric. Use LLM-as-judge for correctness and trajectory quality when ground truth exists; reserve human review for dimensions that require judgment — tone, trust, contextual appropriateness.

- **Layer 3 — Node-Level Tool Precision (per-step, automated):** Was the right tool called at the right step? Did the tool call succeed? Did the agent recover from failure? Trace-level evaluation against a rubric that scores each reasoning step and tool invocation independently. Tools like trajectory-lab (GitHub), LangSmith, Braintrust, and DeepEval support this natively.

### The eval loop

1. **Seed from production.** Human-reviewed correct traces become your first golden cases. Seed the golden dataset from real interactions — not synthetic queries — because production distributions differ from invented ones.
2. **Run on every change.** Treat the golden dataset as a regression suite. Gate model upgrades, prompt changes, and tool schema changes on eval pass rates. If a prompt tweak drops task success from 94% to 89%, you catch it before deployment, not after.
3. **Calibrate your judge.** An uncalibrated LLM-as-judge has predictable biases. Use Agent-as-a-Judge with multi-agent debate (two LLMs score independently, resolve disagreement) — this reduces judge-agreement gap to near-human levels (0.3% deviation in code evaluation per arXiv:2508.02994).
4. **Refresh continuously.** Production traffic generates new failure cases. When the agent fails on a real user interaction and a human fixes it, that case goes into the golden dataset. This is the compound-interest loop — every production incident that gets captured makes future regressions harder.
5. **Set tiered thresholds, not binary gates.** A single pass/fail threshold is blunt. Tier: critical path tasks require 95%+ success; auxiliary tasks 80%+; experimental paths 60%+. Combine with cost caps (block upgrades that increase cost-per-task by >20%) and latency caps (block if p95 > 5 seconds).

### Failure handling inside the eval system

- **Graceful recovery scoring.** A session where the agent fails, detects the failure, and recovers gracefully scores higher than one where the agent silently continues with wrong output. Build this into your trajectory rubric — recovery is a first-class quality signal.
- **Looping detection.** Instrument maximum step counts and context-window usage. An agent that loops for 35 minutes is not failing gracefully — it is failing expensively. Hard timeout with a fallback response (e.g., "I'm unable to complete this request at this time") is scored better than unbounded looping.
- **Circuit-breaker eval.** Before shipping, inject failure scenarios: API timeout, malformed tool response, rate-limit error. Does the agent detect the failure, back off, and either retry or escalate? This is the agent's resilience test suite.

## Evidence

- **Engineering blog: Anthropic** — "Demystifying Evals for AI Agents" (Jan 2026) outlines the task/trial/grader/transcript terminology and the three-layer eval architecture. Emphasizes that "good evaluations help teams ship more confidently — without them, it's easy to catch issues only in production, where fixing one failure creates others." — https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents

- **Survey: arXiv 2510.25445** — "Agentic AI: A Comprehensive Survey" (Dec 2025) surveys 306 practitioners and 20 case studies across 26 domains. Finds that traditional metrics (BLEU, ROUGE, exact match) fail to capture agentic behavior and that organizations with mature evaluation practices report 40% fewer production incidents. — https://arxiv.org/abs/2510.25445

- **Technical guide: NVIDIA** — "Mastering Agentic Techniques: AI Agent Evaluation" (May 2026) articulates the distinction between model evaluation (capability baseline) and agent evaluation (end-to-end behavior). Recommends evaluating trajectories, not just outputs, and making cost and latency first-class metrics alongside accuracy. — https://developer.nvidia.com/blog/mastering-agentic-techniques-ai-agent-evaluation

- **GitHub: Trajectory Lab** — Open-source evaluation harness for tool-using LLM agents. "Most agent projects ship with an examples/ folder and a vibe check. Production agents need real signal: was the right tool called, in the right order, did the output satisfy a domain-specific rubric, did v2 break a case v1 passed?" — https://github.com/RitikPatill/trajectory-lab

- **GitHub: Agent Eval Arena** — Evaluation harness with golden datasets, multi-scorer execution, regression detection across model versions, and CI gates for model promotion. "Most AI teams either ship without eval — and find regressions in production — or have a Jupyter notebook that someone runs occasionally, which nobody trusts in CI." — https://github.com/mizcausevic-dev/agent-eval-arena

- **GitHub: Production-Grade AI Agent** — Real-world agent repo with LangSmith observability, HITL (human-in-the-loop), golden dataset evaluation, and pytest test suite. "Before any change goes to production, I run it against a golden dataset. If correctness drops below 0.7 or faithfulness drops, I track score trends in LangSmith to catch regressions proactively." — https://github.com/codeninja2022-create/production-grade-ai-agent

## Gotchas

- **Golden datasets go stale without a refresh pipeline.** A dataset built once and never updated will tell you the agent still passes last quarter's test cases — while silently failing on the distribution that has shifted since. Capture production failures, human-correct them, and add them to the suite automatically.
- **LLM-as-judge has systematic biases.** Positional bias (preferring first or last options), verbosity bias (rating longer outputs higher), and self-preference (judge models rating outputs from similar models higher) are documented failure modes. Calibrate with diverse judge models and multi-agent resolution before trusting scores on high-stakes dimensions.
- **Single-pass eval hides variance.** Agent outputs are non-deterministic. Running each test case once gives you a single point estimate on a stochastic system. Run trials multiple times (3–5 minimum) and report pass rates with confidence intervals — not just pass/fail.
- **Trajectory length is a proxy for cost, not quality.** Agents that take more steps don't necessarily produce better results. Some of the worst production agents have the longest reasoning traces — they are confidently wrong and verbose about it. Score the path independently from the outcome.
- **Benchmarks like SWE-bench and AgentBench are for capability probing, not production readiness.** SWE-bench measures whether a code agent can resolve a GitHub issue. It does not measure latency, cost, safety, or consistency across sessions. Use benchmarks for directional capability signal; use your own golden dataset for shipping decisions.
