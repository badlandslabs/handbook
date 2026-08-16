# S-2734 · The Self-Evaluation Circuit Breaker Stack — When Your Agent Judges Its Own Work and Costs You $4,200 Overnight

You ship an agent that plans, reflects, and refines its own output. Three weeks later you wake up to a $4,217 bill for one agent's overnight run. The agent was working — returning valid results every call, never crashing, never erroring. It was evaluating itself, finding its own work insufficient, and iterating. 47 times. The self-evaluation prompt had a subtle bias toward "needs more granularity" with large inputs. Nobody caught it because the loop was the feature.

This is the self-evaluation circuit breaker problem: when the quality-judgment step of a reflection loop is broken, it doesn't fail loudly — it fails expensively.

## Forces

- **Self-evaluation is the most dangerous loop endpoint.** A tool error stops a loop. A bad evaluation step accelerates it — each iteration generates more context, which triggers the same false "needs detail" verdict, which generates even more context.

- **The cost curve is non-linear.** Iteration 1 costs $2. Iteration 47 costs $120. The last 17 iterations cost more than the first 30 combined. By the time a human notices, the damage is done.

- **Standard loop guards miss the failure mode.** Max iterations blocks legitimate multi-step workflows. Hard token limits destroy in-flight tasks. Neither distinguishes "still working" from "looping on bad judgment."

- **The evaluation step is invisible to most monitoring.** Tool call traces show LLM invocations, not the quality decision logic. The evaluator's output — "this is good enough" — is just another LLM call, easy to overlook.

## The Move

### Layer 1: Separate the Evaluator from the Actor

Never let the same agent instance judge its own output. Use a distinct, lightweight evaluation prompt — scoped to a single question: "Is this output ready to return, or does it need another iteration?"

```python
EVALUATOR_PROMPT = """You are a quality gate. Given a task and an output, answer exactly:
READY — if the output satisfies the task requirements.
REFINE — if the output needs another iteration. Include one specific gap.

Do not suggest what to refine. Do not elaborate. Answer with READY or REFINE plus one gap."""

def evaluate(task: str, output: str, evaluator: LLM) -> str:
    result = evaluator.call([
        {"role": "system", "content": EVALUATOR_PROMPT},
        {"role": "user", "content": f"Task: {task}\n\nOutput:\n{output}"}
    ])
    return result.content.strip()[:100]  # cap at first 100 chars
```

### Layer 2: Per-Iteration Cost Budget with Decay

Each iteration gets a smaller budget. If iteration N costs C tokens, iteration N+1's budget ceiling is C × 0.7. This makes indefinite loops economically impossible without hard-cutting legitimate multi-pass workflows.

```python
MAX_ITERATIONS = 20
COST_DECAY = 0.7
BASE_BUDGET = 5000  # tokens per iteration

def should_continue(step: int, tokens_used: int, last_cost: float) -> bool:
    if step >= MAX_ITERATIONS:
        return False
    budget = int(BASE_BUDGET * (COST_DECAY ** step))
    if tokens_used > budget:
        return False
    if last_cost > budget * 3:  # 3× spike = something wrong
        return False
    return True
```

### Layer 3: Evaluator Calibration Gate

Before deploying, run the evaluator against 5 known-READY and 5 known-REFINE examples. If it misclassifies more than 20%, the prompt is broken — halt the pipeline and alert.

```python
CALIBRATION_PAIRS = [
    ("Write a greeting", "Hello, world!", "READY"),
    ("Write a greeting", "", "REFINE"),
    # ... 8 more pairs
]

def calibrate(evaluator: LLM) -> float:
    errors = 0
    for task, output, expected in CALIBRATION_PAIRS:
        result = evaluate(task, output, evaluator)
        actual = "READY" if result.startswith("READY") else "REFINE"
        if actual != expected:
            errors += 1
    error_rate = errors / len(CALIBRATION_PAIRS)
    if error_rate > 0.2:
        raise EvaluatorCalibrationError(f"Error rate {error_rate:.0%} exceeds 20% threshold")
    return error_rate
```

### Layer 4: Dollar Circuit Breaker

Track cumulative cost in real money, not tokens. Set a hard stop in USD — enforced at the loop boundary, not the API layer.

```python
SESSION_BUDGET_USD = 5.00  # per task
running_cost = 0.0

for step in range(MAX_ITERATIONS):
    result = agent.act(task, context)
    cost_usd = result.usage.total_tokens * TOKENS_PER_DOLLAR
    running_cost += cost_usd

    verdict = evaluate(task, result.output, evaluator)
    if verdict.startswith("READY") or not should_continue(step, result.usage.total_tokens, cost_usd):
        return result

    if running_cost >= SESSION_BUDGET_USD:
        raise BudgetBreakerTripped(f"Ran ${running_cost:.2f} — circuit breaker triggered at step {step}")
```

### Layer 5: Self-Evaluation Prompt Hardening

If you must keep self-evaluation, hard-code explicit convergence signals. Train the evaluator to detect diminishing returns:

```
If the output addresses all requirements in the task, answer READY.
If the output addresses all requirements but you want more polish, answer READY.
Only answer REFINE if a specific, named requirement is unaddressed.
```

## Receipt

> Verified 2026-08-16 — DevOS team documented the canonical incident: Planner agent stuck in refinement loop for 5.5 hours, 47 iterations, $4,217.43. Root cause: self-evaluation prompt flagged "needs granularity" on large inputs even when work was complete. NexGismo (2026) and AgentFuse (GitHub, MIT licensed) both document the same pattern across multiple incidents, with one retailer incident reaching $12M in a single runaway event. AgentFuse implements the financial circuit breaker pattern in MCP server form.

## See also

- [S-2186 · The Agent Budget Guard Stack](/opt/data/handbook/stacks/s2186-the-agent-budget-guard-stack-when-your-agent-is-your-biggest-monthly-expense.md) — hard token and dollar limits at the call boundary
- [S-2100 · The Convergence Detection Stack](/opt/data/handbook/stacks/s2100-the-convergence-detection-stack-when-your-refinement-loop-runs-all-night-and-still-looks-done.md) — semantic convergence signals for refinement loops
- [S-1291 · The Failure Ceiling Stack](/opt/data/handbook/stacks/s1291-the-failure-ceiling-when-your-agent-cant-tell-its-stuck-and-the-system-has-no-brake.md) — detecting when an agent is stuck vs. still working
