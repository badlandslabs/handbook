# S-1890 · The Difficulty-Aware Escalation Stack — When Static Tiers Hit Their Ceiling

You built the routing layer: rule-based, four tiers, maps intent to model. Cost dropped 40%. Then you found the silent killer — your "simple" classifier routing bucket is sending genuinely hard queries to Haiku 4.5, which returns plausible-sounding wrong answers that pass your syntax checks. Your "complex" bucket is routing 60% of queries to Opus 4.8 when Sonnet 4.6 would have been sufficient. Your tier boundaries were set by intuition, not data. This is where static routing hits its ceiling and difficulty-aware escalation takes over.

The distinction that changes everything: **difficulty-aware routing estimates the cost of being wrong, not just the cost of inference.** A cheap model on a high-stakes task is more expensive than an expensive model on a cheap task — you just pay the bill later, in errors.

## Forces

- **Static tiers have brittle boundaries.** Rule-based routing works when intent maps cleanly to complexity — which is rarer than it looks. A "change my password" intent might be trivially hard or involve federated identity, MFA, compliance attestation, and cross-region replication. The same intent, wildly different difficulty.
- **Perplexity and token count are bad proxies for difficulty.** You can't reliably estimate task difficulty from surface features. A 10-word math word problem is harder than a 200-word summary request. A short SQL question may require a schema-aware model; a long creative brief may need only Haiku.
- **The routing accuracy requirement is asymmetric.** Misrouting a hard task to a cheap model (false negative) is worse than misrouting an easy task to a frontier model (false positive). Most routing systems optimize for cost, not error cost.
- **Routing collapse is a real failure mode.** Learned routers trained on binary strong/weak preferences tend to drift toward one model, especially on ambiguous queries. EquiRouter (2025) showed 17% cost reduction but requires supervised ranking to prevent collapse.

## The move

**Build a difficulty estimator that feeds a cascade: try cheap → escalate if uncertain → stop at sufficient.**

### 1. The Difficulty Estimator (3 signals)

Don't use one signal. Combine three orthogonal estimators:

```python
import anthropic
import openai
from sklearn.linear_model import LogisticRegression
from collections import deque
import numpy as np

class DifficultyEstimator:
    """Three-signal difficulty estimation for cascade routing."""

    def __init__(self, router_model="haiku-4.5"):
        self.client_haiku = openai.Client()
        self.router_model = router_model
        self.history = deque(maxlen=500)  # outcome-labeled routing pairs

    def estimate(self, prompt: str) -> dict:
        # Signal 1: LLM-based difficulty classification
        difficulty = self._llm_classify(prompt)

        # Signal 2: Semantic complexity via embedding divergence
        complexity = self._embedding_complexity(prompt)

        # Signal 3: Historical accuracy for similar prompts
        historical = self._historical_accuracy(prompt)

        return {
            "difficulty": difficulty,      # 0.0–1.0
            "complexity": complexity,      # 0.0–1.0
            "historical_confidence": historical,  # 0.0–1.0
            "composite": (difficulty * 0.5 + complexity * 0.3 +
                          (1 - historical) * 0.2)
        }

    def _llm_classify(self, prompt: str) -> float:
        """Use a small model to rate difficulty 0–10, then normalize."""
        system = """Rate the difficulty of this task 0–10:
0-2: Fact retrieval, formatting, classification, extraction
3-4: Simple Q&A, summarization, rewrite
5-6: Multi-step reasoning, code generation, comparison
7-8: Complex multi-domain analysis, ambiguous requirements
9-10: Novel reasoning, multi-hop inference, research synthesis
Reply with only the number."""
        resp = self.client_haiku.chat.completions.create(
            model=self.router_model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": prompt}],
            max_tokens=4,
            temperature=0
        )
        return float(resp.choices[0].message.content.strip()) / 10.0

    def _embedding_complexity(self, prompt: str) -> float:
        """Embedding variance as a proxy for multi-concept complexity."""
        # Use sentence-level embeddings; high variance = multi-concept
        emb = self._embed(prompt)
        return float(np.std(emb))

    def _historical_accuracy(self, prompt: str) -> float:
        """Look up outcome rate for prompts with cosine similarity > 0.85."""
        similar = [h for h in self.history
                   if cosine_sim(self._embed(prompt), self._embed(h["prompt"])) > 0.85]
        if not similar:
            return 1.0  # no data → assume average
        return np.mean([h["success"] for h in similar])

    def record_outcome(self, prompt: str, model: str, success: bool,
                       escalated: bool):
        self.history.append({
            "prompt": prompt, "model": model,
            "success": success, "escalated": escalated
        })

    def _embed(self, text: str) -> np.ndarray:
        # placeholder — use your embedding provider
        return np.random.randn(1536)
```

### 2. The Cascade Router

```python
TIERS = [
    {"name": "fast", "model": "haiku-4.5", "max_difficulty": 0.35},
    {"name": "medium", "model": "sonnet-4.6", "max_difficulty": 0.65},
    {"name": "strong", "model": "gpt-4.5", "max_difficulty": 0.90},
    {"name": "frontier", "model": "opus-4.8", "max_difficulty": 1.00},
]

def route_cascade(prompt: str, estimator: DifficultyEstimator,
                  min_success_confidence: float = 0.85) -> str:
    """
    Route with escalation: start cheap, stop when confident enough.
    Falls back to stronger model if output fails a quick sanity check.
    """
    difficulty = estimator.estimate(prompt)
    target_tier = next(
        (t for t in TIERS if difficulty["composite"] <= t["max_difficulty"]),
        TIERS[-1]
    )

    # Cascade: try the selected tier, escalate on signal
    for tier in TIERS[TIERS.index(target_tier):]:
        response = call_model(tier["model"], prompt)

        # Lightweight sanity gate — catches obvious failures cheaply
        if tier["name"] != "frontier":
            gate_pass = sanity_check(prompt, response, difficulty["composite"])
            if gate_pass:
                estimator.record_outcome(prompt, tier["model"],
                                        success=True, escalated=False)
                return response
            # Failed sanity — escalate
            estimator.record_outcome(prompt, tier["model"],
                                    success=False, escalated=True)
            continue

        # Frontier tier: no further escalation
        estimator.record_outcome(prompt, tier["model"],
                                success=True, escalated=False)
        return response

def sanity_check(prompt: str, response: str, difficulty: float) -> bool:
    """Fast gate before escalating. Tuned for difficulty level."""
    # Check 1: output length sanity
    if len(response) < 10:
        return False

    # Check 2: uncertainty markers (higher bar for harder tasks)
    uncertainty_threshold = 0.3 if difficulty < 0.5 else 0.15
    if uncertainty_threshold > 0:
        uncertainty_ratio = _count_uncertainty_markers(response) / max(len(response), 1)
        if uncertainty_ratio < uncertainty_threshold and difficulty > 0.5:
            return False  # too confident for hard task → might be hallucinating

    return True

def _count_uncertainty_markers(text: str) -> int:
    markers = ["i'm not sure", "could be", "may not", "unclear",
               "cannot determine", "might not", "uncertain"]
    return sum(1 for m in markers if m.lower() in text.lower())
```

### 3. Routing Accuracy: The Asymmetric Loss Function

Standard routing optimizes for correct/incorrect. Production routing needs asymmetric loss:

```python
def routing_loss(true_model: str, predicted_model: str,
                 stakes: float = 1.0) -> float:
    """
    Asymmetric loss: under-routing (cheaper model on hard task) is 4×
    more expensive than over-routing (expensive model on easy task).
    """
    under_route = predicted_model in ["haiku-4.5", "sonnet-4.6"] and \
                  true_model in ["gpt-4.5", "opus-4.8"]
    over_route = predicted_model in ["gpt-4.5", "opus-4.8"] and \
                  true_model in ["haiku-4.5", "sonnet-4.6"]

    if under_route:
        return stakes * 4.0   # wrong answer is expensive
    elif over_route:
        return 0.25           # wasted cost, not a failure
    else:
        return 0.0             # correct tier
```

### 4. Monitoring: The Routing Audit Trail

```python
# After each request, log for the closed loop
router_metrics.record(
    request_id=request_id,
    difficulty_estimate=difficulty["composite"],
    routed_tier=tier["name"],
    actual_outcome="success" if passed else "escalated",
    escalated_from=tier["name"] if escalated else None,
    tokens_spent=token_count,
    latency_ms=latency
)

# Key dashboard metrics:
# - Escalation rate per tier (should be < 10% for fast tier)
# - Per-tier accuracy (model's actual success on routed tasks)
# - Difficulty estimate calibration (was the estimate right?)
# - Cost per successful task (not just cost per request)
```

## Receipt

> Verified 2026-07-30 — Key findings from Zylos Research (2026-01-29), dasroot.net multi-model routing analysis (2026-03-12), BEST-Route (Ding et al. 2025), RouteLLM (LMSYS/Berkeley): Learned routers (DeBERTa-based classifiers, GPT-4-as-judge preference data) achieve 85% cost reduction at 95% quality vs. GPT-4-only baselines. EquiRouter's supervised ranking prevents routing collapse, a failure mode absent from naive binary preference training. Cascade routing (fast → escalate on uncertainty) reduces average cost by 30–40% vs. single-tier routing on mixed-difficulty workloads. Best-of-N sampling compounds with routing: routing to fast model + 3 samples can match frontier quality at 20% of cost for extractive tasks.

## See also

- [S-06 · Model Routing](s06-model-routing.md) — Static tiering foundations (predecessor)
- [S-1802 · The Reasoning Budget Control Stack](s1802-the-reasoning-budget-control-stack-when-thinking-too-hard-costs-too-much.md) — Reasoning cost management; works synergistically with escalation routing
- [S-114 · Context Budget](s114-context-budget.md) — Static vs. adaptive budget thinking; the difficulty estimator is the adaptive version for model selection
