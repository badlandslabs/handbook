# S-1844 · The Agent Recovery Stack — When Your Agent Crashes on Step 47 and Starts Over From Scratch

Your agent is processing 200 GitHub issues. It crashes on item 47. The next run starts at item 1 — hours of work are gone, and you have no way to know what was already done. This is the checkpoint absence problem: agents are stateful in concept but stateless in practice, and production noise — timeouts, OOMs, dropped connections, model outages — eats the work.

The teams that run agents reliably don't trust the agent to be resilient. They build resilience around the agent.

## Forces

- **A 10-step pipeline where each step has 85% reliability succeeds end-to-end only ~20% of the time.** Failures compound multiplicatively across agent steps. — *[Zylos Research, May 2026](https://zylos.ai/en/research/2026-05-06-agent-self-healing-failure-recovery/)*
- **Agents fail differently than software.** A conventional service crashes and logs a stack trace. An agent may silently loop for 35 minutes, accumulate context until the model halts, or take an irreversible action before a human can intervene. — *[Zylos Research](https://zylos.ai/en/research/2026-05-06-agent-self-healing-failure-recovery/)*
- **Checkpointing and recovery are semantic-blind in most frameworks.** LangGraph checkpoints graph state, but a read and an email send get the same treatment — the semantic meaning of what was accomplished is lost. — *[effect-log Show HN, GitHub](https://github.com/xudong963/effect-log/blob/master/blog/show-hn.md)*
- **Agents don't just crash — they fail subtly.** An LLM might hallucinate a tool call, return malformed JSON, or get stuck in a loop while reporting 200 OK. — *[AgentReviews, May 2026](https://agentreviews.dev/blog/ai-agent-failure-recovery-methods)*

## The Move

Three layered patterns form a recovery stack that handles crash recovery, runtime bounds, and tool-level failure isolation:

### 1. Hard Execution Bounds

The single most important guardrail. Set it before anything else.

- **Step cap:** `MAX_STEPS = 12` for general agents, `recursion_limit=12` in LangGraph. If the agent doesn't finish in 12 steps, stop, document the state, and escalate. — *[blog.rajpoot.dev, May 2026](https://blog.rajpoot.dev/posts/ai/llm-agent-error-recovery-2026)*
- **Cost cap:** Hard budget per run (e.g., `$1.00`). Track spend in real time. The `agent-watchdog` library provides `max_budget_usd` guards that halt runs before the bill arrives. — *[GitHub: woodwater2026/agent-watchdog](https://github.com/woodwater2026/agent-watchdog)*
- **Time cap:** Per-step timeout (30–60s for most tool calls) plus total run timeout. Long-running agents that never crash but never finish are equally dangerous.

### 2. Checkpoint and Resume

State persists across crashes so work is never lost.

- **Turn-level checkpointing:** Write one row per turn to a durable store (JSONL, SQLite). On crash, resume from the last completed turn — not from the beginning. `agent-resume` (zero-dependency, stdlib-only) implements this pattern: crash on item 47, resume from item 48. — *[GitHub: MukundaKatta/agent-resume](https://github.com/MukundaKatta/agent-resume)*
- **Semantic checkpoints:** Capture what was accomplished, not just graph state. Distinguish "this turn produced a report" from "this turn sent an email" — the recovery path differs. — *[effect-log Show HN](https://github.com/xudong963/effect-log/blob/master/blog/show-hn.md)*
- **Whole-run durable execution:** Anthropic's Dynamic Workflows introduced durable resumable runs natively. The Microsoft Agent Framework ships with first-class checkpoint APIs that save executor states and support rehydration. — *[Microsoft Docs](https://learn.microsoft.com/en-us/agent-framework/workflows/checkpoints)*
- **`LivingAI`** (2026) provides crash recovery, checkpointing, and replay across LangGraph, CrewAI, and OpenAI Agents in a single runtime. — *[GitHub: likkisamarthreddy/livingai](https://github.com/likkisamarthreddy/livingai)*

### 3. Tool-Level Circuit Breakers

Agents waste tokens calling broken tools indefinitely. Wrap each tool with a circuit breaker.

- **Three states:** Closed (normal) → Open (failing fast, skip this tool) → Half-Open (probe before re-enabling). — *[agentic-patterns.com, Jeel Thummar](https://www.agentic-patterns.com/patterns/agent-circuit-breaker)*
- **Failure threshold:** Open the circuit after 3–5 consecutive failures per tool. The `purgatory` Python library provides this pattern alongside `tenacity` for retry logic and `wrapt` for proxy-based wrapping. — *[Octopus Blog, Oct 2025](https://octopus.com/blog/mcp-timeout-retry)*
- **Fallback chain:** When tool A fails, route to tool B. A news API is down → fall back to web search. Web search is rate-limited → fall back to cached results. — *[Harness Engineering Academy](https://harnessengineering.academy/blog/building-resilient-ai-agents-implementing-retry-logic-fallback-patterns-and-graceful-degradation-for-unreliable-tools/)*

### 4. State Machine Guardrails

Constrain agent behavior formally — smaller model, smaller problem.

- Statewright (Show HN, 126 points, azurewraith / ex-NVIDIA Distinguished Engineer) uses formal state machines to define allowed tools and valid transitions per state: planning state uses read-only tools, implementation state uses scoped edit tools, testing state runs bash only. The model cannot skip steps or use the wrong tools. — *[Hacker News: Show HN](https://news.ycombinator.com/item?id=48108778)*
- Each state has iteration limits and explicit exit conditions. Transitions are deterministic, making failure modes predictable and bounded.

## Evidence

- **Blog post:** *LLM Agent Error Recovery in 2026* — Practical working playbook with `MAX_STEPS=12`, per-tool retries, cost caps, and escalation hooks. — [blog.rajpoot.dev](https://blog.rajpoot.dev/posts/ai/llm-agent-error-recovery-2026)
- **GitHub:** *agent-watchdog* — Framework-agnostic safety layer with loop detection, real-time budget guards, and graceful halts for LangChain, CrewAI, and AutoGPT. — [github.com/woodwater2026/agent-watchdog](https://github.com/woodwater2026/agent-watchdog)
- **Research synthesis:** *AI Agent Self-Healing and Failure Recovery* — Detailed taxonomy of six failure categories, circuit breaker patterns, supervisor trees, and graceful degradation strategies drawn from 2025–2026 post-mortems. — [zylos.ai](https://zylos.ai/en/research/2026-05-06-agent-self-healing-failure-recovery/)

## Gotchas

- **LangChain's `with_retries` doesn't work on `StructuredTool` instances.** The documented limitation is that retry logic cannot be applied via the standard `Runnable` interface to tools returned by `get_tools()`. Use the proxy pattern (`wrapt`) or tenacity decorators instead. — *[Octopus Blog](https://octopus.com/blog/mcp-timeout-retry)*
- **Framework loop detection fails silently.** LangGraph's recursion limit prevents infinite loops at the graph level, but the agent can still call the same broken tool repeatedly within a single allowed step. You need application-level loop detection (same tool + same arguments within N steps). — *[agent-watchdog README](https://github.com/woodwater2026/agent-watchdog)*
- **Descriptive tool errors are non-negotiable.** If a tool returns `null` or an empty dict on failure instead of an explicit error, the agent assumes success and propagates the failure downstream. Every tool must return structured error responses. — *[suhasbhairav.com](https://suhasbhairav.com/blog/why-ai-agents-need-retry-and-fallback-instructions)*
- **Retry is not the same as recovery.** Retrying a failed tool call is necessary but not sufficient — you also need idempotency guards so that a retried operation doesn't create duplicate side effects (double-sent emails, duplicate database writes). — *[Harness Engineering Academy](https://harnessengineering.academy/blog/building-resilient-ai-agents-implementing-retry-logic-fallback-patterns-and-graceful-degradation-for-unreliable-tools/)*
