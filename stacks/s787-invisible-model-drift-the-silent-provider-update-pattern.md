# S-787 · Invisible Model Drift: The Silent Provider Update Pattern

[Your agent worked perfectly on Monday. On Wednesday, JSON parsing breaks silently, response lengths shift, and the classifier accuracy drops from 94% to 79%. You haven't deployed anything. The model name is identical. But the behavior changed — because the provider updated the model underneath without announcement. This is the new operational reality of AI infrastructure: your dependencies can change between API calls with zero versioning guarantee.]

## Forces

- **LLM providers don't offer npm-style versioning.** `npm install express@4.18.2` pins a specific binary forever. `model = "claude-sonnet-4-20250514"` pins a *name*, not a behavior. Providers update the underlying model continuously — sometimes breaking, sometimes improving — and communicate nothing.
- **The April 2026 incident made this visceral.** Anthropic removed the ability to pin specific Claude model versions. Developers using `claude-sonnet-4-5` were silently migrated to `claude-sonnet-4-6`. Downstream pipelines broke — JSON schemas rejected output that had worked for weeks, format compliance dropped, downstream parsers threw exceptions. The HN thread filled with baffled engineers who had done everything right.
- **GPT-4 accuracy on a specific task dropped from 84% to 51% between March and June 2023 without version change** (Stanford/UC Berkeley study). The model name was identical. No communication. Teams had no explanation for the sudden regression.
- **Behavioral change without code change is the hardest failure to detect.** Traditional software breaks visibly — a deployment fails, a test suite catches it, a circuit breaker trips. Invisible model drift produces wrong answers that look correct, passed assertions that now miss real failures, and canaries that cross without anyone noticing.
- **You can't version-lock your way out.** Even when pinning works, providers deprecate old versions. At some point, you're forced to migrate — and without a behavioral regression suite, you have no signal for whether the new version is safe.

## The Move

Treat model provider updates as an *implicit deployment* — and build the infrastructure to detect and survive them.

### 1. Behavioral Canaries (Detect)

Before any code change, instrument a probe suite that exercises your agent's critical paths:

```python
import anthropic
from datetime import datetime

class ModelDriftCanary:
    """Lightweight behavioral smoke test run on every production request batch."""

    def __init__(self, client: anthropic.Anthropic, probe_tasks: list[dict]):
        self.client = client
        self.probe_tasks = probe_tasks
        self.baseline_scores: dict[str, float] = {}
        self.baseline_hash: str = ""

    def capture_baseline(self) -> str:
        """Run probe tasks and store outputs + scores as baseline."""
        results = {}
        for task in self.probe_tasks:
            resp = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                messages=[{"role": "user", "content": task["prompt"]}]
            )
            results[task["id"]] = {
                "output": resp.content[0].text,
                "latency_ms": resp.usage.total_tokens / 1e3,  # rough proxy
            }
        self.baseline_hash = hash(str(results))
        self.baseline_scores = {
            task["id"]: task["judge"](results[task["id"]]["output"])
            for task in self.probe_tasks
        }
        return self.baseline_hash

    def check_drift(self, threshold: float = 0.05) -> dict:
        """Compare current probe scores against baseline. Returns drift report."""
        current_results = {}
        for task in self.probe_tasks:
            resp = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                messages=[{"role": "user", "content": task["prompt"]}]
            )
            current_results[task["id"]] = resp.content[0].text

        drift_report = {}
        for task in self.probe_tasks:
            current_score = task["judge"](current_results[task["id"]])
            baseline_score = self.baseline_scores[task["id"]]
            delta = baseline_score - current_score
            drift_report[task["id"]] = {
                "baseline": baseline_score,
                "current": current_score,
                "delta": delta,
                "drifted": delta > threshold,
            }

        # Aggregate signal: 3+ consecutive probe regressions = alert
        drifted_count = sum(1 for v in drift_report.values() if v["drifted"])
        return {
            "probes": drift_report,
            "alert": drifted_count >= 3,
            "avg_delta": sum(v["delta"] for v in drift_report.values()) / len(drift_report),
        }
```

Run canaries on a 1% shadow traffic split continuously. A single probe regression is noise; three trending together is a provider signal.

### 2. Output Schema Contracts (Survive)

Define strict output contracts that fail loudly when model behavior shifts:

```python
from pydantic import BaseModel, ValidationError
import json

class ExtractionContract(BaseModel):
    user_id: str
    amount: float
    currency: str

def safe_extract(raw_output: str) -> ExtractionContract:
    """Fail fast on schema drift — don't let bad outputs pass silently."""
    try:
        data = json.loads(raw_output)
        return ExtractionContract(**data)
    except (json.JSONDecodeError, ValidationError) as e:
        raise ModelDriftError(
            f"Schema contract violated. Provider may have updated model behavior. "
            f"Original error: {e}. Raw output: {raw_output[:200]}"
        )
```

A `ModelDriftError` carries the signal forward: log it, alert on it, correlate it with other teams' errors. When three teams' pipelines start throwing the same error on the same day, you've detected a provider event without any monitoring infrastructure.

### 3. Version Notification Hooks (Prepare)

Subscribe to provider changelogs even when they don't publish them. The community detects these changes first:

- Monitor your provider's status page programmatically (Cloudflare Workers + PagerDuty webhook)
- Track r/LocalLLaMA, provider-specific HN threads, and model version registries for behavioral reports
- Maintain a `#model-drift-alerts` Slack channel where practitioners post "anyone else's outputs different today?"

### 4. Cross-Provider Routing with Behavioral Parity (Resilience)

Design your gateway to route equivalent requests to two providers and diff the outputs:

```python
async def parity_check(prompt: str, primary: LLMClient, shadow: LLMClient):
    """Shadow-routing detects provider-level behavioral drift."""
    primary_out = await primary.complete(prompt)
    shadow_out = await shadow.complete(prompt)

    # Structural diff — not semantic
    primary_struct = parse_structured_output(primary_out)
    shadow_struct = parse_structured_output(shadow_out)

    if structural_diff(primary_struct, shadow_struct) > 0.2:
        logger.warning(
            f"High parity divergence: primary={primary_struct.keys()}, "
            f"shadow={shadow_struct.keys()}"
        )
        # Alert, don't block — one provider may be wrong, not drifting
```

Divergence between providers is a signal; divergence between your baseline and current provider output is confirmation.

## When to Reach for This

- You rely on a hosted model API (OpenAI, Anthropic, Google, Azure OpenAI)
- Your agent's critical paths include format-sensitive downstream consumers (JSON → schema → database)
- You have no automated behavioral test suite that runs against production traffic
- Your team has experienced a "nothing changed but it broke" incident in the past 6 months

If you're self-hosting (Ollama, llama.cpp, vLLM), you control the version — but you now own the update lifecycle. The same detection patterns apply; only the remediation changes.

## Receipt

> Verified 2026-07-07 — The April 2026 Anthropic version-pin removal incident is documented on HN (viral thread), aima.io, and tianpan.co. GPT-4 regression study: arxiv.org/abs/2307.09009 (Stanford/UC Berkeley). The probe-based canary pattern is implemented in production at multiple teams documented in the Zylos Research longitudinal evaluation report (2026-04-14) and the AgentMarketCap continuous evaluation infrastructure article (2026-04-12).

## See also

- [S-101 · Deterministic Agent Sessions](s101-deterministic-agent-sessions.md) — session-level verifiability as the foundation for drift detection
- [S-580 · The Shadow Deployment Pattern](s580-shadow-deployment-pattern.md) — shadow routing as a deployment primitive
- [S-584 · Agent Versioned Release Bundles](s584-agent-versioned-release-bundles.md) — treating agent components as versioned, auditable bundles
- [S-668 · The Trace-Eval Gap](s668-the-trace-eval-gap-why-instrumented-teams-still-ship-blind.md) — why instrumented teams still lack behavioral regression signals
