# S-1579 · The Clock-In/Clock-Out Stack — When Your Agent Wakes Up Knowing Nothing

Your agent spent four hours mapping a 90,000-line codebase, tracing data dependencies, and building a migration plan. You come back the next morning, start a new session, and the agent asks: "What would you like to work on today?" Every file it read, every decision it made, every path it ruled out — gone. The work is yours to redo.

This isn't a context-window problem. It's a session-boundary problem: agents treat every session as a fresh start, and the work done in prior sessions evaporates. The Clock-In/Clock-Out protocol fixes it by making session entry and exit deterministic, structured events — not accidents.

## Forces

- **Sessions are stateless by default.** Every new LLM invocation starts from zero, regardless of what the previous session accomplished. The transcript ends; the institutional knowledge ends with it
- **Continuity artifacts are rarely structured.** When teams do persist state, they usually write ad-hoc notes, copy-paste context into system prompts, or rely on the model's implicit memory — all of which are fragile and non-deterministic
- **Clock-in without clock-out creates zombie state.** If agents read continuity artifacts on entry but never write them on exit, the artifacts grow stale. The next session reads outdated state and acts on it confidently
- **Manual handoffs don't scale.** A human can summarize progress for an AI, but the summary is lossy, inconsistent, and disappears when the human is unavailable
- **Context resets are invisible failures.** The agent doesn't report "I lost my context" — it reports nothing. It confidently proceeds from a false starting point and nobody notices until the wrong output lands

## The move

**Protocol: bracket every session with deterministic continuity artifacts.**

The protocol lives in a project-level `AGENTS.md` (or equivalent) and encodes two enforced sequences — one for session start, one for session end. The harness, not the agent, enforces the protocol so it cannot be skipped.

### Clock-In (Session Start)

```
1. Read PROGRESS.md         ← what was being worked on
2. Read DECISIONS.md        ← key decisions and their rationale
3. Read TODO.md             ← remaining work queue
4. Run `make check`         ← verify environment consistency
5. Read any COMPACT.md      ← if prior session hit context limit
6. Resume from TODO.md "Next Steps"
```

The agent must reach a "cold start" state — one where it knows the current objective, the decisions already made, and the environment is consistent — before taking any action.

### Clock-Out (Session End)

```
1. Update PROGRESS.md       ← what was accomplished this session
2. Update DECISIONS.md      ← any new decisions made and why
3. Update TODO.md            ← next steps, remaining blockers
4. Run `make check`         ← confirm environment is consistent
5. Commit all artifacts     ← persist to durable store
```

The agent writes its own continuity artifacts. This is critical: the agent that did the work is the one that records it, so the record is authoritative, not inferred.

### The Three Core Artifacts

| Artifact | Purpose | Updated by |
|----------|---------|------------|
| `PROGRESS.md` | Current state of work, accomplishments this session | Agent on clock-out |
| `DECISIONS.md` | Key decisions, their rationale, and what was ruled out | Agent on clock-out |
| `TODO.md` | Work queue: next steps, blockers, pending questions | Agent on clock-out |

### Continuity Protocol Variants

**Minimal (3 artifacts):** PROGRESS, DECISIONS, TODO — as above.

**Full (6 artifacts):** Adds:
- `COMPACT.md` — context-window summarization output (written when compaction triggers, read on clock-in if exists)
- `CONTEXT.md` — current working context summary (entity definitions, conventions, project-specific rules)
- `ARCHIVE.md` — completed work summaries for long projects (prevents TODO from growing unbounded)

**Tiered by session type:**

| Session type | Required clock-out artifacts | Optional |
|---|---|---|
| Development session | All 3 core + `make check` | ARCHIVE |
| Incident response | All 3 core + RUNBOOK.md delta | |
| Research/exploration | All 3 core + findings digest | COMPACT |
| Scheduled automation | PROGRESS + TODO only | |

### Handling Forced Exits (crash, timeout, interrupt)

```
On forced exit:
  1. Write TODO.md draft (what was in progress)
  2. Write PROGRESS.md partial (what was completed before the interruption)
  3. Mark TODO items with [IN_PROGRESS: <last_action_taken>]
  4. Next clock-in reads [IN_PROGRESS] items and asks: "continue or abort?"
```

The key principle: **always leave artifacts in a state better than you found them**, even on failure. A partial artifact is more useful than a stale one.

### Schema for PROGRESS.md

```markdown
# Progress — [Project Name]

## Session Summary
**Date:** YYYY-MM-DD
**Duration:** ~X hours
**Agent:** [model/version if relevant]

## Accomplished
- [ ] ...
- [ ] ...

## Environment State
- Files modified: ...
- Tests added/updated: ...
- Config changes: ...

## Open Questions
- [ ] ...

## Next Session Starts At
[TODO.md "Next Steps" section]
```

### Schema for DECISIONS.md

```markdown
# Decisions — [Project Name]

## Key Decisions
| Decision | Rationale | Date | Reversible? |
|----------|-----------|------|-------------|
| ... | ... | ... | ... |

## Ruled Out
| Option | Why Not | Date |
|--------|---------|------|
| ... | ... | ... |

## Conventions Established
- [ ] ...
```

## The Makefile Anchor

```make
.PHONY: check
check:
	@echo "=== Environment Consistency Check ==="
	@git status --short
	@test -f PROGRESS.md && echo "PROGRESS.md exists" || (echo "ERROR: PROGRESS.md missing" && exit 1)
	@test -f TODO.md && echo "TODO.md exists" || (echo "ERROR: TODO.md missing" && exit 1)
	@echo "=== Running test suite ==="
	$(PYTEST) --tb=short -q
	@echo "=== Check complete ==="
```

Running `make check` on both clock-in and clock-out ensures the agent never leaves the environment in an inconsistent state — and the clock-in check catches stale artifacts before work begins.

## Why Not Just Use Memory Systems?

External memory systems (vector stores, episodic memory pipelines) are complementary, not substitutes. The distinction:

| Layer | Lives in | Failure mode |
|-------|---------|-------------|
| Context window | LLM working memory | Eviction, degradation |
| External memory | Vector store, DB | Retrieval misses, staleness |
| Continuity artifacts | Source-controlled files | Agent discipline |

Continuity artifacts are **human-readable, version-controlled, and diffable** — properties that vector-store memory lacks. When something goes wrong, you can `git diff` your way to understanding what changed. You can't do that with an embedding store.

The protocol pattern works *with* memory systems: memory handles implicit knowledge retrieval; artifacts handle explicit state that must survive resets.

## Failure Modes

- **Clock-out skipped → stale artifacts.** If the agent crashes without writing artifacts, the next session inherits stale state. Mitigation: make `make check` on clock-in warn if PROGRESS.md hasn't been updated in >24h
- **Artifact format drift.** Over time, agents write PROGRESS.md in inconsistent formats. Mitigation: schema template in `AGENTS.md`; `make check` validates format
- **Agent ignores artifacts on clock-in.** Mitigation: harness-level enforcement — if the agent takes an action before completing the clock-in sequence, the harness terminates the action and re-prompts
- **COMPACT.md is lossy.** When context compaction triggers, the summary loses detail. Mitigation: treat COMPACT.md as a bridge, not a permanent record — next session should verify key facts against live environment
- **Too many artifacts → artifact fatigue.** Teams start with 6 artifacts, agents spend 20% of session time maintaining them. Mitigation: start with 3 core artifacts; add optional ones only when the team has workflow discipline

## See also

[S-1550 · The Plan Object Stack](../stacks/s1550-the-plan-object-stack-when-your-agent-loses-the-plan-between-sessions.md) — Cross-session plan durability, the sibling concern (what plan survives; this entry covers how the agent knows it)

[S-1572 · The Brain-Hands Session Stack](../stacks/s1572-the-brain-hands-session-stack-when-your-agent-is-a-pet-not-a-cattle.md) — Separating decision-making from execution environment; clock-in/out works best when brain and hands are decoupled

[S-1564 · The Long-Session Coherence Collapse](../stacks/s1564-the-long-session-coherence-collapse-when-your-agent-reads-everything-and-know-less-turn-by-turn.md) — The degradation problem this protocol partially mitigates by keeping context fresh via structured eviction

[S-1000 · The Context Exhaustion Stack](../stacks/s1000-the-context-exhaustion-stack-when-your-agent-silently-degrades-as-the-window-fills.md) — The root problem (finite context) this protocol manages at the artifact layer rather than the window layer

## Receipt

> Verified 2026-07-24 — Research: AgentPatterns.ai Clock-In/Clock-Out Protocol (maturity: adopted, reviewed 2026-06-01); Blake Link Session Handoff Protocol (blakelink.us, Sep 2025); Agent Continuity GitHub blueprint (richardwhiteii/agent-continuity, MIT, 2026-01-05); Session Continuity Protocol GitHub (nu-gui/CLAUDE-CODE-CLI-AGENTS-blueprint, target: rehydration <30s); vLLM SAAR session-aware routing (vllm.ai, Jun 2026) for cross-reference on session continuity in routing. Pattern confirmed as production-adopted with multiple independent implementations. Handbook coverage gap confirmed: zero entries cover session bracketing protocols or deterministic continuity artifacts. Distinct from S-1550 (plan persistence), S-1572 (brain/hand decoupling), and S-1574 (memory staleness).
