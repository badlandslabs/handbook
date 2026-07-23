# S-1548 · The Agent Failure Taxonomy Stack — When Agents Break in Ways Unit Tests Cannot Catch

A conventional web service crashes and logs a stack trace. An agent may silently loop for 35 minutes, spawn redundant subprocesses, accumulate context until the model halts mid-reasoning, or take an irreversible action — all without a single error log. The failure taxonomy for agents is categorically different from traditional software, and treating it as a debugging problem produces broken systems. The pattern that works: model failures as a first-class systems problem with explicit detection, classification, and recovery primitives.

## Forces

- **Specification failures dominate.** Galileo (2025) analysis found specification failures account for ~42% of multi-agent failures, coordination breakdowns for ~37%, and verification gaps for only 21%. This means most agent failures live upstream of the agent itself — in what the agent was asked to do, not how it did it.
- **Pipeline reliability compounds brutally.** A 10-step pipeline where each step has 85% reliability produces ~20% end-to-end success. A single 2% failure rate per step on a 30-step agent task leaves you with ~55% reliability. Unit testing the happy path misses all of this.
- **Agents fail non-deterministically.** The same input can produce different tool call sequences, different context window pressures, and different failure modes on different model versions. A regression test suite that passed last Tuesday may be testing a world that no longer exists.
- **Traditional try-catch does not apply.** Agents fail by producing wrong-but-plausible outputs, looping without progress, or taking irreversible actions before a human can intervene. These are not exceptions — they are expected modes of operation that require different handling.

## The Move

**1. Classify failures by their recovery path, not their symptom.** Group agent failures into three buckets with distinct remediation strategies:
- *Specification failures* — the agent did what was asked, but the ask was wrong. Recovery: fix the task definition, not the agent.
- *Coordination failures* — multiple agents or steps disagree on shared state, priority, or authority. Recovery: introduce explicit state arbitration, supervisor handoffs, or consensus protocols.
- *Verification failures* — the agent produced a result that looks correct but isn't. Recovery: add a separate verifier agent (typically a smaller, faster model) whose only job is to check whether the output actually answers the query.

**2. Implement a loop detector as a hard circuit breaker.** Count tool-call cycles per reasoning step. If an agent calls the same tool more than N times with non-progressing state, or cycles through N tool calls without a visible state change, trigger a rollback. LangGraph and Microsoft Agent Framework both provide native checkpoint/resume primitives for this.

**3. Use stateful rollbacks, not retry loops.** A naive retry (re-run the same input) does not fix the failure — it re-runs the same reasoning that produced the failure. Instead: capture checkpoints at each reasoning milestone, and on failure, restore to the last known-good state before retrying with a modified strategy. The agentmemory project's 12 auto-capture hooks (GitHub: rohitg00/agentmemory, 25k+ stars) demonstrate that automatic checkpointing is a solved problem in tooling.

**4. Route critical outputs through a verifier agent before committing side effects.** The AI System Design Guide (ombharatiya/ai-system-design-guide, 2025) documents this pattern: pipe tool outputs to a verifier agent that checks correctness before the next step proceeds. If the verifier says "no," trigger the self-correction loop as if it were a hard error.

**5. Build graceful degradation as the default.** When a non-critical component fails, the agent should continue with degraded capability rather than halt. Define explicit degradation paths: if the search tool fails, fall back to cached results; if a sub-agent times out, the supervisor routes to the next available worker.

**6. Instrument for failure observability.** Agent failures are invisible in standard APM. Log: reasoning step count, tool call sequence, context window utilization percentage, and LLM token velocity. A spike in reasoning steps without corresponding progress is the earliest signal of a loop.

## Evidence

- **Research paper (arXiv 2511.15755):** Multi-agent orchestration for incident response achieves deterministic outcomes — zero quality variance across trials — versus high variance in single-agent setups. Single-agent: 1.7% actionable recommendations, 140× worse solution correctness. Multi-agent supervisor: 100% actionable recommendations, zero quality variance. — [arXiv:2511.15755](https://arxiv.org/abs/2511.15755)

- **Engineering guide (ombharatiya/ai-system-design-guide):** Critical tool outputs should route through a Verifier Agent — a smaller model checking "does this output actually answer the query?" — before the next step proceeds. Failures classified as specification (~42%), coordination (~37%), verification (~21%) per Galileo 2025 analysis. — [GitHub: ombharatiya/ai-system-design-guide/07-error-handling-and-recovery](https://github.com/ombharatiya/ai-system-design-guide/blob/main/07-agentic-systems/07-error-handling-and-recovery.md)

- **Research synthesis (Zylos Research, 2026-05-06):** Fault tolerance for agents is "not optional engineering hygiene — it is the core engineering challenge of the agentic era." A 10-step pipeline at 85% per-step reliability = ~20% end-to-end success, illustrating why naive reliability assumptions collapse in multi-step agent systems. — [Zylos Research — Agent Self-Healing and Failure Recovery](https://zylos.ai/zh/research/2026-05-06-agent-self-healing-failure-recovery/)

- **Open-source project (rohitg00/agentmemory):** Ships 12 auto-capture hooks for automatic checkpointing across tool calls, replacing manual memory management. Hit 25,650 GitHub stars in 2026, indicating the market has moved from "do it yourself" checkpointing to tool-native solutions. — [GitHub: rohitg00/agentmemory](https://github.com/rohitg00/agentmemory)

- **Production case study (Devinity, 2026):** Naive RAG pipelines fail at retrieval ~40% of the time. The real cost is not per-query price — it's cost per correct answer. A $0.08 agentic query at 95% accuracy beats a $0.01 naive query at 60% accuracy. This extends to agent pipelines generally: spending tokens on verification is cheaper than the cost of failures. — [Devinity — Agentic RAG in 2026](https://www.devinitysolutions.com/blog/agentic-rag-2026)

## Gotchas

- **Do not retry without rollback.** Retrying the same input on the same agent state re-executes the same reasoning. If the failure is in the approach — not random noise — the retry produces the same failure. Always restore to a checkpoint before retrying.
- **The verifier agent is not optional for high-stakes actions.** Skipping verification on file writes, API calls, or database mutations because "the model said it was confident" is the most common source of production incidents. Confidence and correctness are uncorrelated in LLM outputs.
- **Context window pressure is a failure mode, not a performance metric.** As context fills, agents degrade before they fail. Monitor context utilization proactively — not just when an error occurs. A 90% full context window is already degraded.
- **Model version changes break failure assumptions.** An agent that recovered gracefully on GPT-4o may loop indefinitely on a newer model with different reasoning patterns. Treat model updates as a failure-mode regression test trigger, not a routine deployment.
