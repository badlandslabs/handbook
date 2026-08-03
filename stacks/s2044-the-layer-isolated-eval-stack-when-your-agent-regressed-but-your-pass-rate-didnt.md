# S-2044 · The Layer-Isolated Eval Stack — When Your Agent Regressed But Your Pass Rate Didn't

Your agent scores 94% on your eval suite. Your production error rate doubled last week. Your CI passed every commit. The aggregate number told you *whether* the system degraded, not *which part* broke. You need layer-isolated evaluation: decompose the agent into architectural layers, test each in deterministic no-LLM mode, and lock every slice.

## Forces

- **Aggregate scores mask layer-level regressions.** A correct final answer achieved through a broken safety layer, a skipped escalation, and a hallucinated intermediate tool call looks identical to a clean trajectory in a pass/fail test. The masking effect is structural — one number cannot distinguish which of 8 subsystems degraded.
- **LLM-as-judge introduces sampling noise, not determinism.** LLM-based eval scores vary across runs on the same input. This is fine for human-in-the-loop quality assessment but fatal for CI gating — you cannot hard-reject a merge when the judge itself is non-deterministic. A 5% variance on a 94% pass rate means you cannot tell if the system got better or worse across a commit.
- **The deterministic scaffold is testable without an LLM.** Most production agents run on top of a fixed scaffold: routing logic, intent classification, escalation policies, safety validators, memory fetch gates. These are code — not model outputs. They can be unit-tested deterministically. The gap is that teams don't isolate and test them separately.
- **Regression localization requires fixed taxonomy.** Without a consistent layer decomposition, you cannot compare across runs. Each team member names failures differently, regression reports are incomparable, and the "which layer broke?" question goes unanswered until someone manually reads the trace.

## The Move

**Step 1 — Decompose into a fixed layer taxonomy.** Divide the agent's scaffold into architectural layers with clear boundaries:

| Layer | What it does | Failure mode |
|---|---|---|
| Ontology pre-resolution | Entity/term canonicalization before routing | Misroutes due to alias ambiguity |
| Intent signals | Classifies task type and urgency | Wrong intent → wrong plan |
| Routing | Selects agent/path for task | Escalation bypass, wrong agent |
| Decomposition | Breaks task into steps | Incomplete plan, missing dependencies |
| Escalation | Detects and promotes hard cases | Escalation avoidance |
| Safety | Policy enforcement, guardrails | Tool call through without check |
| Memory | Fetch, store, consolidate | Stale data in context |
| Envelope/defense | Cross-cutting: rate limits, timeouts, circuit breakers | Cascade failures |

**Step 2 — Write assertion slices for each layer in pure-mode (no LLM in loop).** Pure-mode tests use deterministic inputs and assert on fixed outputs:

```python
# Safety layer — pure-mode assertion slice
def test_safety_blocks_destructive_tool():
    """Safety layer must block rm -rf on production paths."""
    scaffold = AgentScaffold()
    scaffold.load_state({
        "tool_calls": ["filesystem.rm", "path=/prod/data"],
        "user_context": {"role": "agent", "env": "production"},
        "policy": SAFETY_POLICY_v3,
    })
    result = scaffold.safety_layer.check()
    assert result.decision == "BLOCK"
    assert "destructive_tool_production" in result.reason_codes

# Memory layer — pure-mode assertion slice
def test_memory_fetch_returns_recent():
    """Memory fetch must return entries within session horizon."""
    scaffold = AgentScaffold()
    now = time.time()
    scaffold.load_state({
        "memory_store": [
            {"ts": now - 3500, "content": "old_entry"},  # > 1hr stale
            {"ts": now - 120, "content": "recent_entry"},  # < 10min fresh
        ],
        "session_start": now - 1800,
        "fetch_policy": MEMORY_POLICY_v2,
    })
    result = scaffold.memory_layer.fetch(context={})
    assert len(result.entries) == 1
    assert result.entries[0]["content"] == "recent_entry"
```

**Step 3 — Lock per-slice baselines and gate CI.** Each slice gets a locked baseline (expected pass/fail pattern at a known-good commit). The pure suite runs on every PR:

```yaml
# .github/workflows/agent-scaffold-eval.yml
- name: Run pure-mode eval suite
  run: |
    pytest tests/scaffold/pure_mode/ \
      --slice=ontology,intent,routing,decomp,escalation,safety,memory,envelope \
      --baseline=tests/scaffold/baselines/v1.2.0 \
      --gate=strict
  # 238 cases across 23 slices → ~10ms/case → full suite in ~2.4s
```

A baseline mismatch on the `safety` slice blocks the merge regardless of end-to-end pass rate.

**Step 4 — Use the LLM judge only for the trajectory layer.** After pure-mode gating passes, run LLM-as-judge over the full traces as a complementary signal — not as a gate. This separates fast deterministic feedback (CI, always runs) from semantic quality assessment (canary, runs on main).

**Step 5 — Report layer-level deltas, not just aggregate.** Every eval run produces a per-slice heatmap:

```
Slice          Baseline  Current  Delta  Status
ontology       100%      100%     ±0     ✓
intent         98%       98%     ±0     ✓
routing        97%       91%     -6     ✗ REGRESSION
escalation     99%       97%     -2     ⚠ WARNING
safety         100%      100%     ±0     ✓
memory         96%       96%     ±0     ✓
envelope       98%       95%     -3     ⚠ WARNING
```

The routing layer regressed 6 points. The aggregate score barely moved because the routing layer has lower weight in the final task-success metric. Without layer isolation, this regression ships.

## Receipt

> Verified 2026-08-02 — arXiv:2606.11686 (Zhang/Wang/Lei, Lumivate, June 2026): 238 baseline cases across 23 slices, 225 cases run in 2.39s (~10ms/case), full suite in CI. Decomposition taxonomy: ontology pre-resolution, intent signals, routing, decomposition, escalation, safety, memory, cross-cutting envelope/defense. Pure-mode tests achieve determinism (LLM judge variance eliminated), enabling hard CI gates. Layer decomposition resolves the "masking effect" — routing regression of 6 points invisible in aggregate 94% score was caught by the routing slice. Core insight: the deterministic scaffold is code; test it like code. LLM-as-judge is complementary, not a replacement for structural testing.

## See also

- [S-812 · The Three-Layer Agent Eval Stack](stacks/s812-the-three-layer-agent-eval-stack-endpoint-scores-lie-trajectories-dont.md) — trajectory vs. endpoint scoring (layer eval builds on this)
- [S-1045 · The Agent Debugging Stack](stacks/s1045-the-agent-debugging-stack-when-your-agent-fails-and-you-cant-find-where.md) — causal chain debugging when layer regression surfaces
- [S-996 · The Harness Matters More Stack](stacks/s996-the-harness-matters-more-stack-when-your-model-isnt-the-problem.md) — harness engineering is where agent reliability is made or lost
