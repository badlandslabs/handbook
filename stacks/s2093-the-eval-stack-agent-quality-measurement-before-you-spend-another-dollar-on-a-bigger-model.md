# S-2093 · The Eval Stack: Agent Quality Measurement Before You Spend Another Dollar on a Bigger Model

Teams obsess over which model powers their agent and ignore how they know whether it works. Model size is upstream of the problem. The eval infrastructure is where production agent quality actually lives — and most teams don't have one.

## Forces

- **Benchmarks measure potential, not reliability.** AgentBench, WebArena, τ-bench, SWE-bench all answer "can this agent class do this task?" — not "does my agent do it reliably in my domain?" A 65% on AgentBench tells you nothing about your customer support agent's failure modes.
- **Single-turn metrics lie about multi-turn agents.** BLEU, ROUGE, and even MMLU don't capture trajectory quality — whether the agent chose the right tools in the right order, recovered from errors, or wasted tokens on dead ends. An agent that gets the right answer via a 40-step hallucinated detour is not a good agent.
- **LLM-as-judge scales but lacks taste.** Using a strong LLM to score agent outputs gives you cheap, fast evaluation — but the judge model has known failure modes: it praises fluency over correctness, it doesn't catch subtle factual drift across long traces, and it can't taste the difference between an acceptable refusal and a graceful one.
- **Golden datasets rot.** A test set built today from production traces will be 40% misaligned with real traffic in 6 months as user behavior, tool APIs, and prompts evolve. Teams build evals once and then trust stale tests.
- **Evaluation is not a tool problem.** Picking between DeepEval, RAGAS, LangSmith, Braintrust, Arize Phoenix, or Promptfoo is downstream of the real question: what does your evaluation *system* look like? The framework is a component; the architecture is the deliverable.

## The move

Build a layered eval system — three tiers that together cover the lifecycle:

**1. Offline regression suite (before deploy)**
- Curate a golden dataset of 50–200 representative agent interactions from production traces, not synthetic examples
- Run this suite in CI/CD on every prompt or model change
- Track: task success rate, tool call sequence accuracy, trajectory efficiency (step count vs. minimum steps), refusal correctness
- Use a deterministic checker for task success when ground truth exists; use LLM-as-judge for subjective dimensions (tone, helpfulness) with a human calibration set of ~20 cases

**2. Shadow + online evaluation (during deploy)**
- Run candidate agent versions in shadow mode alongside production — real traffic, no user impact — for 1–2 weeks
- Sample 5% of production traces for human review, stratified by: high-cost sessions, sessions with tool failures, sessions where the agent requested clarification
- Track: cost per task, latency percentiles (p50, p99), tool call error rates, rate of unnecessary tool invocations, user escalation rate

**3. Continuous improvement loop (after deploy)**
- Ingest flagged production failures back into the golden dataset automatically, with a human review queue for triage
- Re-run the regression suite weekly; regressing cases get priority triage
- Calibrate LLM-as-judge quarterly against your human-reviewed cases to detect drift

**Domain-specific trajectory evals beat public benchmarks.** For tool-using agents: define the minimum correct tool-call sequence for each task type, then score agents on (a) whether they reached the goal, (b) whether they used the minimum sequence or wasted steps, (c) whether they recovered gracefully on the failures they hit. This is more actionable than any benchmark number.

**Track the ratio that matters: eval signal to decision.** The goal of evaluation is to enable a decision (ship/rollback, prompt A vs. B, model X vs. Y). If your eval output doesn't change a decision, it is generating noise. Prune metrics that don't drive actions.

## Evidence

- **ZenML LLMOps case study (2026):** Langchain engineers described achieving top-5 performance on Terminal Bench 2.0 through harness engineering alone — zero model changes. Their key finding: "An agent equals a model plus a harness. The model is a black box. The harness is everything that can be engineered and improved." — [ZenML LLMOps Database, Langchain case study](https://www.zenml.io/llmops-database/building-production-ready-ai-agents-through-harness-engineering-and-continual-learning)
- **BigDataBoutique engineering post (2026):** An LLM practitioner outlined the three-layer production eval architecture (offline regression + shadow + online monitoring) and documented the specific failure modes each layer catches. Key quote: "Most teams treat LLM evaluation as a tool-selection problem. It is not. Picking DeepEval over Ragas, or LangSmith over Braintrust, is downstream of a question that almost nobody answers explicitly: what does the evaluation system look like?" — [BigDataBoutique blog](https://bigdataboutique.com/blog/llm-evaluation-frameworks-metrics-best-practices)
- **arXiv survey (2507.21504, July 2025):** A systematic taxonomy of LLM agent evaluation organized across two dimensions — what to evaluate (agent behavior, capabilities, reliability, safety) and how to evaluate (interaction modes, datasets, metric computation, tooling) — finding that the field lacks consensus on evaluation process and enterprise-specific challenges remain underaddressed. — [arXiv:2507.21504](https://arxiv.org/abs/2507.21504)
- **Hacker News discussion (July 2025, 128 points):** Practitioners on an "Evaluate AI agent in production" thread agreed: "If you don't have evals, you really don't know if you're moving the needle at all" and "Evals are a core part of any up-to-date LLM team. If some team was just winging it without robust eval practices, they're not to be trusted." — [HN #44712315](https://news.ycombinator.com/item?id=44712315)
- **Langfuse engineering guide (2025):** Documented the golden dataset maintenance problem: test sets built from production traces degrade ~40% in 6 months without active refresh from new traffic, making dataset hygiene a first-class engineering concern. — [Langfuse Golden Dataset Guide](https://langfuse.com/resources/engineering/golden-dataset-evaluation)

## Gotchas

- **Public benchmark scores are a floor, not a ceiling.** A high AgentBench score means your agent class *can* perform — not that *your* agent *will* perform reliably in your specific tool environment. Always build domain-specific trajectory evals.
- **LLM-as-judge has a taste problem.** The judge model can be too generous on fluency, too lenient on factual drift, and inconsistent on edge cases. Always calibrate against a human-reviewed subset of 20+ cases before trusting judge scores for consequential decisions.
- **Offline eval can't catch tool-API drift.** Your golden dataset tests against the tool behavior of today. When a third-party API changes its response schema or a UI updates, your eval suite will pass but your agent will fail silently in production. Monitor tool-call error rates in production, not just in the test harness.
- **Golden datasets need a half-life policy.** Treat your test set like a cache — it decays. Set a calendar reminder to review and refresh every 90 days, prioritizing cases that surfaced as failures in production shadow runs.
