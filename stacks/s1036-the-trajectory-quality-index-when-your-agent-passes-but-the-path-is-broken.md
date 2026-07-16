# S-1036 · The Trajectory Quality Index: When Your Agent Passes but the Path Is Broken

Your agent scores 91% on your test suite. In production it loops on paginated APIs, calls deletion tools twice, rewrites its own recent output, and burns 3× more tokens than it should — yet reaches the right answer, so the test passes. You have optimized for correctness and failed to measure what is actually costing you money, time, and risk. You need the Trajectory Quality Index.

## Forces

- **Resolve rate hides process.** Two agents with identical pass rates can have zero overlapping tool-call sequences. One reaches the answer in 6 steps; the other takes 14 with two retries and a rollback. Pass/fail scoring is blind to this difference.
- **Reliability compounds multiplicatively.** At 95% reliability per step: 5 steps → 77% end-to-end; 10 steps → 60%; 20 steps → 36%. An agent that "mostly works" at the step level is statistically likely to fail the task. You cannot see this without trajectory-level visibility.
- **Trajectories are structurally noisy.** Raw traces vary across runs due to model non-determinism, tool-return variance, and environmental state. Normalizing into canonical actions is a prerequisite to any structural analysis — without it, "search loop" and "different valid path" look identical.
- **Trajectory evaluation is computationally expensive.** Running full multi-turn traces in an eval harness multiplies cost and latency by an order of magnitude. Teams defer it until production pain forces the issue — which means they learn about trajectory regressions from users, not tests.

## The Move

The Trajectory Quality Index (TQI) is a multi-dimensional scoring framework that evaluates *how* an agent completes a task, not just *whether* it does. Where resolve rate is a binary output signal, TQI is a structured diagnostic over the execution path. It sits inside your eval harness and feeds both regression gates and continuous improvement loops.

### 1. Normalize Traces into Canonical Actions

Raw agent traces are too noisy for structural comparison. A scaffold adapter normalizes each raw action into a canonical form with an effect label — what the action did to observable state.

```python
# Minimal scaffold adapter (from TRACEPROBE framework)
class CanonicalAction:
    def __init__(self, raw_action: dict):
        self.action_type = normalize_type(raw_action["type"])
        self.target = raw_action["target"]
        self.effect = label_effect(raw_action["before"], raw_action["after"])
        self.is_verification = is_verification_step(raw_action)
        self.is_destructive = is_destructive(raw_action)

def label_effect(before: State, after: State) -> str:
    if after == before: return "noop"
    if after.added and not before.added: return "create"
    if after.modified and not before.modified: return "update"
    if after.deleted: return "delete"
    if len(after - before) > 3: return "bulk"
    return "edit"

def is_verification_step(action: dict) -> bool:
    """Verification steps (test runs, lint, compile) are structural markers."""
    return any(kw in action["tool"] for kw in ["test", "lint", "compile", "check", "verify"])

# Example canonical sequence for a code-agent task:
# [search(file=A)] → [read(fragment)] → [edit(...)] → [edit(...)] → [verify(run=tests)] → [submit]
```

Once normalized, you can apply rule-based structural detectors that don't require ground-truth labels.

### 2. Detect Structural Failure Modes

Four structural anti-patterns account for the majority of trajectory-level regressions:

```python
def detect_structural_failures(trajectory: list[CanonicalAction]) -> list[dict]:
    failures = []

    # 1. SEARCH LOOP: same action+target within last N steps
    if detect_search_loop(trajectory, window=5):
        failures.append({"type": "search_loop", "severity": "high",
                         "signal": "same file/query repeated without state change"})

    # 2. VERIFICATION SKIP: destructive edit without subsequent verify
    destructive_steps = [i for i, a in enumerate(trajectory) if a.is_destructive]
    for d_step in destructive_steps:
        subsequent_verify = any(
            trajectory[j].is_verification
            for j in range(d_step+1, min(d_step+4, len(trajectory)))
        )
        if not subsequent_verify:
            failures.append({"type": "verification_skip", "step": d_step,
                             "severity": "critical", "signal": "destructive edit not followed by verify"})

    # 3. OFF-ANCHOR EXPLORATION: wandering from task goal
    if detect_goal_drift(trajectory, goal_embedding):
        failures.append({"type": "off_anchor", "severity": "medium",
                         "signal": "semantic distance from task goal increased"})

    # 4. RAPID REWRITE: undoing a recent edit within 3 steps
    if detect_rapid_rewrite(trajectory, window=3):
        failures.append({"type": "rapid_rewrite", "severity": "medium",
                         "signal": "same target modified, un-modified, re-modified"})

    return failures

def detect_search_loop(traj: list, window: int) -> bool:
    """Two identical search actions without intervening state change."""
    for i in range(len(traj) - window):
        if traj[i].action_type == traj[i+window].action_type:
            if traj[i].target == traj[i+window].target:
                if not any(a.effect != "noop" for a in traj[i+1:i+window]):
                    return True
    return False

def detect_rapid_rewrite(traj: list, window: int) -> bool:
    """Same file edited, then edited again within window — indicates backtracking."""
    for i in range(len(traj) - window):
        if traj[i].action_type in ("edit", "update"):
            for j in range(i+1, min(i+window, len(traj))):
                if traj[j].target == traj[i].target and traj[j].action_type in ("edit", "update"):
                    return True
    return False
```

### 3. Score the Trajectory Quality Index

TQI is a composite of five sub-scores, each measured per trajectory:

```python
@dataclass
class TrajectoryQualityIndex:
    resolve_rate: float          # Did the task succeed? (0 or 1, or pass@k)
    convergence_steps: int       # Steps from first action to completion
    token_cost: float            # Total input + output tokens × price
    structural_health: float     # 1 - (structural_failures / steps), clamped [0, 1]
    efficiency: float            # Steps / optimal_steps_baseline

    @property
    def score(self) -> float:
        # Weighted composite: correctness + process quality
        return (
            self.resolve_rate      * 0.30 +
            self.structural_health * 0.30 +
            self.efficiency        * 0.20 +
            self.token_cost_score  * 0.10 +   # inverse: lower cost = higher score
            self.convergence_score * 0.10
        )

    @property
    def token_cost_score(self) -> float:
        # Normalize against budget: 1.0 if under budget, 0.0 if at 3× budget
        budget = self.optimal_token_budget
        ratio = self.token_cost / budget
        return max(0.0, 1.0 - (ratio - 1.0) / 2.0)

    @property
    def convergence_score(self) -> float:
        ratio = self.convergence_steps / self.optimal_steps_baseline
        return max(0.0, 1.0 - (ratio - 1.0) / 3.0)
```

### 4. Cross-Trajectory Comparison (CONVERGE)

When evaluating a new model, prompt, or scaffold — compare its trajectory distribution against a reference baseline. CONVERGE aligns two trajectories and classifies divergences:

```python
def converge(trajectory_a: list, trajectory_b: list, gold_patch: str = None):
    """
    Align two trajectories and classify structural differences.
    Oracle-free effect labels for shared parts;
    gold-patch anchors for milestone classification.
    """
    aligned = longest_common_subsequence_align(trajectory_a, trajectory_b)

    divergences = []
    for segment in aligned.diverged_regions:
        divergence_type = classify_divergence(segment, gold_patch)
        divergences.append(divergence_type)

    return {
        "aligned_ratio": aligned.length / max(len(trajectory_a), len(trajectory_b)),
        "divergence_count": len(divergences),
        "divergence_types": Counter(d.type for d in divergences),
        "verdict": "improvement" if diverges_positively(divergences)
                   else "regression" if diverges_negatively(divergences)
                   else "neutral"
    }
```

### 5. The Five-Stage Trajectory Harness

Integrate TQI into a CI-grade eval harness:

```
┌─────────────────────────────────────────────────────────────┐
│                  5-Stage Trajectory Harness                  │
├─────────────────────────────────────────────────────────────┤
│  1. DEFINE   → Task suite + optimal baselines + budgets    │
│  2. SIMULATE → Run agent in sandboxed environment          │
│  3. TRACE    → Collect canonical action sequence            │
│  4. SCORE    → TQI: resolve + structural + efficiency       │
│  5. GATE     → Hard CI fail if TQI < threshold or any     │
│                critical structural failure (verify_skip,  │
│                rapid_rewrite on destructive action)         │
└─────────────────────────────────────────────────────────────┘
```

Set trajectory-level thresholds as first-class SLOs:
- `TQI >= 0.85` for all production tasks
- `verify_skip` on any destructive action → hard fail regardless of resolve rate
- `search_loop` count ≤ 2 per task
- `token_cost <= 2× baseline` per task class

## Receipt

> Verified 2026-07-13 — TRACE Probe framework (arXiv:2607.06184) implements the normalize→detect→score pipeline; IoT Digital Twin PLM analysis (June 2026) documents the 5-stage harness architecture; Google Cloud practitioner guide (May 2026) documents compounding decay math; TDS 12-metric framework (May 2026) documents the trajectory vs. output eval gap from 100+ enterprise deployments. No code was run.

## See also

- [S-1001 · The Agent Evaluation Stack](s1001-the-agent-evaluation-stack-when-benchmarks-say-pass-but-production-breaks.md) — the broader eval architecture TQI sits inside
- [S-1027 · The Scaffold Stack](s1027-the-scaffold-stack-when-your-agent-loops-forever-and-charges-your-budget.md) — scaffold adapters as the prerequisite for trajectory normalization
- [S-1013 · The Multi-Agent Boundary Stack](s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — state consistency as a prerequisite for reliable effect labeling
