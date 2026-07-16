# S-1039 · The Specialist Router Stack — When Your Agent Runs Everything Through Opus and Bills You for It

You have a 40% cost reduction on the table. A pool of specialized models — Haiku for classification, Sonnet for code, Opus for hard reasoning — each at 10–85% the cost of your current all-frontier setup. But your agent routes nothing. Every request, from "categorize this email" to "reason through this contract edge case," hits the same $30/M-token frontier model. The reason isn't technical complexity. It's that nobody built the routing logic that sits inside the agent's execution loop. This is the **specialist router stack** — and the router is not a gateway, it's a first-class part of your agent.

## Forces

- **The cost-quality surface is non-uniform.** Simple tasks (classification, formatting, extraction) achieve 90–95% of frontier quality on small models at 3–10% of the cost. The same small model on multi-hop reasoning tasks produces 40–60% failure rates. Static routing ignores this — it picks one model at request time and commits.
- **Agent sub-tasks have wildly different complexity within a single session.** A single agent run might decompose into: intent classification (trivial), document retrieval (moderate), legal reasoning (hard), format synthesis (moderate), final summary (trivial). A monolithic model choice optimizes for the hardest step and overpays for everything else.
- **Routing wrong is silent.** When a cheap model is assigned a task above its capability, it produces plausible-but-wrong output at speed. No error. No 500. Just bad answers that downstream steps treat as valid. Traditional observability doesn't catch this — you'd need task-specific output validation.
- **Escalation introduces latency.** Routing to a specialist and then escalating to frontier adds a round-trip. For latency-sensitive workflows, the cost saving must be weighed against the p95 latency budget. Escalation chains that cascade 3+ hops destroy the latency target entirely.
- **Confidence signals are unreliable.** LLMs are notoriously overconfident on failures and underconfident on successes. A model's self-reported confidence does not map reliably to task difficulty or output quality — especially on tasks near the model's capability boundary.

## The move

### 1. Build a complexity classifier as the routing brain

Don't route on the raw query. Classify the query's **expected complexity** before model selection.

Three reliable signals to combine:
- **Token-compressed query signature** (embedding similarity to labeled eval set): RouteLLM's BERT classifier, trained on Chatbot Arena data, maps query embeddings to model capability scores. Train your own on your specific task distribution — the domain shift from general arena data to your workload is the main source of routing regret.
- **Explicit complexity tags from task decomposition**: When your agent decomposes a task (planner-worker pattern), the decomposition output includes implicit complexity signals — number of sub-tasks, known-tool vs. novel-tool ratio, multi-hop depth. Feed these to the router.
- **Historical win-rate by task type**: Log (model, task_signature, outcome) for every routing decision. After 500+ samples, the win-rate matrix becomes the strongest signal — it captures what "hard" means for *your* specific task distribution, not the benchmark distribution.

### 2. Implement three routing strategies as first-class modes

Match the strategy to the agent's operating context:

| Strategy | Trigger | Mechanism | Savings | Best for |
|---|---|---|---|---|
| **Static tier** | Predictable, homogeneous workloads | Rule-based task-type → model mapping | 30–50% | Routing the initial dispatch before decomposition |
| **Confidence-gated escalation** | Tasks with verifiable outcomes | Small model → if confidence < threshold → escalate to frontier | 40–70% | Classification, extraction, structured output with validation available |
| **Parallel dispatch with cherry-pick** | High-stakes tasks where quality > latency | Dispatch to small + frontier simultaneously → use frontier result → log small model's outcome for training | 20–35% (small model's result still useful for eval training) | Legal analysis, contract review, technical reasoning |

Confidence-gated escalation is the highest-ROI pattern for production agents. The escalation trigger must be based on **output validation**, not self-reported confidence:
- For classification: re-query with inverted labels, check consistency
- For extraction: cross-validate extracted fields against source document
- For reasoning: ask a second model to identify flaws in the reasoning chain
- For code: execute the generated code, fail-fast on errors

### 3. Instrument the regret log — this is your training set

Routing regret is the gap between what the cheap model produced and what the frontier model would have produced. Every escalation decision is a labeled data point.

```
{ query_signature, selected_model, escalated_to, escalation_trigger,
  selected_output_quality_score, escalated_output_quality_score,
  latency_delta, cost_delta }
```

After 200+ logged escalations, retrain the router's complexity classifier on your domain-specific regret data. The open-source RouteLLM router (LMSYS/Berkeley) supports fine-tuning on custom datasets — this is the mechanism that converts production routing decisions into router improvements. Teams running this loop for 60 days report routing regret dropping from 15–20% to 4–7%.

### 4. Enforce the escalation budget — latency is a first-class constraint

Route escalation decisions into a **latency budget ledger**. Every escalation consumes budget. When the budget is exhausted, force the current model to produce its best output and stop — do not escalate further.

```
budget_remaining = latency_slo - elapsed_time
if escalation_cost > budget_remaining:
    force_best_effort_and_stop()
```

This prevents the cascade failure where a hard task triggers escalating rounds through 3+ models, each consuming latency budget, producing nothing for the user.

### 5. Use the small-model pool as a committee, not a fallback

The highest-ROI pattern for agents that can't afford quality regressions: run two specialist models in parallel on moderate-complexity tasks, and a third frontier model only when the two specialists disagree above a threshold.

```
specialist_a = dispatch(task, "haiku")  # fast, cheap
specialist_b = dispatch(task, "sonnet") # moderate cost
agreement = semantic_similarity(specialist_a.output, specialist_b.output)

if agreement < disagreement_threshold:
    frontier_result = dispatch(task, "opus")  # only if needed
    return fuse(specialist_a, specialist_b, frontier)
else:
    return specialist_a  # or specialist_b, or fused output
```

This reduces frontier model invocations by 55–75% on workloads where specialists handle most tasks, while maintaining quality via committee disagreement detection. The Scopir parallel-agent pattern (Claude + Codex + Copilot cross-check) is the same structure applied at the multi-agent level.

## Verification

Before deploying to production: run shadow mode for 2 weeks. Log every routing decision and its outcome without acting on escalations. Measure your actual regret rate before building the enforcement layer. Most teams discover their task distribution is 60–80% simple — routing those to small models is the cost win. The 20–40% complex tasks justify the infrastructure.

## Tradeoffs

- **Routing infrastructure is not free.** The router itself (BERT classifier, ~110M params) adds 10–30ms latency per routing decision. At high request volumes this is negligible; at low volumes it's a meaningful fraction of total latency.
- **The eval set for training the router requires ongoing maintenance.** As your agent's task distribution evolves (new product features, new user intents), the routing model's calibration drifts. Budget for quarterly retraining or automated online learning updates.
- **Parallel dispatch doubles cost on escalated tasks.** Cherry-pick mode is only cost-efficient when the escalation rate is below 20% of routed tasks. Above that threshold, the cost of always running frontier in parallel outweighs the occasional savings from using the specialist result.
