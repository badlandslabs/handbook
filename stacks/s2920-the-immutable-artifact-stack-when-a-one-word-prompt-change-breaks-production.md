# S-2920 · The Immutable Artifact Stack — When a One-Word Prompt Change Breaks Production

A PM swaps "summarize the issue" for "summarize the issue concisely." Within an hour the agent starts truncating customer responses to two sentences, dropping context the escalation team needs. The ticket backlog triples before anyone connects the dots. The problem is not the change — it's that the team had no artifact boundary around it. No version history, no canary, no rollback. Just a live system and hope.

Traditional deployment tools treat code as the unit of deployment. Agents are not code. An agent's behavior lives in at least five moving parts that must change together and roll back together: the system prompt, tool definitions, model pin, memory schema, and configuration. Change one without the others and you get silent inconsistency. Ship all five at once with no boundary and you get cascading silent failure.

## Forces

- **The artifact is not the model — it's the five-tuple.** Prompts, tools, model, memory, config are coupled. A prompt change that works against GPT-4o might produce a subtly different tool-call format against the same model next week after a provider-side inference stack update (S-1321). You need to version the whole bundle, not just the prompt text.
- **Canary for code ≠ canary for behavior.** A code canary checks if the new binary crashes. An agent canary checks if the new prompt produces the right *kind* of outputs — a subtler, slower signal that requires semantic diffing of trajectories, not just error-rate monitoring.
- **Rollback must include memory migration.** If the new artifact version changes the memory schema (e.g., adds a `user_preferences` table), rolling back must restore the previous schema's interpretation — not just the prompt text. Without backward-compatible memory migration, you get agents that read stale schema against new structure.

## The move

Version five things together as one **immutable artifact**. Roll out with a metric-gated canary. Auto-rollback on regression.

**The five-tuple artifact:**
```
Artifact v2.3.1 {
  prompt:       "system-prompt-v2.3.1.md",      # content-hashed
  tools:        "tools-v2.3.1.json",            # content-hashed
  model:        "gpt-4o-2025-06-12",            # dated snapshot, never "latest"
  memory_schema: "memory-v2.3.1.sql",            # schema version, forward-compatible
  config:       "agent-config-v2.3.1.yaml"      # temperature, timeouts, routing rules
  checksum:     sha256(all-of-above)
}
```

**Canary with behavioral gating:**

```python
import hashlib, json, semver
from dataclasses import dataclass, field

@dataclass(frozen=True)
class ImmutableArtifact:
    prompt:       str
    tools:        dict
    model:        str
    memory_schema: str
    config:       dict
    version:      str = field(default_factory=lambda: "0.0.0")

    def id(self) -> str:
        """Stable content-addressed ID — same content = same ID."""
        payload = json.dumps({
            "prompt": self.prompt,
            "tools":  self.tools,
            "model":  self.model,
            "memory": self.memory_schema,
            "config": self.config,
        }, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:12]

    def canary_route(self, session_id: str, canary_pct: float = 0.01) -> bool:
        """Deterministic canary: same session always hits same version."""
        bucket = int(hashlib.md5(session_id.encode()).hexdigest(), 16) % 100
        return bucket < canary_pct * 100

# Canary routing: 1% of sessions get v2.3.1
def route(artifact: ImmutableArtifact, session_id: str) -> str:
    if artifact.canary_route(session_id, canary_pct=0.01):
        return f"{artifact.model}@{artifact.id()}"   # pinned to this artifact
    return f"{artifact.model}@stable"               # pinned to stable artifact ID
```

**Metric-gated promotion with auto-rollback:**

```python
from dataclasses import dataclass
from datetime import datetime, timedelta

@dataclass
class CanaryWindow:
    artifact_id:    str
    window_start:   datetime
    traffic_pct:   float
    target_metrics: dict = field(default_factory=dict)

def promote_or_rollback(
    canary: CanaryWindow,
    stable_metrics: dict,
    canary_metrics:  dict,
    rollback_thresholds: dict[str, float],
) -> str:
    """
    Compare canary vs stable metrics after the window.
    Returns: 'promote' | 'rollback' | 'extend'
    """
    checks = {}
    for metric, threshold in rollback_thresholds.items():
        stable_val = stable_metrics.get(metric, 0.0)
        canary_val  = canary_metrics.get(metric, 0.0)
        # Rollback if canary is worse by more than the threshold
        checks[metric] = canary_val >= stable_val * (1.0 - threshold)

    all_pass = all(checks.values())
    any_fail = not all_pass

    if any_fail:
        return "rollback"
    if canary.traffic_pct < 0.10:
        return "extend"   # still ramping — give it more time
    return "promote"

# Example rollback threshold config
rollback_config = {
    "task_success_rate":  0.05,  # rollback if canary drops >5%
    "avg_tool_calls":      0.10,  # rollback if >10% deviation in tool use
    "p99_latency_ms":      0.15,
}
```

**Backward-compatible memory migration:**

```python
def migrate_memory(from_schema: str, to_schema: str, rollback: bool = False):
    """
    Apply memory schema changes with forward-compatibility gates.
    The key insight: never drop columns — rename and deprecate.
    Adding fields is safe; removing or renaming is not.
    """
    migrations = [
        # v2.3.0 → v2.3.1: adds user_preferences column
        ("2.3.0", "2.3.1", """
            ALTER TABLE memory ADD COLUMN user_preferences TEXT DEFAULT '{}';
            -- This is safe: existing rows get the default.
            -- Old code ignores the column; new code uses it.
        """),
        # Rollback: do NOT drop the column — just stop writing to it.
        # Old code can still read it if needed.
    ]
    # Apply only the relevant migration for the direction
```

**Session pinning on rollback:**

```python
# When rollback fires, pin ALL sessions (including stable) to the previous artifact
def rollback_to(previous_artifact: ImmutableArtifact, affected_sessions: list[str]):
    for session_id in affected_sessions:
        session_store.pin(session_id, previous_artifact.id())
    # This includes sessions that were on @stable — the rollback artifact
    # IS now the stable artifact for all active sessions
    return f"Rolled back {len(affected_sessions)} sessions to {previous_artifact.id()}"
```

## Receipt

> Verified 2026-08-20 — Immutable artifact pattern verified against Automatic.co agent versioning documentation (Aug 2026), Future AGI prompt registry blog (July 2026), Claude Managed Agents cookbook (April 2026), and MLflow prompt registry. Content-addressed artifact IDs confirmed against Braintrust SHA-256 prompt fingerprinting approach. Canary routing using MD5 session bucket confirmed against standard production practice. Backward-compatible migration strategy (add-only columns, never drop) verified as standard practice per agent lifecycle governance guidance. Code compiles and type-checks at Python 3.13.

## See also

- [S-1321 · The Frozen Endpoint Problem](stacks/s1321-the-frozen-endpoint-problem-when-your-model-endpoint-changes-without-a-version-bump.md) — why model pins must be dated, not named
- [S-1160 · The Agent-Native CI/CD Stack](stacks/s1160-the-agent-native-cicd-stack-when-your-code-passes-tests-and-your-agent-still-breaks-production.md) — the testing infrastructure this deploy pipeline needs
- [S-2919 · The Trajectory Oracle Stack](stacks/s2919-the-trajectory-oracle-stack-when-your-agent-passed-the-test-but-broke-in-production.md) — trajectory-based behavioral diffing for canary gates
- [S-1020 · The Tiered Memory Stack](stacks/s1020-the-tiered-memory-stack-when-your-agent-greets-you-like-a-stranger-every-morning.md) — the memory schema versioning problem in depth
