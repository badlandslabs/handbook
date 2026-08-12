# S-2537 · The Agent Evaluation Stack — When You Ship Agents and Can't Tell If They Work

You built the agent. It passes your demo. You ship it. Three weeks later you discover it's been routing 40% of Tier 2 support tickets to the wrong team, silently, with HTTP 200 and normal latency. Your APM shows green. Traditional testing assumes deterministic output — same input, same output. Agents break that contract by design. They plan, call tools, reason across steps, and fail in ways that live inside the trajectory, not the final answer. Without evaluation infrastructure, you have no way to know your agent works until a customer tells you it doesn't.

## Forces

- **Trace vs. outcome** — the final output tells you almost nothing about whether the agent got there correctly; the failure is usually in the 4th tool call, invisible in a pass/fail check
- **Non-determinism vs. reproducibility** — even with temperature=0, model updates, hardware changes, and server-side batching introduce variance; a test that passes once means nothing without re-runs or statistical bounds
- **Offline validation vs. production drift** — a passing CI suite means nothing if the agent's behavior silently changes after a model provider update or a tool's response format shifts
- **Cost and latency as failure modes** — agents can succeed at their task while burning $500 in API calls or looping for 20 minutes; traditional error rates miss both
- **The tooling split** — CI/code-first frameworks (DeepEval, promptfoo) and production observability platforms (LangSmith, Langfuse, Phoenix) serve different stages; most teams use one from each column

## The move

Build a three-layer evaluation stack that covers pre-ship, regression, and production:

**1. Diagnostic hierarchy — three levels, not one.**
- *End-to-end*: black-box check — did the task actually complete? Score against ground truth or LLM judge.
- *Trajectory-level*: inspect the full ordered trace — was the plan sound, were tools called correctly, were retries or handoffs appropriate?
- *Component-level*: identify the failing part — which retriever, tool call, or sub-agent broke — so you fix the right thing.

Use these as a diagnostic stack: start at end-to-end, drill to trajectory, isolate at component. Never stop at end-to-end alone.

**2. Two-tool combo — CI gate + observability platform.**
Most mature teams pair a code-first eval framework (run in CI on every commit) with a tracing/observability platform that scores production traffic in real time:
- *Code-first*: DeepEval (Python, pytest-style assertions, trajectory scoring), promptfoo (config-driven, red-teaming focus), or RAGAS (retrieval-heavy pipelines)
- *Observability*: LangSmith (deepest LangChain integration, managed SaaS), Langfuse (open-source, self-hostable, OpenTelemetry-native), or Arize Phoenix (notebook-first, fastest setup, strong built-in eval engine)

**3. Define Safety SLIs — the fifth reliability dimension.**
Microsoft's Agent SRE pattern adds a Safety SLI to the traditional four (correctness, latency, tool success, cost). The Safety SLI catches behavioral failures invisible to traditional APM: unauthorized actions, hallucinated paths, policy bypasses. Track it alongside your existing SLOs. A circuit breaker that trips when Safety SLI drops below 99% catches runaway behavior before the invoice does.

**4. Treat every diagnosed production failure as a regression test in waiting.**
Every customer-reported failure should produce: a trace, a label, a dataset row, and a scorer. If the failure is reproducible, it belongs in your CI eval suite. The goal is to never ship the same behavioral failure twice.

**5. G-Eval and LLM-as-a-judge for anything requiring judgment.**
Deterministic checks (exact string match, tool name, parameter shape) are fast and reliable. LLM-as-a-judge — a separate model scoring quality dimensions — handles anything requiring judgment: correctness, tone, safety, helpfulness. Calibrate judges against human-reviewed samples periodically; uncalibrated judges drift.

**6. Track operating envelopes, not just pass/fail.**
Log cost per task, latency per step, and token counts alongside quality scores. An agent that scores 95% but costs $50 per task or loops 30 times is not production-ready regardless of its quality score.

## Evidence

- **HN thread (Ask HN):** Practitioners shared 7 core failure modes agents exhibit that traditional testing misses — hallucination under unexpected inputs, context limit surprises, cascade failures where 3 compounding tool errors happen before human review, and silent behavioral drift after model updates. Root cause: traditional APM flags zero errors while the agent makes wrong decisions. — [Ask HN: How are you testing AI agents before shipping to production? — Hacker News](https://news.ycombinator.com/item?id=47325105)

- **Microsoft engineering post:** Documented the "Day 2 problem" — agents fail silently in ways that standard observability doesn't catch (unauthorized transactions approved, wrong database paths written). Introduced Safety SLI as the 5th reliability dimension alongside correctness, latency, tool success, and cost. Ships in open-source `agent-sre` package within Microsoft's Agent Governance Toolkit. — [Applying Site Reliability Engineering to Autonomous AI Agents — Microsoft Tech Community](https://techcommunity.microsoft.com/blog/linuxandopensourceblog/applying-site-reliability-engineering-to-autonomous-ai-agents/4521357)

- **SWE-bench benchmark data:** The SWE-bench leaderboard (2,294 real GitHub issues, 12 Python repos) shows state-of-the-art agents resolving ~79% of issues, with the Verified subset (500 human-filtered tasks) providing the canonical quality bar for coding agents. First published October 2023; actively maintained. — [SWE-bench Leaderboard — codesota.com](https://www.codesota.com/browse/agentic/swe-bench)

## Gotchas

- **Golden datasets rot.** If you generate reference outputs with the same model you're testing, your evals are circular. Human-validated ground truth is the only legitimate benchmark baseline.
- **A single eval run is not a verdict.** Model variance means a 70% pass rate on one run might be 85% or 55% on the next. Run critical scenarios multiple times; flag flakiness explicitly.
- **Observability without evaluation is theater.** Collecting traces of every agent run is useful for debugging, but traces alone don't catch regressions. You need a scorer that runs against sampled traces and feeds results back to the CI gate.
- **The Safety SLI is useless without thresholds.** Defining "Safety SLI must stay above 99%" means nothing if no one owns the alert, the circuit breaker, or the rollback. The metric requires an operational response to be real.
- **Tracing production traffic adds latency and cost.** Async trace collection (batch uploads, sampling) keeps overhead manageable — don't instrument every turn if you're cost-constrained.
