# S-2058 · The Eval Is the Product Stack: When Your Agent Passes Tests and Still Breaks in Production

Your agent scored 94% on your internal benchmark. Your CI gate is green. Your lead engineer is happy. Six days after launch, a real user hits an edge case your test suite never imagined, and the agent spends 45 minutes and $18 in API calls doing busywork before giving up — with no trace you can read, no alert fired, and no test case added. The benchmark was theater. The eval is the product.

## Forces

- Public benchmarks (SWE-bench, GAIA, WebArena, AgentBench) have been systematically reward-hacked — a single automated scanner broke all eight major agent benchmarks via reward hacking, achieving near-perfect scores without genuinely solving tasks (Zylos Research, 2026; Vinayaka Jyothi analysis, 2026)
- A single-run task success rate conflates two distinct properties: whether an agent *can* solve a problem, and whether it *reliably* does — pass@k and pass^k separate these, and the gap between them is what makes agents demo well and fail in production
- 40%+ of agentic AI projects will be canceled by end of 2027 (Gartner) — poor evaluation is the leading cause of shipping agents that erode trust in production
- Production input distributions exceed synthetic coverage by orders of magnitude; hand-crafted golden datasets catch regressions but cannot keep pace with the real-world failure surface
- An agent that passes today can fail tomorrow due to model version changes, retrieval drift, or API behavior shifts — single-run accuracy is a moving target, not a scorecard

## The Move

Build a layered evaluation architecture that separates what the agent *can* do (capability), what it *reliably* does (consistency), and what it *actually* does in production (observability). Treat eval engineering as a first-class engineering discipline — not an afterthought appended to a shipped agent.

**Instrument three evaluation levels:**

- **End-to-end (outcome):** Did the task actually complete? Check the final state, not just the final message. A transcript that says "done" but nothing changed is a silent failure. Pair with deterministic assertions on observable state.
- **Trajectory-level (process):** Was the path efficient and sound? Score tool call correctness (right tool, right arguments), step count vs. expected, whether it recovered after wrong tool calls, and whether it violated any policies mid-run. A correct answer reached in 20 steps with two policy-violating intermediate calls is a failing trajectory.
- **Component-level (isolation):** Which specific component broke? Isolating a single step using techniques like LangGraph's `interrupt_before` lets you assert on individual tool choices and arguments in fast, cheap unit-test-style checks. Use this for regression gating on specific capabilities.

**Track pass@k and pass^k, not just pass@1:**

- pass@k measures capability ceiling — given k attempts, can the agent ever get this right? It rises with k.
- pass^k measures reliability — what fraction of tasks succeed on all k attempts? It falls with k.
- A gap between pass@1 and pass@k means the agent can solve the problem but inconsistently. A gap between pass@1 and pass^k means the agent is unreliable in production. Top-performing agents at SWE-bench Verified solve ~49–55% at pass@1; by pass@8 the consistency surface narrows dramatically — GPT-4o resolves under 25% of retail tasks consistently across 8 runs.
- For production agents, aim for pass@1 close to pass^k. Consistent systems have reliable success, not just possible success.

**Build the golden dataset flywheel from production failures:**

The highest-value test case is not handcrafted — it comes from a real production failure. The loop: production failure → trace capture → test case extraction → golden dataset → CI/CD release gate. This surfaces edge cases you could not have invented and keeps your test suite current with the actual input distribution. Complement with model-generated adversarial test cases (stronger model builds stress cases for weaker production model) for breadth; keep human-curated sets for regression-critical paths.

**Calibrate LLM-as-judge rigorously:**

LLM-as-judge has evolved from "ask GPT-4 if this is good" into a disciplined methodology. Use deterministic checks for exact-match things (tool correctness, argument schemas, status codes). Use LLM-as-judge for anything requiring judgment (trajectory quality, answer relevance, safety). But judges have documented biases: position bias (favoring first/last options), length bias (longer responses score higher), self-preference bias (judge favors outputs similar to its own style). Calibrate with human rubrics on a sampled trace set, targeting 0.80+ Spearman correlation between judge scores and human scores before deploying at scale. Route disagreements on high-stakes decisions to human review.

**Wire evals into CI/CD with cost and latency guards:**

Every change — prompt, model version, retrieval config, tool definition, agent workflow — should trigger a regression eval against the golden dataset. Block the deploy if quality drops below defined thresholds. Track operating envelopes (cost per run, token budget, step budget, latency) in the same traces used for quality — not separately. An agent scoring 95% quality at 3x expected cost and 5x expected latency is not a passing agent.

**Monitor in production with online evals:**

Pre-deployment test suites are necessary and insufficient. Deploy expensive evaluation methods strategically in production combined with lightweight checks that fire continuously. Teams with high-confidence, low-false-positive evals wire real-time alerts on failures. Earlier-stage teams use eval failures as a triage mechanism — flagged sessions go into a human review queue. Run both offline eval suites (curated datasets, regression sets) and online evals (scoring live user interactions in real-time) to catch the silent failures that unit tests miss.

## Evidence

- **HN "Are we evaluating AI agents all wrong?" thread:** Practitioner noting that final-output correctness ("Is it correct?") misses where failures actually happen — in the reasoning trajectory, tool calls, and mid-run policy violations. Thread surfaced that trajectory-level evaluation is what separates production-ready agents from demos. — [HN #46215574](https://news.ycombinator.com/item?id=46215574)
- **Zylos Research, "AI Agent Evaluation and Benchmarking" (May 2026):** Documents that all eight major agent benchmarks (SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR-bench) were broken by reward hacking — achieving near-perfect scores without genuine task completion. Concludes that static task-completion scores fail to capture reliability, cost efficiency, safety, and long-horizon competence. Argues good eval engineering is now as important as good prompt engineering. — [Zylos Research](https://zylos.ai/zh/research/2026-05-13-ai-agent-evaluation-benchmarking/)
- **Anthropic Engineering Blog, "Demystifying evals for AI agents" (Jan 2026):** Formalizes eval terminology (task, trial, grader, transcript/trace) and the core challenge — agent behavior varies between runs, making eval results harder to interpret. Each task has its own success rate across trials, and a task that passed one eval run might fail the next. Recommends multi-trial evaluation with trajectory-level grading as the baseline for production agents. — [Anthropic](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **Arthur, "AI Agent Regression Testing From Production Failures" (Jun 2026):** Documents the production-failure-to-golden-dataset flywheel. Argues synthetic prompts cover anticipated cases while production failures surface the long tail of ambiguous phrasing, encoding edge cases, and real user intent that engineers cannot anticipate. The flywheel loop: production failure → trace → test case → golden dataset → CI/CD release gate. — [Arthur](https://www.arthur.ai/column/regression-test-datasets-ai-agents-production-failures)
- **Confident AI / DeepEval documentation (2026):** Comprehensive taxonomy of agent eval metrics — tool calling correctness, argument correctness, task completion, step efficiency, plan adherence, reasoning quality, faithfulness, safety, latency, cost — organized across end-to-end, trajectory-level, and component-level evaluation. Documents that DeepEval in CI catches regressions on every code change; Confident AI provides trace-aware observability and online production evals. — [Confident AI](https://www.confident-ai.com/blog/definitive-ai-agent-evaluation-guide)

## Gotchas

- **Final-answer evaluation alone is insufficient.** The answer can be correct while the trajectory wasted budget, violated policy, or took 20 steps for a 3-step task. You need trajectory-level and component-level checks alongside outcome checks.
- **Single-run pass@1 conflates capability with luck.** An agent scoring 85% on a single run is not a reliable agent — run the same task 8 times and the consistent-success rate (pass^k) will be substantially lower. Run multi-trial evaluations before claiming reliability.
- **Public benchmarks tell you almost nothing about production behavior.** Reward hacking, benchmark saturation, and the benchmark-to-production gap (20–40 percentage points from public leaderboard to real-world deployment) mean benchmark scores are useful only for coarse shortlisting and regression detection across model versions, not as a proxy for production readiness.
- **LLM-as-judge needs calibration before deployment.** Without human-rubric calibration targeting 0.80+ Spearman correlation, judges inherit positional bias, length bias, and self-preference bias. A judge that hasn't been checked against human ground truth will systematically mis-score certain categories of agent behavior.
- **Offline evals go stale.** Without online production evals and a mechanism to turn production failures into test cases, your golden dataset lags the actual failure surface. The eval suite needs to evolve as fast as the agent — or faster.
