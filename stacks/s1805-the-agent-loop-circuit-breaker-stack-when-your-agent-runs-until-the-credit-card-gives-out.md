# S-1805 · The Agent Loop Circuit Breaker Stack — When Your Agent Runs Until the Credit Card Gives Out

Your agent is supposed to classify support tickets and hand off exceptions to a human. It encounters an ambiguous ticket, fails to classify it, calls the classification tool again, gets a slightly different answer, fails again, retries, and loops. Nobody told it when to stop. The billing alert arrives the next morning: $3,200. It never handed anything to a human — it was too busy failing.

This is not a prompt problem. It is a **structural failure mode** unique to agents: Infinite Agentic Loops (IALs). Unlike a crashing program, the agent never errors out. It keeps working, confidently and expensively.

## Forces

- **Agents are stochastic — a loop condition that fails once may pass the next time.** LLM outputs shift with minor context changes, so the same conditional check that should break a loop instead passes repeatedly.
- **Iteration compounds cost without bounds.** Each retry re-reads the full context window. Iteration 10 doesn't cost 10× iteration 1 — it costs thousands more tokens because it re-ingests every prior failed attempt.
- **Traditional exception handling doesn't cover agentic failures.** A hallucinated tool call returns HTTP 200. A semantically wrong response is syntactically valid. A retry that looks successful but makes no real progress is invisible to a try-catch block.
- **The termination condition must be explicit and enforced externally.** The agent cannot reliably decide when to stop — it has no intrinsic sense of diminishing returns or context saturation.
- **Tool call ambiguity creates self-reinforcing loops.** When a tool output is ambiguous, the agent re-calls the same tool expecting a clearer answer. It gets the same ambiguity. This can repeat indefinitely.

## The Move

**Five interlocking safeguards that cover the real failure surface:**

- **Hard step-count and cost-circuit breakers.** Define a maximum number of agentic loop iterations and a cost ceiling per task *before the loop starts*. When either threshold is hit, the loop terminates and routes to a human or dead-letter queue. This is not a timeout — it is a budget.
- **Spec-before-loop: define "done" before the first call.** Write the termination condition as a first-class artifact, not an afterthought. The agent must receive a clear specification of what constitutes completion, not just what task to perform.
- **Consecutive-action deduplication.** Track the last N tool calls or reasoning steps. If the agent calls the same tool with the same arguments more than N times in a row, interrupt and escalate. This catches the most common loop pattern before it escalates.
- **Semantic progress detection, not just structural bounds.** Track whether the agent's state is actually changing (e.g., file modified, external system updated, new information retrieved). A loop that produces new outputs but no new *meaning* is still a failure. Some teams compare a state hash or output diff every N steps.
- **Audit ledger with append-only history.** Log every loop iteration — tool calls, responses, tokens consumed, cost accrued — to an immutable ledger. This serves double duty: it provides the circuit breaker with real-time data and creates a post-mortem trail when a loop does escape.

## Evidence

- **arXiv empirical study (July 2026):** *When Agents Do Not Stop: Uncovering Infinite Agentic Loops in LLM Agents* scanned 6,549 real-world LLM agent repositories with IAL-Scan, a static analysis tool. Found 68 confirmed IAL failures across 47 projects at 91.9% precision. Defines IAL taxonomy: repetition loops (same action repeated), ineffective retry loops (retry produces no new state), oscillation loops (A→B→A→B), and non-termination loops (no exit condition ever fires). — [arXiv:2607.01641](https://arxiv.org/abs/2607.01641)
- **FreeCodeCamp tutorial (June 2026):** Documents two real incidents: a Claude Code recursion loop that burned $16,000–$50,000 in five hours, and a four-agent LangChain loop that ran for eleven days and cost $47,000. Both agents were working correctly — nobody defined when to stop. The tutorial provides Python primitives for a spec writer, circuit breaker, ledger, and deduplication guard. — [freeCodeCamp](https://www.freecodecamp.org/news/how-to-build-a-production-safe-agent-loop-from-exit-conditions-to-audit-trails)
- **GitHub issue (open):** Kilo Code agent entered an infinite file-reading loop on a simple code review query, generating 8.5 million tokens and burning $7.59 in credits. The agent made 4+ consecutive redundant tool calls reading the same files without ever providing an answer. The issue identifies the root cause: the agent accumulates full conversation history with each tool call, with no token budget limits, cost circuit breakers, or duplicate read detection. — [GitHub Issue #3767](https://github.com/Kilo-Org/kilocode/issues/3767)
- **Agent Patterns site:** Documents a quantified example: a normal 3-4 step agent run costs ~$0.08. Once an infinite loop starts, 60+ steps in 15 minutes costs ~$12. The loop cycle — plan → call_tool → analyze → plan → call_tool → analyze — is indistinguishable from productive work without instrumentation. — [AgentPatterns.tech](https://www.agentpatterns.tech/en/failures/infinite-loop)
- **LangChain / Interrupt 2026 (May 2026):** Launched LangSmith Engine — a production trace monitoring tool that watches agent runs, clusters recurring failure patterns into named issues, diagnoses root causes, and proposes fixes. Addresses the post-loop diagnosis problem: even with circuit breakers, teams need to understand *why* loops happen to fix the underlying agent logic. — [LangChain Blog](https://www.langchain.com/blog/introducing-langsmith-engine)

## Gotchas

- **Setting step limits too low.** A hard cap of 10 steps will kill legitimate complex tasks. Pair structural limits with semantic progress detection — let the agent work if it is making state changes, kill it if it is repeating without progress.
- **Circuit breakers only help if they actually fire.** A breaker configured to alert instead of terminate is not a circuit breaker — it is a notification. For high-cost agent loops, the breaker must hard-terminate, not just warn.
- **The "one more try" retry is the most expensive anti-pattern.** When an agent step fails, re-running it with the full context window costs more than the original attempt. Build retry budgets separately from total step budgets.
- **Ambiguous tool outputs are loop fuel.** Tools that return probabilistic or non-deterministic output (LLM-based classifiers, non-deterministic parsers) are loop accelerators. Design tool interfaces for deterministic output, or add a disambiguation layer before the loop.
- **Sub-agents inherit the loop problem.** If a parent agent spawns child agents and one child enters a loop, the parent may never detect it. Monitor cost and step count at both the parent and child level. The Claude Code GitHub issue tracker has an open report of sub-agents specifically getting stuck in loops while the main agent appeared fine. — [GitHub Issue #72080](https://github.com/anthropics/claude-code/issues/72080)
