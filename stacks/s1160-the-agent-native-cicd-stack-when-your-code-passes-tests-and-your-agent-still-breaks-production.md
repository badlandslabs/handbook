# S-1160 · The Agent-Native CI/CD Stack — When Your Code Passes Tests and Your Agent Still Breaks Production

[Your agent PR is green. All unit tests pass, linting is clean, type checks pass. You merge. The next morning your on-call engineer wakes up to a 40% drop in task completion rate across production. The system prompt you changed to "sound friendlier" deleted the instruction that told the agent to truncate after 5 items. The agent is now returning 47-item lists. No error was logged. Every request returned HTTP 200. Traditional CI cannot catch this class of failure because it only tests code — not the 5 things that actually control agent behavior: code + prompts + model + tools + retrieval. Agent-native CI/CD closes this gap.]

## Forces

- **Agent behavior is a product of 5 inputs; CI only tests 1.** Code, system prompt, model version, tool definitions, and retrieval index — change any one silently and the build stays green. A single-line prompt edit can drop task completion by 20 points with no test failure and no stack trace.
- **Agents return 200 even when they are catastrophically wrong.** Kubernetes readiness probes, load-balancer health checks, and HTTP status codes all pass while the agent produces systematically incorrect outputs. You cannot use traditional deployment gates to catch agent regressions.
- **Observability without evaluation is a lagging indicator.** 89% of production agent teams run observability but only 52% run evals — a 37-point gap where quality silently decays (LangChain State of Agent Engineering Survey, 2026). You find out about the regression when customers do.
- **The deploy risk stack is non-deterministic.** Model swaps, prompt edits, tool schema changes, and retrieval index rebuilds all require behavioral gates. They are not covered by the same test.

## The move

### The five inputs you must version-control

```
Agent behavior = f(code, prompt, model, tools, retrieval)
```

Traditional CI tracks `code`. Agent-native CI/CD tracks all five as first-class inputs with version snapshots and a dependency graph for each deploy.

### The three-tier eval gate architecture

**Tier 1 — PR gate (minutes, <$5/run)**
Triggered on every PR. 50–100 golden dataset cases. LLM judge scores per dimension (tool selection, argument extraction, result utilization, plan coherence, task completion). Blocks merge if any dimension drops >3 points vs. baseline.

```python
# Tier 1 gate: per-PR behavioral regression check
import anthropic
from your_eval_harness import GoldenDataset, LLMasJudge

client = anthropic.Anthropic()
dataset = GoldenDataset.load("golden/pr_gate_cases.jsonl")

baseline = dataset.load_baseline("sweep-1159-baseline.json")
candidate_prompt = Path("prompts/agent-prompt.yaml").read_text()

results = dataset.run(
    agent_prompt=candidate_prompt,
    max_samples=100,
    model="claude-sonnet-4-20250514",
)

delta = results.score_delta(baseline, dimensions=[
    "tool_selection", "argument_extraction",
    "result_utilization", "plan_coherence", "task_completion"
])

# Block merge if any dimension regresses > 3 points
for dim, delta_pt in delta.items():
    if delta_pt < -3.0:
        raise PipelineError(
            f"REGRESSION: {dim} dropped {delta_pt:.1f}pt "
            f"(threshold: -3.0pt). BLOCKING MERGE."
        )
```

**Tier 2 — Nightly gate (hours, <$50/run)**
Runs against 300–500 cases, full regression suite, plus cost tracking per run. Catches regressions that emerge only on long-tail inputs. Also gates on token cost delta: flags if new version burns >15% more tokens per task.

**Tier 3 — Shadow gate (pre-rollout)**
New agent version runs in shadow mode alongside production traffic. Compares output distributions. Canary route 5% of traffic for 1 hour. Automated rollback if task completion drops >5% or error rate doubles.

```python
# Tier 3: shadow evaluation + canary rollback
async def shadow_evaluate(new_agent: Agent, prod_traffic: list[Task]):
    new_outputs = await new_agent.run_batch(prod_traffic, parallel=20)
    old_outputs = await old_agent.run_batch(prod_traffic, parallel=20)

    diff = distribution_shift(new_outputs, old_outputs)
    task_completion_delta = (
        new_outputs.task_completion_rate
        - old_outputs.task_completion_rate
    )

    if task_completion_delta < -0.05:
        rollback(f"Shadow eval failed: {task_completion_delta:.1%} drop")
    elif diff.toxicity > 0.02:
        rollback(f"Output distribution shifted: toxicity +{diff.toxicity:.3f}")
    else:
        promote_to_canary(new_agent, traffic_pct=0.05, duration="1h")
```

### The golden dataset discipline

Start with 25–50 manually verified cases. Store as `{input, expected_trajectory, expected_output, metadata}`. Treat as code — PR review required to add cases. The dataset should cover:
- Happy paths (agent handles correctly)
- Edge cases (agent should gracefully degrade)
- Regression targets (cases that broke before and should not break again)
- Cost cases (complex tasks that should not exceed token budget)

Use `pass@k` — run each case k times and pass if it succeeds at least once — not exact-match assertions.

### Version the full execution context

```yaml
# agent-deploy-manifest.yaml — version this alongside code
version: "2.1.0"
components:
  code:          "sha-a3f9c2d"
  system_prompt: "sha-b7e1a08"
  model:         "claude-sonnet-4-20250514"
  tools:
    - name: "mcp-github"
      version: "1.2.0"
    - name: "mcp-slack"
      version: "0.8.3"
  retrieval:
    index:     "v47-prod"
    chunking: "semantic-512"
  guardrails:
    output_filter: "v3.2.0"
```

### The rollback trigger table

| Signal | Threshold | Action |
|--------|-----------|--------|
| Task completion rate | -5% vs. baseline | Automated rollback |
| Error rate (tool failure) | +2× baseline | Pause canary |
| Token cost per task | +15% vs. baseline | Alert + manual approval |
| Output toxicity score | >0.02 shift | Hard rollback |
| Latency p95 | +500ms | Alert |

## Receipt

> Verified 2026-07-15 — Research sourced from: Zylos Research "Agent-Native CI/CD: Deployment Pipelines for AI Agent Systems" (2026-05-17); RockB "Agent CI/CD Eval Pipeline Integration Guide 2026" (2026-06-19); TuringPulse "Safe Agent Deployments: Canary Releases, Shadow Mode, and Progressive Rollouts for LLM Systems" (2026-01-27); LangChain State of Agent Engineering Survey 2026 (89% observability / 52% eval gap). Code examples built to spec from documented patterns. Not executed against a live agent — Receipt pending.

## See also

- [S-987 · The Agent Evaluation Stack](s987-the-agent-evaluation-stack-when-you-cant-tell-if-your-agent-is-actually-working.md) — eval foundations this CI gate builds on
- [S-998 · The Capability Ceiling Stack](s998-the-capability-ceiling-stack-when-your-agent-ships-but-stalls-on-hard-tasks.md) — why eval suites must cover the long tail, not just what works
- [S-997 · The Agent Observability Stack](s997-the-agent-observability-stack-when-the-agent-looks-okay-but-decides-wrong.md) — post-deploy monitoring that complements pre-deploy gates
- [W-09 · Prompt Versioning and Change Management](workspace/w09-prompt-versioning.md) — version-controlling the prompt input this pipeline gates on
