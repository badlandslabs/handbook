# S-1869 · The Difficulty Routing Stack — When You Spend Opus Prices on Haiku Tasks

Your agent pipeline routes every request to your best model. The invoices are brutal. Then you discover that 60% of your tasks were answerable by a model 12× cheaper — and you had no way to know which 60% at routing time.

The fix is difficulty-aware orchestration: classify each task's complexity before routing, then match it to the minimum sufficient pipeline.

## Forces

- **The cost-quality crossover is task-specific.** AIME math needs high reasoning effort (+22pts). PR-scale code review wins at low effort. Expert-SWE refactoring peaks at medium. Blindly using high effort across all tasks wastes 4–17× the cost per correct answer (Digital Applied, 900-task benchmark, 2026).
- **Static routing is still the default.** Most production agents hardcode a single model for all tasks. The 40–85% cost reduction from intelligent routing is real but under-adopted because the difficulty estimation problem wasn't solved.
- **Difficulty is not the same as complexity.** A 10,000-line codebase review can be low-difficulty (just find syntax errors) while a one-line refactoring request can be high-difficulty (what are the downstream dependencies?). Task complexity and difficulty diverge in non-obvious ways.
- **Routing quality depends on what you know at routing time.** You can't run the task to know how hard it is. Difficulty estimation must use features available before the LLM call: query text, user history, tool signatures, and schema complexity.

## The move

Three cascading decisions, each informed by the difficulty estimate:

### 1. Classify difficulty (pre-call)

Use a lightweight classifier (DistilBERT, 12M params, ~1ms latency) on the incoming request. Extract features:

```python
# Difficulty classifier using lightweight model
class DifficultyEstimator:
    """12M-param classifier. Trained on historical task outcomes + cost labels."""
    DIFFICULTY_LEVELS = ["lookup", "factual", "procedural", "reasoned", "creative"]

    def estimate(self, request: dict) -> str:
        features = self.extract_features(request)
        # Features: query length, entity count, temporal markers,
        # tool count, context length, historical success rate for task type
        embedding = self.embedding_model.encode(features)
        return self.classifier.predict(embedding)

    def extract_features(self, request: dict) -> dict:
        return {
            "token_count": len(request["query"].split()),
            "named_entities": count_named_entities(request["query"]),
            "has_temporal": has_temporal_marker(request["query"]),
            "tool_arity": len(request.get("available_tools", [])),
            "context_length": request.get("context_tokens", 0),
            "historical_success_rate": self.task_history.get(request["type"], 0.85),
        }
```

Alternative: **heuristic difficulty proxy** (no training required):
- `lookup`: single entity, <5 tokens, no temporal → route to fast model
- `factual`: entities + relations, no sub-problems → light model
- `procedural`: numbered steps, "how to" → medium model
- `reasoned`: "why", "implications", multi-constraint → strong model
- `creative`: open-ended, no ground truth → strong model + extended output

### 2. Route by difficulty tier

| Difficulty | Model Tier | Reasoning Mode | Tool Depth |
|---|---|---|---|
| lookup / factual | Fast model (Haiku-class) | None | Single call |
| procedural | Medium model (Sonnet-class) | Minimal | 1–2 tool calls |
| reasoned | Strong model (Opus-class) | Full CoT | Full tool access |
| creative | Strong model + large output | Full CoT | Research + draft loop |

```python
def route(request: dict) -> AgentConfig:
    difficulty = difficulty_estimator.estimate(request)

    routing_table = {
        "lookup":     {"model": "fast",   "tools": ["search"],           "steps": 1},
        "factual":    {"model": "medium", "tools": ["search", "lookup"], "steps": 2},
        "procedural": {"model": "medium", "tools": ["*"],               "steps": 3},
        "reasoned":   {"model": "strong", "tools": ["*"],               "steps": 10},
        "creative":   {"model": "strong", "tools": ["*"],               "steps": 15},
    }
    return AgentConfig(**routing_table[difficulty])
```

### 3. Match pipeline depth to difficulty

The arXiv:2509.11079 DAAO paper (Difficulty-Aware Agent Orchestration) shows that varying pipeline depth per query — not just model tier — compounds the gains:

- **Modular operator selection**: attach different agent operators based on difficulty. Lookup tasks need a retrieval operator. Reasoning tasks need a decomposition + verification chain. The same model operating on a deeper pipeline outperforms a stronger model on a shallow pipeline at lower cost.
- **11.21% accuracy improvement** over static single-pipeline systems, at 64% of the cost — by matching pipeline depth to query difficulty.
- **AgentRouter** (12M-param classifier, arXiv:2605.07112) uses correctness probability as the routing signal: predict which models will answer correctly, then pick the cheapest among those predicted-correct. This directly maximizes cost-per-correct-answer rather than accuracy alone.

### Water-filling token allocation (arXiv:2605.23929)

For multi-step workflows, distribute the reasoning budget across steps proportionally to each step's difficulty:

```python
def waterfill_token_budget(total_budget: int, step_difficulties: list[float]) -> list[int]:
    """Allocate token budgets across steps using water-filling.
    Higher difficulty steps get proportionally more tokens."""
    total = sum(step_difficulties)
    return [int(total_budget * d / total) for d in step_difficulties]
```

## Key insight: cost-per-correct-answer

The right metric is not accuracy, not cost-per-token, but **cost-per-correct-answer**. A task that costs $0.001 but fails 40% of the time costs $0.0017 per success. A task that costs $0.01 but succeeds 99% of the time costs $0.0101 per success. The expensive model is cheaper per outcome on hard tasks.

Map your task distribution first. Then find your crossover points.

## Receipt

> Receipt pending — 2026-07-30

## See also

- [S-06 · Model Routing](s06-model-routing.md) — static routing table basics
- [S-857 · The Test-Time Compute Budget Stack](s857-the-test-time-compute-budget-stack-when-your-agent-thinks-too-much-and-costs-too-much.md) — internal reasoning budget, not task-level difficulty routing
- [S-1865 · The Scaffold-First Fallacy](s1865-the-scaffold-first-fallacy-when-a-model-upgrade-costs-less-than-a-harness-fix.md) — distinguish harness contribution from model contribution before routing decisions
