# R-18 · Why Agents Fail to Stop: Infinite Agentic Loops

Agents don't crash — they keep going. Unlike traditional software where an infinite loop throws a stack overflow, an LLM agent in an infinite loop generates plausible-looking reasoning chains, calls tools, writes files, and burns budget while appearing to work. The field has no standard vocabulary for this class of failure. This entry supplies one.

> **Source:** Hou et al., *When Agents Do Not Stop: Uncovering Infinite Agentic Loops in LLM Agents*, arXiv:2607.01641v1 [cs.SE], July 2, 2026. HUST research. IAL-Scan tool: 91.9% precision across 47 real-world agent projects, 68 confirmed IAL failures.

## Forces

- **IALs are structurally different from programming loops.** An ordinary `while(true)` is caught by a static analyzer. An IAL arises from the interaction between agent reasoning, framework semantics, runtime observations, and termination logic — none of which are in scope for traditional loop detection.
- **The agent appears productive.** The IAL generates plausible tool calls, intermediate reasoning, and outputs. Unlike a crash, nothing signals "wrong." The budget drain is the only symptom.
- **Static loop detection misses the feedback path.** A termination condition that looks correct in a static test can fail at runtime because the LLM generates unexpected tool responses that invalidate the condition's assumptions.
- **Framework authors don't design for IALs.** Most agent frameworks (LangChain, CrewAI, AutoGen) provide termination as a parameter, not a reliability mechanism. The burden falls on application developers who don't know what they're guarding against.

## The move

**Define the six IAL categories** (Hou et al., 2026):

### Type 1 — Reasoning Loop
The agent reaches the same or equivalent reasoning state and re-proposes the same action. Classic self-reinforcing thought pattern: the agent's confidence in the current plan increases with each iteration, making it less likely to abandon it even as evidence accumulates that it isn't working.

**Signal:** Repeated tool calls with identical or near-identical input parameters.

### Type 2 — Tool Loop
The agent calls the same tool repeatedly because each tool result confirms (or appears to confirm) the current plan, or because the tool returns a "success" status for an action that didn't achieve the actual goal.

**Signal:** Rapid succession of the same tool invocation with escalating parameters.

### Type 3 — Frame Logic Loop
The agent's world model diverges from reality but becomes internally consistent. It acts on false premises and each action produces observations that are interpreted through the false lens — self-confirming belief.

**Signal:** Tool results that should contradict the agent's current plan but don't; the agent never "surprises" itself.

### Type 4 — Goal State Ambiguity
The agent cannot determine whether it has achieved the goal. The goal is vague or the success criteria are unverifiable programmatically. The agent keeps working because it has no proof it's done.

**Signal:** Goal-status checks that always return "inconclusive" or "partial"; the agent escalates rather than terminates.

### Type 5 — Framework Loop
The orchestration framework's retry logic, replanning mechanism, or error-handling layer creates a loop independent of the agent's own reasoning. The framework keeps resubmitting the same task.

**Signal:** Agent-level logs show termination, but execution logs show re-submission from the framework layer.

### Type 6 — Environment Loop
The external environment (APIs, file system, databases) produces non-terminating sequences of states that the agent interprets as needing continued action. The environment is genuinely stuck, but the agent is blamed.

**Signal:** Tool calls that return stable-state results (e.g., "no new messages," "file unchanged," "database polling returns empty") with no termination signal.

### Detection: IAL-Scan

Hou et al.'s **IAL-Scan** static analyzer achieved **91.9% precision** finding IAL failures across 47 real-world agent projects without executing the agents. Key detection signals it flags:

- **Termination condition never satisfiable**: the termination guard evaluates to false under all reachable states
- **Goal state never reached**: the agent's success conditions are structurally unreachable from the initial state
- **Bounded execution assumption violated**: the framework assumes finite execution but the agent's action space permits unbounded paths
- **Feedback path too weak**: tool outputs that should terminate the loop instead reinforce continued execution

```python
# Minimal IAL-Scan signal: repeated identical tool call N times
from collections import Counter

def detect_tool_loop(trace: list[dict]) -> list[str]:
    """Return tool names that form a loop pattern in the trace."""
    calls = [step["tool"] for step in trace if step.get("tool")]
    counts = Counter(calls)
    loops = []
    for tool, n in counts.items():
        if n >= 3:
            # Check if calls are consecutive and identical
            indices = [i for i, t in enumerate(calls) if t == tool]
            for i in range(len(indices) - 2):
                if indices[i+2] - indices[i] <= 5:  # within 5 steps
                    loops.append(f"{tool} loop: {n}x calls")
    return loops

# Hard step budget — the only universal IAL safety net
MAX_STEPS = int(os.environ.get("AGENT_MAX_STEPS", "50"))
if len(trace) >= MAX_STEPS:
    raise LoopBudgetExceeded(f"Step budget {MAX_STEPS} exceeded")
```

### Prevention checklist

| Layer | Mechanism |
|---|---|
| **Termination condition** | Must be **verifiable in finite time** — prove it can't loop before deploying |
| **Step budget** | Hard cap; the only universally reliable IAL stop |
| **Tool call deduplication** | Same tool + same params within N steps = loop flag |
| **State hashing** | Hash of agent's internal world-model state; repeated state = loop |
| **Progress monotonicity** | Each step must advance a measurable score; stagnation = loop |
| **Framework audit** | Check framework retry/replan logic for non-terminating paths |

## Receipt

> Verified 2026-07-27 — arXiv:2607.01641 (Hou et al., HUST, July 2, 2026) describes IAL-Scan on 47 real projects with 91.9% precision. 6-category taxonomy is novel. R-18 is the first field reference for this taxonomy. IAL-Scan is a static analysis tool (source not yet publicly available at arXiv). The 6-type classification is the primary contribution — this entry distills it for practitioner use.

## See also

- [S-1076 · Agent Failure Recovery Stack](/stacks/s1076-the-agent-failure-recovery-stack-when-your-agent-loops-forever-or-worse.md) — recovery ladder after loop detection
- [S-199 · Agent Self-Healing Loops](/stacks/s199-agent-self-healing-loops.md) — runtime loop recovery strategies
- [S-096 · Termination Policy](/stacks/s096-termination-policy.md) — deterministic termination guards
