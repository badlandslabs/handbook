# S-1655 · The Layered Eval Stack — When You Don't Know If Your Agent Is Actually Working

When an agent silently makes the right plan for the wrong reason, or completes the task but in a way that would be catastrophic at scale — and you find out from a user, not a test.

## Forces

- **Agents are non-deterministic by design.** The same input can produce different tool-call sequences, different reasoning paths, different outcomes. A single test run tells you almost nothing about reliability.
- **Traditional testing assumes deterministic behavior.** Exact-match assertions, regression suites, and CI gates all break when "correct" means a spectrum of valid outcomes.
- **The taste problem.** LLMs lack grounded taste — they can easily praise and criticize, but praising good work while criticizing bad is a separate skill. Evals run by LLMs can be gamed, biased by verbosity, or calibrated to the wrong standard.
- **Outcome and trajectory are different things.** An agent can reach the right answer via a terrible path (wasting tokens, calling the wrong tools first, making a lucky guess) — or reach the wrong answer via a perfect process (corrupted data downstream). You need both.
- **Benchmarks don't predict production.** An agent scoring 49% on SWE-bench Verified might handle 90% of real bug fixes; one topping GAIA might fail on domain-specific workflows it was never tested against.

## The move

Build a **three-layer eval architecture** — offline regression, shadow/hybrid evaluation, and production monitoring — with distinct tools, triggers, and success criteria at each layer.

### Layer 1: Offline Regression Suite (pre-deploy)

- Run structured test cases against every commit and on a nightly schedule.
- Define **tasks** (input + success criteria) and run multiple **trials** (same task, multiple attempts) to catch non-deterministic failures.
- Use **deterministic graders** for exact checks (tool called, arguments match schema, output format correct). Use **LLM-as-judge** only for things that require judgment — and validate the judge itself against human-labeled samples targeting ≥0.80 Spearman correlation.
- For tool-calling agents: test what tools were called, in what order, with what arguments — not just what the agent said.
- Integrate into CI/CD: a failing eval blocks deployment. Set a quality gate (e.g., >90% task completion on the core workflow).
- Recommended tooling: **Promptfoo** for prompt regression, **DeepEval** for Python-native test-style evals, **Rubric-eval** for trace-level behavior checking.

### Layer 2: Shadow and Hybrid Evaluation (staging + canary)

- Run live agent behavior in a staging environment against production-representative data.
- **Shadow mode**: the agent acts normally but a parallel evaluator scores the run without blocking output. This catches failures that only appear with real inputs.
- Use **trace-based evaluation**: instrument every tool call, reasoning step, and state change. A trace shows where metrics failed and enables root-cause diagnosis — essential for multi-step agents where a mid-run failure cascades.
- Human reviewers should sample a percentage of runs and score against a structured rubric. Refine the rubric from real review data.
- For code-generating agents: use domain-relevant benchmarks as directional signals — SWE-bench Verified for code agents, GAIA for general-assistant agents, WebArena for web-navigation agents — but treat scores as calibration data, not pass/fail gates.

### Layer 3: Production Monitoring (post-deploy)

- Track **task completion rate** (end-to-end success), **partial completion rate** (agent made progress but didn't finish), **failure rate by type** (model error, tool error, timeout, quality rejection), and **human intervention rate** (how often humans must override or correct output).
- Monitor **cost and latency as first-class quality dimensions** — surprise LLM bills from untracked token usage are a real failure mode. Track cost per agent, per model, per task type.
- Detect **behavioral drift**: agent success rates should be tracked over time. A drop from 94% to 88% over two weeks is a signal even if no individual run has "failed."
- Log full execution traces for post-mortems. Basic error logs tell you what broke; traces tell you why and where.
- Use structured human feedback loops: subject-matter experts review specific runs, rate output quality, and add context. Convert this into updated test cases.

### On LLM-as-Judge specifically

- Works well for: natural language quality, coherence, adherence to style guidelines, general reasoning soundness.
- Breaks down for: domain-specific expert knowledge (medical, legal, financial), tasks where the judge model has systematic biases (verbosity bias, self-preference bias, position bias), and cases where "correct" requires proprietary context.
- Best practice: validate the judge with human-labeled golden examples. If the judge can't reproduce human scores on a held-out set, throw it out for that dimension.
- For expert-domain agents: always keep a human (specifically, a domain expert) in the loop. LLM-as-judge can flag obvious issues but cannot reliably validate specialized outputs.

## Evidence

- **Anthropic Engineering Blog:** "Demystifying Evals for AI Agents" (Jan 2026) — defines the task/trial/grader vocabulary, outlines the unit/integration/canary eval structure, and notes that the capabilities making agents useful (autonomy, flexibility) are precisely what makes them hard to evaluate. — [anthropic.com/engineering/demystifying-evals-for-ai-agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **Confident AI:** "LLM Agent Evaluation Metrics in 2026" (Jun 2026) — describes the three diagnostic levels (end-to-end → trajectory → component), emphasizes tracing as the backbone of eval systems, and catalogs LLM-as-judge biases with calibration guidance targeting 0.80+ Spearman correlation. — [confident-ai.com/blog/llm-agent-evaluation-complete-guide](https://www.confident-ai.com/blog/llm-agent-evaluation-complete-guide)
- **The Thinking Company / Thinking.inc:** "AI Agent Evaluation in Production (2026 Guide)" (Mar 2026) — describes the three monitoring layers with specific metrics: task completion rate (>90% target for well-defined workflows), failure rate by type, human intervention rate, and quality drift tracking. Notes Gartner: 40% of enterprise AI failures by 2028 will trace to inadequate evaluation/monitoring, not model capability. — [thinking.inc/en/blue-ocean/agentic/ai-agent-evaluation-production/](https://thinking.inc/en/blue-ocean/agentic/ai-agent-evaluation-production/)
- **Hacker News:** "Ask HN: How are you monitoring AI agents in production?" (4 months ago) — practitioners citing real incidents (DataTalks database wipe, Replit agent deleting data during code freeze) as motivation. Solutions discussed: execution tracing, risk detection on outputs, cost tracking per agent, human-in-the-loop approval for high-risk actions. — [news.ycombinator.com/item?id=47301395](https://news.ycombinator.com/item?id=47301395)
- **ACM IUI 2025:** "Limitations of the LLM-as-a-Judge Approach for Evaluating LLM Outputs in Expert Knowledge Tasks" — finds that LLM judges underperform domain experts significantly on specialized tasks; recommends keeping human SMEs in the loop for expert-domain evaluation. — [dl.acm.org/doi/10.1145/3708359.3712091](https://dl.acm.org/doi/10.1145/3708359.3712091)
- **BigData Boutique:** "LLM Evaluation in Production" (Jan 2025) — maps tool selection to team size and use case: small teams → Promptfoo + DeepEval; RAG-heavy → Ragas + Phoenix/Langfuse; enterprise → MLflow or Foundry SDK; multi-agent → Braintrust or LangSmith. Notes that tool selection is downstream of architecture. — [bigdataboutrique.com/blog/llm-evaluation-frameworks-metrics-best-practices](https://bigdataboutrique.com/blog/llm-evaluation-frameworks-metrics-best-practices)

## Gotchas

- **Single-trial runs are nearly useless for agents.** Always run multiple trials per task — a 70% success rate over 10 trials reveals something a single run cannot.
- **LLM-as-judge has systematic biases.** Position bias (preferring first or last options), verbosity bias (preferring longer responses), and self-preference (favoring outputs from similar models) are well-documented. Validate, don't trust.
- **Benchmark scores are directional, not predictive.** A SWE-bench Verified score tells you something about code-agent capability on a specific benchmark task set. It tells you almost nothing about whether the agent will handle your codebase, your tools, your edge cases.
- **Trajectory and outcome metrics must be tracked independently.** Optimizing for task completion alone can hide terrible efficiency (the agent got there, but via 47 tool calls when 3 would have sufficed).
- **CI gates without eval coverage are theater.** Running evals only when someone remembers to is not a quality system — it must be automated and blocking.
- **Human-in-the-loop is not optional for expert domains.** An LLM judge cannot reliably validate a tax calculation, a legal summary, or a medical diagnosis. Budget for expert review as a core part of the eval loop.
