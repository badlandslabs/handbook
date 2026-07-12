# S-917 · The Capability Erasure Stack — When Self-Improvement Becomes Self-Destruction

Self-improving agents don't just get better. They also forget. As agents autonomously refine workflows, accumulate skills, self-train their models, and update memory, they progressively degrade capabilities they previously mastered. This is not a training bug — it is a structural property of continual adaptation. The same mechanism that lets agents improve destroys the substrate of their past competence.

## Situation

You deploy a code-review agent that consistently flags security vulnerabilities, handles dependency audits, and follows your team's PR conventions. Three months later, after the agent has iteratively updated its own prompts and fine-tuned itself on recent merged PRs, it starts missing SQL injection vulnerabilities it caught flawlessly on day one. Its recall rate on security patterns has dropped from 94% to 61%. No configuration changed. No model updated externally. The agent trained itself into failure.

This is **capability erosion under self-evolution** (arXiv:2605.09315, UIUC, May 2026): the systematic degradation of previously mastered capabilities during the process of autonomous adaptation.

## Forces

- **Catastrophic forgetting is structural, not accidental.** Neural networks trained on new distributions overwrite the weights that encoded old behaviors. Agents that fine-tune on recent success trajectories literally overwrite the parameters that handled edge cases from earlier training. This isn't a bug in the learning algorithm — it is gradient descent doing exactly what it was designed to do.
- **Evolution is rewarded, capability preservation is not.** A/B tests show workflow updates improving throughput. They don't show capability regressions because the test suite only measures the new behavior. Old capabilities are not regression-tested unless you deliberately measure them.
- **Four evolution channels, four failure modes.** Capability erosion manifests across: (1) **workflow evolution** — agent refactors its own process and silently drops steps; (2) **skill acquisition** — agent learns new task patterns and overwrites related ones; (3) **model fine-tuning** — RLVR/SFT on recent data degrades generalization; (4) **memory evolution** — the agent rewrites its own memory store and evicts entries that enabled past successes.
- **You cannot detect what you don't measure.** Standard monitoring tracks throughput, error rate, and latency — not capability fidelity. By the time a regression surfaces in user reports, the agent may have shipped hundreds of bad outputs.

## The move

**1. Benchmark before you evolve.** Before any autonomous update, run a capability probe set — a fixed suite of tasks the agent was previously good at. This is your baseline. Store the scores in a capability registry with timestamps.

```python
# Minimal capability probe runner
def run_capability_probe(agent, probe_suite):
    results = {}
    for probe in probe_suite:
        score = agent.execute(probe.task, expected=probe.expected_outcome)
        results[probe.id] = {
            "score": score,
            "passed": score >= probe.threshold,
            "timestamp": datetime.utcnow().isoformat(),
        }
    return results

# Example probe suite entry
SECURITY_PROBES = [
    Probe(id="sql-injection-p0", task="Review: SELECT * FROM users WHERE id='$input'", expected="flag_vulnerability"),
    Probe(id="auth-bypass-p1", task="Review: /api/admin missing auth decorator", expected="flag_missing_auth"),
    Probe(id="dep-audit-2024", task="Audit dependencies for CVE-2024-29824", expected="correct_cve_lookup"),
]
```

**2. Apply Capability-Preserving Evolution (CPE).** When the agent autonomously updates, constrain the update to protect baseline capabilities. Three mechanisms from UIUC research:

- **Rehearsal**: Before fine-tuning on new data, replay a sample of old tasks. This reactivates the relevant weight subspaces, reducing overwrite.
- **Elastic weight consolidation (EWC)**: Penalize changes to weights that were critical for baseline tasks. Identifies and protects high-importance parameters.
- **Selective plasticity**: Freeze shared/base layers during fine-tuning, only adapt task-specific heads. Preserves generalization.

```python
# CPE checkpointing — save capability snapshot before evolution
def pre_evolution_checkpoint(agent, probe_suite):
    snapshot = {
        "weights": agent.model.get_weights(),
        "prompt_templates": agent.prompt_library.snapshot(),
        "memory_entries": agent.memory.get_all(keys=["tool_capability", "security_pattern"]),
        "probe_scores": run_capability_probe(agent, probe_suite),
        "version": agent.version,
    }
    store.set(f"capability_v{snapshot['version']}", snapshot)
    return snapshot

# Post-evolution regression gate
def post_evolution_regression_gate(agent, pre_checkpoint, probe_suite, regression_threshold=0.05):
    post_scores = run_capability_probe(agent, probe_suite)
    regressions = []
    for probe_id, post in post_scores.items():
        pre_score = pre_checkpoint["probe_scores"][probe_id]["score"]
        delta = pre_score - post["score"]
        if delta > regression_threshold:
            regressions.append({
                "probe": probe_id,
                "pre": pre_score,
                "post": post["score"],
                "drop": delta,
            })
    if regressions:
        agent.rollback(pre_checkpoint)
        alert_ops(f"Evolution blocked: {len(regressions)} capability regressions", regressions)
    return post_scores
```

**3. Separate the evolver from the operator.** Never fine-tune the production model in-place. Maintain a separate evolution instance: apply updates there, benchmark against probes, and only promote to production if all probes pass. The production agent uses a frozen checkpoint until the evolution instance passes the gate.

**4. Log evolution events as capability risks.** Every autonomous update — prompt edit, memory write, fine-tune, workflow change — should emit a structured event with the affected capability categories. Build a capability timeline: which capabilities degraded after which evolution events. Over time, this reveals which evolution patterns are safe and which are erosive for your specific agent.

## Receipt

> Receipt pending — 2026-07-10
> Researched from: arXiv:2605.09315 "Do Self-Evolving Agents Forget?" (UIUC, May 2026); agentmarketcap.ai synthetic data flywheel articles (Q1 2026); agentmemo.ai on agent capability testing patterns.

## See also

- [S-383 · Goal Drift: The Silent Competence Erosion Pattern](s383-goal-drift-the-silent-competence-erosion-pattern.md) — behavioral/context-side drift vs. training-side erosion
- [F-83 · Agent Capability Testing](f83-agent-capability-testing.md) — probe-based capability verification
- [S-106 · Behavioral Drift Detector: Continuous Agent Competence Monitoring](s106-the-behavioral-drift-detector-stack-when-88-percent-of-your-agents-go-off-script-without-you-knowing.md) — continuous rolling-baseline evaluation for production agents
- [S-004 · Governance Decay: Context Compaction Silently Erases Safety Constraints](s004-governance-decay.md) — constraint erasure as a distinct failure mode from capability erosion
