# S-1409 · The Failure Recovery Stack — When Your Agent Runs and Fails and Runs and Fails the Same Way

Your agent ran 847 times last week. Three of those runs failed silently — no exceptions, no alerts, dashboards showed green. The work was supposed to happen; it didn't. You found out because a downstream system surfaced the gap. The agent had no idea anything went wrong, so it tried the exact same approach 12 hours later and failed the same way. This is the failure recovery gap: the space between "run finished" and "work actually happened."

Detection without recovery is observability theater. The failure recovery stack closes that gap — it gives agents the ability to detect non-obvious failures, recover gracefully, and avoid repeating the same failure mode twice.

## Forces

- **Agents fail silently, not loudly.** Unlike traditional software, agents don't throw exceptions when they go wrong — they produce wrong outputs that sound plausible, exhaust token budgets without error, or complete a run without creating the intended side effect. Standard APM misses this entirely.
- **A retry that repeats the same approach is not recovery.** Retrying without changing the input, tool, or strategy is just repeated failure with extra latency. Real recovery requires diagnosing the failure mode and changing what the agent does next.
- **Token budget exhaustion is a silent killer.** Agents can run out of budget mid-task and produce a plausible-looking final answer without having completed the actual work. The agent thinks it succeeded; the user gets nothing.
- **Semantic drift is invisible to metrics.** An agent can be highly active — calling tools, generating output — while making zero progress toward the goal. Activity ≠ progress.
- **Recovery state must survive process restarts.** If an agent crashes mid-task, it should resume where it left off, not start over from scratch.

## The Move

Build a recovery layer that intercepts the gap between "run completed" and "work delivered," then gives the agent structured paths to recover without human intervention.

### 1. Instrument the delivery point, not just the run

The single highest-leverage addition: verify that the side effect actually happened. If the agent creates a GitHub issue, check that the issue exists. If it updates a spreadsheet, verify the cell changed. If it sends a message, confirm delivery. This check lives **outside** the agent's execution trace — the agent can't self-report this reliably.

```python
# Verify side effect, not just completion
def verify_delivery(expected: DeliverySpec) -> bool:
    if expected.type == "github_issue":
        return check_github_issue_exists(expected.resource_id)
    elif expected.type == "sheet_update":
        return verify_cell_value(expected.sheet_id, expected.range, expected.value)
    # ...
```

*Source: Pazi blog — "The cron framework only knows what the agent self-reports"*

### 2. Detect semantic drift with progress probes

Track what the agent has actually accomplished at each step, not just what it has done. A progress probe periodically asks: "given everything that's happened so far, how close are we to the goal?" If the answer hasn't improved in N steps, the agent is drifting and needs intervention — not another retry of the same approach.

```python
# Progress probe: semantic checkpointing
def is_making_progress(trajectory: list[Step], threshold: int = 3) -> bool:
    # Count consecutive steps with no meaningful state change
    # "Meaningful" = new information, progress toward goal, not just tool calls
    consecutive_stagnant = 0
    for step in reversed(trajectory):
        if step.has_novel_progress():
            break
        consecutive_stagnant += 1
    return consecutive_stagnant < threshold
```

*Source: Zylos Research — "Agents can drift semantically: high activity, zero progress"*

### 3. Route failures to recovery strategies, not retry loops

Map failure modes to recovery strategies. The agent should not retry blindly — it should select a response based on what went wrong:

| Failure Mode | Recovery Strategy |
|---|---|
| Tool call error (API timeout, rate limit) | Exponential backoff with jitter, switch to alternate tool |
| Token budget exhaustion | Truncate, summarize earlier steps, continue with compressed context |
| Semantic drift (no progress in N steps) | Abandon current approach, decompose goal into smaller steps |
| Tool returned unexpected format | Retry with corrected arguments from parsed error message |
| Delivery side effect missing | Re-execute from last confirmed good state checkpoint |

*Source: Fastio — "A single error can derail an entire multi-step workflow"*

### 4. State checkpointing for crash recovery

Persist the agent's state at meaningful checkpoints — after each completed step, not just at the end of the run. When the agent restarts (OOM kill, timeout, redeploy), it resumes from the last checkpoint, not the beginning.

```python
# Checkpoint after each completed step
@dataclass
class AgentCheckpoint:
    step_number: int
    trajectory_summary: str       # Compressed summary for LLM context
    confirmed_outputs: dict       # Verified outputs (delivery checks passed)
    pending_work: list[str]       # Remaining steps not yet started
    recovery_hint: str            # "Resume from step 4, last confirmed: X"

def save_checkpoint(checkpoint: AgentCheckpoint, run_id: str):
    checkpoint_path = f"checkpoints/{run_id}/step_{checkpoint.step_number}.json"
    with open(checkpoint_path, "w") as f:
        json.dump(asdict(checkpoint), f)
```

*Source: Zylos Research — "Agents lose conversation state mid-task during process restart"*

### 5. Set hard operating envelopes and enforce them

Define and track cost, latency, and token budgets per run as first-class constraints. When a threshold is hit, the agent stops — it doesn't produce a partial result and call it done. The envelope is a safety net, not a suggestion.

```python
MAX_STEPS = 20
MAX_TOKENS = 500_000
MAX_COST_PER_RUN = 2.00  # USD

def enforce_envelope(metrics: RunMetrics) -> EnvelopeAction:
    if metrics.steps >= MAX_STEPS:
        return EnvelopeAction.STOP_AND_SUMMARIZE
    if metrics.total_tokens >= MAX_TOKENS:
        return EnvelopeAction.SUMMARIZE_AND_HALT
    if metrics.cumulative_cost >= MAX_COST_PER_RUN:
        return EnvelopeAction.STOP_AND_REPORT
    return EnvelopeAction.CONTINUE
```

*Source: Confident AI — "Track operating envelopes (cost, latency, step/token budgets) in the same traces used for quality"*

## Evidence

- **Blog post — Pazi:** "5 Silent Failure Modes in Production AI Agents" documents crons that succeed but never deliver, where the root cause is the agent creating side effects then running out of budget before announcing completion. The fix: verify delivery as a first-class act, not a derived conclusion from run status. — [URL](https://blog.pazi.ai/silent-failure-modes-production-ai-agents)

- **Research article — Zylos Research:** "AI Agent Self-Healing: Automated Recovery and Resilience Patterns" (March 2026) formalizes three agent failure modes — liveness failures (process dead), semantic drift (active but zero progress), and token budget exhaustion — and maps each to a distinct recovery strategy. Draws on distributed systems patterns (Kubernetes probes, Erlang supervision trees, Chaos Engineering). — [URL](https://zylos.ai/research/2026-03-02-ai-agent-self-healing-recovery-patterns)

- **Survey — Cleanlab:** "AI Agents in Production 2025" found that only 5% of engineering leaders have agents in production, and among those, fewer than 1 in 3 are satisfied with their observability and guardrail solutions. 63% plan to improve evaluation and recovery infrastructure in the next year. The #1 production pain point isn't model quality — it's knowing when the agent failed and whether it recovered. — [URL](https://cleanlab.ai/ai-agents-in-production-2025)

- **Blog post — Fastio:** "AI Agent Error Handling: Best Practices & Patterns for 2025" details exponential backoff, circuit breaker patterns, and state checkpointing as the three core recovery mechanisms that separate production-ready agents from prototypes. — [URL](https://fast.io/resources/ai-agent-error-handling)

## Gotchas

- **Don't rely on the agent to report its own failures.** The agent's confidence in its output is not a signal of correctness — agents produce highly plausible wrong answers. Delivery verification must happen outside the agent's execution context.
- **Retrying the same approach is not recovery.** If a tool call failed because the tool's schema changed, retrying with the same arguments will fail the same way. Recovery requires diagnosing the failure mode before retrying.
- **Checkpoint summaries compress context — but compression loses information.** The compressed trajectory summary used for context after a restart will inevitably omit some details. Design checkpoints at fine enough granularity that lost detail doesn't block recovery.
- **Operating envelopes are only useful if they're enforced.** Defining MAX_STEPS and MAX_COST but not stopping when they're hit is theater. The enforcement must be outside the agent's loop.
- **Crash recovery without delivery verification is incomplete.** Saving checkpoint state is necessary but not sufficient — the agent also needs to re-verify that previous steps' outputs still hold (an upstream dependency may have changed since the checkpoint was saved).
