# S-1548 · The Reasoning Token Tax Stack — When Your Agent Quietly Spends 9× What You Budgeted

Your AI coding agent just fixed a bug. The visible response: 400 tokens. The actual bill: 3,600 tokens. You budgeted $0.01 per task. You're paying $0.09. The difference is the reasoning token tax — and it's the silent multiplier that makes agentic pipelines cost 2.3× to 8.7× more than your visible output metrics suggest. Extended thinking modes in frontier models (Claude Opus 4.6, o3, o4-mini, Gemini 2.5 Flash) generate internal chain-of-thought steps that you pay for but never see in the output.

## Forces

- **Thinking tokens are output tokens at output rates.** Anthropic, OpenAI, and Google all bill extended reasoning as output tokens — the most expensive tier. A 4,000-thought-token request on Claude Opus 4.6 costs $0.1125 vs $0.0125 without thinking. That's a 9× multiplier on a single call.
- **Agents amplify the tax at pipeline scale.** A 15-step agentic task triggers planning, tool selection, execution, verification, error recovery, and synthesis calls — each generating hidden reasoning tokens. A 20-call pipeline with a 4× average multiplier inflates your inference bill by 80× versus what naive token counting predicts.
- **Visible output metrics are useless for budgeting.** `completion_tokens` in API responses excludes thinking tokens. Most dashboards show you 400 tokens; the actual cost is 3,600. Teams that plan budgets from visible output overshoot by 2–9× on complex tasks.
- **The multiplier is task-dependent and invisible.** Simple bug fixes attract a 2.3× multiplier. Multi-file refactors hit 8.7×. You can't predict cost from request size alone — the model's internal reasoning depth determines the bill, not the prompt.

## The move

**Track thinking tokens explicitly.** Every major provider now exposes them:

```python
import anthropic

client = anthropic.Anthropic()

response = client.messages.create(
    model="claude-opus-4-6",
    max_tokens=4096,
    messages=[{"role": "user", "content": "Refactor the auth module across 12 files"}],
    extra_headers={"anthropic-beta": "output-100k-2025-11-13"}
)

visible_tokens = response.usage.output_tokens
thinking_tokens = response.usage.custom_tokens.get("thinking_tokens", 0)
# thinking_tokens == 28,000 on a complex refactor
# visible_tokens == 800
# You're paying for 35,600 output tokens, not 800.

effective_multiplier = (thinking_tokens + visible_tokens) / visible_tokens
# = 44.5× on this call alone
```

**Budget by task complexity tier, not by visible token count.** Establish three tiers:

| Tier | Complexity | Observed Multiplier | Budget Assumption |
|------|-----------|--------------------|------------------|
| Tier 1 | Single-turn, short response | 1.2–1.5× | `visible × 2` |
| Tier 2 | Multi-step, tool use, moderate reasoning | 2.5–5× | `visible × 5` |
| Tier 3 | Complex multi-file, deep reasoning, agentic chains | 5–9× | `visible × 10` |

**Route extended-thinking models only where the tax pays for itself.** Extended thinking adds $0.03–$0.035 per 1K thought tokens on Claude Opus 4.6. For Tier 1 tasks where a fast model suffices, routing to Haiku or Flash cuts cost 40–60× and often matches quality. Reserve extended-thinking models for tasks where the hidden reasoning quality delta translates to downstream savings (fewer retries, fewer failed builds, fewer escalations).

**Enforce per-task token budgets as cost gates.** Set `max_tokens` conservatively — not as a quality ceiling, but as a cost ceiling. A 128K output token budget with a 9× multiplier on a complex agent task can reach $4.50 per call. A 4K budget caps it at $0.15:

```python
def call_with_cost_cap(
    client, prompt, 
    max_visible_tokens=2048,
    max_reasoning_multiplier=8.0,  # conservative estimate
    cost_per_1k_output=0.015      # your effective rate
):
    max_total_output = int(max_visible_tokens * max_reasoning_multiplier)
    max_cost = (max_total_output / 1000) * cost_per_1k_output
    
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=max_visible_tokens,
        messages=[{"role": "user", "content": prompt}],
        extra_headers={"anthropic-beta": "output-100k-2025-11-13"}
    )
    
    actual_output = response.usage.output_tokens
    actual_cost = (actual_output / 1000) * cost_per_1k_output
    
    if actual_cost > max_cost * 1.1:  # 10% grace
        log.warning(f"Token tax breach: {actual_output} tokens = ${actual_cost:.4f}")
    
    return response
```

**Separate thinking token costs in dashboards.** Route `thinking_tokens` and `visible_output_tokens` to separate metrics in your observability platform. Aggregate by tier, model, and task type monthly. The teams that discover they have a cost problem are the ones who can see the tax — everyone else gets surprised by the bill.

## Receipt

> Verified 2026-07-23 — AgentMarketCap (April 24, 2026) reported 2.3×–8.7× reasoning token multipliers across Claude Opus 4.6, o3, and Gemini 2.5 Flash on coding agent tasks. Simple bug fixes: 2.3×; multi-file refactors: 8.7×. Anthropic confirmed thinking tokens are billed as output tokens in API documentation. The `output-100k-2025-11-13` beta header exposes `thinking_tokens` in response usage for Claude. OpenAI's `o1`/`o3` family exposes reasoning tokens via `completion_tokens_details.reasoning_tokens`. Google Vertex exposes via `生ai-extension metadata`.

## See also

- [S-1472 · The Compounding Reliability Stack](s1472-the-compounding-reliability-stack-when-99-percent-is-not-99-percent-of-your-problem.md) — Lusser's Law means a 9× cost multiplier on a 15-step pipeline compounds: every step pays the tax again
- [S-1239 · The Runtime Verification Loop](s1239-the-runtime-verification-loop-when-your-agent-step-looks-okay-but-isnt.md) — runtime gates catch tax overruns mid-pipeline before the full bill accrues
- [S-1158 · The Adaptive Compute Stack](s1158-the-adaptive-compute-stack-when-you-rout-every-query-through-a-gpt4-pipeline.md) — adaptive routing based on query complexity is precisely where the reasoning token tax lives: Tier 1 tasks routed to expensive reasoning models pay the full tax for zero benefit
- [S-08 · Prompt Caching](s08-prompt-caching.md) — caching reduces visible input costs but does nothing for the thinking token tax, which is pure output billing
