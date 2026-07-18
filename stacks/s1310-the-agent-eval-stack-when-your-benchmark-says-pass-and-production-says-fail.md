# S-1310 · The Agent Eval Stack — When Your Benchmark Says Pass and Production Says Fail

Your agent passes every benchmark. It scores 65% on SWE-bench, 80% on GAIA, and all your internal unit tests green. Then it ships to production and quietly corrupts customer records for three days before anyone notices. The benchmark wasn't lying — it was measuring the wrong thing. This is the agent eval problem: standard benchmarks measure whether an agent *can* solve tasks in ideal conditions, not whether it *will* remain reliable when constraints accumulate, context degrades, and stakes are real.

## Forces

- **Benchmarks measure potential, not reliability.** SWE-bench and GAIA test task completion in structured conditions. Production throws partial context, edge cases, and silent constraint violations that benchmarks never see. The "Constraint Decay" paper (287 HN points, arxiv:2605.06445) found a ~30 percentage point performance drop from unconstrained to fully-specified production tasks across eight web frameworks.
- **Trajectory and outcome metrics measure different things.** An agent can reach the right answer through a broken reasoning chain — one that fails under slightly different inputs. Braintrust's eval framework explicitly distinguishes these: trajectory scoring catches regressions that outcome-only eval misses.
- **LLM-as-judge works at ~80% human agreement — until it doesn't.** On subjective quality tasks, judge models match humans well. On expert-domain content (legal, medical, specialized code), agreement drops to 60–70%. Without domain-specific rubrics, the same judge model varies up to 30% in scoring depending on prompt wording.
- **Enterprise agents achieve 60% success on first runs, dropping to 25% across eight runs.** Gartner (cited via Galileo AI, June 2025) found this pattern across real deployments. A single benchmark run tells you almost nothing about long-term reliability.
- **Over 40% of agentic AI projects will be cancelled by 2027.** Same Gartner data. The primary driver: teams ship without knowing whether their agent works, then discover failures only when customers complain.

## The Move

Build a three-tier evaluation system that measures what benchmarks miss.

**Tier 1 — Golden test set (your ground truth):**
- Curate 50–100 representative tasks with known expected outcomes. These should reflect your actual production distribution, not benchmark elegance.
- Run this set before every deployment, after every model swap, and whenever you modify agent tools or prompts.
- This alone catches the majority of regressions before they reach users. (Data-Gate, 2026; benchmarkingagents.com)

**Tier 2 — Dual-metric scoring (trajectory + outcome):**
- **Outcome metrics:** Did the agent complete the task? Is the final output correct?
- **Trajectory metrics:** Did the agent follow a sound reasoning path? Did it use the right tools, in the right order, for the right reasons?
- Braintrust's eval pattern: `data + task + scorers`. Each eval takes a test case, runs it against your agent function, and scores against both deterministic checks and LLM-as-judge rubric. Production traces feed back into the test set — failed production runs become new test cases.

**Tier 3 — LLM-as-judge with calibrated rubrics:**
- Use code-based scorers for deterministic checks (exact match, regex, JSON structure, API response shape).
- Use LLM-as-judge for qualities rules can't capture: tone, relevance, coherence, whether the agent's reasoning was sound.
- Provide the judge a 5-point rubric with concrete behavioral anchors for each score level — don't ask "is this good," define what "good" looks like in your domain.
- Validate your judges: sample 20 outputs, score them with both the judge and a human, measure agreement. Recalibrate when agreement drops.

**Bonus — Monitor for constraint decay in coding agents:**
- If your agent generates backend code, evaluate it at multiple constraint levels: L0 (functional only), L1 (add structure), L2 (add ORM/data layer rules), L3 (full production spec including schema, auth, and deployment requirements).
- The Constraint Decay paper found the biggest drops at L2→L3, particularly in data-layer defects (incorrect query composition, ORM violations). Test specifically at your actual constraint level, not the benchmark's level.

## Evidence

- **HN Discussion:** "What broke when I tried to evaluate an AI agent in production" — evaluator tried benchmark-style approach and it failed in unexpected ways (non-determinism, context sensitivity, silent errors). — [news.ycombinator.com/item?id=47416033](https://news.ycombinator.com/item?id=47416033)
- **HN Discussion:** "Principles for production AI agents" (128 points) — eval suite owner reports prompt tweaks "passed an initial vibe check, but when run against the full eval suite, clearly performed worse." Another commenter: "Teams without robust eval practices are not to be trusted." — [news.ycombinator.com/item?id=44712315](https://news.ycombinator.com/item?id=44712315)
- **Research Paper + HN (287 points):** "Constraint Decay: The Fragility of LLM Agents in Backend Code Generation" — 80 greenfield + 20 feature tasks across 8 web frameworks at 4 constraint levels. Assertion pass rate drops ~30pp from L0 to L3. Data-layer defects (incorrect ORM, query composition) identified as primary root cause. — [arxiv.org/abs/2605.06445](https://arxiv.org/abs/2605.06445) + [news.ycombinator.com/item?id=48256912](https://news.ycombinator.com/item?id=48256912)
- **AI Beat analysis** of Constraint Decay paper — confirms agents perform better in minimal frameworks (Flask) and worse in convention-heavy environments (Django, FastAPI). — [ai-beat.github.io/news/2026/05/constraint-decay-coding-agents](https://ai-beat.github.io/news/2026/05/constraint-decay-coding-agents)
- **Benchmarking reference:** Comprehensive benchmark overview covering SWE-bench Verified, WebArena, AgentBench, Terminal-Bench, OSWorld, Tau-Bench — each links to live official leaderboards. Key note: "High scores on MMLU, GPQA, and HumanEval do not predict agentic capability." — [benchmarkingagents.com/agent-benchmarks](https://benchmarkingagents.com/agent-benchmarks)
- **Enterprise framework:** FuturOneAI open-source evaluation framework — defines task completion rate (>85% target), first-pass accuracy, hallucination rate, latency (p50/p95/p99), and cost-per-task as primary metrics. Emphasis on evaluating "the complete agent system, not just the underlying model." — [github.com/FuturOneAI/ai-agent-evaluation-framework](https://github.com/FuturOneAI/ai-agent-evaluation-framework)
- **Platform:** AWS Labs Agent Evaluation — targets Amazon Bedrock agents, Knowledge Bases, Amazon Q Business, SageMaker endpoints. Supports configurable evaluators, offline pre-deployment testing, and online production monitoring. — [awslabs.github.io/agent-evaluation](https://awslabs.github.io/agent-evaluation)
- **Gartner data (via Galileo AI):** Enterprise agents achieve 60% first-run success, 25% across eight runs. 40%+ of agentic AI projects will be cancelled by end of 2027 due to evaluation gaps. — [galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks](https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks)
- **LXT survey (Oct 2025):** 60% of organizations now deploying agents; 39% of AI projects fell short of expectations in both 2024 and 2025. — [lxt.ai/blog/ai-agent-evaluation](https://www.lxt.ai/blog/ai-agent-evaluation)

## Gotchas

- **Don't trust single-run benchmark scores.** The Constraint Decay paper and enterprise data both show: run once under ideal conditions, you get a flattering number. Run eight times or under real constraints, you get a much lower one.
- **Don't skip trajectory scoring on multi-step agents.** The agent can reach the right answer through a broken path — one that will fail silently on edge cases. If you only score outcomes, you'll never see it.
- **Don't use a judge prompt without a rubric.** Asking an LLM "is this response good?" produces wildly inconsistent results. Asking "rate this response on a 1–5 scale for factual accuracy, relevance, and coherence, using these anchors: [anchor definitions]" produces 80% human agreement. Without anchors, agreement varies by up to 30% across prompt variations.
- **Don't measure only what benchmarks measure.** Standard benchmarks like SWE-bench test whether a task *can* be completed. Production requires measuring whether tasks *are* completed correctly, at scale, under real constraints, with acceptable latency and cost. Build your own test set around your actual failure modes.
