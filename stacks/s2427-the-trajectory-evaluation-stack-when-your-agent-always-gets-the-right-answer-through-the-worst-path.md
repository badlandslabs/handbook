# S-2427 · The Trajectory Evaluation Stack — When Your Agent Always Gets the Right Answer Through the Worst Path

Your agent completes the task. The test passes. Your dashboard shows green. But the agent called the wrong tool first, ignored a guardrail that happened not to bite this time, and recovered by luck — not design. Endpoint scoring certified the answer. It said nothing about the behavior. This is the eval gap: teams measure outcomes, then ship, then discover their agent reaches correct answers through reckless paths. Over 40% of agentic AI projects will be canceled by end of 2027, per Gartner — not because the models fail, but because teams cannot reliably measure whether their agents work. The gap between "the agent completed the task" and "the agent completed the task the right way" is where agents quietly become liabilities.

## Forces

- **Agents are systems, not models** — they plan, call tools, maintain memory, and adapt across multiple steps. Classical metrics like BLEU or ROUGE score static text, not dynamic behavior. Standard unit tests are pretty much useless for non-deterministic, context-based decision systems.
- **Outcome metrics lie** — an agent can reach a correct answer through a reckless trajectory, then fail catastrophically the next time the lucky recovery doesn't happen. Task success rate alone predicts nothing about whether the agent is safe to run autonomously.
- **Eval is underinvested** — only 5.2% of surveyed organizations have AI agents live in production (Cleanlab, 2025). Of those, less than 1 in 3 teams are satisfied with their observability or guardrails. 70% of production teams struggle with evaluation metrics specifically.
- **Stack churn compresses time** — 70% of regulated enterprises rebuild their agent stack every 3 months or faster. Without defensible eval infrastructure, each iteration is a blind leap.

## The move

Evaluate trajectories, not just endpoints. Build a layered eval system that scores how the agent behaves, not just what it produces.

**Three evaluation levels, used as a diagnostic stack:**

- **End-to-end** — treats the whole system as a black box. Did the task succeed? This is the floor, not the ceiling. Use it to catch obvious regressions.
- **Trajectory-level** — inspects the path: which tools were called in what order, with what arguments, and whether each step satisfied policy. A correct answer achieved through a reckless path fails this level.
- **Component-level** — drills into which specific retriever, tool, sub-agent, or prompt caused the failure. Use this after trajectory eval flags a problem.

**Trajectory rubric dimensions (per-step scoring):**

- Tool selection correctness — right tool, right arguments
- Reasoning coherence — does the next step follow logically from the last?
- Constraint adherence — did it respect guardrails, permissions, budget?
- Recovery quality — if it made an error, did it detect and correct it?
- Efficiency — did it take the shortest viable path?

**Minimum viable eval setup for production agents:**

- 50–200 real examples drawn from production traffic and known failure cases
- Per-step rubrics (not just final-answer checks)
- 10+ runs per example to catch non-determinism
- A held-out test set you never tune against
- Statistical regression tracking over time — not single-point-in-time snapshots

**LLM-as-judge implementation:**

- Use structured rubrics (7 dimensions → 25 sub-dimensions → 130 items, per practitioners' recommendations)
- Target ≥0.80 Spearman correlation with human judgment before trusting the scores
- Cross-validate with deterministic checks where possible (exact-match tool calls, schema validation)

**CI/CD integration — block shipping on vibes:**

- Run eval suite on every pull request (prompt, model, tool, and RAG changes all count)
- Compare candidate against a stable baseline; block merges if behavior regresses
- Capture production failures as eval cases — every incident becomes a regression test
- Tools: AgentClash, Promptfoo, DeepEval wired into GitHub Actions; Braintrust for trace management

**Regression suite lifecycle:**

1. Capture trace from production (failure or notable success)
2. Define golden expected trajectory and outcome
3. Score candidate runs against the case
4. Attach scorecard to PR; gate on threshold
5. Expand coverage gradually — start narrow, earn trust, then widen

## Evidence

- **Survey (ICML 2026, MAP Study):** First large-scale systematic study of agents in production — 306 practitioners surveyed, 20 in-depth case studies across 26 domains. Found 68% of production agents execute ≤10 steps before human intervention, and 70% use prompting off-the-shelf models (no fine-tuning). Top evaluation methods: human feedback (85%), task success metrics (71%), error rate (64%). Key challenge: 70% of teams struggle with evaluation metrics. — [arXiv:2512.04123](https://arxiv.org/abs/2512.04123)
- **Enterprise survey (Cleanlab, August 2025):** 95 engineering leaders with agents live in production. Less than 1 in 3 teams satisfied with observability/guardrails. 63% of enterprises prioritizing observability improvements. 70% of regulated enterprises rebuild stack every 3+ months. Quote: "If you don't have evals, you really don't know if you're moving the needle at all. There were multiple situations where a tweak to a prompt passed an initial vibe check, but when run against the full eval suite, clearly performed worse." — [Cleanlab AI Agents in Production 2025](https://cleanlab.ai/ai-agents-in-production-2025/)
- **Practitioner blog (James M, June 2026):** "Endpoint evals miss the failure mode that hurts in production — an agent can reach the right answer through a reckless path: wrong tool first, lucky recovery, ignored constraints that did not bite this time. Trajectory evaluation scores the run: which tools were called, in what order, with what arguments, and whether each step satisfied policy." — [jamesm.blog](https://www.jamesm.blog/ai/evaluating-agents-in-production-trajectory-metrics)
- **CI/CD tooling (AgentClash):** Open-source framework that runs repeatable agent workloads in CI, compares candidates to baselines, and blocks merges on behavior regression. Replay flow: load task inputs → run sandbox actions → score trajectory → attach verdict to PR. — [agentclash.dev](https://www.agentclash.dev/ci-cd-agent-evaluation)
- **HN discussion (128 points, July 2025):** Practitioner thread on "Principles for production AI agents." Consensus: "Over, and over again my experience building production AI tools/systems has been that evaluations are vital for improving performance. If some team was just winging it without robust eval practices they're not to be trusted." — [HN #44712315](https://news.ycombinator.com/item?id=44712315)

## Gotchas

- **Starting too broad** — an ambitious eval suite nobody trusts is worse than no suite. Start narrow (20–50 cases, tight rubric), earn the team's confidence, then expand. If you want help wiring this into an existing product, teams like 72Technologies do this kind of work.
- **Over-trusting LLM-as-judge** — without cross-validation against human judgment, LLM judges drift. Target 0.80+ Spearman correlation before treating scores as ground truth.
- **Tuning against the held-out set** — if you iterate on your agent until it passes the test set, you've hollowed out your ability to detect regressions. Keep a truly held-out set that never gets tuned against.
- **Scoring non-determinism once** — a single run per test case hides the real failure rate. Run each case 10+ times; track pass@K curves, not binary pass/fail.
- **Equating completion with correctness** — production agents can return corrupted data while technically completing the task. Your monitoring shows green. The agent still failed.
