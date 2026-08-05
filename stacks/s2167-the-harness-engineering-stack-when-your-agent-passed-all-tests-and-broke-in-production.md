# S-2167 · The Harness Engineering Stack — When Your Agent Passed All Tests and Broke in Production

Your agent scored 94% on your test suite. It aced the regression tests. Your team signed off. Three days in production it started selecting the wrong tools, drifting from its task, and generating confident but incorrect outputs — all while returning HTTP 200 and calling tools at normal throughput. The tests passed. The agent failed. You were testing the wrong thing.

## Forces

- **Response quality ≠ action correctness.** Standard LLM benchmarks measure whether an answer is good. Agent evaluation measures whether the right action happened — a fundamentally different pass condition. The agent can produce a perfect response while taking the wrong action, or take the right action while producing a poor-sounding explanation.
- **Single-step benchmarks miss pipeline collapse.** Each step in a multi-step agent may have 85% reliability. Ten steps in sequence yield a 20% end-to-end success rate — not because any single step is broken, but because failures compound. Standard unit tests never surface this.
- **Regression is invisible without continuous gates.** A prompt change can improve performance on one query class while degrading five others. Without automated regression gates in CI/CD, degraded variants reach production where users encounter them first.
- **The pass condition is the side effect.** Whether a CRM was updated, a refund code was generated, or a warranty flag was applied — not what the agent said it would do.

## The Move

Shift agent evaluation from accuracy measurement to **deployment readiness assessment**, with automated gates that run in CI/CD and block releases that fail any readiness dimension.

**The 7 Harness Gates** (Agent-Evaluator framework, backed by Axian's production evaluation taxonomy):

- **Gate A — Goal Achievement:** Did the agent accomplish the stated objective? This is the outcome, not the explanation.
- **Gate B — Behavioral Integrity:** Did the agent follow its defined protocol — correct tool selection, correct parameter values, no unauthorized actions? Enforced via expected tool-call sequences.
- **Gate C — Reliability:** Does the agent succeed consistently across runs and variants of the same task, not just on the happy path?
- **Gate D — Performance Contract:** Does it meet latency, token budget, and step-count SLAs? An agent that works but costs 10× budget isn't production-ready.
- **Gate E — Security Boundary:** Did the agent resist prompt injection, stay within its permission scope, and not exfiltrate data? Requires adversarial test cases, not just functional tests.
- **Gate F — Multi-Agent Coordination:** In multi-agent systems, do agents correctly share state, avoid deadlocks, and handle coordination failures gracefully?
- **Gate G — Observability:** Does the agent emit structured traces with sufficient detail to reconstruct any failure? If you can't replay it from logs, it isn't production-ready.

**Operationalizing gates:**

- Run all 7 gates against every pull request via CI/CD integration
- Set per-gate threshold scores that must pass before deployment proceeds
- Track gate scores over time — a declining Gate B score is an early warning before users complain
- Use LLM-as-judge for Gates A and B (a separate model evaluates whether the action was correct), with deterministic checkers for Gates D–G
- Require trace-level replays: if you can't reproduce a failure from logs alone, the failure is not yet diagnosed enough to ship past Gate G

## Evidence

- **PyPI/GitHub:** Agent-Evaluator by bullpeng72 — evaluation framework with 7 Harness Gates and 58 metrics (25 native trackers + 33 harness configs). Supports 24 frameworks including LangChain, CrewAI, AutoGen, DSPy, PydanticAI via a single decorator line. Auto-recognizes framework and measures metrics without code modification. — https://github.com/bullpeng72/Agent-Evaluator | https://pypi.org/project/agent-evaluator
- **Blog post (Axian, Solutions Architect Todd Parker):** Frames the shift from "Was the answer good?" to "Did it act correctly?" Documents the 7-gate evaluation framework and explains why agents represent "a predictable layer above a model's variability." Cites Gartner: 40% of enterprise applications will include task-specific AI agents by 2026 (up from <5% in 2025). — https://www.axian.com/2026/03/10/ai-agent-evaluation/
- **Research synthesis (Zylos, 2026):** In multi-step pipelines, a 10-step workflow where each step has 85% reliability succeeds only ~20% of the time end-to-end. Documents failure taxonomy: ~42% specification failures, ~37% coordination breakdowns, ~21% verification gaps. — https://zylos.ai/en/research/2026-05-06-agent-self-healing-failure-recovery

## Gotchas

- **LLM-as-judge is gamed by verbosity.** If you score goal achievement by how confidently the agent explains its actions, verbose failure modes score higher than concise correct ones. Anchor judgments to verifiable side effects, not self-reported reasoning.
- **Benchmark saturation masks regression.** If your test cases don't cover enough surface area, a 94% score can coexist with degraded performance on inputs you haven't encountered yet. Expand your test distribution continuously.
- **Gate G (observability) is the most commonly skipped gate — and the most critical for diagnosing failures.** Teams implement Gates A–F, then discover they can't replay failures because the trace is missing tool parameters, intermediate states, or error context. Build tracing first, not last.
