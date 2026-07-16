# S-1184 · The Agent Failure Recovery Stack — When Your Agent Loops Forever and Burns Your Budget

Your agent gets a malformed tool response. It retries. The retry fails too. It tries again with slightly different arguments — a third time, a fourth. Each retry sends the full conversation context back to the LLM, burning tokens on every iteration. Meanwhile 50 other tasks queue behind it, the downstream service is still struggling, and you've now spent $47 on a single task that should have cost $0.30. By the time you notice, the agent has been looping for 35 minutes. This is not a prompting problem. It is a structural failure of the error handling layer — and it is endemic to agentic systems in production.

## Forces

- **Agent retries amplify cost in ways microservice retries don't.** A traditional microservice retry resends an HTTP request (~a few KB). An agent retry resends the entire conversation context to the LLM. Ten retries on an 8K-token conversation = 80,000 input tokens. The retry storm problem is fundamentally worse in agentic systems because the retry lives inside a probabilistic reasoning engine that may make different (sometimes worse) decisions on each attempt.
- **Hard step caps alone are blunt instruments.** A hard cap of N steps stops a runaway agent, but it stops a productive one too — mid-work, with no state preserved, no error signal, and the user gets nothing. Teams that rely only on step caps end up with agents that either over-constrain themselves or blast through the cap and start billing.
- **Agents fail silently in ways traditional software doesn't.** A conventional web service crashes and logs a stack trace. An agent may: silently loop for 35 minutes accumulating context, spawn redundant subprocesses contending for shared resources, or take an irreversible action before a human can intervene. The failure modes are qualitatively different from traditional software — and so are the detection requirements.
- **The 10-step pipeline problem is brutal math.** A 10-step pipeline where each step has 85% reliability succeeds only ~20% of the time end-to-end (Galileo, 2025). If each failure is treated as a hard crash rather than a recoverable event, the system is unusable at scale.

## The Move

Build a layered failure recovery architecture that spans hard guardrails (circuit breakers, step caps), probabilistic self-correction (LLM-as-judge, Reflexion), and human escalation paths. The goal is to make every failure mode a *bounded, observable event* — not a silent budget drain or a runaway process.

### Layer 1 — Hard Guardrails (stop the bleeding first)

- **Hard step cap with named exception.** Set `MAX_STEPS = 12` and raise a typed `AgentExceededSteps` exception rather than returning whatever partial state the agent happened to reach. This makes the failure detectable and loggable. For LangGraph, use `recursion_limit=12`.
- **Token and cost budget per run.** Track cumulative input tokens and estimated cost in a run context object. Set a `MAX_COST_USD` budget and hard-stop before the agent can exceed it, even if steps remain. Instrument with `run.metric("cost_usd", ...)` and route loop alerts to on-call.
- **Circuit breaker per tool.** Track failure rates per tool independently. When failures exceed a threshold within a time window, open the circuit — fail fast for subsequent calls to that tool rather than waiting for timeouts. This prevents a single flaky downstream service from creating a thundering herd that makes the outage worse.

### Layer 2 — Probabilistic Self-Correction (let the agent try to fix itself)

- **LLM-as-judge at runtime.** Use a judge LLM (GPT-4o or Claude 3.7 Sonnet for high-stakes; distilled models like Galileo Luna-2 at 3B–8B for cost-sensitive paths) to evaluate intermediate steps. Score each action on promise (how close does this bring the agent to the goal?) and progress (how much improvement does this action make relative to the current state?). Flag a flawed intermediate step before it propagates through the rest of the reasoning chain.
- **Reflexion / self-reflection loop.** After a tool execution, have the agent explicitly evaluate: did the tool output match my intent? Did it change state as expected? If not, can I infer why and try an alternative? This is lightweight compared to full reranking and catches the most common class of failures — the tool worked but produced unexpected output.
- **Fallback paths instead of retries.** For non-idempotent failures (e.g., a write that partially succeeded), don't retry — route to a fallback path (human review, queue for manual completion, return partial output with clear error signal). Retry logic is for transient failures; semantic failures need structured fallback.

### Layer 3 — Stateful Recovery (preserve work across failures)

- **Checkpoint/resume via framework primitives.** LangGraph and Microsoft Agent Framework both provide native checkpoint/resume primitives. Rather than rerunning from scratch on failure, resume from the last confirmed-good state. The checkpoint should include: conversation history, tool call results, intermediate outputs, and the agent's current reasoning state.
- **Structured state snapshots.** On each completed step, write a structured snapshot (not just conversation append) that includes: step number, tool called, tool result, LLM reasoning summary, and a validity flag. On failure, the recovery routine can inspect the snapshot chain to identify the earliest bad step rather than re-executing blind.

### Layer 4 — Human Escalation (escalate rather than loop)

- **Confidence threshold routing.** For high-stakes operations (financial transactions, irreversible actions, customer communications), define a confidence threshold below which the agent surfaces the decision to a human reviewer instead of continuing. Queue uncertain decisions rather than making them autonomously.
- **Human-in-the-loop as a first-class state.** Build HITL as an explicit state in the agent's state machine, not as an error handler. The agent enters `await_haiting_approval` state, waits for an event, and resumes with feedback — exactly like a human workflow engine. Timeout the wait (e.g., 7 days) and escalate to a secondary reviewer if no response arrives.

## Evidence

- **Engineering blog — Zylos Research (May 2026):** Production AI agent systems fail in qualitatively different ways than traditional software: agents may silently loop for 35 minutes, spawn redundant subprocesses, accumulate context until the model halts, or take irreversible actions before intervention is possible. The research synthesizes failure taxonomies: ~42% specification failures, ~37% coordination breakdowns, ~21% verification gaps. Circuit breakers, supervisor trees, and idempotent retry are cited as core architectural patterns.
  — https://zylos.ai/zh/research/2026-05-06-agent-self-healing-failure-recovery/

- **Engineering blog — Tian Pan / Software Engineer (April 2026):** The retry storm problem: in agentic systems, retrying a failed tool call doesn't just retry the tool — it re-processes the full prompt, all prior messages, and tool call history. Ten retries on an 8K context = 80,000 input tokens. Production reports show that uncontrolled agent retry loops can turn a $0.01 task into a $2+ cost event in under a minute. Solution: idempotent retry with exponential backoff and per-step cost accounting.
  — https://tianpan.co/blog/2026-04-10-retry-storm-problem-agentic-systems

- **GitHub — AI System Design Guide (ombharatiya):** Error handling has evolved from try-catch blocks to agentic self-correction and stateful rollbacks. LangGraph and Microsoft Agent Framework provide native checkpoint/resume primitives. The taxonomy of failures includes hallucinated tools (model calls a non-existent function), tool call failures (timeout, rate limit), semantic failures (tool worked but output is wrong), and loop detection. Recommended pattern: self-correction loop → stateful rollback → graceful degradation → human escalation.
  — https://github.com/ombharatiya/ai-system-design-guide/blob/main/07-agentic-systems/07-error-handling-and-recovery.md

## Gotchas

- **Don't use retry logic for semantic failures.** A tool that returns HTTP 200 but semantically wrong data should not be retried — it will return the same wrong data. Detect semantic failure via LLM-as-judge or explicit output validation, then route to a fallback path or human review.
- **Step caps without instrumentation are a blunt instrument.** A step cap that raises an exception is useful only if something catches that exception and alerts you. Without observability on *which* step failed, *why*, and *what state the agent was in*, a step cap just converts a silent failure into a noisy one.
- **Circuit breakers must be per-tool, not global.** A global circuit breaker for the entire agent means a single failing tool takes down the whole system. Track failure rates independently per tool — one endpoint going down should only affect calls to that endpoint.
