# S-1180 · The Cost of Silence: When Your Agent Fails Without Telling You

Your agent runs for eleven days straight. Nobody notices until the bill arrives: $47,000 in API calls, zero useful output. The agent hit an error, retried, hit the same error, retried again — and kept retrying past any reasonable threshold. No alert. No circuit breaker. No human in the loop. Just silence and compounding cost. This is the dominant failure mode in production agentic systems, and most teams discover it the hard way.

## Forces

- LLM-based agents are non-deterministic: the same prompt + tools can produce different execution paths, including failure paths that deterministic testing never caught
- Retry logic designed for deterministic systems amplifies the problem in agentic stacks — three agents hitting a rate limit simultaneously compound it into a retry storm
- Token budgets, circuit breakers, and stop conditions are afterthoughts in most agentic frameworks, not primitives
- The most dangerous failure mode is silent: the agent produces output that looks plausible but is contextually wrong or incomplete
- Framework abstraction layers (LangChain, etc.) hide observability details that production debugging requires
- Without explicit per-task budgets, agents optimize for task completion rather than cost efficiency — and on long-horizon tasks, those diverge catastrophically

## The Move

Structure every agentic system around operational primitives that make failure visible, bounded, and recoverable. Not a framework — a set of contract patterns that survive framework changes.

**Envelope every subagent task with explicit bounds:**
- State the goal in one sentence and the acceptance criteria for "done"
- Set a hard budget: max tool calls, max tokens, max cost estimate
- Define stop conditions: what "failure" looks like before the agent decides for itself
- Never let a subagent run without these — vagueness is a cost multiplier

**Implement a circuit breaker at the tool/API layer:**
- Track failures per tool or provider with a three-state machine: closed (normal), open (blocked), half-open (probe)
- Three consecutive failures within 60 seconds → open, block all calls, wait 5 minutes, then probe once
- Success returns to closed; failure extends the cooldown
- This prevents retry storms from cascading across agents when a rate limit hits

**Design tools for an "alien collaborator" — not a developer:**
- Anthropic's framing: every tool name, parameter, and description must be unambiguous to a non-deterministic model
- Narrow tool scope: a tool that does one thing well beats a tool that does many things poorly
- Pre-filter inputs: don't dump raw database tables as tool arguments; summarize and structure data before passing it to the LLM
- Evaluate tools independently: prototype → evaluate → improve, not deploy-and-hope

**Add human escalation at cost and confidence boundaries:**
- Every task envelope should declare a cost threshold that triggers human approval
- Shannon's approach: per-task token budgets with automatic model fallback (Sonnet → Haiku) when budgets are hit
- For high-stakes actions (database writes, external API calls), require explicit HITL checkpoints

**Make observability a first-class output, not a log file:**
- Every agent action should emit a trace event with: task ID, model used, tokens consumed, tool called, result status
- Temporal-style time-travel debugging: replay any execution step-by-step from the event log
- Prometheus metrics + OpenTelemetry tracing for production-grade visibility
- Budget tracking visible in real time, not post-hoc on the invoice

## Evidence

- **Engineering blog post:** Anthropic's "Building Effective AI Agents" recommends starting with direct LLM API calls, using frameworks only when complexity demands it, and emphasizing tool design quality — "We need not only good implementations, but also good design, descriptions, and evaluations." — https://www.anthropic.com/engineering/building-effective-agents
- **GitHub repo / operational playbook:** p3nchan/orchestration-playbook documents the Task Envelope and Circuit Breaker patterns from months of running 5+ agents across multiple models. The Circuit Breaker pattern explicitly targets retry storms: three consecutive failures within 60 seconds triggers a block state, preventing cascading failures across agents — https://github.com/p3nchan/orchestration-playbook
- **Engineering blog / case study:** Coasty.ai documented a real $47,000 production incident: an agent stuck in an infinite retry loop for 11 days. Root cause: no per-task budget, no stop condition, no human escalation. The fix is structural, not procedural — https://coasty.ai/blog/ai-agent-error-handling-and-recovery-computer-use-disaster-stories
- **Open-source framework:** Shannon (2,089 stars, Go/Rust/Python) implements Temporal-style workflows with time-travel debugging, hard token budgets per task/agent with automatic model fallback, WASI sandboxing, and OpenTelemetry tracing — https://github.com/Kocoro-lab/Shannon
- **HN discussion:** Commenters on Anthropic's agent post confirmed the framework overhead problem: one team built a V0 with direct API calls, then spent months migrating to a framework that introduced abstraction layers incompatible with their observability setup — https://news.ycombinator.com/item?id=44301809

## Gotchas

- A retry button is not error handling — retrying a non-deterministic failure without a circuit breaker just burns budget and can worsen the failure (retry storm)
- Framework defaults are not production defaults — LangChain, CrewAI, and AutoGen all require explicit configuration of budgets, timeouts, and escalation before they are safe in production
- Plausible output is not correct output — agents that fail silently produce confident, coherent text that is contextually wrong; this requires output validation, not just runtime monitoring
- Context window management is a reliability feature, not a cost optimization — tools that dump raw data into prompts cause the agent to miss the relevant part; pre-filter before passing
- Multi-agent systems compound single-agent failure modes — each additional agent multiplies the retry storm surface area; circuit breakers must be at the system level, not per-agent
