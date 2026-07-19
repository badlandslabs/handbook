# S-1340 · The Spend Guardrail Stack — When Your $0.01 Request Costs $5,000

You launched a market-research pipeline on a Friday afternoon. Four agents, LangChain orchestration, weekend run. Monday morning the bill is $47,000. Nobody noticed the agents looping — they were making progress. They just weren't making *useful* progress. No error. No crash. No alert. Just a credit card charge that shouldn't exist.

This is the spend guardrail failure. The cost problem in agentic systems is rarely one bad prompt. It is the multiplication effect of retries, tool loops, escalations, and long-running sessions — each individually reasonable, sum individually catastrophic.

## Forces

- **Agents are stacked cost surfaces.** Normal chat: one request, one response, one surface. Agentic: planning → tool selection → retrieval → function calls → retries → synthesis. Each layer is individually priced. The total path can be wildly uneconomic even when every individual decision was defensible.
- **Token-based billing exposed the gap.** Anthropic and OpenAI shifted to per-token pricing in 2026. The era of "tokenmaxxing" flipped to "token rationing." Legacy FinOps tools can't see inside external LLM APIs — they show cloud spend, not API spend.
- **Agents can retry, so agents can loop.** Without hard caps, a failed tool call retries, hits the same failure, retries again, escalates to a bigger model, and compounds. The loop pays for itself every iteration.
- **Observability is not control.** Dashboards show cost *after* the fact. A $5,000 loop that runs over the weekend costs $5,000 whether you see it Tuesday or never.

## The Move

### 1. Hard Cost Caps — Per-Request and Per-Task

Define non-overrideable budgets at three scopes:

```python
# Per-request hard cap
MAX_COST_PER_REQUEST = 0.50  # USD — agent halts, not alerts

# Per-task step budget
MAX_STEPS_PER_TASK = 8  # model-call-to-tool-call cycles

# Per-task total cost budget
MAX_TASK_BUDGET = 2.00  # USD — across all sub-calls

class SpendGuardrail:
    def __init__(self, max_cost: float, max_steps: int, max_retries: int = 2):
        self.max_cost = max_cost
        self.max_steps = max_steps
        self.max_retries = max_retries
        self.spent = 0.0
        self.steps = 0
        self._escalation_policy = []

    def before_llm_call(self, model: str, estimated_tokens: int, cost_per_1k: float):
        estimated = (estimated_tokens / 1000) * cost_per_1k
        if self.spent + estimated > self.max_cost:
            raise BudgetExceeded(f"Would exceed ${self.max_cost} cap (spent: ${self.spent:.2f})")
        return True

    def after_tool_call(self, cost: float, tool: str, success: bool):
        self.spent += cost
        self.steps += 1
        if self.steps > self.max_steps:
            raise StepBudgetExceeded(f"Step {self.steps} exceeds max {self.max_steps}")
        if cost > self.max_cost:
            raise BudgetExceeded(f"Tool '{tool}' alone would exceed cap")
        if not success:
            self._handle_failure(tool, cost)

    def _handle_failure(self, tool: str, cost: float):
        retry_count = getattr(self, '_retry_count', 0) + 1
        self._retry_count = retry_count
        if retry_count > self.max_retries:
            self._escalate(tool, cost)
        # else: allow retry within budget

    def _escalate(self, tool: str, cost: float):
        # Only escalate to larger model after cheap model exhausted its steps
        if self._escalation_policy:
            next_model = self._escalation_policy.pop(0)
            log.warning(f"Escalating from '{tool}' failure to {next_model}")
        else:
            raise EscalationExhausted("No escalation path available — task halted")
```

### 2. Tool Allowlisting — Reduce Decision Branching

Not every agent needs every tool. Restrict by workflow type:

```python
WORKFLOW_TOOLS = {
    "code_review": ["read_file", "grep", "shell"],
    "data_analysis": ["sql_query", "read_csv", "plot"],
    "web_research": ["search", "fetch_url", "extract"],
    # No shell, no write_file, no database mutations in research
}

class ToolAllowlist:
    def __init__(self, workflow: str):
        self.allowed = WORKFLOW_TOOLS.get(workflow, set())

    def before_tool_call(self, tool: str):
        if tool not in self.allowed:
            raise ToolNotAllowed(
                f"Tool '{tool}' not in allowlist for workflow '{self.workflow}'. "
                f"Allowed: {self.allowed}"
            )
```

### 3. Retry Separation — Transient vs. Logic Loops

Distinct retry budgets for different failure types:

```python
# Transient errors (network, rate limit, timeout) — retry with backoff
MAX_TRANSIENT_RETRIES = 2
RETRY_BACKOFF_BASE = 2  # seconds

# Logic loops (same tool, same error, same context) — do NOT retry
# Flag for human review instead
MAX_LOGIC_RETRIES = 0  # hard stop on logic failures

def handle_tool_failure(failure_type: str, tool: str, context: dict):
    if failure_type == "transient":
        return retry_with_backoff(tool, max_attempts=MAX_TRANSIENT_RETRIES)
    elif failure_type == "logic":
        log.error(f"Logic failure in '{tool}' — escalate to human")
        notify_human(f"Agent logic failure in '{tool}': {context}")
        raise LogicLoopDetected(f"Logic failure on '{tool}' — not retrying")
```

### 4. Runtime Budget Enforcement — Not Alerts, Stops

```python
# Middleware wrapper — intercepts before every LLM call
class SpendMiddleware:
    def __init__(self, guardrail: SpendGuardrail):
        self.guardrail = guardrail

    async def run(self, agent, task):
        start_spent = self.guardrail.spent
        try:
            result = await agent.run(task)
            return result
        except BudgetExceeded as e:
            log.critical(f"SPEND GUARDRAIL TRIGGERED: {e}")
            notify_finance(f"Budget exceeded on task: {task[:100]}")
            return {"status": "halted", "reason": str(e), "spent": self.guardrail.spent}
        finally:
            log.info(f"Task complete — spent ${self.guardrail.spent:.4f}")
```

### 5. Observable Metrics — Track the Multiplication

| Metric | What It Catches |
|--------|----------------|
| `cost_per_completed_task` | Regression in agent efficiency |
| `avg_model_calls_per_task` | Creeping reasoning complexity |
| `avg_tool_calls_per_task` | Loop or tool-selection degradation |
| `retry_rate_by_tool` | Specific tool failure patterns |
| `escalation_rate` | When agents are bumping to larger models |

## Receipt

> Receipt pending — 2026-07-19. Run the `SpendGuardrail` class against a synthetic 50-task dataset with injected retry loops and escalation scenarios. Validate: step cap halts at correct count, cost cap halts before exceeding, retry separation correctly distinguishes transient from logic failures.

## See also

- [S-1000 · The Context Exhaustion Stack](/stacks/s1000-the-context-exhaustion-stack-when-your-agent-silently-degrades-as-the-window-fills.md) — context window as budget; related to token-level spend tracking
- [S-988 · The Agent Failure Recovery Stack](/stacks/s988-the-agent-failure-recovery-stack-when-your-agent-silently-burns-budget-in-the-dark.md) — recovery patterns; guardrails prevent the burn
- [S-1011 · The Rate-Limited Multi-Agent Pattern](/stacks/s1011-the-rate-limited-multi-agent-pattern-when-all-your-agents-attack-your-api-quota-together.md) — API quota limits; different failure axis but same budget discipline
