# S-2584 · The Evals Stack: Why Your Agent Ships Fine but Fails in Production

Your agent passes every test in staging. In production, it silently skips refund API errors and reports the case resolved. No single-turn accuracy metric catches that.

## Forces

- **Determinism breaks down.** Traditional software: same input → same output → exact-match assertions work. Agents: probabilistic outputs, multi-step chains, tool calls with side effects — you can't assert on what you can't predict.
- **The demo-to-production gap is structural.** Teams validate the model with benchmarks (MMLU, HumanEval), not the agent as a system. The thing they ship isn't the thing they tested.
- **Evaluation is under-resourced.** The MAP study found 74% of production agents rely primarily on human evaluation. That's not scalable and it's not consistent.
- **Failure modes are invisible.** A tool returns an unexpected error, the agent recovers "gracefully" (i.e., silently skips the step), and the system reports success. Task complete, user unhappy.
- **Stakes scale with autonomy.** As agents take more steps without humans in the loop, the cost of undetected failure grows. Gartner projects 40% of enterprise AI failures by 2028 will trace to inadequate evaluation and monitoring, not model capability gaps.

## The Move

Treat evaluation as a continuous loop across the full agent lifecycle, not a gate between development and production. The pattern that actually works in production combines three layers:

- **Offline evals before every deploy** — curated golden datasets with known-good outputs; automated pass/fail on task success rate, tool call accuracy, and trajectory efficiency; LLM-as-judge with a separate model to avoid self-grading bias.
- **Online evals in production** — sample production traces continuously; automated anomaly and latency alerts; human spot-checks on safety-critical paths.
- **Golden dataset bootstrapping** — start with human vibes-based eval to establish baseline; every production failure becomes a test case; dataset grows as the agent encounters edge cases.
- **Trace-level observability** — instrument every tool call, every step decision, every context window fill; you can't evaluate what you can't see.
- **Step-count governance** — the MAP study found 68% of production agents cap at ≤10 steps before human intervention. Use this as a default guardrail; more steps = more accumulated error surface.
- **Fail-closed by default** — when a tool errors or returns unexpected output, the agent should escalate or halt, not recover silently. Make "skip and continue" the explicit exception, not the default behavior.

## Evidence

- **Survey (n=306, 86 deployed):** First large-scale study of AI agents in production — 74% rely primarily on human evaluation, 70% use off-the-shelf models without weight tuning, 79% rely heavily on manual prompt construction, 68% execute ≤10 steps before human intervention. Evaluation practices vary widely even within the same domain. — *Measuring Agents in Production (MAP), arXiv:2512.04123v1, December 2025* — https://arxiv.org/html/2512.04123v1

- **Engineering blog:** Production-grade evaluation pipelines require separate judge models to reduce self-grading bias. Task success, graceful recovery from tool failures, and consistency under variability matter more than scoring well on curated test sets. Agents must be evaluated on behavioral dimensions, not just text output. — *Evaluating AI Agents in Practice: Benchmarks, Frameworks, and Lessons Learned, InfoQ, March 2026* — https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned

- **Survey (n=1,837 enterprises):** Only 5% have AI agents in production. 70% of regulated enterprises rebuild their agent stack every 3 months. <1 in 3 teams are satisfied with their observability and guardrails. 63% are prioritizing observability improvements. — *AI Agents in Production 2025: Enterprise Trends and Best Practices, Cleanlab* — https://cleanlab.ai/ai-agents-in-production-2025

- **Vendor guide:** Offline evals test correctness and regressions before deployment; online evals catch quality drift and safety violations in production. Production failures seed the golden dataset, turning regressions into future test coverage. — *Evaluating AI Agents at the Run, Trace, and Thread Level, LangChain* — https://www.langchain.com/resources/agent-evals

- **Analyst report:** By 2028, 40% of enterprise AI failures will trace to inadequate evaluation and monitoring of agent systems rather than model capability gaps. — *Gartner "AI Risk Management Predictions," 2026 (cited in Thinking Inc guide)* — https://thinking.inc/en/blue-ocean/agentic/ai-agent-evaluation-production

## Gotchas

- **Benchmarks mislead.** MMLU and HumanEval test the model, not the agent. A high benchmark score doesn't predict whether your agent will correctly handle a failing API call mid-session.
- **"Graceful degradation" can be silent failure.** If your agent swallows tool errors and reports success, you have no way to detect it without trace-level instrumentation.
- **Human eval doesn't scale.** It's the right starting point to bootstrap your golden dataset, but 74% of teams still relying on it as primary is a problem — it's slow, inconsistent, and doesn't catch regressions between human review cycles.
- **LLM-as-judge has bias.** A judge model evaluated by the same model family will systematically over-rate. Use a different model family for the judge, or at minimum a larger model for the judge than the agent.
- **Golden datasets go stale.** Production behavior drifts as user inputs evolve. Your golden dataset needs a curation workflow — production failure samples should automatically feed back into the test suite.
