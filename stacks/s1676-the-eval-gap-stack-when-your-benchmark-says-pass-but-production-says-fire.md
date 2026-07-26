# S-1676 · The Eval Gap Stack: When Your Benchmark Says Pass but Production Says Fire

You have shipped an agent. Your benchmark says 85% accuracy. Your users are filing bugs. Your cost-per-task has tripled. You cannot explain why.

## Forces

- **Accuracy is a lie for agents.** AlphaEval (2026) found the best production agent scored 64.41/100 on real tasks while benchmarks implied 85%+. Accuracy measures the destination, not the trajectory.
- **Trajectory and outcome diverge.** An agent can achieve a correct final answer through broken reasoning, or fail to achieve the answer despite sound reasoning. Benchmarks catch the former only; you need both.
- **Human eval doesn't scale, automated eval doesn't capture nuance.** MAP (306 practitioners, 26 domains) found 74% of production teams still rely primarily on human evaluation — not because they want to, but because automated benchmarks miss what matters.
- **The variance tax.** Pass@1 shows 60% success; pass@8 shows 25% — the 35-point drop is invisible if you only measure pass@1. Yet teams measure pass@1 because it looks better.
- **Cost variation is invisible when untracked.** CLEAR framework research found 50x cost variation ($0.10–$5.00/task) across agents with equivalent accuracy. Accuracy-only evaluation conceals cost explosion.

## The Move

Layer eval types across three tiers, and track cost as a first-class metric.

**Tier 1 — Outcome evals (the ground truth):**
- Binary yes/no: did the agent meet the user's goal?
- Define this first. "Did the ticket get resolved?" "Did the code compile and pass tests?" "Did the report get generated?"
- Start simple: aunhumano (Sep 2025) recommends no eval system at all until you have at least this. A yes/no e2e test that catches regressions is better than a complex framework that nobody maintains.

**Tier 2 — Trajectory evals (the early warning system):**
- Tool selection correctness: did the agent invoke the right tools in the right order?
- Hallucination rate: are facts in the agent's reasoning grounded in retrieved context?
- Step budget adherence: did the agent stay within the defined maximum steps (MAP found 68% of production agents use ≤10 steps — set your budget and track breaches)?
- Context window efficiency: what fraction of the context window was actually used?
- Error recovery: did the agent recognize and handle errors, or silently fail and proceed?

**Tier 3 — Business evals (the layer that makes executives care):**
- Cost per task (track this always — the CLEAR paper found 50x variance invisible to accuracy-only teams)
- Time-to-completion
- Escalation rate: how often does the agent hand off to a human?
- Session-level satisfaction (if human-in-the-loop)

**The eval stack in practice:**
- Use trajectory metrics as regression detectors for the agent scaffolding (tool definitions, prompt changes, architecture changes)
- Use outcome metrics as the release gate
- Use business metrics for capacity planning and ROI justification
- Align LLM-as-judge evaluations with human judgment: validate judge correlation (Galileo recommends 0.80+ Spearman) before trusting automated scores
- Version your eval suite like code. A benchmark you built once and never update becomes a liability — the agent drifts, the benchmark doesn't

**Recommended tooling (cross-referenced):**
- DeepEval (confident-ai, ~11K GitHub stars, Jul 2026) — 50+ plug-and-play metrics for agents, RAG, chatbots; runs locally; integrates with LangChain, LangGraph, OpenAI Agents, CrewAI, Anthropic, Google ADK, Pydantic AI
- AlphaEval (arxiv:2604.12162, GAIR-NLP GitHub) — 94 production-grounded tasks from 7 companies; evaluates complete agent products as commercial systems, not just model capabilities
- Coval (coval.dev) — simulation-based evaluation for agents, inspired by autonomous vehicle testing; automated test coverage for agentic systems
- Galileo (galileo.ai) — production observability with rubric-based evaluation frameworks (7 dimensions → 25 sub-dimensions → 130 items)

## Evidence

- **MAP Study (arXiv:2512.04123, Dec 2025):** Surveyed 306 practitioners and conducted 20 in-depth case studies across 26 domains. Found 74% rely primarily on human evaluation; 70% use prompting only (no weight tuning); 68% of production agents execute ≤10 steps before human intervention. "Production agents are built using simple, controllable approaches." — [IBM Research / UC Berkeley / Stanford](https://arxiv.org/html/2512.04123v1)
- **AlphaEval (arXiv:2604.12162, Apr 2026):** Benchmark of 94 production-grounded tasks from 7 companies across 6 occupational domains. Best-performing agent scored 64.41/100 on real-world tasks. Identified three structural gaps between research and production eval: task under-specification, judgment subjectivity, and continuous evolution. — [GAIR-NLP / AlphaXiv](https://arxiv.org/html/2604.12162)
- **CLEAR Framework (arXiv:2511.14136, Nov 2025):** Found 37% gap between lab performance and production deployment. Accuracy-only metrics correlate 2x worse with production success than the CLEAR multi-dimensional framework (ρ=0.41 vs ρ=0.83). 50x cost variation ($0.10–$5.00/task) for equivalent accuracy across production agents. — [Sushant Mehta / arXiv](https://arxiv.org/html/2511.14136v1)
- **"On evaluating agents" (aunhumano.com, Sep 2025):** Practitioner post on HN (42 points). Key recommendation: start with simple e2e evals (yes/no success criteria) before building complex frameworks. "No amount of evals will replace the need to look at the data — look at the agent traces to identify issues." — [HN discussion, aunhumano.com](https://news.ycombinator.com/item?id=45121547)
- **Galileo Evaluation Guide (galileo.ai, Jul 2026):** Production evaluation framework recommending separation of trajectory vs. outcome metrics; 130-item rubric across 7 dimensions; LLM-as-judge validation at 0.80+ Spearman correlation. Notes 40%+ of agentic AI projects will be cancelled by end of 2027 (Gartner, 2025). — [Galileo AI](https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks)

## Gotchas

- **Accuracy-only dashboards hide trajectory failures.** Your agent may be achieving correct answers through broken reasoning. When the model changes or the context shifts, the trajectory breaks and the answers go wrong. You won't see it coming.
- **Cost is invisible until it's catastrophic.** If you're not tracking cost-per-task, you're flying blind. CLEAR found $0.10–$5.00 variance for the same accuracy — a team optimizing for accuracy alone will miss a 50x cost overrun.
- **Eval staleness is a production risk.** Benchmarks decay. The environment changes, the agent changes, the requirements change. If your eval suite is not versioned and maintained, it gives false confidence.
- **LLM-as-judge needs validation, not just deployment.** An unvalidated LLM judge is a biased judge. Before trusting automated scores, calibrate against human judgment on a representative sample. Without this step, you're measuring the judge's beliefs, not the agent's quality.
