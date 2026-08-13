# S-2573 · The Eval Stack — When You Ship an Agent and Have No Idea If It's Better

When an agent goes to production and a week later you're still guessing whether it's improving — not because the agent is opaque, but because your measurement infrastructure is.

## Forces

- **Output variability vs. determinism** — agents can reach the right answer by the wrong path, or a plausible wrong answer by a correct-looking process. Final output alone tells you almost nothing about quality.
- **The regression you can't see** — agents can degrade in production without a deploy, code change, or visible error. Model provider updates silently shift behavior mid-conversation.
- **Cost vs. coverage** — human review at 100% sampling is expensive; automated eval at 100% coverage is unreliable. Teams settle for neither.
- **Benchmarks saturation** — public benchmarks get absorbed into training data. Your agent's specific task (contract review, customer triage, research synthesis) has no pre-existing benchmark that matters.

## The Move

Build an eval stack that measures agent behavior at multiple granularities, not just final output. Treat evaluation as a first-class engineering artifact — versioned, automated, and gatted.

**The four-layer eval stack:**

- **Layer 1 — Component quality.** Test each building block independently before checking end-to-end runs: tool selection accuracy across the full inventory (sliced by task type and ambiguity), argument quality (required fields, valid values), and planning quality (step ordering, premature stopping). Run these on every PR.
- **Layer 2 — Trajectory quality.** Score the full multi-step execution path, not just the terminal output. The audit trail is the evidence — in regulated domains (healthcare, finance, legal), the scored trajectory IS the compliance record. Measure step correctness, tool-call sequence fidelity, and intermediate-state validity.
- **Layer 3 — End-to-end / functional quality.** Does the agent complete the task? Did it use the right tool? Answer the actual question? Format output correctly? These run against a golden dataset: versioned inputs with expected outputs or scored rubrics.
- **Layer 4 — Production monitoring.** Sample live traffic for human review (10% baseline, 25%+ for client-facing workflows), track structured rubric scores across 8 quality dimensions monthly, and flag any agent showing >3% quality decline week-over-week. This is where the eval loop closes.

**Build the golden dataset from real failures.** Start with 20–50 high-signal cases drawn from your highest-impact incidents and core user journeys, not from hypothetical scenarios. Expand weekly as production reveals new failure modes. Each case needs: fixed `input`, `expected_behavior`, `checks` (deterministic validations), and `tags` (risk + scenario grouping). Without versioning, test results become incomparable between runs.

**Gate CI/CD on eval runs.** Every commit that touches prompts, model selection, or workflow logic should trigger the full eval suite. Compare candidate against baseline on fixed datasets — this is the experiment. The dataset and evals stay fixed so you isolate the impact of the change. Without this gate, you're deploying blind.

**Use LLM-as-judge with calibration, not faith.** LLM judges scale evaluation but introduce reliability variance. Calibrate against human annotations using Spearman correlation before trusting automated scores. For open-ended tasks where ground truth doesn't exist (summarization, creative writing), a well-designed rubric + LLM judge is the only viable option — just validate it first.

## Evidence

- **HN Discussion (2025):** On Anthropic's "Building Effective AI Agents" post (543 points), practitioners debated framework choice and evaluation gaps. A respondent noted: "Over, and over again my experience building production AI tools has been that evaluations are *vital* for improving performance" — and questioned whether LLM-as-critic works without empirical validation. — [HN #44301809](https://news.ycombinator.com/item?id=44301809)
- **HN Discussion (2025):** On "Six Principles for Production AI Agents" (128 points), practitioners cited the LLM-as-judge reliability problem, internal experiments showing variance, and the recommendation to own your evals rather than rely on benchmarks. — [HN #44712315](https://news.ycombinator.com/item?id=44712315)
- **Production Engineering Guide (Dec 2025):** A principal ML engineer described building automated eval pipelines triggered on every commit — getting reports on success rates, efficiency, and regressions before deployment. Compared eval infrastructure to test suites: "foundational, not optional." — [ashutoshtripathi.com](https://ashutoshtripathi.com/2025/12/01/ai-agent-performance-evaluation-a-production-engineers-guide)
- **LLM Evaluation Taxonomy (2026):** Production teams use four eval types in combination: LLM-as-Judge, reference-driven metrics, rubric-based assessment, and automated UI/functional testing. Coverage across these types correlates with catching different failure modes. — [arXiv:2604.12162](https://arxiv.org/pdf/2604.12162) (AlphaEval study, 2026)
- **Langfuse Cookbook:** The three-phase eval progression: (1) manual trace inspection during initial build, (2) online evaluation via production sampling and user feedback signals, (3) offline evaluation at scale via golden datasets run in automated pipelines. — [langfuse.com](https://langfuse.com/guides/cookbook/example_pydantic_ai_mcp_agent_evaluation)
- **Agent Patterns:** Golden dataset case schema: `id`, `input`, `expected_behavior`, `checks` (deterministic), `tags`. Without versioned cases, teams get unstable diffs and noisy CI gates they stop trusting. — [agentpatterns.tech](https://www.agentpatterns.tech/en/testing-ai-agents/golden-datasets)

## Gotchas

- **Benchmark saturation is real.** Public evals (MMLU, HumanEval) get absorbed into training data. Your agent's specific domain has no off-the-shelf benchmark that measures what you actually care about. Build your own.
- **Sampling bias in golden datasets.** A suite dominated by happy paths will give you false confidence. Balance coverage across failure modes, especially cases drawn from production incidents — these are the highest-signal test cases.
- **LLM-as-judge overconfidence.** Judges perform better on some task types (factual QA) than others (subjective tone, nuanced reasoning). Validate judge scores against human annotations before treating them as ground truth.
- **Eval lag.** Offline evals on every commit catch regressions fast, but they measure behavior on static datasets — not live production distribution drift. You need both layers; offline evals don't replace production monitoring.
