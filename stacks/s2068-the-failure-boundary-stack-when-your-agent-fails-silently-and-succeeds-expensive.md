# S-2068 · The Failure Boundary Stack: When Your Agent Fails Silently and Succeeds Expensively

The moment you give an AI agent a long-running task — multi-step research, automated coding, autonomous browsing — you have implicitly accepted a new class of failure. Traditional software fails loudly: a stack trace, an error code, a crash. Agents fail in silence: they loop for 35 minutes, accumulate context until the model halts, spawn redundant subprocesses that contend for shared resources, and can take irreversible actions before any human notices. The worst part: they return HTTP 200 while doing it wrong.

## Forces

- **Silent vs. loud failure** — agents produce plausible-looking output while failing, unlike services that throw exceptions
- **Open-ended loops without stopping conditions** — a task with no natural terminus runs until context fills, budget exhausts, or someone kills it
- **Compounding unreliability** — a 10-step pipeline where each step is 85% reliable succeeds end-to-end only ~20% of the time (Zylos, 2026)
- **Irreversible actions** — by the time you detect failure, the agent may have already sent emails, executed trades, or modified production data
- **Exception is not failure** — the model can behave incorrectly without any exception being raised; the failure is semantic, not syntactic

## The Move

Build external guardrails that treat the agent as an untrusted process — not because the model is bad, but because the agent's reasoning chain is opaque and unbounded. The pattern has three layers:

- **Circuit breakers** — hard external stops enforced regardless of what the agent decides. Loop detection (same tool+args called N times), budget guards ($X max spend per run), iteration limits (N steps without task completion), and cost-velocity monitors (sharp spend increase per minute) all trigger halts.
- **Self-correction loops** — soft internal recovery where the agent reflects on failure and retries with modified intent. Reflexion (Shinn et al., NeurIPS 2023) is the canonical form: the agent receives a failure signal, verbalizes what went wrong into an episodic memory buffer, and uses that reflection to guide the next attempt — no weight updates, no fine-tuning. LangGraph and Microsoft's agent framework implement this as checkpoint/resume with a verifier agent.
- **Stateful rollback** — durable checkpointing so a failed step doesn't cascade into full restart. Temporal's workflow replay pattern (used in production by OpenAI, Scale AI, Replit) is the gold standard: each completed step is persisted; a failed activity retries from the last successful checkpoint, not from scratch.

## Evidence

- **Ask HN reliability audits:** Harper Labs conducted reliability audits across 50+ test cases and identified 7 consistent failure modes including "works in demos, invents data when input is slightly off" and "gets stuck in a loop endlessly retrying a failed step." A Gartner estimate cited in the thread projects over 40% of AI agent projects will fail by 2027. A January 2026 prompt injection in a customer support agent processed a $47,000 fraudulent refund before detection. — [Ask HN: How are you testing AI agents before shipping to production? | Hacker News](https://news.ycombinator.com/item?id=47325105)
- **Circuit breaker library:** agent-watchdog (MIT, PyPI) implements framework-agnostic circuit breakers for agent runs: `max_identical_calls` (halt if same tool+args called N times), `max_budget_usd`, `max_steps` without progress signal, and `context_window_threshold`. 27 commits since March 2026. — [GitHub: woodwater2026/agent-watchdog](https://github.com/woodwater2026/agent-watchdog)
- **Reflexion paper:** Shinn et al. (Princeton, NeurIPS 2023, 3,217 stars) showed that verbal self-reflection — storing failure explanations in episodic memory and using them as context for retry — outperforms standard retry without reflection. The agent doesn't update weights; it updates its memory of why it failed. — [GitHub: noahshinn/reflexion](https://github.com/noahshinn/reflexion) · [arXiv:2303.11366](https://arxiv.org/abs/2303.11366)
- **Exception as observation (Hive):** The Hive agent framework HN thread (107 points, 2026) introduced treating exceptions as observations fed back into the context window rather than as crashes. "In Hive, we catch that stack trace, serialize it, and feed it back into the Context Window as a new prompt: 'I tried to read the file and failed with this error — how should I adapt?'" — [Show HN: Agent framework that generates its own topology | Hacker News](https://hn.nuxt.dev/item/46979781)
- **Enterprise recovery gap:** Commvault (May 2026) found 83% of organizations have incomplete visibility into agent-to-agent interactions. The recovery problem for agentic systems is qualitatively different from traditional backup: agents are stateful, continuously operating, and make runtime decisions that can only be understood in context. — [The Hidden Recovery Problem in Agentic AI | Commvault](https://www.commvault.com/blogs/the-hidden-recovery-problem-in-agentic-ai)

## Gotchas

- **Retry without reflection just re-produces the same failure.** Naive retry loops (re-executing the same tool call N times) hit the same root cause. Effective retry requires the agent to have a reason to try differently — a reflection, a parameter change, or a tool swap.
- **Iteration limits without progress signals are blunt instruments.** An agent can hit N steps while making semantic progress (reading a long document, synthesizing many sources). Pair step-count limits with semantic staleness detection — has the output changed meaningfully in the last K steps?
- **Budget guards are dollar-denominated but cost is latent.** The cost of a run isn't known until the API bill arrives. Budget guards must estimate cost per call (input tokens × rate + output tokens × rate) and project forward, not just count completed steps.
- **Checkpointing without idempotency causes side-effect duplication.** If step 3 of your pipeline sends an email and the workflow restarts from step 2, a naive retry sends the email twice. Durable execution with idempotency guards is the correct solution; a progress file alone is insufficient for side-effecting steps.
