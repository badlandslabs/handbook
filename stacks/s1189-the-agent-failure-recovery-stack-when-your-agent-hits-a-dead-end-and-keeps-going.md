# S-1189 · The Agent Failure Recovery Stack — When Your Agent Hits a Dead End and Keeps Going

You have an agent that works in demos. In production, it loops on a broken tool, burns $200 in tokens, or crashes at step 9 of 12 with no way to resume. You need a failure recovery architecture.

## Forces

- Agents fail non-deterministically — the same prompt that worked once crashes the next time due to model drift, token limits, or hallucinated tool arguments
- A single unhandled error cascades into complete workflow failure, blocking downstream tasks
- Context pollution: failed attempts leave artifacts (broken state, misleading reasoning traces) that degrade every subsequent attempt
- Most teams build agents without recovery in mind, then retrofit it at 2am when the on-call phone rings
- Hard step caps alone aren't enough — you also need loop detection (same tool, same args) and budget guards

## The Move

Build layered failure recovery. Each layer handles a different failure mode. Stack them from cheapest to most expensive.

**Layer 1 — Hard step cap + loop detection:**
- Set `MAX_STEPS` (e.g., 12 for LangGraph) and halt if exceeded. Document state at halt for post-mortem.
- Implement sliding-window loop detection: track `(tool_name, tool_args)` tuples; trigger halt if the same call repeats N times within a window. Zero-dependency options: `tool-loop-guard` (PyPI, MIT), `agent-watchdog` (supports LangChain, CrewAI, AutoGPT).
- Budget guard: enforce per-run cost ceiling. `agent47` (bmdhodl/agent47, MIT) provides runtime cost guardrails — stops execution when budget is hit, not after.

**Layer 2 — Error classification before retry:**
- Not all errors deserve retry. Classify at the point of failure:
  - **Retry transient:** HTTP 429 (rate limit), 5xx server errors, network timeouts, DNS failures
  - **Skip permanent:** HTTP 401/403 (auth), 404 (resource gone), schema validation failures, malformed JSON
  - Retrying a 401 wastes tokens; skipping a 429 loses a valid request
- Implement as a router over ordered providers with per-provider circuit breakers. On `QUOTA_EXHAUSTED`, deprioritize the provider for the billing period — don't keep retrying a depleted account.

**Layer 3 — Exponential backoff with jitter for retries:**
- Never retry immediately. Use exponential backoff: `delay = base * 2^attempt + random_jitter`.
- Without jitter, 100 agents recovering simultaneously from a 503 will re-flood the same endpoint at the same time.

**Layer 4 — State checkpointing at workflow boundaries:**
- Save checkpoint after each major step (e.g., after each node in LangGraph). On crash, resume from the last checkpoint instead of re-executing from step 1.
- Critical for long-running tasks: GetATeam's email gateway agent crashed mid-flow, blocking all queued messages. Checkpointing would have allowed partial recovery instead of full queue loss.
- The checkpoint should capture: agent state, tool results so far, and a cursor indicating next step.

**Layer 5 — Context pollution mitigation (fresh-environment recovery):**
- Research from Letta's Recovery-Bench (NeurIPS 2025, arXiv) finds that continuing from a failed state is often worse than restarting clean. The failed state's reasoning traces, erroneous actions, and corrupted environment state pollute the agent's context.
- Recovery-Bench methodology: a weak agent attempts a task and fails; the failed trajectory is replayed in a fresh environment to measure recovery quality.
- Key finding: the best-performing models in fresh states are NOT the best at recovery. GPT-5 showed significant ranking improvement under recovery conditions compared to fresh-state rankings.
- Practical approach: after N failed attempts, save the failed state to a log, then re-spawn the agent with a clean context and inject a summary of what was attempted. Don't carry the pollution forward.

**Layer 6 — Graceful degradation chain:**
- If primary tool fails, try fallback. Example chain: `OpenAI → Anthropic → Azure OpenAI → cached response → general error message`.
- The final fallback should always return something usable (even if generic) so the workflow doesn't hard-crash.

**Layer 7 — Human escalation:**
- For tasks the agent cannot recover from: surface the failure, the agent's state at halt, and the last N tool results to a human.
- Design the escalation as a structured summary, not a raw log dump. Include: what was attempted, what failed, current state, recommended next action.
- TensorPool Agent (Show HN, Jan 2026) — autonomous GPU training job recovery — surfaced a key tension in HN discussion: agents babysitting long-running jobs must have smarter progress checks to avoid silently nursing zombie jobs. Progress verification before escalation prevents both false positives and silent failures.

## Evidence

- **Blog post:** "LLM Agent Error Recovery in 2026 — Patterns That Don't Loop Forever" — Manvendra Rajpoot, May 2026, covers hard step caps, tool-level retries, fallback paths, cost circuit breakers, and state checkpointing — [https://blog.rajpoot.dev/posts/ai/llm-agent-error-recovery-2026](https://blog.rajpoot.dev/posts/ai/llm-agent-error-recovery-2026)

- **NeurIPS paper:** "Recovery-Bench: Evaluating Agentic Recovery from Mistakes" — Shangyin Tan, Kevin Lin, Koushik Sen, Matei Zaharia (UC Berkeley/ICL), presents benchmark showing context pollution degrades recovery and that fresh-environment replay outperforms continued-from-failure — [https://openreview.net/forum?id=8FZRnDgDxq](https://openreview.net/forum?id=8FZRnDgDxq) | [https://github.com/letta-ai/recovery-bench](https://github.com/letta-ai/recovery-bench)

- **Show HN:** "TensorPool Agent: Autonomous recovery for distributed training jobs" — autonomous GPU job recovery with progress checks; HN discussion surfaced silent stall risk requiring smarter verification — [https://news.ycombinator.com/item?id=46812909](https://news.ycombinator.com/item?id=46812909)

- **DEV.to:** "Three Error Recovery Patterns for LLM Agent Tool Failures" — provider-level circuit breakers with per-error-type routing, exponential backoff, quota-exhausted deprioritization — [https://dev.to/mukundakatta/three-error-recovery-patterns-for-llm-agent-tool-failures-3dkl](https://dev.to/mukundakatta/three-error-recovery-patterns-for-llm-agent-tool-failures-3dkl)

- **GitHub:** `woodwater2026/agent-watchdog` — circuit breaker for agent runs: loop detection, budget guards, graceful halts, framework-agnostic — [https://github.com/woodwater2026/agent-watchdog](https://github.com/woodwater2026/agent-watchdog)

- **GitHub:** `bmdhodl/agent47` — runtime cost guardrails with budget enforcement, loop detection, and kill switch; MCP server for spending tracking — [https://github.com/bmdhodl/agent47](https://github.com/bmdhodl/agent47)

- **GitHub:** `MukundaKatta/tool-loop-guard` — zero-dependency sliding-window loop detector for repeated tool calls — [https://github.com/MukundaKatta/tool-loop-guard](https://github.com/MukundaKatta/tool-loop-guard)

- **Engineering post:** "Why 90% of AI Agents Fail in Production" — GetATeam, Nov 2025; case study of cascading failure from single API timeout; checkpointing at workflow boundaries identified as key mitigation — [https://blog.geta.team/why-90-of-ai-agents-fail-in-production-and-how-we-solved-it](https://blog.geta.team/why-90-of-ai-agents-fail-in-production-and-how-we-solved-it)

## Gotchas

- **Hard step caps alone don't catch loops** — an agent can call different tools each step while still looping (e.g., trying variations of the same wrong approach). You need both step caps AND loop detection on repeated `(tool, args)` pairs.
- **Retrying permanent errors wastes budget** — a 401 will not resolve by retrying. Classify errors before deciding to retry. A circuit breaker that retries all errors equally is broken by design.
- **Checkpointing side effects is hard** — if your agent writes to an external system (sends an email, writes a DB record) and crashes after that step, resuming from checkpoint re-triggers the side effect. Design checkpoints to capture idempotency: either make steps idempotent, or record which side effects have been committed.
- **Continuing from a polluted context often makes things worse** — Letta's Recovery-Bench demonstrates empirically that fresh-environment recovery outperforms continued-from-failure. If you've tried 3 recovery attempts, save the log and re-spawn clean rather than continuing to pollute the context.
- **Silent stalls are worse than loud failures** — the TensorPool HN discussion highlighted that autonomous agents babysitting long-running jobs need progress verification, not just error detection. An agent that reports "working" while the job has deadlocked is a silent stall. Build heartbeat/ping checks.
