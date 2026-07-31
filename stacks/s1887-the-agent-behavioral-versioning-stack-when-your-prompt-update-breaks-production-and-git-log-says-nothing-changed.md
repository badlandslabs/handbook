# S-1887 · The Agent Behavioral Versioning Stack — When Your Prompt Update Breaks Production and Git Log Says Nothing Changed

You ship a new feature on Thursday. You update the system prompt to add a new tool description. You push. By Friday afternoon, ticket resolution rates have dropped 23% and three agents are routing customers to the wrong department. Your git log is clean. Your CI passed. The model version didn't change. Nobody touched the code. Your agent broke between Tuesday and Friday — and there is no version to roll back to.

This is the behavioral versioning problem: agents exist at the intersection of four independently-evolving layers, and no single layer captures what the agent actually *does*. Traditional version control assumes determinism. Agents aren't deterministic. The behavior you shipped last week was a product of prompt + model weights + tool definitions + runtime context that has since shifted. The git log has no record of that intersection, and neither does your rollback mechanism.

## Forces

- **Four layers, zero unified history.** Prompt edits, model updates, tool manifest changes, and context distributions all evolve independently. A git commit captures one layer. The combination that matters — what the agent actually did, and why — lives in none of them.
- **Behavioral changes don't show up as errors.** An agent that becomes 15% more verbose or 8% more reluctant to use a certain tool isn't broken. It just behaves differently. No exception fires. No alert fires. You find out when customers complain or costs spike.
- **Rollback without a behavioral snapshot is guesswork.** If you revert the prompt and nothing changes, the model drifted. If you redeploy the model and nothing changes, the tool schema drifted. Without a behavioral baseline, you spend hours on bisection instead of fixes.
- **Silent model drift is real.** A Stanford/UC Berkeley study tracked GPT-4 accuracy on a specific task dropping from 84% to 51% between March and June 2023 — with no version change, no changelog, no alert. The same thing happens to agents continuously. The model provider updated something. You had no way to know.

## The Move

**Build a behavioral snapshot system that treats agent behavior as a versioned artifact, independent of any single layer's version.**

### 1. Version every layer that drives behavior

Treat the following as first-class versioned inputs:

- **Prompt/instruction layer**: versioned in git (good), but also snapshot at deployment time with a content hash
- **Model layer**: pin model version + provider + deployment ID, not just the model name — `"gpt-4o-2025-01-25"` is not the same as `"gpt-4o-2025-03-12"`
- **Tool manifest layer**: snapshot every `tools/list` response with a schema hash. Tools change outside your codebase — an MCP server update can change a parameter name without a deployment in your system
- **Context/configuration layer**: snapshot system context, pinned knowledge base versions, RAG index versions

Bundle these into an **atomic behavioral snapshot** with a single version identifier:

```yaml
# agent-snapshot-v47.yaml
version: "47"
deployed_at: "2026-07-28T14:23:00Z"
components:
  prompt_hash: "sha256:a3f8b2..."
  model: "gpt-4o-mini-2025-03-12"
  model_deployment: "env-prod-us-east-1"
  tool_manifest_hash: "sha256:c7d1e9..."
  tool_manifest_version: "12"
  rag_index_version: "v2026-Q3-001"
  context_config: "standard-long-context"
```

### 2. Track behavioral metrics as CI artifacts

Record behavioral baselines at every snapshot using a lightweight eval harness:

```bash
# Run behavioral baseline on snapshot v47
agent-eval run \
  --snapshot ./snapshots/v47 \
  --eval-set ./evals/regression-set-2026Q3.jsonl \
  --output ./baselines/v47-report.json

# The report captures:
# - pass_rate per task
# - trajectory_length distribution
# - tool_call_pattern fingerprint
# - cost_per_task
# - refusal_rate per sensitive topic
```

Diff the current snapshot against the previous one. Block deployment if any metric shifts beyond threshold:

```bash
agent-eval diff \
  --baseline ./baselines/v46-report.json \
  --candidate ./baselines/v47-report.json \
  --thresholds '{"pass_rate_delta": -0.03, "trajectory_length_p95": 1.5}'

# Output:
# ✗ pass_rate: 91.2% → 87.4% (delta: -3.8%, threshold: -3%)
#   trajectory_length_p95: 12 → 14 (delta: +16.7%, threshold: +50%) ✓
# BLOCKED: behavioral regression detected
```

### 3. Track behavioral fingerprints, not just outcomes

The most sensitive detector of behavioral drift is the **trajectory fingerprint**: the sequence pattern of tool calls, not just whether the task succeeded. An agent that reaches the right answer via a different tool path is a behavioral change even if the final output is correct. Store trajectory fingerprints as structured data:

```python
# Fingerprint = hash of (tool_sequence, argument_schema, call_order)
# Not: what was the output?
# But: how did it behave?

def compute_fingerprint(trace: list[ToolCall]) -> str:
    sequence = [
        f"{call.tool}:{call.args_schema_hash}:{call.order}"
        for call in trace
    ]
    return hashlib.sha256("|".join(sequence).encode()).hexdigest()[:12]

# Alert when fingerprint changes without a corresponding intentional change
if new_fingerprint != expected_fingerprint and not intentional_change:
    alert("Behavioral fingerprint drift detected — investigate before users notice")
```

### 4. Implement one-click rollback to the last known-good snapshot

Rollback must restore the behavioral bundle, not just the code:

```bash
# Roll back to snapshot v45
agent-rollback restore --snapshot v45

# What this restores:
# 1. Prompt hash → revert to v45 prompt content
# 2. Tool manifest → pin MCP servers to v45 schema versions
# 3. Model config → redeploy with v45 model/pin
# 4. Context config → restore pinned knowledge base
# 5. Agent eval → run regression set, confirm baseline restored

# Verify rollback worked
agent-eval verify --snapshot v45 --eval-set ./evals/regression-set.jsonl
```

### 5. Use flip-gated evaluation for regression detection

Instead of tracking aggregate accuracy, track per-example pass/fail on a held-out eval set across every deployment. A **flip** is a pass→fail or fail→pass transition:

- **P→F (pass→fail)**: regression. Alert and block.
- **F→P (fail→pass)**: improvement. Document and merge.
- **F→F** and **P→P**: no behavioral change for this example.

The flip-gated approach catches regressions that aggregate metrics hide. An agent that degrades on 3 critical safety examples out of 500 can drop aggregate accuracy by only 0.6% — below every alert threshold — while silently breaking high-stakes cases.

## Receipt

> Verified 2026-07-30 — Pattern validated against: Zylos Research (Apr 2026) on longitudinal evaluation and behavioral snapshots; Tianpan (Apr 2026) on atomic behavioral versioning; Flowscope (Jul 2026) on held-out regression sets and flip-gated eval; Agentmelt on agent behavioral versioning taxonomy. GitHub `git-agentic` project implements atomic behavioral snapshots across code + prompts + tools + model config. `mcpdiff` (referenced in S-1033) provides tool manifest snapshot and diff tooling. Stanford/UC Berkeley GPT-4 drift data (84%→51%, Mar–Jun 2023) cited as evidence for silent model drift. Deployment blockers and flip-gated eval patterns are consistent with Anthropic's agent eval framework guidance (Jan 2026).

## See also

- [S-1033](s1033-the-behavioral-version-stack-when-your-git-log-is-clean-but-your-agent-is-broken.md) — The Behavioral Version Stack (prior art: the four-layer versioning model and flip-gated eval baseline)
- [S-1004](s1004-the-agent-eval-stack-when-your-benchmark-says-pass-but-production-keeps-breaking.md) — The Agent Eval Stack (LLM-as-judge calibration, trajectory scoring)
- [S-1885](s1885-the-quiet-failure-stack-when-your-agent-succeeds-silently-and-wrong.md) — The Quiet Failure Stack (why silent behavioral changes are harder to detect than crashes)
- [S-1885](s1885-the-agent-incident-response-stack-when-your-agent-breaks-and-nobody-knows-why.md) — The Agent Incident Response Stack (trace reconstruction as incident forensics)
- [S-1056](s1056-the-mcp-tool-contract-gate-when-your-health-probe-is-green-but-your-agent-still-breaks.md) — The MCP Tool Contract Gate (tool schema versioning as part of behavioral snapshots)
