# S-2409 · The Trace Replay Stack — When Your Agent Failed and You Cannot Reconstruct What Happened

Your agent approved a $14,000 refund last Tuesday. The logs show it received the right inputs, called the right tools, and returned HTTP 200. You have no idea why. You cannot replay the run. You cannot step through it. You cannot attach a debugger. All you have is a final output and an invoice. This is the debugging crisis in production agentics: agents fail silently, leave no stack trace, and every failed run becomes a mystery.

## Forces

- **Agent failures compound across steps** — the visible symptom (wrong output) is often three steps removed from the root cause (a bad parameter passed in step 1). Standard monitoring sees the endpoint, not the causal chain.
- **The session is the unit of failure** — a single bad LLM call can corrupt memory, tool state, and downstream reasoning. Debugging the final output in isolation is like diagnosing food poisoning by tasting the dessert.
- **Agents are nondeterministic** — the same input can produce different trajectories on different runs. You cannot reproduce the failure by re-running the request.
- **88% of agent failures trace to infrastructure gaps** (missing guardrails, absent monitoring, inadequate trace instrumentation) — not model quality. You fix the wrong thing if you start with the model.
- **Debugging multi-agent issues takes 3–5× longer** than single-agent problems because failure chains span process boundaries.

## The move

Trace-driven debugging treats every agent execution as a queryable causal graph — not a log file.

### The four debugging primitives

1. **Full session trace reconstruction** — capture every LLM call, tool invocation, retry, and intermediate plan with timestamps, token counts, and input/output for each step. Session-level tracing is the minimum viable artifact. Without it, the failure is unrecoverable.
2. **Deterministic replay** — substitute recorded outputs for nondeterministic operations (LLM calls, external APIs) during replay. The agent calls deterministic stubs that return the recorded response. This reconstructs the exact failure trajectory.
3. **Issue clustering** — aggregate failures by failure class (hallucinated tool calls, wrong parameter types, silent data corruption) rather than by symptom. Clustered failures point to systemic fixes; isolated failures point to edge-case handling.
4. **Production-to-eval pipeline** — every confirmed failure in production automatically becomes a test case in the eval harness. The regression test is the fix. No manual test writing.

### The silent failure detection layer

Standard monitoring watches for HTTP errors. Agents return HTTP 200 with wrong answers. Detection must read content, not status. Four classes account for most silent failures:

- **Hallucinated tool calls** — agent selects a non-existent or irrelevant tool, gets a null/garbage response, and builds on it
- **Tools that succeed with wrong data** — API returns 200 with incorrect values; no error fires
- **Quality decay after model changes** — a provider-side model change shifts behavior without a commit
- **Retries that resolve onto a weaker path** — exponential backoff falls back to degraded infrastructure and silently continues

Detection requires: semantic output validation (content-aware, not status-aware), downstream feedback loops (user corrections, escalation events), and behavioral proxies (tool-call count spikes, context utilization changes, retry rate).

### The OpenTelemetry foundation

Instrument with OTel from day one — not retrofitted later. Required spans: parent agent span, child LLM spans, child tool spans. Capture parent-child relationships across agent boundaries. Implement tail-based sampling to capture all spans for failed runs while sampling successful ones cheaply. This is orders of magnitude cheaper than retrofitting observability into a production agent system.

### Replay workflow

**Record mode:** During production execution, capture all agent interactions into a structured execution log (the trace).

**Replay mode:** Instead of calling the live LLM or live tools, the agent calls deterministic stubs that query the replay engine for the next recorded event. Engineers can step through the exact failure trajectory, inspect state at each step, and identify the root cause without guessing.

## Evidence

- **Zylos Research (2026):** 88% of agent failures trace to infrastructure gaps — not model quality. Teams running multi-agent systems spend 40% of sprint time investigating failures rather than building features. Debugging multi-agent issues takes 3–5× longer than single-agent problems. — [zylos.ai/research/2026-04-30-trace-driven-debugging-ai-agent-failures](https://zylos.ai/research/2026-04-30-trace-driven-debugging-ai-agent-failures)
- **Anthropic postmortem (Aug 2025):** A routing misconfiguration sent Claude Sonnet 4 requests to servers provisioned for a different context window. The bug ran for weeks undetected because latency, error rate, and throughput were all fine. "We relied too heavily on noisy evaluations." The fix required trace-level content inspection, not status monitoring. — [anthropic.com/engineering/a-postmortem-of-three-recent-issues](https://www.anthropic.com/engineering/a-postmortem-of-three-recent-issues)
- **GitHub / opswald/agent-debugging-playbook:** A practitioner-authored playbook codifies the debugging workflow: full session trace reconstruction → deterministic replay → decision graph building → production-to-eval pipeline. Includes concrete checklists for replay readiness and production incident response. — [github.com/opswald/agent-debugging-playbook](https://github.com/opswald/agent-debugging-playbook)
- **HN Ask "How are you monitoring AI agents in production?":** Practitioners universally report: no step-by-step visibility, surprise LLM bills from untracked token usage, risky outputs going undetected, no audit trail for post-mortems. — [news.ycombinator.com/item?id=47301395](https://news.ycombinator.com/item?id=47301395)
- **Latitude / Complete Guide to Debugging AI Agents in Production:** "Evaluating the final output in isolation shows a well-structured, confident response. LLM-as-judge scores it highly on coherence and relevance. The corruption lives in the context, not the completion." — [latitude.so/blog/complete-guide-debugging-ai-agents-production](https://latitude.so/blog/complete-guide-debugging-ai-agents-production)
- **Tessary / Silent LLM Agent Failures:** "A span carries one error channel. A tool returning wrong data with status OK never touches it." Documents the four-class silent failure taxonomy with detection strategies. — [tessary.ai/blog/silent-llm-agent-failures](https://tessary.ai/blog/silent-llm-agent-failures)

## Gotchas

- **OTel without tail-based sampling loses the failures.** If you only sample successful runs, the failed ones — which are rare and expensive to debug — never get instrumented. Configure tail-based sampling that captures 100% of failed run traces.
- **Session replay requires deterministic stubs for all external calls.** If you replay but still hit the live LLM, you get different outputs and cannot reproduce the failure. Every external call must have a recorded-response stub during replay.
- **Context corruption is invisible without per-step state capture.** The failure is usually visible in the final output, but the corruption entered the context three steps earlier. You need to inspect context state at every step, not just the final result.
- **LLM-as-judge can score a corrupted output as high-quality.** If the corruption happened gradually (a series of slightly wrong intermediate values the agent built on), the final output can still read as coherent. Judge quality independently at each step.
