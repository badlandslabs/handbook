# S-2360 · The Prompt CI/CD Stack — When Your Three-Word Prompt Tweak Halts Revenue

Three words added to a customer support system prompt — "improve conversational flow" — weakened the content filter enough to let policy-violating phrases slip through to end users. A JSON output instruction reworded from "Output strictly valid JSON" to "Always respond using clean, parseable JSON" introduced trailing commas and omitted required fields under edge conditions, silently breaking every downstream parser. Neither change looked risky. Neither triggered any alert. Both caused business impact within hours of deployment.

This is the failure mode Prompt CI/CD addresses: prompt changes that are invisible, unversioned, unreviewed, and unvalidated — until they aren't.

## Forces

- **Prompts fail silently.** The API returns HTTP 200, the response is valid text, and downstream systems proceed as if everything worked. By the time the regression surfaces in product metrics, the causal chain is cold.
- **Prompts compound in obscurity.** After three months, no one on the team can explain what the current system prompt does or why specific lines are there. Adding new instructions makes it 40% longer. Nobody reviews the delta.
- **Prompt debt is invisible debt.** Unlike code, prompts have no compiler, no type checker, and no automatic test runner. The gap between "works in development" and "works in production" is measured in user reports.
- **Prompt changes bypass every code safeguard.** The same change that would require a PR review, CI pass, and staged rollout if it were a Python file goes live the moment someone edits a string in a config file.

## The move

Treat every prompt change as a deployment. Apply the same pipeline discipline used for code — version, validate, gate, roll out, observe, roll back — to the prompts that steer your agent.

### The architecture

The pipeline has six stages:

**1. Version** — Store each prompt as an immutable versioned artifact in a prompt registry. Label versions `Development`, `Staging`, `Production`. Never mutate a published version.

```
agent-configs/
├── research-agent/
│   ├── v1.0.0/
│   │   ├── system_prompt.md
│   │   ├── tools.json
│   │   └── config.yaml
│   ├── v1.1.0/
│   │   ├── system_prompt.md
│   │   ├── tools.json
│   │   └── config.yaml
│   └── eval/
│       ├── golden_dataset.jsonl   # known input → expected output pairs
│       └── eval_config.yaml
```

**2. Validate** — Before any promotion, run the candidate prompt against a golden dataset. The minimum viable eval pipeline has three layers:

- **Deterministic assertions** on output structure: schema validity, required fields, type correctness
- **LLM-as-judge** for semantic quality: relevance, coherence, safety
- **Regression suite** on known-failure cases: the edge conditions your agent has failed on before

**3. Gate** — Block promotion in CI if evaluation scores cross any threshold. Three triggers, any one fires:

```
# .github/workflows/prompt-eval.yml
- name: Run prompt evaluation suite
  run: |
    python -m agent_eval run \
      --prompt-version ${{ github.sha }} \
      --dataset eval/golden_dataset.jsonl \
      --thresholds precision:0.85,safety:0.95,json_validity:1.0 \
      --gate strict

# Three-trigger gate: any one fires → CI fails
# Trigger 1: floor  — any rubric mean drops below pinned threshold
# Trigger 2: regress — candidate scores below last-deployed version
# Trigger 3: canary — delta between candidate and prod exceeds margin
```

**4. Roll out** — Promote through stages. Never go directly from Development to Production. Canary at 5% → 25% → 100%, watching per-version metrics at each step.

**5. Observe** — Log `prompt_version` on every production span. Track per-version error rates, latency, JSON validity rates, and cost. If a version degrades silently, you need the signal to find it.

**6. Roll back** — One command, no redeploy. Point the Production label at the last-known-good version:

```
# Instant rollback — no code deploy needed
prompt-cli assign-label --prompt research-agent/system --label Production --version v1.0.0
```

### The key class

```python
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
from typing import Optional

class PromptLabel(Enum):
    DEVELOPMENT = "Development"
    STAGING = "Staging"
    PRODUCTION = "Production"

@dataclass
class PromptVersion:
    version: str
    prompt: str
    tools: list[dict]
    config: dict
    created_at: datetime
    commit_sha: str
    label: PromptLabel = PromptLabel.DEVELOPMENT

@dataclass
class PromptChange:
    from_version: PromptVersion
    to_version: PromptVersion
    diff: str
    eval_scores: dict[str, float]
    approved_by: str
    created_at: datetime

    def is_regression(self, threshold: float = 0.02) -> bool:
        """Detect if any metric regressed beyond threshold."""
        for metric, score in self.eval_scores.items():
            prev = self.from_version.config.get(f"metric_{metric}_floor", 0.0)
            if score < prev - threshold:
                return True
        return False
```

### The eval harness pattern

Production teams that process 200+ evaluation cases per route across multiple Celery, Ray, or Kubernetes runners achieve sub-3-minute CI gates. The pattern: run evaluation in parallel against the judge provider's rate limit, then apply the three-trigger gate:

```
def eval_gate(candidate_version: str, dataset: Path) -> bool:
    results = run_parallel_eval(
        dataset=dataset,
        prompt_version=candidate_version,
        max_workers=16,
        judge_provider="gpt-4o"
    )

    floor_pass  = all(r.mean >= r.pinned_floor for r in results)
    regress_pass = none_below_last_deployed(candidate_version, results)
    canary_pass  = delta_within_margin(candidate_version, results, margin=0.05)

    return floor_pass and regress_pass and canary_pass
```

## Receipt

> Verified 2026-08-09 — Based on: Langfuse Prompt CI/CD documentation, tutorialQ Agent CI/CD pipeline guide (2026), Tian Lu (tianpan.co) two-part prompt versioning analysis (Apr–May 2026), Future AGI prompt versioning for CI/CD (2026), Databricks Agent Bricks prompt management guide, myengineeringpath.dev Prompt Management guide (2026). Real failure cases documented in the sources: 3-word prompt tweak weakening content filters, JSON instruction reworded → parsing breakage, prompt change causing structured-output error rate spike that halted revenue workflows. All confirmed via live extraction.

## See also

- [S-1239 · The Runtime Verification Loop](stacks/s1239-the-runtime-verification-loop-when-your-agent-ships-and-nobody-knows-if-its-any-good.md) — eval infrastructure that feeds into the CI gate
- [S-958 · The Synthetic Trajectory Fidelity Stack](stacks/s958-the-synthetic-trajectory-fidelity-stack-when-your-eval-data-doesnt.md) — building the golden dataset that powers the validate stage
- [S-2328 · The Coin Flip Judge Stack](stacks/s2328-the-coin-flip-judge-stack-when-your-production-eval-passes-but-your-judge-just-flipped.md) — LLM-as-judge instability in the semantic quality layer
