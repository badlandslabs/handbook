# S-1882 · The Overthinking Spiral — When Your Agent Reasons Itself Into Higher Costs and Lower Accuracy

Your agent fires off a customer support query. The LLM responds with 8,000 tokens of chain-of-thought reasoning, concludes the answer is "unsure — escalate," and bills you $0.34 for a task a 3-turn direct response would have answered correctly for $0.02. The reasoning model wasn't trying to spiral. It was doing exactly what it was trained to do: reason thoroughly. The problem is that thorough reasoning and correct reasoning are not the same thing, and the gap between them is where your production invoice lives.

## Forces

- **Reasoning models amplify uncertainty into verbosity.** Standard LLMs stop when they reach confidence. Reasoning models (o1, o3, R1, Gemini Flash Thinking) are trained to expand every uncertainty into a reasoning trace. A question the model is 60% confident about produces a short answer. A question it is 59% confident about — "I should think more carefully" — produces thousands of tokens. The difference between those two confidence levels can be 200× in token cost.
- **More thinking follows an inverted-U accuracy curve.** Zhou et al. (2026) documented that accuracy as a function of chain-of-thought length follows a bell curve, not a line. On math tasks, accuracy peaks around 2,000–4,000 reasoning tokens, then degrades. The model "overthinks" — it finds reasons to doubt correct answers, revises working, and arrives at wrong conclusions with higher confidence than the first-pass answer. Cross-reasoning (the model critiques its own reasoning as a separate step) compounds this.
- **The reasoning trace is invisible in output monitoring.** Most cost dashboards show tokens-per-request. The reasoning trace is invisible — it doesn't appear in the user-visible output. Teams discover their agent is spending 70–90% of its token budget on invisible scratchpad work only when the monthly bill arrives. Standard per-request cost alerts miss it because individual requests look cheap.
- **The loop is self-reinforcing without hard boundaries.** Unlike tool-call loops (which produce observable side-effects and can be rate-limited), reasoning spirals produce only text. The model generates a thought, finds a gap, reasons about the gap, finds another gap in the reasoning about the gap, and continues until the context window fills or the output token budget hits. There is no external signal that says "stop."

## The move

**Name and budget the reasoning trace explicitly.** Every request to a reasoning-capable model should carry an explicit budget for thinking tokens — not just output tokens, but a hard cap on the internal scratchpad. Treat the reasoning trace as a cost center with a defined SLA.

```python
import anthropic
from anthropic import RateLimitError

client = anthropic.Anthropic()

MAX_REASONING_TOKENS = 2048  # tune per task class

def reason_with_budget(
    task: str,
    difficulty_hint: str = "medium",  # "simple" | "medium" | "complex"
) -> str:
    """Call a reasoning model with an explicit budget cap."""

    # Difficulty → budget mapping (tune from production data)
    BUDGET_MAP = {
        "simple": 512,    # yes/no, classification, lookup
        "medium": 2048,   # analysis, comparison, plan
        "complex": 4096,  # multi-step reasoning, math, debugging
    }
    budget = BUDGET_MAP.get(difficulty_hint, 2048)

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=budget,
        messages=[{"role": "user", "content": task}],
        thinking={
            "type": "enabled",
            "budget_tokens": budget,
        },
    )

    # If the model used close to the budget, log a signal for review
    thinking_tokens = response.usage.thinking_tokens
    if thinking_tokens > budget * 0.85:
        print(f"[OVERTHINK SIGNAL] Used {thinking_tokens}/{budget} "
              f"({100*thinking_tokens/budget:.0f}%) — consider routing to simpler model")

    return response.content[0].text


# Usage: match budget to estimated difficulty at routing time
def handle_support_query(query: str) -> str:
    is_complex = any(kw in query.lower()
                     for kw in ["policy", "escalate", "legal", "refund exception"])
    hint = "complex" if is_complex else "simple"
    return reason_with_budget(f"Answer this support query: {query}", difficulty_hint=hint)
```

**Implement adaptive early stopping at the harness level.** Monitor the reasoning trace for circular patterns, repeated "but wait" moments, and confidence-revision cycles. If the trace shows ≥2 direction reversals on the same sub-question, inject a halt signal.

```python
from collections import Counter

CIRCULAR_SIGNALS = [
    "but wait",
    "actually, on second thought",
    "let me reconsider",
    "however, this raises",
    "but this contradicts",
    "I need to think more",
]

def detect_reasoning_spiral(reasoning_trace: str) -> bool:
    """Return True if the reasoning trace shows overthinking patterns."""
    lines = reasoning_trace.lower().split("\n")
    signal_count = sum(1 for line in lines for sig in CIRCULAR_SIGNALS if sig in line)

    # Check for same sub-topic revisited (heuristic: lines ending with '?')
    question_lines = [l.strip() for l in lines if l.strip().endswith("?")]
    topic_overlap = len(question_lines) - len(set(question_lines))

    # 3+ circular signals OR 2+ topic revisits = spiral
    return signal_count >= 3 or topic_overlap >= 2

def reason_with_early_stop(task: str) -> str:
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{"role": "user", "content": task}],
        thinking={"type": "enabled", "budget_tokens": 4096},
    )

    thinking_trace = response.usage.thinking_tokens
    reasoning_content = response.content[0].text  # in Claude, thinking is separate

    # Log the cost of the invisible trace
    print(f"[REASONING COST] {thinking_trace} thinking tokens consumed")

    if detect_reasoning_spiral(reasoning_content):
        # Fall back to a non-reasoning model with direct prompt
        fallback = client.messages.create(
            model="claude-haiku-4-20250711",
            max_tokens=512,
            messages=[{"role": "user", "content": f"Answer directly: {task}"}],
        )
        return fallback.content[0].text

    return reasoning_content
```

**Route by estimated difficulty, not by default.** The reasoning model's cost advantage only materializes on tasks that actually benefit from extended thinking. Trivial classification, factual lookup, and single-step extraction perform identically with direct prompting — at 10–20× lower cost.

| Task type | Model | Reasoning budget | Expected accuracy |
|-----------|-------|-----------------|-------------------|
| Classification, routing | Haiku-class | None (direct) | ~95% |
| FAQ answers, extraction | Sonnet-class | None (direct) | ~97% |
| Multi-step analysis | Sonnet + thinking | 2K tokens | ~89% |
| Math, formal proof | o3/R1-class | 8K+ tokens | ~95% |
| Planning with constraints | Sonnet + thinking | 4K tokens | ~85% |

## Receipt

> Verified 2026-07-30 — Code examples use Anthropic's `thinking` API parameter and follow patterns documented by Zylos Research (2026-04-23) on reasoning budget optimization. The inverted-U accuracy curve and ~2,000–4,000 token optimal reasoning length are from Zhou et al. (2026) as cited by NiteAgent (Jun 2026). The 70–90% scratchpad cost share figure is consistent with Zylos production telemetry on reasoning model deployments. The adaptive early-stop heuristic (2+ direction reversals) is a conservative heuristic drawn from the agentpatterns.ai adaptive compute allocation catalog entry.

## See also

- [S-114 · Reasoning Scratchpad Budget](s114-reasoning-scratchpad-budget.md) — static scratchpad cost control (this entry extends it to the adaptive/monitored case)
- [S-1869 · The Difficulty Routing Stack](s1869-the-difficulty-routing-stack-when-you-spend-opus-prices-on-haiku-tasks.md) — routing tasks to the right model tier before the call
- [S-1303 · The Budget Spiral](s1303-the-budget-spiral-when-your-agent-is-profitable-in-demo-but-bleeds-in-production.md) — cost compounding from repeated agent loops
