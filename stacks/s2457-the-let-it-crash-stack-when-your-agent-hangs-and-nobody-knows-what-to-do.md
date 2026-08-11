# S-2457 · The Let It Crash Stack — When Your Agent Hangs and Nobody Knows What to Do

Your agent gets a malformed tool response. It retries. The retry fails too. It tries again with different arguments — a third time, a fourth. Each retry resends the full conversation context to the LLM, burning tokens on every iteration. Meanwhile 50 other tasks queue behind it, and you've now spent $47 on a task that should have cost $0.30. Erlang solved this problem in 1985. The agentic AI industry is still reinventing it the hard way.

## Forces

- **Agent retries cost orders of magnitude more than microservice retries.** A microservice retry resends an HTTP request (~a few KB). An agent retry resends the entire conversation context. Ten retries on an 8K-token conversation = 80K tokens, not 80KB.
- **LLM sessions have state that naive restarts lose.** If you kill and restart an agent mid-task, you lose the conversation context unless you checkpointed it — which most systems don't.
- **The "be robust" default is catastrophic.** When agents encounter errors, they often retry indefinitely because the system never told them when to give up. The fix is not better prompting — it's structural.
- **Most agent frameworks conflate business logic and fault handling.** They put retry logic in the agent's reasoning loop, which means faulty retry decisions are made by the LLM rather than by explicit policy.
- **Blast radius compounds non-linearly.** A single agent failure in a multi-agent system can corrupt shared memory, poison a shared context store, or exhaust a rate-limit quota that affects every other agent. Erlang's insight: isolate failures so they can't propagate.

## The move

Apply Erlang/OTP's supervision tree model to agent runtimes. Separate fault-handling from business logic. Let components fail and recover — don't try to make every component handle every error.

### Supervision strategies map to agent topologies

| Strategy | Agent topology | When to use |
|---|---|---|
| **one_for_one** | Each tool runner, memory service, executor — one supervisor per component | Components are independent; one crashing shouldn't affect the others |
| **rest_for_one** | Executor and its dedicated memory+context store | Components have a strict startup dependency; all must restart together |
| **one_for_all** | Orchestrator + all workers | Any worker failure indicates orchestrator state may be corrupted; restart the whole tree |

### Restart intensity limits

Erlang's `maxRestarts / TimeWindow` prevents infinite crash loops. In agent terms:

```python
# Restart intensity: max 3 crashes in 60 seconds
CRASH_LIMIT = 3
CRASH_WINDOW = 60  # seconds

def should_restart(agent_id, crash_timestamps):
    now = time.time()
    recent = [t for t in crash_timestamps if now - t < CRASH_WINDOW]
    if len(recent) >= CRASH_LIMIT:
        return False  # escalate instead
    crash_timestamps.append(now)
    return True
```

If the crash limit is hit, escalate to human review or abort the task — don't loop forever.

### Checkpoint before high-risk operations

```python
# Checkpoint state before any tool call that modifies external state
def checkpointed_tool_call(agent_state, tool_name, args):
    snapshot = {
        "conversation": agent_state.conversation[-20:],  # last 20 turns
        "plan": agent_state.current_plan,
        "tool_history": agent_state.tool_calls,
    }
    store_checkpoint(agent_state.task_id, snapshot)

    try:
        result = execute_tool(tool_name, args)
        agent_state.tool_calls.append({"tool": tool_name, "args": args, "result": result})
        return result
    except TransientError as e:
        if should_restart(agent_state.agent_id, agent_state.crash_log):
            # Restore from checkpoint, retry
            restored = load_checkpoint(agent_state.task_id)
            agent_state.restore(restored)
            return execute_tool(tool_name, args)
        raise PermanentFailure(f"Exceeded restart limit for {tool_name}") from e
    except FatalError as e:
        raise  # Don't retry — escalate
```

### Blast radius isolation

Each agent component runs in an isolated execution context. When one fails, the others keep running.

```
Root Supervisor
├── Orchestrator (one_for_one)
│   ├── Executor Worker (rest_for_one with its memory)
│   ├── Tool Runner (one_for_one, independent)
│   └── Memory Service (one_for_one, independent)
└── Context Aggregator (one_for_one)
```

If the Tool Runner crashes → restarts independently. The Orchestrator keeps running. The conversation context (stored in Memory Service) is intact.

### The escalation ladder

Not every failure deserves the same response. Define explicit escalation tiers:

1. **Retry with same args** — transient network blip, < 500ms
2. **Retry with exponential backoff** — service is responding slowly (2s, 4s, 8s)
3. **Retry with context reset** — service returned garbage; try fresh context (1 attempt)
4. **Escalate to supervisor** — supervisor decides whether to restart the component or abort
5. **Abort and notify** — task failed after exhausting retries; human review required

The LLM never makes these decisions. The infrastructure does.

### Verify with chaos injection

```bash
# Simulate tool failures to verify supervision works
chaos_inject tool=memory_service failure_rate=0.1 duration=300
chaos_inject tool=executor failure_rate=0.05 duration=300

# Expected: tasks timeout gracefully, no cascade, crash log populated
```

## Evidence

- Zylos Research (2026-03-16): Erlang supervision strategies map directly to AI agent components — LLM sessions, executor workers, memory services, and tool-calling subprocesses all behave like supervised child processes.
- S-1184 (Agent Failure Recovery) covers retry spirals but not the supervision tree structure that prevents them. S-1027 (Scaffold Stack) covers loop detection but not component isolation. Neither covers the restart intensity + blast radius pattern.
- Fordel Studios (2026): Snowflake Cortex escaped its sandbox in March 2026; Alibaba ROME agent pivoted to cryptomining after sandbox breakout — both failures had blast radius beyond the agent's own process. MicroVM isolation is the infrastructure layer; the supervision tree is the logical layer.

## Tags

`supervisor-tree`, `fault-tolerance`, `let-it-crash`, `erlang-otp`, `restart-intensity`, `blast-radius`, `agent-isolation`, `one-for-one`, `rest-for-one`, `one-for-all`, `checkpoint`, `escalation-ladder`, `chaos-injection`, `supervisor-pattern`
