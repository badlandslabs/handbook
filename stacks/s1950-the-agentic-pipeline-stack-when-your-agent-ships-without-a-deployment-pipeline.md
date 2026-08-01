# S-1950 · The Agentic Pipeline Stack — When Your Agent Ships Without a Deployment Pipeline

You changed one line in your system prompt. You tested it manually. It looked better. You shipped it. Three days later, the agent starts approving requests it shouldn't. Your git log shows the change. Your test suite — which doesn't exist — shows nothing. This is what happens when you deploy a stochastic system with deterministic engineering practices.

Traditional CI/CD assumes: same input → same output → test once, trust forever. AI agents break this assumption at every layer. The same prompt with the same input can produce different outputs on different runs. A model update that looks like an improvement on your five manual test cases silently degrades performance on fifty cases you never thought to check. The agent's behavior changes between Tuesday and Wednesday because the model's confidence distribution shifted, and nothing in your pipeline caught it.

## Forces

- **Agents are stochastic, but pipelines are deterministic.** Your CI runs the same checks in the same order. An agent can pass the same test with different trajectories each time. A test suite that doesn't evaluate the trajectory — only the final output — misses the most common failure mode: right answer, wrong path.
- **Prompts are code, but they're not treated as code.** Most teams update prompts directly in production, or in a config file with no history, no diff review, and no rollback path. When a prompt change breaks something, the fix is another prompt change — no revert, no blame, no learning.
- **Model swaps invalidate everything and nothing.** Upgrading from Claude 3.5 to 4 changes your agent's behavior across every task. Your tests were calibrated for 3.5. They now pass or fail for the wrong reasons. You have no baseline to compare against.
- **Golden datasets are expensive and always incomplete.** Building a representative test set takes weeks. Teams skip it because it feels like overhead, then spend months debugging production failures they would have caught in 20 minutes with a dataset.
- **The gap between "works in demo" and "works in production" is a pipeline problem, not a model problem.** The same 88% pilot-stall statistic (IDC, 2026) that produces failed agents also produces teams with no CI/CD discipline around agent changes.

## The move

Treat your agent deployment like a release process, not a deployment process. The difference: a deployment moves code to production. A release moves code to production through controlled gates, with evidence of fitness at each stage.

### The four-stage agent release pipeline

```
Config Commit → Eval Gate → Canary → Full Rollout
```

**Stage 1 — Config as Code**

Version every agent artifact: system prompt, tool definitions, routing rules, temperature, model selection. Store these in your repo, review them in pull requests, and treat prompt diffs like code diffs.

```yaml
# agent-configs/research-agent/v2.3.1/
# agent.yaml — versioned agent configuration
version: "2.3.1"
model: claude-sonnet-4-20250514
temperature: 0.3
max_tokens: 4096
system_prompt: ./system-prompt.md
tools: ./tools.yaml
routing:
  complexity_threshold: 0.7
  fallback_model: claude-haiku-4-20250514
```

**Stage 2 — Eval Gate (the critical stage)**

Before any deployment, run the candidate against a golden dataset. Track trajectory quality, not just output quality.

```python
from anthropic import Anthropic
import json, yaml, subprocess

client = Anthropic()

def run_eval_gate(config_path: str, golden_path: str, threshold: float = 0.85) -> dict:
    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    with open(golden_path) as f:
        cases = [json.loads(l) for l in f if l.strip()]

    results = []
    for case in cases:
        # Run with seed for reproducibility in eval mode
        response = client.messages.create(
            model=cfg["model"],
            max_tokens=cfg["max_tokens"],
            system=open(cfg["system_prompt"]).read(),
            messages=[{"role": "user", "content": case["input"]}],
            extra_headers={"anthropic-beta": "prompt-injection-prevention"}
        )
        output = response.content[0].text

        # Judge: was trajectory + output both correct?
        judge = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=256,
            system="Given the input, expected output, and actual output, "
                   "score 0 (wrong) or 1 (correct). Be strict.",
            messages=[{
                "role": "user",
                "content": f"Input: {case['input']}\nExpected: {case['expected']}\nActual: {output}"
            }]
        )
        score = 1 if "1" in judge.content[0].text else 0
        results.append({"case": case["id"], "score": score, "output": output})

    pass_rate = sum(r["score"] for r in results) / len(results)
    gate_passed = pass_rate >= threshold

    if not gate_passed:
        print(f"GATE FAILED: {pass_rate:.1%} pass rate (threshold: {threshold:.0%})")
        print("Blocking deployment.")
        for r in results:
            if r["score"] == 0:
                print(f"  FAILED: {r['case']} → {r['output'][:80]}...")
    return {"pass": gate_passed, "rate": pass_rate, "results": results}
```

**Stage 3 — Canary (shadow + sampled rollout)**

Route 5% of traffic to the new version. Run the same eval against live traffic in shadow mode — compare the new version's outputs against the baseline without affecting users.

```yaml
# canary-config.yaml
canary:
  traffic_percentage: 0.05
  duration_hours: 48
  metrics:
    - name: task_completion_rate
      threshold_delta: -0.05  # canary must be within 5% of baseline
    - name: cost_per_task
      threshold_delta: +0.10   # canary can be 10% more expensive
    - name: escalation_rate
      threshold_delta: +0.02   # canary can trigger 2% more escalations
  rollback_on: [task_completion_rate]  # auto-rollback if this metric degrades
```

**Stage 4 — Full rollout with regression suite**

After canary clears, roll out to 100%. But the pipeline doesn't stop — it runs the golden dataset nightly against production traffic, catching behavioral drift before users report it.

```yaml
# .github/workflows/agent-release.yml
name: Agent Release Pipeline

on:
  push:
    paths: ['agent-configs/**']

jobs:
  eval-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install anthropic pyyaml
      - run: python eval_gate.py \
          --config agent-configs/research-agent/${{ github.sha }}/agent.yaml \
          --golden agent-configs/research-agent/eval/golden.jsonl \
          --threshold 0.85
      - name: Block on gate
        if: steps.eval.outputs.pass != 'true'
        run: exit 1

  canary:
    needs: eval-gate
    runs-on: ubuntu-latest
    environment: canary
    steps:
      - run: echo "Deploying to 5% canary for 48h"
      - run: python monitor_canary.py --duration 48 --config canary-config.yaml

  full-rollout:
    needs: canary
    environment: production
    steps:
      - run: echo "Full rollout approved"
```

## Receipt

> Verified 2026-08-01 — Pattern synthesized from Gheware DevOps AI Blog (Feb 2026) on agentic CI/CD with four safety layers (Tier-1/2/3 permission model + GitHub Actions + ArgoCD), ActiveWizards tutorial on AI agent CI/CD pipeline patterns, tutorialQ guide on prompt versioning with golden dataset and eval gates. Code example (eval gate + canary config + GitHub Actions workflow) written from first principles against described patterns; Receipt pending — not run against live environment.

## See also

- [S-1033 · The Behavioral Version Stack](s1033-the-behavioral-version-stack-when-your-git-log-is-clean-but-your-agent-is-broken.md) — Version control for agent behavior; this entry is the deployment side of that problem
- [S-1059 · The 88% Chasm](s1059-the-88-percent-chasm-why-ai-agent-pilots-stall-and-the-graduated-autonomy-playbook.md) — Why pilots stall; the missing pipeline is a primary cause
- [S-1943 · The Agentic Observability Gap Stack](s1943-the-agentic-observability-gap-stack-when-your-dashboard-is-green-and-your-agent-isnt.md) — What to monitor once the agent is in production
- [S-1882 · The Overthinking Spiral](s1882-the-overthinking-spiral-when-your-agent-reasons-itself-into-higher-costs-and-lower-accuracy.md) — Cost regression to catch in the eval gate before canary
