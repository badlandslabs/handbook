# [S-1300] · The Attention Gravity Well

When long-running agents silently stop following instructions they read hours ago — the problem is not the instruction, it's the position.

## Situation

Your agent follows every rule at step 1. By step 50 — 50,000 tokens into the context — it starts violating constraints it has never violated before. You add more instructions. Nothing changes. You blame the model. The real problem: instructions placed in the middle of a growing context window fall into an attention dead zone that gets deeper with every step.

## Forces

- Context windows grow continuously in production agents; the position of any fixed instruction is always moving
- The instruction following problem looks like a model capability failure, so teams spend weeks on prompting — which never works
- System prompts are static; the context around them is dynamic and monotonically growing
- Engineers fix this by adding more instructions (makes it worse) rather than repositioning (the actual fix)
- Most tooling doesn't expose attention weights, so the root cause is invisible

## The Move

The attention U-curve (Liu et al., 2023) shows LLMs attend most strongly to the very beginning and very end of context, with a sharp drop in the middle. As an agent's context window grows, originally-placed instructions migrate into this dead zone — not lost, but no longer weighted in decisions.

Three patterns exploit this structurally:

**1. Attention Anchoring**
Place critical instructions at BOTH the beginning and the end of the system prompt. The model will weight both positions. Redundant placement is not wasteful — it is the load-bearing constraint.

```markdown
# System prompt structure

[ROLE] You are a cautious data-processing agent.
[CRITICAL CONSTRAINT — BOTH ENDS] Never write to filesystem outside /workspace.
Never execute shell commands. Never modify data in-place.

... [middle sections: tools, context, task] ...

[CRITICAL CONSTRAINT — REPEATED] Reminder: you may NOT write to
filesystem outside /workspace or execute shell commands.
```

**2. Recency Injection Loop**
For long-running agents, re-inject a compressed constraint summary as a periodic memory retrieval at regular token thresholds (every 8K–15K tokens of growth). The summary must include critical constraints verbatim, not paraphrased.

```python
ANCHOR_THRESHOLD_TOKENS = 12_000
CRITICAL_CONSTRAINTS = [
    "Never write outside /workspace",
    "Always confirm destructive operations",
    "Escalate to human on unknown file types",
]

def check_attention_anchor(ctx_token_count: int, agent_session):
    if ctx_token_count >= ANCHOR_THRESHOLD_TOKENS:
        anchor_msg = {
            "role": "system",
            "content": f"[ATTENTION ANCHOR] Critical constraints: {CRITICAL_CONSTRAINTS}"
        }
        # Inject at end of context — recency position
        agent_session.add_message(anchor_msg)
        agent_session.reset_context_tracking()
```

**3. Constraint Priority Hierarchy in Tool Definitions**
Move enforcement into the tool schema itself rather than relying on prompt placement alone. Use `description` fields and `required` constraints as structural guardrails that survive attention decay.

```json
{
  "name": "write_file",
  "description": "WRITE-FILE: Cannot write outside /workspace. "
              + "Attempting to write to any path containing '..' or '/etc' "
              + "or '/root' will be rejected. This is not overridable.",
  "parameters": {
    "properties": {
      "path": {
        "type": "string",
        "description": "Must start with /workspace. Path traversal is blocked."
      }
    }
  }
}
```

**4. Instruction Gravity Score**
Track the effective "gravity" of each instruction based on token position. Before trusting a critical instruction, verify it hasn't drifted past the 40%–60% context position threshold.

```python
def instruction_gravity_score(position: int, total_tokens: int) -> float:
    """
    Returns 0.0 (attention dead zone) to 1.0 (full attention weight).
    Based on empirical attention decay curves from Liu et al. 2023.
    """
    if total_tokens == 0:
        return 1.0
    ratio = position / total_tokens
    if ratio < 0.15 or ratio > 0.85:
        return 1.0  # primetime positions
    if 0.30 <= ratio <= 0.70:
        return 0.3  # dead zone
    return 0.6  # transition zone
```

## Receipt

> Verified 2026-07-18 — Bento Labs (April 25, 2026) documented the attention U-curve mechanism with empirical evidence from long-running agent trajectories. Production failure observed at ~50,000 tokens where system prompt instruction adherence drops sharply. The three-pattern fix (dual-end anchoring / periodic re-injection / schema-embedded constraints) tested across multiple agent frameworks. Agnost AI (June 2, 2026) independently confirmed agent drift as a silent production failure mode that looks like model regression but is actually a harness decay problem. arXiv:2601.04170 (Rath, Jan 2026) provides the three-type drift taxonomy (semantic / coordination / behavioral) — this entry covers the specific mechanism that causes *semantic drift* in single-agent instruction following.

## See also

- [S-383 · Goal Drift: The Silent Competence Erosion Pattern](s383-goal-drift-the-silent-competence-erosion-pattern.md) — the higher-level consequence of accumulated attention decay across a session
- [S-342 · Autonomous Context Compression](s342-autonomous-context-compression.md) — compression strategy that can inadvertently push critical instructions into the dead zone
- [S-363 · Context Window Position Architecture](s363-context-window-position-architecture.md) — broader treatment of positional effects in context management
- [S-401 · Agent Drift: The Longitudinal Regression Problem](s401-agent-drift-the-longitudinal-regression-problem.md) — cross-session behavioral degradation
