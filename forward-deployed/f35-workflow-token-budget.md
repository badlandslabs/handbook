# F-35 · Workflow Token Budget

[S-02](../stacks/s02-context-budget.md) allocates tokens within a single call. [F-29](f29-cost-attribution.md) attributes spend to features after the fact. [F-08](f08-agent-cost-control.md) lists caps as a requirement. None of them show how to enforce a spend ceiling across the multiple model calls a single workflow makes. A research agent that uses three model calls and five tool rounds has no natural spending limit unless you build one. Without it, a loop condition, a noisy tool, or an over-eager planner turns a $0.04 task into a $0.40 one silently.

## Situation

A research agent runs: triage call (classify the request) → two search calls (retrieve sources) → synthesis call (reason over sources) → format call (structure the output). Five calls, predictable in normal operation. Under an edge case — a vague query triggers expanded searches — the agent adds three more search calls and runs synthesis twice. The total jumps from 7 000 to 18 000 tokens and from $0.04 to $0.11. At 10 000 sessions/day, the undetected cost increase is $700/day. A 5 000-token workflow ceiling detects and terminates the runaway at call 4, saving 90% of the runaway cost.

## Forces

- **A workflow has no natural token ceiling.** Each model call is bounded by `max_tokens`. The workflow itself is not. Loop conditions, retry logic, or planner over-expansion can multiply the expected call count without any single call exceeding its limit.
- **Pre-call estimation is approximate.** You can estimate how many tokens the next call will cost based on input length and expected output. You can't know exactly. The budget check must use pre-call estimates to refuse calls before they run, not just to log spend after.
- **Stage allocations improve predictability.** Assigning a fraction of the total budget to each stage gives each stage a local ceiling. The format stage shouldn't spend 40% of the budget. If it does, something is wrong — the formatter is being asked to do synthesis work.
- **Early termination must be graceful.** When the budget ceiling triggers, the right response is to return whatever is complete, not to crash or return nothing. A partial result with a `budget_exceeded: true` flag is more useful than a 500 error.
- **Per-session budget is separate from per-day cap.** The workflow budget is a per-request limit (this workflow for this user gets N tokens). The daily cap is an aggregate (the whole system spends at most M tokens/day). Both are needed; neither replaces the other.

## The move

**Wrap every model call in a budget tracker. Check remaining budget before each call. Allocate fractions per stage. Return partial results with a flag on budget exhaustion.**

**Budget tracker:**

```js
class WorkflowBudget {
  constructor(totalTokens) {
    this.total   = totalTokens;
    this.spent   = 0;
    this.stages  = {};  // stage_name → tokens_spent
  }

  // Call before each model call. Throws if estimated input would exceed budget.
  check(estimatedInputTokens, stageName) {
    const remaining = this.total - this.spent;
    if (estimatedInputTokens > remaining) {
      throw new BudgetExceededError(
        `Stage "${stageName}" needs ~${estimatedInputTokens} tokens but only ${remaining} remain of ${this.total}`
      );
    }
  }

  // Call after each model call with actual usage from response.usage
  record(usage, stageName) {
    const used = usage.input_tokens + usage.output_tokens;
    this.spent += used;
    this.stages[stageName] = (this.stages[stageName] ?? 0) + used;
  }

  get remaining() { return Math.max(0, this.total - this.spent); }
  get fractionUsed() { return this.spent / this.total; }
}

class BudgetExceededError extends Error {
  constructor(msg) { super(msg); this.name = 'BudgetExceededError'; }
}
```

**Workflow with budget enforcement:**

```js
async function runResearchWorkflow(query, { budgetTokens = 5000 } = {}) {
  const budget  = new WorkflowBudget(budgetTokens);
  const result  = { query, stages: {}, budget_exceeded: false };

  try {
    // Stage 1: triage (small)
    budget.check(400, 'triage');
    const triageResp = await model.call(triagePrompt(query));
    budget.record(triageResp.usage, 'triage');
    const taskType = parseTriageOutput(triageResp);
    result.stages.triage = { task_type: taskType };

    // Stage 2+: searches (variable count based on triage)
    const searchCount = taskType === 'complex' ? 2 : 1;
    for (let i = 0; i < searchCount; i++) {
      budget.check(1200, 'search');  // estimate: 1200 tok/search round
      const searchResp = await model.call(searchPrompt(query, i));
      budget.record(searchResp.usage, 'search_' + i);
      result.stages['search_' + i] = { results: parseSearchOutput(searchResp) };
    }

    // Stage 3: synthesis (largest)
    budget.check(2500, 'synthesis');
    const synthResp = await model.call(synthesisPrompt(query, result.stages));
    budget.record(synthResp.usage, 'synthesis');
    result.stages.synthesis = { summary: parseSynthesis(synthResp) };

    // Stage 4: format (small)
    budget.check(600, 'format');
    const formatResp = await model.call(formatPrompt(result.stages.synthesis));
    budget.record(formatResp.usage, 'format');
    result.output = parseFormat(formatResp);

  } catch (err) {
    if (err instanceof BudgetExceededError) {
      result.budget_exceeded = true;
      result.budget_note     = err.message;
      result.output          = result.stages.synthesis?.summary ?? 'Budget exhausted before synthesis.';
    } else {
      throw err;
    }
  }

  result.token_usage = { total: budget.spent, by_stage: budget.stages, budget: budgetTokens };
  return result;
}
```

**Stage allocation guide:**

| Stage type | Token fraction | Cap signal if exceeded |
|---|---|---|
| Triage / classification | 5–10% | Classifier is doing synthesis work |
| Retrieval / tool calls | 30–40% | Too many searches; prune tool loop |
| Reasoning / synthesis | 40–50% | Normal; largest legitimate consumer |
| Formatting / extraction | 10–15% | Formatter over-generating; constrain max_tokens |

**Budget sizing by workflow type:**

```
Light (Q&A, single-tool):      2 000 – 5 000 tokens    ~$0.02–0.05
Medium (research, multi-step): 5 000 – 15 000 tokens   ~$0.05–0.15
Heavy (code gen, long reports):15 000 – 50 000 tokens  ~$0.15–0.50
```

Start conservative; measure `budget.fractionUsed` across real traffic; raise the ceiling if the p95 session uses <70% of budget.

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0, `gpt-tokenizer` (cl100k). Workflow: 5 calls (triage, search×2, synthesis, format). Prices: $3.00/M input, $15.00/M output.

```
=== 5-call research workflow: token accumulation ===

Stage        Input   Output  Cumulative  Remaining   Cost
triage         312      58        370      4630      $0.0018
search_1       580     420       1370      3630      $0.0098
search_2      1100     380       2850      2150      $0.0188 ← over allocation
synthesis     2200     820       5870         0      $0.0377 ← over allocation
format         980     210       7060         0      $0.0438 ← over allocation

Actual: 7 060 tokens vs 5 000 budget → ceiling would trigger at call 4

=== Runaway scenario: budget ceiling vs no ceiling ===

Normal workflow (5 calls):          7 060 tokens  $0.0438
Runaway (50 calls, agent loops):   70 600 tokens  $0.4384
  At 10k sessions/day:                           $4 384/day

With 5 000-token ceiling:
  Triggers at call 4 (budget exhausted)
  Saves ~90% of runaway cost per session
  Returns partial result with budget_exceeded: true

WorkflowBudget class: 87 tokens (client-side code, not in prompt)
Per-call overhead: 0 tokens — budget check runs before API call
```

The 5 000-token budget is too tight for this workflow (actual: 7 060). Revise to 8 000 after measuring real traffic. The point is not to set the ceiling at exactly the expected cost — it's to have a ceiling at all, so that a 10× runaway terminates at 4 calls instead of 50.

## See also

[S-02](../stacks/s02-context-budget.md) · [F-08](f08-agent-cost-control.md) · [F-29](f29-cost-attribution.md) · [S-56](../stacks/s56-preflight-token-check.md) · [F-20](f20-rate-limits-and-retry.md) · [S-19](../stacks/s19-agent-loop.md)

## Go deeper

Keywords: `workflow token budget` · `token ceiling` · `spend cap` · `per-session budget` · `budget middleware` · `runaway agent` · `stage allocation` · `budget_exceeded` · `cost control` · `token accumulation`
