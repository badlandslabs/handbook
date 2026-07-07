# S-749 · Agent-Native CI/CD: The Deployment Pipeline That Prompts and Models Need

You updated one line in your system prompt, merged the PR, and shipped to production. Three users reported wrong answers. No stack trace. No error log. Just a wrong answer, two hours later, from an agent that passed all your unit tests. Shipping changes to an AI agent is not the same as shipping code. The pipeline that works for software breaks for agents — and the teams that figured out why are now running the patterns below.

## Forces

- **Traditional CI only tracks code; agent behavior is distributed across five mutable layers.** Code + model version + system prompt + tool definitions + retrieval index + guardrail policy — any one can cause a silent regression that no assertion catches — [Zylos Research, May 2026](https://zylos.ai/en/research/2026-05-17-agent-native-cicd-deployment-patterns)
- **Deterministic assertions break for probabilistic outputs.** `assert output == "approved"` fails 40-60% of the time on a language model that paraphrases. The pipeline must evaluate *trajectories*, not just outputs — [RockB, May 2026](https://baeseokjae.github.io/posts/ai-agent-testing-guide-2026)
- **The canary problem is harder for prompts than for code.** Error rates and latency are orthogonal to output quality. A prompt change can produce 0% errors while systematically downgrading answer correctness for 15% of queries — [CallSphere, June 2026](https://callsphere.ai/blog/ci-cd-ai-agents-automated-testing-deployment-rollback-strategies-2026)
- **Rollback of prompts is not the same as rolling back a deployment.** If you push a bad model version, you revert the model. If you push a bad prompt, you need a stored, versioned copy of the prompt that you can re-instantiate instantly — GitOps for prompts — [AWS Prescriptive Guidance, 2026](https://docs.aws.amazon.com/prescriptive-guidance/latest/agentic-ai-serverless/prompt-agent-and-model.html)

## The move

### 1. Treat prompts and configs as code — version them in Git

Store every behavioral artifact alongside the code that uses it: system prompts as `.md` or `.txt` files in the repo, tool schemas as JSON, retrieval configs as YAML. Commit them. Review diffs. The moment a prompt change goes through the same PR review process as code, you gain rollback for free.

```
prompts/
├── agent-support/
│   ├── v1.2_prod.md      # current production
│   ├── v1.3_turndown.md  # under eval
│   └── v1.1_rollback.md  # known-good
└── agent-coder/
    ├── prod.yaml
    └── staging.yaml
```

A `git revert` becomes an instant prompt rollback — no redeploy, no feature flag, just a config reload.

### 2. Build a golden dataset before the pipeline

A golden dataset is a set of input → expected trajectory pairs that define correct agent behavior. Each entry includes: the input query, the expected tools called (in order), and the expected output category. You don't need exact string matches — you need enough structure to detect regressions.

```
# golden/support_triage.yaml
- id: "triage_001"
  input: "My order hasn't shipped in 5 days"
  expected_tools: [lookup_order, check_shipping_policy]
  expected_category: "refund_eligible"
  expected_escalate: false

- id: "triage_002"
  input: "I want to cancel my subscription"
  expected_tools: [lookup_account]
  expected_category: "cancellation_request"
  expected_escalate: true
```

Build the initial set from production traces — replay sessions, extract tool call sequences, label the outcomes. Add edge cases from production failures. Target 50-200 entries minimum; grow it on every regression found.

### 3. Run eval gates, not just unit tests

Insert an evaluation step into CI that runs the golden dataset against the proposed change. The gate runs all 200 entries and computes a trajectory match score: did the agent call the right tools in the right order? Did the output fall in the expected category?

```
# .github/workflows/agent-eval.yml (simplified)
- name: Run eval gate
  run: |
    agent-eval run \
      --dataset golden/ \
      --agent ./prompts/agent-support/v1.3_turndown.yaml \
      --threshold 0.90 \
      --report eval_report.json
  # Blocks merge if score < 0.90
```

The gate should run on every PR touching prompts, tool schemas, model versions, or retrieval configs. A change to a tool description can silently alter which tool an agent selects — tool schema changes need eval coverage too.

Three types of checks in the eval layer, cheapest first:

- **Structural checks** — JSON schema validation, enum bounds, required fields present (cost: milliseconds)
- **Golden trajectory checks** — does the agent follow the same tool sequence on known inputs? (cost: seconds, 5-20x inference calls)
- **LLM judge checks** — does the output satisfy the intent? (cost: dollars, use sparingly as the final check)

### 4. Run shadow rollouts before production

A shadow rollout sends real production traffic to the new agent version while keeping the old version live. No users see the new outputs — you do. Compare the two trajectories on the same inputs:

```
shadow_pct: 5%  # 5% of traffic goes to new version
metrics:
  - trajectory_match: compare tool call sequences
  - output_category: compare output classifications
  - escalation_rate: count hard escalations
  - tool_selection_rate: per-tool call frequency
```

If the shadow run shows a >5% drop in trajectory match or a shift in tool selection that wasn't intended, hold the rollout. The shadow period should run 24-48 hours minimum — enough to cover different time zones, query distributions, and edge cases.

### 5. Instrument instant rollback

If a rollout starts degrading (judge score drops, escalation rate climbs), you need to revert in seconds, not minutes. The mechanism: a config flag that points to the active prompt version. Flip it to the previous SHA.

```python
# Simplified rollback mechanism
def rollback_agent(agent_id: str, prompt_version: str):
    agent_config[agent_id]["active_prompt"] = prompt_version
    # Publishes to agent config store — takes effect within one polling cycle
    # No redeploy, no restart, no incident response overhead
```

Store the previous 3-5 versions in Git with tags. A rollback is a one-line config change, not a full redeployment.

### 6. Monitor continuously, not just at deploy time

Deploy-time evaluation catches regressions in the artifact you changed. Continuous monitoring catches regressions from model updates, upstream API changes, or data drift in the retrieval layer.

Track three production signals:
- **Trajectory stability** — is the tool call sequence changing over time without an intentional deploy?
- **Escalation rate** — are users (or the agent) escalating more often than last week?
- **Output entropy** — has the distribution of output categories shifted?

A spike in any of these is a signal to hold traffic on the current version while you investigate.

## Tradeoffs

- **Eval gates add latency to the PR process.** A 200-entry golden dataset run at $0.002/input costs $0.40/run. Multiply by 10-20 PRs/day and it's $4-8/day — cheap. But the 2-5 minute wall time per run creates friction. Run only changed-subset first; full suite on merge.
- **Golden datasets rot.** Agents and environments change; old golden entries stop reflecting current correct behavior. Budget time to prune and refresh quarterly, or your eval gate becomes noise.
- **Shadow rollouts double inference cost.** For 5% shadow traffic, you run ~2x inference calls. Factor this into cost estimates — it pays for itself against the cost of one silent regression in production.
- **Git-backed prompts don't cover model version changes.** Rolling back a model is infrastructure; rolling back a prompt is configuration. Treat them as two separate rollback mechanisms with two separate triggers.

## Receipt

> Verified 2026-07-07 — Topic chosen from gap analysis of 747 existing entries. Coverage check confirmed no existing entry covers the full pipeline (eval gate → shadow rollout → Git-backed prompt rollback → continuous monitoring). Sub-components covered in S-703 (trajectory invariants), S-735 (eval floor), S-748 (multi-agent foundations), and S-94 (output diffing), but the deployment pipeline lifecycle itself had no dedicated entry. Web research: Zylos Research (May 2026), CallSphere (Jun 2026), RockB (May 2026), AWS Prescriptive Guidance (2026) — all confirmed this as an emerging, practitioner-demand pattern with documented failure cases.

## See also

- [S-703 Agent Trajectory Invariants](s703-agent-trajectory-invariants-behavioral-regression-testing-for-agent-systems.md) — the eval substrate that powers the CI gate
- [S-735 The Evaluation Floor](s735-the-evaluation-floor-what-separates-shipping-agents-from-expensive-pilots.md) — the measurement culture the pipeline embeds
- [S-94 Agent Output Diffing](s94-agent-output-diffing.md) — comparing old vs new outputs mechanically, not via LLM judge
- [S-365 MCP Supply Chain](s365-mcp-supply-chain-from-npx-to-production-catalog.md) — versioning the tool layer that the CI gate must also cover
