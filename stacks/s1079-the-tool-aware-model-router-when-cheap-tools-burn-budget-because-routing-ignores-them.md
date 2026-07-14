# S-1079 · The Tool-Aware Model Router — When Cheap Tools Burn Budget Because Routing Ignores Them

Your agent routes queries to models by difficulty. Hard tasks go to Opus. Easy tasks go to Haiku. Token costs drop 50%. You celebrate. Then you notice the bill barely moved. The problem: difficulty-based routing ignores *what the agent actually does*. A "easy" classification task that calls a 2,000-token API tool costs more than a "hard" reasoning task that calls a 10-token calculator. Tool token cost dwarfs LLM inference cost on most production agent tasks — but your router never sees it.

## Forces

- **Tool cost dwarfs model cost in most production agents.** A single tool call can emit 10× the tokens of the LLM prompt that generated it. A difficulty-based router optimizes the wrong variable.
- **Cheap-model-on-hard-task produces fluent wrong output.** When a weak model gets a complex tool-selection decision wrong, it returns a plausible but incorrect call. Downstream catches nothing — the failure is syntactically valid and semantically wrong.
- **Chat routers fail tool tasks.** Switchcraft (Microsoft Research, 2026) found that chat-optimized routers systematically misroute tool-calling queries — they optimize for response quality on non-tool tasks, making them a poor fit for agentic pipelines.
- **Token-intensive reasoning hides the real cost.** Nominally cheaper models can produce longer reasoning chains that cost *more* total than a frontier model on the same tool task. Total cost-per-task (model + tool) is the right unit, not model cost alone.
- **Tool complexity varies within a task.** The same agent, on the same task, may call a simple lookup tool (routing can use a cheap model) followed by a complex synthesis tool (needs frontier). Per-call routing — not per-request routing — is needed.

## The move

**Build a tool-aware model router.** Instead of routing by query difficulty alone, route by the specific tool being called, the cumulative token budget for this step, and the consequence of a wrong call.

### Step 1 — Instrument your tool call costs

Before you can route, you need to know what tools actually cost. For every tool in your agent's belt, collect:

| Metric | What it measures |
|---|---|
| **Mean input tokens** | How many tokens the LLM typically sends to this tool |
| **Mean output tokens** | How many tokens the tool response typically returns |
| **Mean round-trip latency** | Wall-clock time including model + tool + context update |
| **Error rate** | Fraction of calls that fail, timeout, or return degraded output |
| **Consequence severity** | What happens if this call is wrong: no-op / degraded output / data corruption / irreversible action |

Tag each tool with a `cost_tier` (A/B/C/D) and a `consequence_level` (low/medium/high/critical).

### Step 2 — Route by tool tier, not query difficulty

Train or configure a lightweight router (DistilBERT classifier works — Switchcraft used 66M params) that classifies incoming tool-calling decisions by:

1. **Tool identity** — which tool is the agent selecting, and what's its cost tier?
2. **Argument complexity** — how many parameters are being set? Are they simple literals or complex nested structures?
3. **Consequence level** — what's the downside of a wrong call?

Route to:

| Route | Model examples | Use when |
|---|---|---|
| **Nano** | Haiku, GPT-4o-mini, Gemini Flash-Lite | Low-consequence tools, simple parameters (<5 args, all primitives), low token output |
| **Mid** | Sonnet 4.6, GPT-4o | Medium-consequence tools, moderate parameter complexity, <500 token output |
| **Frontier** | Opus 4.8, GPT-5 | High/critical consequence tools, complex nested parameters, high token output |

### Step 3 — Budget-gate the routing decision

Before committing to a route, check two gates:

**Total cost gate:** Estimate `model_cost + tool_input_tokens * model_rate + tool_output_tokens * output_rate`. If the estimated total exceeds the task's budget allocation for this step, escalate to the next tier up.

**Consequence gate:** For critical-consequence tools (data deletion, payment, user-facing content), ignore the router entirely and always use frontier. No routing savings are worth a wrong call on a `delete_record` or `send_email` action.

### Step 4 — Monitor misrouting rate, not just cost

A bad router "saves" by sending hard tasks to cheap models — the cost goes down, quality goes down more. Track:

- **Mispatch rate per tool:** fraction of calls to this tool that produced degraded output (wrong tool selected, wrong parameters, invalid call)
- **Per-tool pass@k:** for tool calls that failed initially, did k retries with the same or upgraded model recover? Track this per tool type, not globally
- **Total cost-per-successful-task:** the only metric that matters. If routing saves $0.10 per task but increases the failure rate by 5%, you lost money on remediation

### Step 5 — Re-route on uncertainty, not just on cost

When a nano/mid model returns a response with low-confidence signals (low logprob, short output on an expected-long response, missing expected fields), re-route to the next tier *before* the agent acts on the response. This is the cascade breaker — it catches the fluent-wrong failure mode that simple cost routing misses.

## Evidence

- **Switchcraft (Microsoft Research, arXiv:2605.09121, May 2026):** DistilBERT router achieves 82.9% accuracy on tool-calling benchmarks, matching GPT-5.3-chat (82.3%) while reducing inference cost 84% — $3,600 savings per million queries. Closes 37% of the oracle gap. Key finding: larger models do not consistently outperform smaller models on tool tasks, and nominally cheaper models can incur higher total cost due to token-intensive reasoning.
- **Key insight:** Existing chat-optimized routers fail tool tasks because they optimize for the wrong distribution. Tool-specific routing requires tool-call-specific training data and feature engineering.
- **Router latency:** 3–17ms P99 on NVIDIA T4 (Switchcraft) — negligible compared to model inference time, confirming the router overhead is a non-issue in practice.
- **Misrouting is silent.** Unlike a bad model response (which is often obviously wrong), a misrouted tool call often returns valid-looking but wrong data. Detection requires output validation, not just call monitoring.

## Variants

**Phase-aware routing.** In a multi-step agent pipeline, early steps (tool selection, argument construction) are more routable to cheap models than late steps (synthesis, judgment, user-facing output). Route differently by step position, not just by tool.

**Team-specific router.** If your agent serves multiple teams with different tool sets, train separate routers per team. The routing distribution for a code-search tool is different from a customer-support lookup tool.

**Cost-cap hybrid.** Set a maximum acceptable cost per task, then route to maximize quality within that budget. This is the right framing for agents with per-task cost SLAs.

## Receipt

> Verified 2026-07-14 — arXiv:2605.09121 (Switchcraft, Microsoft Research, May 2026) extracted; Zylos Research AI Agent Model Routing (2026-03-02) reviewed; handbook S-06 (Model Routing) confirmed as general-purpose routing with no tool-specific treatment; S-361 (Agent Stack Stratification) checked for routing layer placement; S-1076 (Failure Recovery Stack) confirmed as complementary (routing prevents, recovery handles). No duplicate entry found. Actual output: S-1079 written to stacks/.

## See also

- [S-06 · Model Routing](s06-model-routing.md) — generic model routing foundation; this entry extends it to the tool-specific layer
- [S-1076 · The Agent Failure Recovery Stack](s1076-the-agent-failure-recovery-stack-when-your-agent-loops-forever-or-worse.md) — recovery when routing decisions go wrong
- [S-362 · Budget-Aware Agents](s362-budget-aware-agents-cost-as-a-first-class-behavioral-dimension.md) — cost as behavioral dimension; this entry provides the per-tool routing mechanism that makes budget awareness operational
