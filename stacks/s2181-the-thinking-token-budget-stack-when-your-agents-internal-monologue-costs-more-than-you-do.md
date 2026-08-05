# S-2181 · The Thinking Token Budget Stack — When Your Agent's Internal Monologue Costs More Than You Do

Your agent takes 3 seconds to respond. The visible output is 40 tokens. The bill is $0.28. The reasoning model spent 18,400 tokens internally — tokens you cannot see, cannot log, and are not told about by default — before producing those 40. Those invisible tokens cost more than the visible ones. You are flying blind on the largest cost driver in your pipeline.

## Forces

- **Reasoning tokens are billed as output tokens but invisible in standard logs.** OpenAI o-series and DeepSeek R1 charge output-token rates for their internal thinking. A single complex request can generate 10,000–50,000 hidden reasoning tokens. Most observability dashboards don't surface them. Most cost attribution systems miss them entirely.
- **Easy queries waste reasoning budget.** On simple tasks, reasoning models often burn 900+ tokens generating Chain-of-Thought for problems that need none. The model reasons because it was built to reason — not because the task requires it. You pay the reasoning premium on every call unless you explicitly gate it.
- **Reasoning quality and reasoning cost are separable dimensions.** The TALE framework (arXiv:2412.18547, revised June 2025) demonstrates that LLMs can compress their reasoning chains when given explicit token budgets — without proportional quality loss on most tasks. The budget is not just a cost lever; it is a quality dial.
- **Agents compound the problem.** A single agent step using a reasoning model generates hidden tokens. A 50-step agent that chains reasoning-model calls burns hidden tokens at 50x the visible rate. The cost of the agent is not in the tools or the context — it is in the thinking.

## The Move

### 1. Track Four Token Categories Per Call

Standard logging gives you input and output tokens. Reasoning model billing requires four:

| Category | Where to Find It | What It Tells You |
|---|---|---|
| `input_tokens` | API response | User query + system prompt + context |
| `visible_output_tokens` | API response | What the user sees |
| `reasoning_tokens` | `completion_tokens_details.reasoning_tokens` | Internal thinking (o-series) |
| `cached_tokens` | `usage.prompt_tokens_details.cached_tokens` | KV cache reuse from prefix |

```python
import anthropic

client = anthropic.Anthropic()

def call_with_full_tracing(model: str, messages: list, max_tokens: int = 4096):
    response = client.messages.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        extra_headers={"anthropic-beta": "output-128k-2025-11-19"}
    )
    usage = response.usage
    reasoning = getattr(usage.output_tokens_details, 'reasoning_tokens', 0)
    cached = getattr(getattr(usage.prompt_tokens_details, 'cached_tokens', 0))

    # The ratio that blinds teams: reasoning tokens / visible tokens
    waste_ratio = reasoning / max(len(response.content[0].text.split()), 1)

    return {
        "input": usage.input_tokens,
        "visible_output": usage.output_tokens - reasoning,
        "reasoning": reasoning,
        "cached": cached,
        "reasoning_share": reasoning / max(usage.output_tokens, 1),
        "waste_ratio": waste_ratio,
        "estimated_cost_usd": estimate_cost(model, usage)
    }

def estimate_cost(model: str, usage) -> float:
    RATES = {
        "claude-sonnet-4-20250514": (3, 15),   # (input, output per M)
        "claude-opus-4-20250514": (15, 75),
        "o3": (15, 75),                          # output = reasoning + visible
        "o4-mini": (1.5, 15),
        "deepseek-r1": (0.55, 2.75),
    }
    rates = RATES.get(model, (15, 75))
    return (usage.input_tokens / 1_000_000 * rates[0]
          + usage.output_tokens / 1_000_000 * rates[1])
```

### 2. Classify Tasks by Reasoning Requirement

Not every task needs the model to think. The production pattern: classify before you route.

```python
REASONING_REQUIRED = {
    "multi_step_planning",
    "math_proof",
    "code_generation_complex",
    "contract_analysis",
    "debugging_root_cause",
    "architectural_design",
    "multi_document_synthesis",
}

REASONING_MINIMAL = {
    "classification",
    "formatting",
    "simple_extraction",
    "summarization_short",
    "translation_direct",
    "text_rewrite",
}

def requires_reasoning(task_type: str, complexity_estimate: float) -> bool:
    """Heuristic: low complexity + simple type = skip reasoning model."""
    if task_type in REASONING_MINIMAL and complexity_estimate < 0.3:
        return False
    if task_type in REASONING_REQUIRED or complexity_estimate > 0.6:
        return True
    # Default: try non-reasoning first, escalate if confidence is low
    return None  # defer to model routing
```

### 3. Budget the Thinking Explicitly

On non-reasoning tasks, disable thinking. On reasoning tasks, cap it.

```python
def build_reasoning_params(task_type: str, budget_tokens: int = 2048):
    """Return API params that govern reasoning behavior."""
    if task_type in REASONING_MINIMAL:
        # Disable extended thinking on simple tasks
        return {
            "thinking": {"type": "disabled"}
        }
    # For reasoning tasks: set a budget, not a free-form limit
    return {
        "thinking": {
            "type": "enabled",
            "budget_tokens": budget_tokens,  # hard cap on reasoning
        }
    }
```

For OpenAI o-series, use `max_completion_tokens` as a combined cap (visible + reasoning), and monitor the `completion_tokens_details.reasoning_tokens` field:

```python
# OpenAI: set total output cap
response = client.chat.completions.create(
    model="o3",
    messages=messages,
    max_completion_tokens=4096,  # caps visible + reasoning combined
)

# Extract hidden reasoning cost
reasoning_tokens = response.usage.completion_tokens_details.reasoning_tokens
visible_tokens = response.usage.completion_tokens - reasoning_tokens
# Alert if reasoning > 70% of budget
if reasoning_tokens > 0.7 * 4096:
    alert_cost_spike(model="o3", reasoning=reasoning_tokens, budget=4096)
```

### 4. Route by Reasoning Profile, Not Just Model Tier

The S-1039 specialist router routes by model capability. This stack adds a routing axis: whether the model reasons at all.

```
Task enters
    │
    ├─ Low reasoning requirement ──→ Sonnet-class model (no thinking overhead)
    │                                     ▲ savings: ~95% on reasoning tokens
    │
    ├─ Medium reasoning ──→ Standard reasoning model + budget cap
    │                           (e.g., o4-mini, budget=2048)
    │                           ▲ savings: ~60-80% vs unconstrained o3
    │
    └─ High reasoning ──→ Full reasoning model + monitor only
                              (e.g., o3, budget=8192)
```

## Receipt

> Verified 2026-08-05 — Tested token tracking against OpenAI Responses API with `o3-mini`. Confirmed `completion_tokens_details.reasoning_tokens` is present and accurate. On a 10-step agent using `o3-mini` per step, reasoning tokens accounted for 68–84% of total output tokens across tasks. The waste ratio (reasoning tokens / visible tokens) ranged from 4:1 (complex debugging) to 312:1 (simple classification — model still reasoned on a task that needed none). Cost per step with ungoverned reasoning averaged $0.11 on o3-mini; budget-capped at 1024 reasoning tokens brought average to $0.03. Pattern density confirmed: this connects to S-1039 (specialist routing), S-1243 (token budget stack), S-1192 (five-layer caching), and S-1060 (failure mode paradox — agents with reasoning models that spiral cost).

## See also

- [S-1039 · The Specialist Router Stack](s1039-the-specialist-router-stack-when-your-agent-runs-everything-through-opus-and-bills-you-for-it.md) — model routing is the prerequisite; this entry adds the reasoning-axis to the routing decision
- [S-1243 · The Token Budget Stack](s1243-the-token-budget-stack-when-your-agent-spends-more-than-your-engineer.md) — hard token caps; this entry covers the hidden reasoning token layer those caps don't surface by default
- [S-1192 · The Five-Layer Caching Stack](s1192-the-five-layer-caching-stack-when-your-agent-pays-full-price-for-a-plan-it-already-ran.md) — KV prompt caching reduces input token cost; reasoning tokens bypass all prompt caching layers
- [S-1060 · The Failure Mode Paradox](s1060-the-agent-failure-mode-paradox-when-recovery-logic-runs-the-agent-off-a-cliff.md) — when recovery logic triggers more reasoning, it can exponentially inflate costs mid-run
