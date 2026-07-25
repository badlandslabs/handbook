# S-1616 · The Agent Eval Stack — When Your Agent Aces Its Demo and Silently Fails in Production

Your agent passed every prompt you tried in development. You shipped it. Two weeks later, your compliance officer asks how you know it isn't hallucinating patient data. You have no answer. This is the eval gap: agents that perform brilliantly in the sandbox and degrade invisibly in production — and no systematic way to catch it.

## Forces

- **Agent outputs are probabilistic, not deterministic.** A correct answer today is no guarantee of a correct answer next Tuesday. Traditional unit tests cannot check "did the agent do the right thing" because the right thing varies by context and temperature.
- **Behavior changes without version bumps.** LLM providers silently update models. A task that scored 97% in March can drop to 87% by June on the same benchmark — without any code change on your end. Dente et al. document "constraint decay": agents that pass baseline API contracts drop ~30 percentage points once structural constraints (database, ORM, framework requirements) stack on top.
- **Human spot-checks do not scale.** Teams that evaluate pre-launch with careful manual testing stop monitoring post-launch. Production quality degrades within 30–60 days without continuous evaluation. You cannot eyeball millions of agent invocations.
- **The eval is the product.** Without a measurement system, you are shipping on vibes. Every prompt change, model swap, and tool reconfiguration is unanchored — you cannot know if you're improving or regressing.

## The Move

Build a layered evaluation harness with four strata, each catching a different failure class. The key insight: **picking an eval framework (DeepEval vs. Ragas vs. LangSmith) is downstream of this architecture** — tools slot in, they do not replace it.

### Layer 0 — Structural / Smoke Tests (fastest, runs on every PR)
- Is the output valid JSON?
- Are required fields present?
- Do length and format constraints hold?
- Does the API return 200?
These are deterministic checks. If any fail, the agent is broken — no LLM needed to evaluate them. **Must gate CI.**

### Layer 1 — Golden Set Ground Truth (the anchor)
- Curate 100–1,000 query/answer pairs representing real production inputs.
- Label a small slice by hand (expensive but irreplaceable — synthetic labels without human calibration become circular).
- Measure exact match, ROUGE, F1, or BERTScore against known-good answers.
- This is your regression baseline. It tells you nothing about quality — only about *drift* from a known state.

### Layer 2 — LLM-as-Judge with Calibrated Rubric (the primary quality layer)
- Use a separate, capable model to grade agent outputs against a written rubric.
- Rubric must be a single document read by **both** human labelers and the judge — calibration is only meaningful when both sides score the same thing.
- Keep a small, human-labeled gold slice. When judge and human disagree, fix the rubric spec, not the model.
- Track inter-annotator agreement (Cohen's kappa) to know when your rubric is ambiguous.
- Score on multiple dimensions: groundedness (every claim supported by retrieved context), relevance, coherence, tool-use correctness.
- Sample and escalate disagreements; do not hand-score every CI run.

### Layer 3 — Production Monitoring and Regression Gates
- Run eval suite against a shadow slice of live traffic (not all traffic — use stratified sampling).
- Track hallucination rate, context recall, tool-selection accuracy, latency, and cost per invocation.
- Gate CI: no agent change ships if the golden set accuracy regresses below threshold.
- Set alerts on behavioral drift: if task success rate drops >5% week-over-week on the same test set, investigate before users see it.
- Continuous evaluation reduces production incidents by ~67% versus periodic evaluation.

## Evidence

- **arXiv survey:** "Constraint Decay" (Dente, Satriani, Papotti, 2026) — agents that pass a baseline API contract drop ~30pp in assertion pass rates once structural constraints accumulate. Existing benchmarks reward functionally correct but structurally arbitrary solutions. — [https://arxiv.org/abs/2605.06445](https://arxiv.org/abs/2605.06445)
- **Hacker News (287 points):** Discussion of "Constraint Decay" surfaces the core HN finding: models degrade when both behavior and architecture must be correct simultaneously. Commenter jdlhore notes frontier models were excluded from full testing for cost reasons, but the overall constraint-stacking effect holds. — [https://news.ycombinator.com/item?id=48256912](https://news.ycombinator.com/item?id=48256912)
- **Hacker News (128 points):** An engineer who owned an eval suite for a coding agent reports: "Without evals, you cannot know if you're moving the needle at all. Many prompts pass initial vibe checks but fail against full eval suites." Categorizes evals as either warning evals (signal without blocking) or blocking evals (required to ship). Recommends starting with hundreds of evals, then narrowing to feature-specific subsets. — [https://news.ycombinator.com/item?id=44712315](https://news.ycombinator.com/item?id=44712315)
- **Hacker News (110 points):** "Why eval startups fail (2025)" — practical golden dataset gives product, eng, and compliance a shared contract: "these are the scenarios our agent must handle." Argues shipping agent changes without a data-defined "good" is shipping on vibes. — [https://news.ycombinator.com/item?id=48637868](https://news.ycombinator.com/item?id=48637868)
- **Anthropic engineering (Jan 2026):** "Demystifying Evals for AI Agents" — four evaluation layers (capability benchmarks pre-deployment, functional evals against ground truth, trace-based evals for agent-specific behavior, human preference data for end-to-end quality). Agents are hard to evaluate precisely because their autonomy, tool use, and multi-turn adaptation create behavior that single-turn benchmarks miss. — [https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **BigData Boutique (May 2026):** Most teams treat eval as a tool-selection problem; the real question is the evaluation architecture. Ships with offline regression, shadow evaluation, and human-calibrated anchors. LangSmith, Braintrust, Patronus AI, and DeepEval are named as tooling that fits into that architecture. — [https://bigdataboutique.com/blog/llm-evaluation-frameworks-metrics-best-practices](https://bigdataboutique.com/blog/llm-evaluation-frameworks-metrics-best-practices)
- **Towards Data Science (May 2026):** 12-metric framework from 100+ deployments across categories: retrieval (context relevance >0.85), generation (faithfulness, hallucination rate), tool use (selection accuracy, call ordering), and operational (latency, cost-per-invocation, PII leakage). — [https://towardsdatascience.com/building-an-evaluation-harness-for-production-ai-agents-a-12-metric-framework-from-100-deployments/](https://towardsdatascience.com/building-an-evaluation-harness-for-production-ai-agents-a-12-metric-framework-from-100-deployments/)
- **Gartner (2026, cited in thinking.inc):** By 2028, 40% of enterprise AI failures will trace to inadequate evaluation and monitoring — not model capability gaps.

## Gotchas

- **"LLM-as-judge is the answer" is circular thinking.** If the judge is wrong, every metric built on top of it is fiction. Calibrate against human-labeled data before trusting judge scores. Cohen's kappa on your rubric is the signal — if annotators disagree, the judge will too.
- **Zero evals at launch is a debt you will pay.** Teams that skip evaluation infrastructure to ship faster consistently find their agent quality degraded within 30–60 days post-launch with no regression detection.
- **Constraint decay is invisible to task-success metrics.** An agent that passes "does it compile" will fail "does it use the ORM we specified." You need both behavioral and structural evaluation criteria. The 30pp drop Dente et al. document is specifically the gap between functional correctness and architectural compliance.
- **Golden set size matters less than golden set quality.** A 50-query set labeled by a subject matter expert outperforms a 500-query set generated synthetically without review. Spend the SME time upfront.
- **Silent behavioral drift from model updates.** GPT-4 showed measurable behavior changes across versions — tasks at 97% accuracy dropped to 87% by June 2023 on the same benchmark. Re-run your golden set after any model change, even if the provider says nothing changed.
