# S-2131 · The Runaway Loop Stack — When an Agent Does Exactly What You Told It, Forever

Agents don't fail loudly. Traditional code hits an undefined state and crashes. An LLM hits ambiguity and tries to be helpful. A cost counter on one team's LangChain pipeline hit $47,000 before anyone noticed — 11 days of agents doing exactly what they were designed to do, with no crash, no error, no alert. The only signal was the invoice. This is the runaway loop problem: not a bug, but an agent with no stopping condition executing a valid plan that was never finished.

## Forces

- **The cost of a loop compounds non-linearly.** Each iteration re-reads the full context window. Step 1 = 100 tokens. Step 10 = thousands. A task that should cost $0.08 costs $12 when the agent spins 60 times in 15 minutes. Multi-agent systems add a multiplier: orchestrated multi-agent runs are ~30x more expensive per interaction than a chatbot, and complex multi-step tasks can reach 70x.
- **Step counters are circuit breakers, not solutions.** A step counter stops the damage. It does not fix the failure. An agent that hits its step limit on 30% of complex tasks has failed on 30% of complex tasks — you just changed "infinite loop" to "timeout error."
- **Loops are stochastic, not random.** LLMs are deterministic given identical inputs. But a small change in tool output format, a paginated API response, or a context shift can flip the step order and push a stable agent into a loop. What worked in staging can loop in production for reasons that don't show in unit tests.
- **Recovery and prevention require different mechanisms.** Preventing a loop costs less than recovering from one, but you need both — and most teams build only the recovery.

## The Move

### 1. Classify before you act — four loop types, four fixes

Not all loops are the same. From the Agent Patterns taxonomy, cross-referenced against Cloudzy and Meritshot:

| Loop Type | Signature | Fix |
|---|---|---|
| **Hard loop** | Same action repeated identically | Semantic similarity detection on recent actions |
| **Soft loop** | Same action class with minor variation | State audit: has the world state changed? |
| **Retry storm** | Same transient failure causes repeated retries | Exponential backoff with jitter + circuit breaker |
| **Semantic loop** | Model re-reads original task, forgets progress, regenerates plan | Context window hygiene: preserve action history separately from task prompt |

**Design principle from Neel Mishra:** Classify the error type before deciding recovery. A retry loop that hammers a 401 endpoint wastes tokens and time. Always inspect the error type first, then branch into the appropriate recovery path.

### 2. Hard-wire cost circuit breakers at three levels

From the FreeCodeCamp analysis of the $16K–$50K Claude Code incident and the $47K LangChain incident:

**Turn-level budget:** Track cost per turn. If a single step exceeds a threshold (e.g., $2), pause and surface to a human. Most runaway loops are detectable within 3–5 steps if you're watching cost-per-turn.

**Session-level budget:** Hard cap on total spend per task. This is the last line — the thing that stops the 11-day $47K incident. Set it before the loop starts, not after the invoice arrives.

**Step-count circuit breaker:** Necessary but not sufficient. Set a conservative default (e.g., 50 steps for a complex task), but treat hitting the limit as a failure that needs root-cause analysis, not a normal termination.

### 3. Checkpoint state at semantic boundaries, not every step

From LangGraph's `SqliteSaver`/`PostgresSaver` persistence and the CrewAI checkpointing feature (v0.112+):

LangGraph checkpoints state at each superstep. When a graph node fails mid-execution, LangGraph stores pending checkpoint writes from completed nodes, so resuming doesn't re-execute successful steps. This matters because: a 4-step ETL pipeline where step 3 crashes should resume from step 3, not step 1.

**Checkpoint at meaningful boundaries** (step 1 complete, step 2 complete), not at every token. OverCheckpointing adds overhead; under-checkpointing loses progress. The right granularity is "before each tool call that modifies external state."

### 4. Detect loops before the counter hits

From Cloudzy's taxonomy and the semantic similarity approach:

```python
# Track recent action signatures
recent_actions = []
def is_looping(agent_state):
    sig = hash(agent_state.last_action)
    for prev_sig in recent_actions[-5:]:
        if semantic_similarity(sig, prev_sig) > 0.9:
            return True  # Same action class, not making progress
    recent_actions.append(sig)
    return False
```

**The signal is semantic similarity of recent actions, not exact equality.** A soft loop with slight variations will have near-identical action signatures. A healthy agent working on a complex task will have varied action signatures even if it takes many steps.

### 5. Feed LLM-correctable errors back to the LLM

From the Lubu-Labs LangGraph error-handling skill (based on LangChain patterns):

Not all errors should trigger a retry loop. Use LLM-based recovery when the error is caused by incorrect LLM decisions:

- **Tool failures with wrong parameters** — feed the error message back to the LLM with "the tool returned this error: fix your parameters and retry"
- **Semantic/parsing failures** — malformed JSON, schema violations, business rule violations
- **Logic errors the LLM can self-correct** — missing required fields, constraint failures

**Do not feed back to the LLM:** network errors (retry with backoff), auth failures (fix configuration), programming errors (debug, don't retry).

### 6. Define done before the loop starts

From FreeCodeCamp's "spec writer" primitive: the single highest-leverage intervention is forcing the task spec to define explicit termination criteria before the first loop iteration.

Ask: "What does success look like? What are the minimum acceptable outputs? What conditions make the task unsolvable and should abort immediately?" These answers become the loop's exit conditions — not just "run until step N."

## Evidence

- **Blog post (FreeCodeCamp, June 2026):** Documented two runaway loop incidents — a Claude Code recursion loop burning $16,000–$50,000 in 5 hours, and a four-agent LangChain loop burning $47,000 over 11 days. Introduced five Python primitives: spec writer, circuit breaker, ledger, cost budget, escalation queue. — [FreeCodeCamp](https://www.freecodecamp.org/news/how-to-build-a-production-safe-agent-loop-from-exit-conditions-to-audit-trails)

- **Engineering case study (Towards AI, October 2025):** Team deployed a 4-agent LangChain system with A2A coordination. Cost trajectory: $127 (week 1) → $891 (week 2) → $6,240 (week 3) → $18,400 (week 4). Total before shutdown: $47,000. Root cause was lack of cost monitoring and no per-task budget caps. — [Towards AI / Medium](https://pub.towardsai.net/we-spent-47-000-running-ai-agents-in-production-heres-what-nobody-tells-you-about-a2a-and-mcp-5f845848de33)

- **Taxonomy / reference (AgentPatterns.tech, 2026):** Four-loop taxonomy (hard, soft, retry storm, semantic) with detection methods and architectural fixes. Cost example: 60+ steps in 15 minutes = ~$12 vs. normal ~$0.08. — [AgentPatterns.tech](https://www.agentpatterns.tech/en/failures/infinite-loop)

- **Production guide (Cloudzy, June 2026):** Six failure modes for production agent loops. Key claim: "An agent loop is a stochastic system making one sequential decision after another. Without a few specific guardrails, the rare failure becomes a guaranteed one once you run it long enough." — [Cloudzy](https://cloudzy.com/blog/why-ai-agent-loops-fail-in-production)

- **LangGraph docs (LangChain, 2025–2026):** LangGraph stores pending checkpoint writes from completed nodes at a given superstep when a node fails, enabling resume without re-execution. Configured via `SqliteSaver`, `PostgresSaver`, or `MemorySaver`. — [LangChain Reference](https://reference.langchain.com/python/langgraph.checkpoint)

## Gotchas

- **A step counter that never triggers means it's set too high.** For most agent tasks, 20–30 steps is the right ceiling for a single coherent task. If you're setting it to 100, you haven't fixed the loop problem — you've made it possible to run longer before the damage accumulates.
- **Silent failure is the common case.** The $47K incident had no crash, no error log, no alert. The pipeline was working correctly — it was doing exactly what the spec said. You must instrument cost and progress explicitly; absence of errors is not absence of problems.
- **Tool responses dominate token cost.** Braintrust data shows tool responses account for 67.6% of all tokens in an agent trace. System prompts are only 3.4%. Optimizing the system prompt is the wrong lever; truncating or summarizing tool responses is the right one.
- **Checkpointing the wrong thing is worse than no checkpointing.** If you checkpoint every token, you add overhead that compounds the loop problem. Checkpoint at meaningful boundaries — before each external state mutation — and make the checkpoint resumable, not just a snapshot.
- **LLM-based recovery can itself loop.** If you feed an error back to the LLM and it produces another error, you have an error loop. Cap LLM-based recovery at 2–3 attempts before escalating to a human or aborting.
