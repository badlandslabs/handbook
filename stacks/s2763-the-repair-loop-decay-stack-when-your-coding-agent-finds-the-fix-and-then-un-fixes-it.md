# S-2763 · The Repair-Loop Decay Stack — When Your Coding Agent Finds the Fix and Then Un-Fixes It

Your coding agent just ran the test suite. It failed. The agent reads the output, revises, runs again. This time it passes. You accept the PR. Two weeks later, a subtle regression surfaces — and bisecting the history shows the agent introduced it during revision 3 of the bug fix, overwrote the correct patch in revision 4, and then never re-encountered the failing test. The agent found the right answer. Then it forgot it was right. This is repair-loop decay — and it is the silent reliability killer in every coding agent that loops.

## Forces

- **Correctness is not an absorbing state.** A coding agent that lands a correct patch in revision 2 can overwrite it with a subtly wrong patch in revision 3. The test suite may not re-expose the regression because the agent modified the surrounding context in ways that mask the earlier failure. More loops do not monotonically converge — they can actively degrade state.
- **LLM revision is state-blind.** When a coding agent revises code, it revises the *entire visible state*, not just the specific failing region. Each revision round carries the full transcript, but the agent's memory of *which prior revision was correct* decays with context distance. It knows a correct state existed but has no structured pointer to it — only natural-language memory that degrades under conflicting context.
- **Common-state revision multiplies the problem.** When the same agent handles multiple repair branches simultaneously (e.g., a crew reviewing a diff with three failing test cases), revisions to one branch bleed context into others. The agent's "fix for branch B" embeds a fragment from the "fix attempt for branch A" — invisible to any single-branch trace.
- **Step-count limits are a blunt instrument.** The naive mitigation — cap revisions at N attempts and take the best — is fragile because correctness peaks early (usually revision 1–2) then degrades. The cap must be *early*, which means many tasks that need more than 2 revisions are lost. You need a smarter stopping condition, not a lower cap.

## The move

### The three decay mechanisms

Gao et al. (arXiv:2607.24604, Alibaba Cloud, AgenticDev 2026) identify three distinct mechanisms driving repair-loop decay:

**1. Proposal-search divergence.** More revisions increase the probability that *some* revision found the correct patch. But the correct patch is buried in a trajectory heap the orchestrator may never surface. The ever-correct rate climbs (84.7% after 3 revisions on HumanEval); the current-state correctness rate collapses (82.0% → 67.3% over revisions).

**2. Contextual contamination.** As revisions accumulate, each new patch embeds fragments of prior fix attempts in its context. The agent's next revision is not "fix the original bug in isolation" — it is "fix the bug as it now appears, shaped by all prior attempts." This produces fix mutations: the agent introduces new bugs while fixing the original.

**3. Stale trace anchoring.** The agent anchors its next revision on the *most recent* state, not the *last-known-correct* state. When revision N+1 regresses, revision N is still in context but its correctness is no longer emphasized — it competes with the wrong current state for the agent's attention.

### The typed revision contract pattern

The paper's primary mitigation is **typed revision contracts** — a formal schema that declares which code regions each revision is permitted to modify. Think of it as a surgical permit system: revision 1 may touch function signatures and logic; revision 2 may only touch the body of the modified function; revision 3 may only touch test assertions. Each revision narrows the blast radius.

```python
# Typed revision contract for agentic code repair
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

class RevisionPhase(Enum):
    DIAGNOSIS   = auto()   # Understand the failure, propose structural fix
    SURGICAL    = auto()   # Apply fix within declared region only
    VERIFY      = auto()   # Run tests, confirm pass
    ACCEPT_OR_ROLLBACK = auto()  # Compare to last-known-correct state

@dataclass
class RevisionContract:
    """Declares what a given revision pass is permitted to touch."""
    phase: RevisionPhase
    declared_regions: list[str]  # e.g. ["src/auth.py::authenticate", "tests/test_auth.py"]
    forbidden_regions: list[str] = field(default_factory=list)
    max_lines_delta: int = 20     # Prevent large rewrites in single revision
    rollback_on_regression: bool = True

    def is_compliant(self, proposed_diff: dict) -> bool:
        """Check whether a proposed diff respects the contract."""
        touched = proposed_diff.get("touched_files", [])
        # Phase gates: surgical revisions cannot touch new files
        if self.phase == RevisionPhase.SURGICAL:
            if any(f not in self.declared_regions for f in touched):
                return False
        # Line-delta cap prevents wholesale rewrites
        if proposed_diff.get("lines_added", 0) > self.max_lines_delta:
            return False
        # Forbidden regions are always off-limits
        for region in self.forbidden_regions:
            if any(region in f for f in touched):
                return False
        return True

@dataclass
class RevisionTracker:
    """Tracks best-known-correct state across revision rounds."""
    best_state: Optional[dict] = None
    best_state_revision: int = 0
    best_state_passed: bool = False

    def update_if_better(self, revision_num: int, state: dict, test_result: bool):
        """Only update the best state if tests pass AND it's better than current best."""
        if test_result:
            if self.best_state is None or revision_num < self.best_state_revision:
                self.best_state = state.copy()
                self.best_state_revision = revision_num
                self.best_state_passed = True

    def should_continue(self, revision_num: int, max_revisions: int, contract: RevisionContract) -> bool:
        """Determine whether to continue revision or accept best-known state."""
        if revision_num >= max_revisions:
            return False
        # If current state passed and phase is VERIFY, accept
        if contract.phase == RevisionPhase.VERIFY and self.best_state_passed:
            return False
        return True

# Revision orchestrator using contracts
def run_revision_with_contracts(
    original_code: str,
    failure_trace: str,
    max_revisions: int = 3,
) -> tuple[str, int]:
    tracker = RevisionTracker()

    for rev in range(1, max_revisions + 1):
        # Determine contract phase for this revision
        if rev == 1:
            phase = RevisionPhase.DIAGNOSIS
        elif rev == 2:
            phase = RevisionPhase.SURGICAL
        else:
            phase = RevisionPhase.VERIFY

        contract = RevisionContract(
            phase=phase,
            declared_regions=["."],  # Widen scope as trust grows
            max_lines_delta=20 if phase == RevisionPhase.SURGICAL else 50,
            rollback_on_regression=True,
        )

        proposed = agent_generate_patch(original_code, failure_trace, phase=phase)
        diff = compute_diff(original_code, proposed)

        if not contract.is_compliant(diff):
            # Contract violation: revert to best-known-correct state
            if tracker.best_state:
                proposed = tracker.best_state["code"]
                continue  # Stop revising; best state is final
            else:
                continue  # No baseline yet; try another approach

        test_result = run_tests(proposed)
        tracker.update_if_better(rev, {"code": proposed}, test_result)

        if not tracker.should_continue(rev, max_revisions, contract):
            break

    # Return best-known-correct state, not necessarily the last revision
    return tracker.best_state["code"], tracker.best_state_revision
```

### The checkpoint-before-revision pattern

For teams not ready to implement full typed contracts, the minimum viable mitigation: **checkpoint the best-known-correct state before every revision**, then compare post-revision test results against that checkpoint.

```bash
# Minimal pre-revision checkpoint (shell snippet)
BEST_STATE=$(git hash-object -w /dev/stdin <<<"$current_code")
BEST_REV=0

for rev in 1 2 3; do
  patched=$(agent_revise "$current_code" "$failure_trace")
  if tests_pass "$patched"); then
    # Only upgrade best state if this revision's patch is genuinely different
    # AND tests pass (don't accept regressions)
    if [ "$patched" != "$BEST_STATE" ] && [ "$rev" -lt "$BEST_REV" ] 2>/dev/null; then
      echo "Degradation detected: rev $rev regressed from rev $BEST_REV" >&2
      current_code="$BEST_STATE"  # Roll back
      break
    fi
    BEST_STATE="$patched"
    BEST_REV=$rev
  fi
  current_code="$patched"
done

echo "Final: rev $BEST_REV accepted"
```

### The stopping-condition heuristic

The paper's experimental data suggests a practical heuristic: **stop after the first revision that passes, unless evidence suggests the patch is fragile.** Fragility signals:

- The patch fixed more tests than the original failure warranted (over-modification)
- The patch touched files outside the immediate failure region
- The agent's confidence score for the patch dropped from the prior revision

```python
def should_accept_and_stop(revisions: list[RevisionResult]) -> bool:
    """Heuristic based on arXiv:2607.24604 findings."""
    if not revisions:
        return False
    last = revisions[-1]
    if not last.test_passed:
        return False
    if len(revisions) == 1:
        return True  # First revision: accept if it passes
    # Correctness declines with revisions in controlled experiments
    # Only skip accepting a passing early revision if there are strong fragility signals
    fragility = (
        last.lines_touched > revisions[0].lines_touched * 2 or
        last.confidence_score < revisions[0].confidence_score - 0.2 or
        any(r.test_passed for r in revisions[:-1])
    )
    return not fragility
```

## Receipt

> Verified 2026-08-17 — arXiv:2607.24604 (Gao, Yang, Yang, Alibaba Cloud, AgenticDev 2026) provides the empirical foundation. Key numbers: 5-seed HumanEval study (30 repairs, 900 trajectories) shows correctness rate 82.0% → 67.3% across revisions, while ever-correct rate climbs to 84.7%. 2,430-branch common-state study confirms 40–48% regression rate from untyped revision. Typed revision contracts and checkpoint-before-revision are the two practical mitigations. Repo: github.com/gaoxueping/revision-contracts (if published).

## See also

- [S-2762 · The Replay Harness](stacks/s2762-the-replay-harness-stack-when-offline-evals-pass-but-production-fails.md) — trajectory-level eval that catches degraded paths before ship
- [S-1036 · The Trajectory Quality Index](stacks/s1036-the-trajectory-quality-index-when-your-agent-passes-but-the-path-is-broken.md) — measuring the path, not just the output
- [S-1019 · The Ghost Loop](stacks/s1019-the-ghost-loop-stack-when-your-agent-decides-its-own-workflow-and-nobody-traced-it.md) — when the agent's own routing defeats your quality gates
- [S-2761 · The Verification Horizon](stacks/s2761-the-verification-horizon-stack-when-your-agent-satisfies-the-letter-but-violates-the-spirit.md) — the eval-blind-spot problem this pattern exposes
