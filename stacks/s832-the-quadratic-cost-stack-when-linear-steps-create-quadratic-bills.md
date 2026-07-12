# S-832 · The Quadratic Cost Stack — When Linear Steps Create Quadratic Bills

Every agentic loop re-sends its entire conversation history to the LLM on every step. This means N steps don't cost N× a single call — they cost 1+2+3+…+N, which is O(N²). Teams discover this when a quarterly bill arrives and looks nothing like the demo.

## Forces

- A 10-step agent doesn't cost 10× a single call — it costs **25–50×**, depending on average step size
- Context windows exceeding 200k tokens lulled teams into ignoring cost discipline ("we have headroom")
- Each tool call and response is added to history permanently unless explicitly compacted or truncated
- Anthropic measured agents consuming **4× the tokens** of equivalent chat, and multi-agent systems consuming **15×** (2025 production data)
- Token price is per-million, so the jump from $0.002 to $0.24 per task is invisible until the bill arrives
- Cost attribution is missing at the loop level — most teams can see cost per call, not cost per task outcome

## The move

### 1. Model the O(N²) math explicitly

Before optimizing, compute the actual cost envelope:

```
# Naive (wrong): turns × cost_per_call
naive_cost = N * avg_cost_per_call

# Accurate: triangular sum of growing context
accurate_input_tokens = sum(avg_tokens_at_step(i) for i in range(1, N+1))
# ≈ N/2 × avg_tokens_at_step_N  (triangular distribution)
accurate_cost = accurate_input_tokens * price_per_million

# Practical: 10-step agent, 500 tokens/step avg, $2.50/1M input
naive:    $0.125
accurate: $3.13  # 25× the naive estimate
```

Measure cost **per task outcome**, not per API call. A $0.08 task that succeeds beats a $0.24 task that fails and retries.

### 2. Cut the loop — the highest-leverage lever

Capping loop iterations is worth more than any micro-optimization inside the loop. Set `max_steps` hard and design the agent to finish within it:

```python
@dataclass
class LoopBudget:
    max_steps: int = 15          # hard ceiling — stops runaway loops AND caps cost
    soft_warning_step: int = 8   # page someone when 8 of 15 used
    compaction_threshold: int = 5 # if context > 50% full by step 5, compact proactively

def run_agent(agent, task, budget: LoopBudget):
    state = agent.initial_state(task)
    step = 0
    while step < budget.max_steps:
        state = agent.step(state)
        step += 1
        check_budget(state, step, budget)
        if state.is_done:
            return state
    raise LoopBudgetExceeded(step, budget.max_steps, state.last_output)
```

### 3. Architect the three-layer cost fence

**Layer A — Static prefix caching** (largest bang per buck)
Extract everything that never changes across calls and cache it explicitly:

```python
STATIC_PREFIX = SYSTEM_PROMPT + TOOL_DEFINITIONS + SAFETY_CONSTRAINTS
# With Anthropic prompt caching: ~90% input cost reduction on the prefix
# Re-pays on every single step of every single run

DYNAMIC_SUFFIX = f"Task: {task}\nHistory: {compacted_history}\n"
```

**Layer B — Milestone checkpoint and reset**
Rather than letting history grow unbounded, checkpoint state and reset to a compact context at logical boundaries:

```python
# Instead of: accumulate all steps
# Do: checkpoint state at milestones, truncate history

class MilestoneReset:
    def should_reset(self, step: int, tokens: int, context_pct: float) -> bool:
        return (
            step % 5 == 0          # every 5 steps, or
            or context_pct > 0.70  # 70% context utilization
        )

    def checkpoint_state(self, state) -> dict:
        return {
            "goals": extract_active_goals(state),
            "completed": extract_completed_work(state),
            "open_files": extract_file_handles(state),
            "error_context": extract_last_error(state),
        }

    def reset_with_checkpoint(self, checkpoint: dict) -> list[dict]:
        return [
            {"role": "system", "content": f"Prior work: {checkpoint['completed']}"},
            {"role": "system", "content": f"Goals: {checkpoint['goals']}"},
        ]
```

**Layer C — Per-step output truncation**
Tool outputs are the biggest inflation source. Classify and aggressively truncate:

```python
class ToolOutputPolicy:
    # Raw output from tools: truncate to first N lines or size limit
    # Keep: status codes, file paths, error messages, structured data
    # Drop: verbose logs, full file contents, repeated boilerplate
    def truncate(self, tool_name: str, output: str) -> str:
        limits = {
            "read_file": 2000,     # lines of context, not lines of code
            "grep": 500,
            "bash": 300,
            "web_search": 800,
        }
        return output[: limits.get(tool_name, 1000)]

    # For file reads specifically: extract the relevant section
    def extract_relevant_section(self, file_path: str, context: str) -> str:
        if "error in line" in context:
            return f"Relevant section of {file_path}: [extract ±20 lines around error]"
```

### 4. Instrument cost at three granularities

| Level | What | How |
|-------|------|-----|
| **Per-call** | `usage.input_tokens` + `usage.output_tokens` | SDK built-in |
| **Per-step** | `input_tokens × step_number` | Add step counter span to OTel |
| **Per-task** | Sum all steps for one task_id | Group traces by `task_id` span attribute |

The per-task number is what you actually care about. Per-call is noise. Per-step reveals where the growth happened.

```python
from opentelemetry import trace
tracer = trace.get_tracer(__name__)

@tracer.start_as_current_span("agent_loop")
def run_task(task):
    with tracer.start_as_current_span("step", attributes={"step": 0}) as span:
        for step_num in range(1, MAX_STEPS + 1):
            span.set_attribute("step", step_num)
            # ... run step, observe cost ...
            current_cost = estimate_step_cost(step_num, tokens)
            span.set_attribute("cumulative_cost_usd", cumulative_cost)
```

## Receipt

> Receipt pending — 2026-07-08

Key sources: Anthropic multi-agent research (4×/15× multiplier data), Neel Mishra MLOps blog ("Agent Cost: Token Budgets and Optimization"), Waxell AI blog ("AI Agent Context Window Cost: The Compounding Math Your Architecture Is Hiding", May 2026), Vinayaka Jyothi ("Cutting the Cost of AI Agents", May 2026).

## See also

- [S-08](s08-prompt-caching.md) · Prompt Caching — pay once for the static prefix
- [S-21](s21-context-compaction.md) · Context Compaction — compress history before it grows unbounded
- [S-123](s123-prompt-section-cost-attribution.md) · Prompt Section Cost Attribution — which section of the prompt is actually costing you
- [S-829](s829-the-eval-first-stack-when-you-dont-know-if-your-agent-is-working.md) · The Eval-First Stack — know if your agent works before you deploy it
- [S-818](s818-the-self-healing-agent-stack-fault-tolerance-for-autonomous-systems.md) · The Self-Healing Agent Stack — loop detection and budget fences
