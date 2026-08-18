# S-2842 · The Agent Runaway Loop Stack — When Your Agent Runs Until the Credit Card Maxes Out

You ship an agentic workflow. It works perfectly in tests. Three days later you get a $47,000 API bill — the agent entered a retry loop and ran for 11 days. Nobody noticed because nothing stopped it. This is not a model failure; it's a control-plane failure. Every safeguard you skipped in the name of simplicity is now a line item on your invoice.

## Forces

- **Agentic workflows consume 24x more tokens than conversational AI.** A chat session costs cents. An agentic coding task consumes 50K–500K tokens ($0.50–$5.00 per task). Retries multiply this by 2–5x. The economics are fundamentally different from chatbots.
- **Agents act in loops by design.** The perceive → reason → act → repeat cycle is what makes agents powerful. It is also what makes them dangerous — the same machinery that solves complex multi-step problems will happily grind against a wall forever if the task is ambiguous or the tool fails.
- **No alert, no kill switch.** Most teams don't have runtime spend limits, step caps, or anomaly detection on token usage. The first signal is the billing statement. By then the damage is done.
- **Standard safeguards don't transfer from traditional software.** HTTP timeouts, retry logic, and circuit breakers assume fail-fast semantics. Agent loops produce valid HTTP responses — the agent got an answer, it just wasn't useful, so it asked again.
- **The failure is silent.** Unlike a crashed service, a runaway loop doesn't page anyone. It returns what looks like progress (tool calls happening, tokens flowing) while making zero actual progress.

## The Move

Layer four guardrails — each stops a different failure mode. Apply them at the orchestration level, not inside the agent.

**1. Hard step and iteration caps.** Set `max_iterations` and `max_tool_calls_per_run` at the workflow level. LangChain v0.3: `max_iterations=10, early_stopping_method="force"` terminates cleanly instead of grinding to the iteration limit. This alone prevents 90% of runaway cost incidents.

**2. Token and dollar budgets per task.** Track cumulative spend per-run. AgentGuard (174 stars, 2025) and ai-agent-loop (NPM, zero deps) implement hard caps: when the budget hits zero, the agent stops and returns partial results — not an error, not a crash, but a clean stop. Some teams set per-tool budgets: code-execution tools get $2.00, search tools get $0.50, and so on.

**3. Loop detection — same tool, same args.** The tell-tale sign: identical tool calls with identical arguments, 100+ times in a row. ai-agent-loop detects this pattern and caches/block duplicates. Semantic similarity checks catch near-duplicate loops where arguments shift slightly. If the last N actions are identical to the previous N actions, halt — this is not exploration, it's spinning.

**4. State rollback and graceful degradation.** NassimRahimi/agent-failure-recovery (2026) demonstrates the pattern: detect unsafe output, quarantine the bad state, roll back to the last known-good checkpoint, validate the restored state. The agent doesn't crash — it steps back and resumes from a known position. Combine with a human-escalation path: when limits hit, surface the partial result to a human instead of failing opaque.

**5. Real-time spend visibility.** AgentGuard kills processes in real-time before budget exhaustion — not after the fact. Cycles runtime layer (runcycles) provides per-agent spend tracking, tenant-level consumption caps, and async workflow drift detection. Set alerts at 25%, 50%, and 75% of budget — not just at zero.

## Evidence

- **GitHub post-mortem repo:** `rohitsalesforce132/runaway-tool-loop` (2026) — categorizes runaway loops as the #1 production failure mode in agentic systems, framing it as a control-plane failure, not a model failure. Documents 6 distinct loop subtypes with case studies. — https://github.com/rohitsalesforce132/runaway-tool-loop

- **$47,000 incident post:** Kognita blog documents a real 2025 incident: multi-agent LangChain system ran for 11 days (undetected), cost $47,000 in API charges, discovered via billing statement. No spend limit, no runtime timeout, no alerting. Root cause: architecture enabled capability without any enforcement mechanism to stop. — https://www.kognita.co/blog/ai-agent-runaway-cost-no-kill-switch

- **$847 single-loop incident:** GitHub repo `belantosurodev-alt/ai-agent-loop` (NPM: `ai-agent-loop`) documents an agent spending $847 on a task that should have cost $0.03 — same tool, same arguments, 2,847 times. Zero-dependency library adds loop detection, token budgets, and step limits as a wrapper. — https://github.com/belantosurodev-alt/ai-agent-loop

- **HN Show: AgentGuard:** 47 points on HN (July 2025). Built after the author burned $200 on an agent loop. Real-time token spend tracking + auto-kill before budget exhaustion. 174 GitHub stars, 11 forks. — https://news.ycombinator.com/item?id=44742710

- **Cycles runtime docs:** `runcycles/cycles-docs` catalogs 6 distinct runaway incident types: runaway agent execution, recursive tool loops, retry storms, background workflow drift, tenant over-consumption, and unbounded side effects. Root cause framing: "the system keeps acting after it should have stopped — not because it's malicious, but because nothing enforces a bounded execution envelope." — https://github.com/runcycles/cycles-docs/blob/main/incidents/runaway-agents-tool-loops-and-budget-overruns-the-incidents-cycles-is-designed-to-prevent.md

- **LangChain fix guide:** `markaicode.com` (May 2026): `max_iterations=10` + `early_stopping_method='force'` reduces token costs by 92% on looping agents. Root cause identified as ambiguous tool descriptions and missing stop conditions — not model quality. — https://markaicode.com/errors/ai-agent-loop-fix

## Gotchas

- **Rate limits are not budget controls.** You can stay within per-second rate limits and still exceed your intended total spend over a long-running task. Set total cost caps, not just velocity limits.
- **The "partial progress" trap.** When a budget cap hits, the agent may return mid-work state that looks like success. Define what partial completion means for your task and communicate it to callers — don't let them mistake a stopped-at-limit result for a complete one.
- **Agents don't know when to stop.** LLMs optimize for task completion, not cost efficiency. A model will happily keep trying a failing tool indefinitely if the stop condition isn't explicit. The bounds must come from the runtime, not the agent's judgment.
- **Test the guardrails under failure conditions.** Verify that your step cap, token budget, and loop detection actually fire on a production-length run with injected failures. Most teams only test the happy path.
