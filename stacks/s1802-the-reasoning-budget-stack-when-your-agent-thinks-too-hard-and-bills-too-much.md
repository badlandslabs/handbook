# S-1802 · The Reasoning Budget Stack — When Your Agent Thinks Too Hard and Bills Too Much

A simple lookup task costs $0.003. The same task with chain-of-thought enabled costs $0.47. Your agent reaches for reasoning on everything — not because the problem needs it, but because it was never told when to stop thinking. This is not a model problem. It is a budget architecture problem.

## Forces

- **Inference-time compute scales with thinking tokens, not task value.** Each reasoning token costs money. On hard problems, this pays off. On routine tasks, it is pure waste. Most agentic systems apply the same reasoning effort uniformly, regardless of problem difficulty — burning 10–100x more compute than needed on simple cases.
- **Overthinking and underthinking are both expensive.** An agent that thinks too little produces wrong answers that require human correction or rerunning. An agent that thinks too much burns budget on problems that a one-step response would have solved. The cost function for reasoning effort is non-linear and problem-dependent.
- **Reasoning depth is invisible until the invoice arrives.** Unlike token counts in the context window, reasoning token usage is rarely surfaced in production observability. Teams discover they have a reasoning budget problem only when the monthly bill is 40x above forecast — and by then the architecture has already baked the waste into every execution path.
- **Task difficulty is not known at dispatch time.** The agent doesn't know whether the next user query requires deep multi-step reasoning or a direct lookup until it has already started thinking. Static reasoning enable/disable is too blunt; you need a mechanism that adapts at runtime based on observed progress.

## The Move

### 1. Classify at the gate, before reasoning starts

Route each task through a **cheap classifier** (small model, simple heuristic, or keyword check) that assigns a reasoning effort tier:

| Tier | Trigger | Model/Strategy | Typical Use |
|------|---------|----------------|-------------|
| **Direct** | Keyword match, prior similar task | Direct response, no CoT | Lookups, format conversions, simple transforms |
| **Standard** | Default | Standard prompting with brief reasoning | Most routine tasks |
| **Deep** | Ambiguous intent, multi-step dependency, low-confidence classifier | Full chain-of-thought, extended reasoning | Complex analysis, planning, multi-tool chains |

```python
def classify_reasoning_effort(query: str, context: dict) -> str:
    # Fast-path heuristics: known cheap operations
    direct_triggers = ["lookup", "get", "list", "count", "what is",
                       "format as", "convert to", "retrieve"]
    for trigger in direct_triggers:
        if trigger in query.lower():
            return "direct"

    # Check for multi-step indicators
    deep_triggers = ["compare", "analyze", "strategy", "plan",
                     "evaluate", "design", "why did", "explain why"]
    for trigger in deep_triggers:
        if trigger in query.lower():
            return "deep"

    # Check prior similar task outcomes
    if context.get("similar_task_cost") and context["similar_task_cost"] < 0.01:
        return "direct"  # previously cheap, likely cheap now

    return "standard"
```

### 2. Budget caps at the per-step level

Set **hard caps** on reasoning tokens per step, not just per session:

```python
MAX_REASONING_TOKENS = {
    "direct": 0,       # no thinking
    "standard": 512,   # ~200 tokens thinking budget
    "deep": 4096,      # generous but bounded
}

# OpenAI API example
response = client.responses.create(
    model="o4-mini",
    input=user_message,
    reasoning={
        "type": "tokens",
        "max_tokens": MAX_REASONING_TOKENS[tier]
    },
    # ...
)
```

For models without native reasoning budget controls, use **intermediate checkpointing** — halt the reasoning loop every N tokens, evaluate progress, and decide whether to continue or commit to an answer.

### 3. Measure Reasoning-ROI per task type

Track the ratio of reasoning tokens to outcome quality across task categories:

```
Reasoning-ROI = (quality_score - baseline_quality) / reasoning_tokens_consumed
```

Quality can be measured by human ratings, downstream task success rates, or eval scores. Over time, this builds a **reasoning budget table** by task type — empirical evidence for which categories justify deep thinking and which are better served by direct response.

| Task Category | Avg Reasoning Tokens | Quality Lift | ROI |
|---------------|----------------------|--------------|-----|
| Code generation | 2,100 | +12% | Low |
| Bug diagnosis | 4,800 | +34% | High |
| Data lookup | 0 | 0 | Baseline |
| Multi-step planning | 6,200 | +41% | High |
| Simple rewrite | 0 | 0 | Baseline |

### 4. Cascade routing: escalate on difficulty signals

For ambiguous tasks where tier assignment is uncertain, use **cascade routing** — start cheap and escalate:

```
1. Answer with direct response (no reasoning)
2. If confidence < threshold OR task involves >2 tool hops:
     → retry with standard reasoning
3. If still uncertain OR result contradicts known facts:
     → escalate to deep reasoning with full chain-of-thought
4. If still failing after deep reasoning:
     → surface to human with reasoning trace attached
```

This is the inverse of the old "start complex, simplify later" approach — you pay the minimum necessary to get the right answer.

### 5. Monitor at the billing level

Instrument reasoning token counts as a **first-class metric**:

```python
# Log reasoning usage per task
metrics.log({
    "task_id": task_id,
    "reasoning_tokens": response.usage?.tokens?.thinking,
    "reasoning_cost_usd": reasoning_tokens * price_per_token,
    "total_cost_usd": total_cost,
    "reasoning_cost_share": reasoning_tokens / total_tokens,
    "outcome": outcome,
})
```

Alert when `reasoning_cost_share > 0.7` (reasoning is more than 70% of total cost — a signal the agent is overthinking for the task type).

## Tradeoffs

- **Classification accuracy is not 100%.** A misclassified "direct" task that escalates mid-execution costs more than just running it at "deep" from the start. Build in cheap fallback paths, not hard failures.
- **Reasoning-ROI measurement requires outcome telemetry.** You cannot compute ROI without knowing whether the answer was correct or useful. This means you need eval infrastructure alongside cost monitoring — not instead of it.
- **Cascade routing adds latency on edge cases.** Tasks that cascade through multiple tiers take longer. For latency-sensitive use cases, a static tier assignment with better classification may be preferable to dynamic escalation.
- **Deep reasoning on wrong assumptions can be counterproductive.** An agent that thinks deeply about a misframed problem produces more confidently wrong output than one that answers directly. When in doubt, surface uncertainty rather than reasoning your way to false precision.

## See Also

- [S-06 · Model Routing](s06-model-routing.md) — choosing which model to use, which includes cost considerations
- [S-08 · Prompt Caching](s08-prompt-caching.md) — reducing input token costs; complementary to reasoning budget control
- [S-103 · Cost-Aware Context Management](s103-cost-aware-context-management.md) — deciding when context carries economic weight
- [S-99 · Agent Task Economics](s99-agent-task-economics.md) — the broader economics of agentic task execution
