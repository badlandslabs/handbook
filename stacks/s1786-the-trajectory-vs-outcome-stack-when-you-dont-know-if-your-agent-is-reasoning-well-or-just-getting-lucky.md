# S-1786 · The Trajectory vs. Outcome Stack — When You Don't Know If Your Agent Is Reasoning Well or Just Getting Lucky

You shipped the agent. The task success rate looks fine — 72% on the dashboard. But you have no idea if it's solving problems the right way, taking 15 steps when 3 would do, or silently hallucinating intermediate facts that happen to converge on the right answer. Then it hits a slightly different input and the failure mode is catastrophic, not graceful. This is the trajectory-vs-outcome gap: measuring outcomes tells you what happened; measuring trajectories tells you why — and why it will or won't happen again.

## Forces

- **Outcomes are easy to measure, trajectories are hard.** Outcome metrics (did the task complete?) are simple binary signals. Trajectory metrics (did the agent reason soundly, call the right tools, recover from errors?) require instrumenting the execution trace — and most teams don't.
- **74% of production agents rely primarily on human evaluation** (arXiv:2512.04123, ICML 2026). Human evaluation doesn't scale, doesn't run in CI, and different reviewers disagree on what "good reasoning" looks like.
- **The Gartner projection that 40%+ of agentic AI projects will be cancelled by end of 2027** tracks directly to this: teams can't distinguish a regression from a bad day, so they either over-trust the system or abandon it after one surprise failure.
- **Trajectory and outcome metrics can diverge.** An agent can reach the right answer via wrong reasoning and pass outcome checks while building on a brittle foundation. The next input finds the crack.
- **Agents are systems, not models.** Single-turn accuracy metrics and classical NLP benchmarks (BLEU, ROUGE) don't capture multi-step failure modes, tool-call chains, or recovery behavior.

## The Move

Separate trajectory evaluation from outcome evaluation. Treat them as distinct layers, measured at different cadences, feeding different decisions.

### Layer 1 — Outcome metrics (run continuously in production)
- **Task success rate**: binary or rubric-scored pass/fail per session
- **Step efficiency**: steps-to-completion vs. an established baseline — catching bloat before it compounds
- **Error rate**: tool call failures, timeout rate, dead-end rate
- **Cost per task**: token count × model cost — catches pathological reasoning loops early

### Layer 2 — Trajectory metrics (run in CI + on sampled production traces)
- **Tool call precision**: did it call the right tool at the right time? Did it call unnecessary tools?
- **Recovery quality**: when a tool fails, does the agent retry, substitute, or escalate gracefully?
- **Reasoning coherence**: does the intermediate output at step N logically support step N+1? (LLM-as-judge with a rubric)
- **Step limit adherence**: 68% of production agents execute at most 10 steps before human intervention (MAP study). Track how often your agent approaches or exceeds your configured step limit.

### Layer 3 — Grader design (Anthropic's framework)
- **Define the outcome first**: what does success look like in the environment, not in the chat? ("Reservation created in DB" not "Flight booked" message)
- **Code deterministic assertions** where possible — exact-match checks for outputs, schema validation for structured data
- **Use LLM-as-judge for qualitative dimensions** — helpfulness, coherence, instruction adherence — calibrated against human-reviewed samples targeting 0.80+ Spearman correlation
- **Run multiple trials per task**: agent outputs have variance; single trials hide inconsistency

### Layer 4 — CI integration (don't evaluate only in production)
- **Commit-triggered evals**: run full eval suite on every code change affecting the agent
- **Scheduled regression checks**: catch model-provider changes (new base model, system prompt updates) before they hit users
- **Production sampling**: evaluate 5-10% of live sessions — catch real-world distribution gaps that offline test sets miss
- **Progressive canary**: route new agent versions to a small % of users, evaluate their traces, expand only on confirmed non-regression

## Evidence

- **Academic study:** 68% of production agents cap at 10 steps before human intervention; 74% still depend primarily on human evaluation despite known scalability limits — [Measuring Agents in Production (MAP), arXiv:2512.04123, ICML 2026](https://arxiv.org/abs/2512.04123)
- **Industry survey:** Production data from 6,259 agents across 4.5 million tests shows 56.6% overall success rate — revealing the gap between demo performance and real-world deployment — [Galileo AI / MAP study cross-reference](https://arxiv.org/html/2512.04123v1)
- **Engineering blog:** Anthropic's internal eval framework separates Tasks, Trials, Graders, Transcripts, and Outcomes as first-class primitives; emphasizes evaluating environment state over output messages — [Demystifying Evals for AI Agents, Anthropic Engineering, Jan 2026](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **Framework comparison:** DeepEval (pytest-native, agent-trace aware), Promptfoo (YAML-first, red-teaming), and LangSmith (observability + eval unified) represent three distinct philosophies for implementing trajectory evaluation — [Technspire: Agent Evaluation in 2026](https://technspire.com/en/blog/agent-evaluation-2026-deepeval-promptfoo-langsmith)
- **Gartner projection:** Over 40% of agentic AI projects will be cancelled by end of 2027 — primary driver is inability to measure whether systems actually work — [Gartner press release, June 2025](https://www.gartner.com/en/newsroom/press-releases/2025-06-25-gartner-predicts-over-40-percent-of-agentic-ai-projects-will-be-canceled-by-end-of-2027)
- **Practitioner thread:** HN thread on AI agent monitoring surfaced AgentShield, Langfuse, and Braintrust as tools teams reach for when tracing and cost visibility are missing — [Ask HN: How are you monitoring AI agents in production?, Hacker News](https://news.ycombinator.com/item?id=47301395)

## Gotchas

- **Don't use BLEU/ROUGE for agent eval.** These measure surface-level text similarity and are trivially gamed. They correlate poorly with task success in multi-step agents.
- **LLM-as-judge has known limitations.** It works well for coherence and helpfulness but struggles with factual grounding and domain-specific correctness. Calibrate against human review before trusting the numbers.
- **Outcome-only monitoring creates false confidence.** A dashboard showing 85% success rate tells you nothing about whether failures are random noise or systematic — check step efficiency and trajectory traces on failures.
- **Benchmark saturation is real.** UC Berkeley researchers (April 2026) found that every major AI agent benchmark can be exploited for near-perfect scores without solving the underlying task. Use benchmarks for directional signal, not as guardrails.
- **Single-agent designs are easier to evaluate.** If you're struggling to instrument trajectory metrics, start by reducing agent complexity before adding evaluation infrastructure — single agents with focused tools are dramatically easier to trace and grade.
