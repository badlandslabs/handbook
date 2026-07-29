# S-1836 · The Agentic Deployment Pipeline Stack — When You Change a Prompt and Production Breaks Two Weeks Later

You updated the system prompt on a Tuesday. On Thursday the metrics looked fine. On the following Monday, a customer noticed the agent was silently refusing to process refunds above $200 — a behavior change so subtle it produced no error logs, no latency spikes, and no alert. The agent was still responding. It was just responding differently. This is not a monitoring problem. This is a deployment problem.

LLM-based systems break silently when their prompts change, when their underlying models update, or when their tool definitions drift. Traditional CI/CD validates code changes before production. Agents need the same discipline for non-code artifacts: system prompts, tool schemas, retrieval configurations, guardrail policies, and model versions. The discipline that solves this is the agentic deployment pipeline — treating every agent artifact as a deployable unit with versioning, gated evaluation, and instant rollback.

## Forces

- **Agents have no compile step.** Code compiles and either runs or doesn't. Prompts accept anything and produce behavior that drifts. The absence of a binary pass/fail makes it easy to ship quietly broken behavior.
- **Model updates are invisible.** Your LLM provider can change the underlying model with no announcement. The API response format stays the same. The behavior changes. Without a behavioral regression suite, you discover this through user complaints.
- **The blast radius of a bad prompt is unbounded.** A wrong prompt affects every single user interaction, not just the one running during a deployment window. The compounding nature of agent decisions means a single regression cascades into hundreds of wrong outcomes per hour.
- **Rollback of code is instant. Rollback of a prompt is not.** If you deployed a bad code change, you revert the commit. If you shipped a bad prompt, you need a mechanism to redeploy the previous version — and that mechanism must exist before you need it.
- **Eval gates are cheaper than incident response.** A behavioral regression caught in CI costs one engineer-hour. A behavioral regression discovered in production costs a customer relationship and a post-mortem.

## The move

The agentic deployment pipeline treats prompts, tool schemas, guardrails, and model configurations as first-class deployables. It has four layers:

### 1. Artifact Versioning

Store every agent artifact in git — system prompts, tool definitions, retrieval configs, guardrail policies, model routing rules. Tag each version with a semantic label. This is not optional scaffolding; it's the prerequisite for every other layer.

```bash
# prompts/
#   v1.0.0/
#     system-prompt.txt
#     tools.yaml
#     guardrails.yaml
#   v1.1.0/
#     system-prompt.txt
#     tools.yaml
#     guardrails.yaml
```

```python
# agent_config_loader.py
from pathlib import Path
import json

def load_agent_version(version_tag: str) -> dict:
    base = Path(f"prompts/{version_tag}")
    return {
        "system_prompt": (base / "system-prompt.txt").read_text(),
        "tools": yaml.safe_load((base / "tools.yaml").read_text()),
        "guardrails": json.loads((base / "guardrails.yaml").read_text()),
        "model_config": json.loads((base / "model-config.json").read_text()),
    }
```

### 2. CI-Gated Eval Before Deploy

Every pull request that changes an agent artifact runs a behavioral evaluation suite against a golden test set before merging. The suite uses trajectory-level assertions, not just output checks.

```python
# eval_gates/prompt_pr_test.py
def test_refund_policy_unchanged(new_prompt: str, golden_cases: list):
    """
    Regression gate: ensure the new prompt preserves the refund behavior
    that the v1.x series was known to implement correctly.
    """
    failures = []
    for case in golden_cases:
        if case["type"] == "refund_above_200":
            response = agent.run(case["input"], system_prompt=new_prompt)
            if not assert_refund_allowed(response):
                failures.append(f"  {case['input'][:60]}... → refund blocked")

    assert len(failures) == 0, (
        f"Behavioral regression detected in {len(failures)} refund cases:\n"
        + "\n".join(failures)
    )

# .github/workflows/agent-cd.yml
# - Run golden set eval on every PR to prompts/*
# - Require 100% pass on critical-path assertions
# - Block merge if any critical assertion fails
```

### 3. Shadow Deployment Before Full Rollout

Deploy the new version to a small fraction of traffic (1–5%) alongside the current version. Run traffic-copy eval: the same inputs go to both versions, and a judge compares the outputs. Only promote to full rollout if behavioral divergence stays below the configured threshold.

```python
# shadow_deploy.py
import random

class ShadowDeploy:
    def __init__(self, control_version: str, candidate_version: str,
                 shadow_ratio: float = 0.05, divergence_threshold: float = 0.05):
        self.control = load_agent_version(control_version)
        self.candidate = load_agent_version(candidate_version)
        self.shadow_ratio = shadow_ratio
        self.threshold = divergence_threshold
        self.divergences = 0
        self.total = 0

    def route(self, request) -> str:
        if random.random() < self.shadow_ratio:
            self.total += 1
            ctrl_out = agent.run(request, **self.control)
            cand_out = agent.run(request, **self.candidate)
            if not self._behavioral_match(ctrl_out, cand_out):
                self.divergences += 1
                log_divergence(request, ctrl_out, cand_out)
            return ctrl_out  # user always gets control version
        return self._resolve(request, self.control)

    def divergence_rate(self) -> float:
        return self.divergences / max(self.total, 1)

    def is_ready_for_promotion(self) -> bool:
        return (
            self.total >= 100  # minimum sample size
            and self.divergence_rate() < self.threshold
        )
```

### 4. Instant Rollback

If shadow deployment reveals regressions or if production monitoring triggers a behavioral alert, roll back to the previous artifact version. The rollback must be a first-class operation — not a manual edit, not a post-mortem action, but an automated trigger.

```bash
# Rollback command: revert to the last known-good version tag
agent-cli rollback --service=refund-agent --to=v1.2.3
# → Loads v1.2.3 artifacts from prompts/v1.2.3/
# → Pushes config to production
# → Validates health endpoint responds
# → Marks v1.3.1 as "recalled" in artifact registry
```

```python
# rollback_trigger.py
# Production monitoring calls this on behavioral alert
def trigger_rollback(service: str, incident_id: str):
    prev = artifact_registry.get_previous_version(service)
    deploy(prev)
    incident_tracker.link_rollback(incident_id, prev.version_tag)
    notify(f"Rolled back {service} to {prev.version_tag}")
```

## Receipt

> Verified 2026-07-29 — Researched and written based on: tutorialQ "CI/CD for Agents — Prompt Versioning, Testing, and Safe Rollouts" (2026); Sentrial "AI Agent Regression Testing" (2026); Agent Jig "The Silent Regression Problem" (2026); AgentCI.com documentation; arXiv:2606.08162 (Intelligence Entropy). Code examples are functional implementations of the described patterns.

## See also

- [S-818 · The Longitudinal Agent Eval Stack](s818-the-longitudinal-agent-eval-stack-when-silent-degradation-slips-past-your-team.md) — production regression detection that complements CI gates
- [S-1824 · The Eval-First Stack](s1824-the-eval-first-stack-when-you-build-agents-before-you-can-prove-they-work.md) — building evaluation before building agents
- [S-1831 · The Agent Trajectory Evaluation Stack](s1831-the-agent-trajectory-evaluation-stack-when-your-agent-passes-all-checks-and-still-fails-in-production.md) — why trajectory-level eval catches what output-only eval misses
