# S-1033 · The Behavioral Version Stack — When Your Git Log Is Clean but Your Agent Is Broken

You shipped an agent last Tuesday. Nothing in your codebase changed. On Thursday, it started refusing tool calls it had handled reliably for weeks. Your git log is clean, your tests pass, and your CI is green. The agent is broken with no version to roll back to.

Traditional software versioning assumes determinism: same code + same inputs = same outputs. AI agents shatter this assumption. Agent behavior emerges from the intersection of four independently-evolving layers — code, model weights, tool API manifests, and runtime context — and any one of them can shift without leaving a trace in your version control system.

## Forces

- **Four layers, one artifact.** Your git commit captures the prompt edit but not the model update that shipped the same day. Your deployment manifest pins the model version but not the tool API's response schema. No single artifact captures the behavioral contract your agent maintains.
- **Aggregate metrics lie.** A 2% accuracy improvement looks like a ship. But 32% of high-value customer segments quietly degraded while the average moved up. Aggregate scores hide regression on critical paths — the exact failure mode that costs you enterprise contracts.
- **Silent inputs change silently.** Tool descriptions are prompts — they change model behavior. An undocumented API response format change silently breaks argument extraction. Runtime context (user data, session state, environment) shifts daily without any version record.
- **CI has no behavioral gate.** Your test suite passes because it tests code logic, not agent behavior. The moment you merge a prompt edit or update a model, your tests are testing yesterday's agent.

## The move

**Track the behavioral version as a first-class artifact.** Every agent run should be tied to a behavioral version: the combined fingerprint of code hash + model variant + tool manifest hash + eval baseline snapshot.

```
behavioral_version = hash(code + model_tag + tool_manifest + eval_baseline)
```

**Build a flip-gated eval baseline.** Instead of tracking aggregate accuracy, track per-example pass/fail on a held-out eval set across every deployment. A flip is a pass→fail (P→F, a regression) or fail→pass (F→P, a fix). The AgentDevel framework (arXiv:2601.04620, Jan 2026) shows that aggregate accuracy hides regressions that flip-centered gating catches. Set a max P→F threshold — typically 0 for safety-critical examples, 2-3% for general quality.

**Version every tool manifest.** Use `mcpdiff` or equivalent to snapshot MCP tool schemas. Treat description changes as prompt changes — require behavioral eval before merging, not just schema validation.

```
```bash
# Snapshot current tool schemas
mcpdiff snapshot --env prod --output ./contracts/v42/

# Before deploying, diff against baseline
mcpdiff diff ./contracts/v42/ ./contracts/v43/ --severity high

# Block deployment on breaking changes
if mcpdiff has-breaking ./contracts/v42/ ./contracts/v43/; then
  echo "BLOCKED: breaking schema changes detected"
  exit 1
fi
```
```

**Run behavioral CI with llm-canary or evalview.** Snapshot agent trajectories (tool calls, order, arguments) and diff against baseline on every pull request.

```
```bash
# evalview workflow
evalview snapshot --env staging  # Record baseline trajectories
git checkout new-feature
evalview check --env staging     # Diff against baseline

# Output:
#   ✓ login-flow          PASSED    behavior matches baseline
#   ⚠ refund-request     TOOLS_CHANGED  called getRefundStatus → getRefund instead
#   ✗ payment-retry       TOOLS_DROPPED  retry_with_backoff no longer called
```
```

**The four-layer version log.** Maintain a version manifest alongside your code:

```
```yaml
# agent-version.yaml — committed alongside code
version: "2026-07-13.42"
layers:
  code:           "a3f9c1d"          # git commit
  model:          "claude-sonnet-4-20250701"  # provider tag + date
  tool_manifest:  "sha256:7b2e..."  # hash of MCP tool schemas
  eval_baseline:  "gs://bucket/eval-baselines/v42.jsonl"
deployed_at: "2026-07-13T14:22:00Z"
deployed_by: "ci-pipeline"
```
```

Before any rollback, assert which layer diverged. Code drift → revert commit. Model drift → pin previous version. Tool manifest drift → restore previous schemas. Eval baseline drift → update baseline intentionally and document the change.

**Canary with behavioral gates, not error rates.** Route 5% of traffic to the new version. Compare per-example flip rates, not aggregate accuracy. Block promotion if P→F flips exceed threshold.

```
```python
# Flip-gated canary
def evaluate_canary(candidate_baseline: Path, production_baseline: Path) -> bool:
    candidate_runs = run_eval(candidate_baseline)
    production_runs = run_eval(production_baseline)

    pf_flips = count_pass_to_fail(candidate_runs, production_runs)
    fp_fixes = count_fail_to_pass(candidate_runs, production_runs)

    # Block on regressions; allow fixes
    if pf_flips > MAX_ALLOWED_REGRESSIONS:
        return False  # CANARY BLOCKED

    log(f"P→F flips: {pf_flips}, F→P fixes: {fp_fixes}")
    return True  # CANARY APPROVED
```
```

## Receipt

> Verified 2026-07-13 — Research from: tianpan.co "Agent Behavioral Versioning" (Tian Pan, Apr 2026); arXiv:2601.04620 AgentDevel framework (flip-centered gating, P→F/F→P tracking); github.com/agentcontract/spec (behavioral contracts specification); github.com/mcp-contracts/mcp-contracts (mcpdiff tool manifest versioning); dev.to llm-canary CI regression testing guide; github.com/hidai25/evalview (trajectory snapshot and diff). The four-layer version model and flip-centered gating are novel production patterns not yet covered by existing S-entries.

## See also

- [S-1004 · The Agent Eval Stack](stacks/s1004-the-agent-eval-stack-when-your-benchmark-says-pass-but-production-keeps-breaking.md) — eval infrastructure this extends with behavioral gates
- [S-839 · The Agent Eval Stack](stacks/s839-the-agent-eval-stack-when-everything-runs-but-nothing-is-measured.md) — trajectory measurement fundamentals
- [S-100 · Agentic RAG](stacks/s100-agentic-rag.md) — where tool manifest drift most commonly bites
- [S-874 · The MCP Config Drift Stack](stacks/s874-the-mcp-config-drift-stack-when-your-agent-has-a-secret-security-hole-you-dont-know-about.md) — tool schema security angle
