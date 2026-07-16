# S-1176 · The Token Budget Governance Stack — When Your Agent Looks Healthy on the Dashboard and Bills $47,000

Your monitoring dashboard is green. Agent activity scrolls in the logs. The on-call rotation is quiet. Then the monthly invoice lands: $47,000 for eleven days of undetected runaway loop in a four-agent LangChain pipeline. No alert fired. No threshold tripped. The agents looked busy because they were busy — calling tools, sending messages, retrying, spinning. This is not an exotic failure mode. It is what agentic AI looks like when financial limits are treated as an afterthought.

## Forces

- **Agentic workflows are expensive by design, not by accident.** A chat session uses 2,000–5,000 tokens. A single agentic task — plan → execute → verify → retry — consumes 50,000–500,000 tokens. Multiply by steps-per-task and agents-per-fleet and the math is categorically different from conversational AI.
- **The capability architecture and the safety architecture are separate.** The tools that make agents powerful (tool calling, autonomous retry, multi-agent messaging) are the same tools that make runaway possible. Frameworks build the capability layer. Nobody builds the kill switch until after the first incident.
- **Green dashboards are insufficient.** Token spend compounds in non-obvious ways. A "healthy" log stream with 264 hours of agent activity looks identical to normal activity on a dashboard that doesn't track cost per conversation.
- **Per-request limits don't generalize.** Setting a per-request token cap is table stakes. The runaway case is a single long-running conversation that stays under the per-request limit while accumulating thousands of requests.

## The Move

Build a financial circuit breaker layer as a first-class part of your agent runtime — not a monitoring afterthought, not a dashboard alert, but a hard enforcement mechanism that operates independently of the agent's reasoning.

**Three hard limits, enforced mechanically (not in-prompt):**

- `MAX_STEPS_PER_RUN` — absolute action cap per conversation thread (typically 50–100). Prevents infinite planning loops.
- `MAX_COST_PER_RUN_USD` — cost ceiling per single run (typically $1–$10 depending on agent tier). Hard stop, not a warning.
- `MAX_COST_PER_USER_PER_DAY` — daily aggregate per principal (typically $5–$50). Prevents coordinated or repeated runaway across sessions.
- `MAX_WALL_TIME_SECONDS` — time-based kill switch (typically 300–600s). Agents can deadlock on unresponsive tools; wall time catches this where step count can't.

**Loop detection via semantic deduplication:**

The core failure pattern: an analyzer agent and a verifier agent ping-pong on the same decision. Track a hash of `(tool_name, arguments)` per step. If the same call appears more than 2–3 times in a row with no intervening state change, terminate. The DEV Community postmortem frames it as `assert input_hash(name, args) not in seen`.

**Architecture:**

```
Agent Runtime
  ├── Step Counter  ──────────→  MAX_STEPS_PER_RUN  → hard stop
  ├── Cost Accumulator ───────→  MAX_COST_PER_RUN_USD → hard stop
  ├── Wall Clock Timer ───────→  MAX_WALL_TIME_SECONDS → hard stop
  └── Loop Detector
        (hash of tool+args)
              │
              └── Same call 3x → terminate + log
```

**Instrument everything at the call site, not the framework layer.** Interpose cost tracking at every LLM API call (OpenAI, Anthropic, Google). Calculate `input_tokens × input_price + output_tokens × output_price` per call and accumulate in a per-conversation counter. This is more reliable than framework-level tracking because it catches direct API calls.

**Prompt caching as a cost lever, not just a performance one.** Anthropic's cache-aware API and OpenAI's completions API can reduce input costs by 60–85% for repeated patterns (the agent asks "verify these orders" repeatedly, but only the order IDs change). Configure cache prefixing at the tool level, not just the system-prompt level.

**Budget tiers by agent class.** Not all agents are equal. A code-execution agent doing complex reasoning warrants a higher cost cap than a routing agent. Assign cost budgets per agent class at the orchestrator level, not globally.

## Evidence

- **DEV Community postmortem:** A four-agent LangChain pipeline entered a ping-pong loop between analyzer and verifier agents, ran for 11 days (264 hours), cost $47,000. The dashboard showed green throughout. Three lines would have prevented it: `assert step <= MAX_STEPS`, `assert spent <= BUDGET_USD`, `assert input_hash not in seen`. — [DEV Community](https://dev.to/gabrielanhaia/the-agent-that-spent-47k-on-itself-an-autonomous-loop-postmortem-3313)
- **Kognita incident analysis:** Same $47,000 LangChain incident (November 2025), with cost progression: Week 1 $127 → Week 2 $891 → Week 3 $6,240 → Week 4 $18,400. Root cause: no per-agent budget caps, no timeout mechanism, no alert wired to billing. Notes that "this is not an exotic edge case — it is what agentic AI looks like without a managed runtime." — [Kognita](https://www.kognita.co/blog/ai-agent-runaway-cost-no-kill-switch)
- **Google BATS framework:** Google research (with NYU and UC Santa Barbara) published Budget-Aware Test-time Scaling (BATS) framework and Budget Tracker tool — injects real-time token and cost awareness into agent reasoning loops, enabling agents to condition actions on remaining budget. — [CIO](https://www.cio.com/article/4106863/google-unveils-budget-tracker-and-bats-framework-to-rein-in-ai-agent-costs.html) / [arXiv:2511.17006](https://arxiv.org/pdf/2511.17006)
- **Monte Carlo validation:** GitHub research repo demonstrating circuit breaker patterns for multi-agent LLM systems. ADAPTIVE_CB pattern achieves ~85% cascading failure reduction at chain length 5, compared to ~7% for simple two-state circuit breakers. — [hamley241/circuit-breaker-agents](https://github.com/hamley241/circuit-breaker-agents)
- **Industry context:** Model API spend grew from $3.5B to $8.4B between late 2024 and mid-2025. Average enterprise AI operational cost: $85,521/month. 60–85% of spend is recoverable through caching, routing, and budget enforcement. — [Zylos Research, 2026-05-02](https://zylos.ai/research/2026-05-02-ai-agent-cost-engineering-token-economics/)
- **ICONIQ Capital 2026 State of AI:** Inference costs run at 23% of revenue for scaling AI-native companies. IDC FutureScape 2026: organizations with dedicated FinOps teams still underestimate AI infrastructure costs by up to 30%. — [Ranjan Kumar](https://ranjankumar.in/ai-control-plane-cost-governance-budget-allocation-agent-types)

## Gotchas

- **Prompt-level safeguards are bypassable.** Telling an agent "stop after 10 steps" in the system prompt doesn't stop an agent that ignores or reinterprets that instruction. Hard limits enforced in code are the only reliable mechanism.
- **Per-request caps don't catch cumulative runaway.** The $47,000 incident occurred within per-request limits. The danger is a single conversation making thousands of valid requests, not one request exceeding a threshold.
- **A green dashboard means nothing without a cost dimension.** Verbose logging and active agent threads look identical to runaway activity unless cost is being tracked per conversation in real time. Wire spend into the dashboard, not just into billing reports.
- **Cache hits are invisible if you're not logging them.** Prompt caching reduces costs dramatically, but if you're not tracking cache hit rate per call, you don't know how much you're leaving on the table. At $5/M output tokens for Claude Opus 4.6, a 70% cache hit rate on repeated tool-call patterns is significant.
- **Multi-agent cascades amplify cost.** A timeout in one agent triggers retry in another; retry exhausts rate limits; rate-limit errors propagate to a third. Cascading failures are faster and more expensive than single-agent loops. Circuit breakers at agent boundaries (halting a downstream agent when an upstream dependency fails) are as important as cost circuit breakers.
