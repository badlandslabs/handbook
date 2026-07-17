# S-1264 · The Execution Version Control Stack: When Your Agent Runs Hot and Leaves a Mess Behind

A coding agent spends 40 minutes in production. It creates 12 files, edits 7 more, and deletes 3 critical ones. The run fails on step 23 of 30. You fix the prompt. You re-run. The agent creates new versions of the files, leaving the old corrupt ones alongside — or worse, it breaks on a different failure. You now have 25 files to sort through, no clean way to undo, and a production branch that's silently polluted. You have a debug debt problem that tracing alone cannot solve.

## Forces

- **Agents pollute the filesystem as a side effect.** Unlike a crashed process that rolls back on restart, an autonomous coding agent writes files, mutates imports, and creates directories that persist after failure. These are physical artifacts — `git reset --hard` is the only way out, not a state dictionary update.
- **Re-runs are expensive and non-deterministic.** Replaying a 30-step failed run to test a one-step fix costs token budget and returns a different trajectory anyway. The next LLM call produces different decisions even with identical prompts.
- **Standard trace replay only replays the log, not the state.** Capturing spans and LLM calls is necessary but not sufficient — the filesystem state the agent created remains. You can see what happened; you cannot undo it.
- **Standard APM cannot distinguish failed-from-dirty.** An agent that returned HTTP 200 after creating 8 hallucinated files "succeeded" by every metric your dashboard tracks. The damage is in the filesystem, invisible to your observability stack.
- **The real cost is in the manual cleanup.** Engineers report spending 30–90 minutes post-mortem manually reverting agent-created changes before they can even start debugging. This is pure overhead, not value.

## The move

Treat every agent execution as a versioned commit with ACID transaction semantics — checkpoint on start, rollback on failure, fork on debug.

### The core abstraction: execution as git commit

The agent run is modeled as a **versioned execution** with three operations:

1. **`vcr.begin()`** — snapshot the full repository state (working tree + index) before the run starts. Store as a named checkpoint tagged with run ID.
2. **`vcr.commit()` or `vcr.rollback()`** — on success, commit the new state and keep it. On failure, execute `git reset --hard` to the checkpoint, physically deleting every file the agent created or modified.
3. **`vcr.fork(run_id, step)`** — replay the execution from step N, not step 1. Re-use the upstream LLM response for steps 1 through N-1 (zero new token cost), only calling the LLM for step N onward. This is "ghost replay" — you replay the behavior without replaying the cost.

### The ACID execution wrapper

```python
import vcr  # ai-agent-vcr

with vcr.transaction():
    result = agent.run(task)
    if not result.success:
        vcr.rollback()  # git reset --hard to pre-run state
    else:
        vcr.commit()
```

The wrapper guarantees atomicity: either the full run succeeds and commits, or it fails and rolls back the filesystem entirely. No partial state. No orphan files.

### Checkpoint granularity: per-step vs. per-phase

For long-running agents, checkpoint at **phase boundaries** (not every tool call) to keep overhead manageable:

- **Phase 1:** Planning — one checkpoint before planning starts
- **Phase 2:** Tool execution — one checkpoint per 5–10 tool calls
- **Phase 3:** Verification — one checkpoint before verification runs

The cost: ~200ms per checkpoint on a typical repo, acceptable for agents running minutes to hours.

### Fork-and-diff for debugging

When an agent fails at step 23:

1. Fork the run at step 22: `vcr.fork(run_id, step=22)`
2. Apply the fix (prompt change, tool constraint, guard)
3. Replay from step 22 with the upstream LLM responses cached — only step 22+ costs tokens
4. Diff the two execution trees side-by-side to see what changed

This is "git bisect for agent runs": isolate the exact step where behavior diverged, without burning tokens on the first 21 steps.

### The ghost replay optimization

For each upstream step, the LLM response is cached. Replaying from step 5 re-uses cached responses for steps 1–4 — the model is not called again. This means debugging a 30-step run costs tokens for only the steps you're actively changing, not the full trace.

Reported results: **80–90% token reduction** on debug cycles compared to full re-runs.

### Native integration with Claude Code

Claude Code 1.x (April 2026) ships `/rewind` as a built-in command:

```
/rewind --all      # restore code + conversation to checkpoint
/rewind --code     # restore code only, keep conversation
/rewind --chat     # restore conversation only, keep code
```

The rewind system uses a shadow git branch per session. Files are backed up with change detection (only files actually modified get backed up). Rollback is `git checkout` from the shadow branch — O(1) git operation regardless of repo size.

## Evidence

- **GitHub repo:** `ixchio/agent-vcr` — "ACID transactions, time-travel debugging, and zero-cost Ghost Replay for AI agents. Rollback filesystem + state. Works with LangGraph, CrewAI, or raw Python." PyPI: `ai-agent-vcr`, MIT license, 59 commits. — [https://github.com/ixchio/agent-vcr](https://github.com/ixchio/agent-vcr)
- **GitHub repo:** `tathagat22/agent-undo` — "Ctrl-Z for AI agents — a universal reversible side-effect time machine. Rust engine + TypeScript MCP server bridged in-process via NAPI-RS." Supports `undo protect`, `undo run`, `undo rewind`. — [https://github.com/tathagat22/agent-undo](https://github.com/tathagat22/agent-undo)
- **Show HN (timemachinesdk.dev):** "Time Machine – Debug AI Agents by Forking and Replaying from Any Step." Internal framing: "Git for agent execution. Checkpoint, branch, diff, replay." When an agent fails at step 9, fork from step 8 and replay only downstream steps. — [https://news.ycombinator.com/item?id=47315394](https://news.ycombinator.com/item?id=47315394)
- **Claude Code /rewind:** Built-in rollback command shipped April 2026. Uses shadow git branch per session, change-detection backups, O(1) rollback via `git checkout`. — [https://blog.vincentqiao.com/en/posts/claude-code-rewind](https://blog.vincentqiao.com/en/posts/claude-code-rewind)
- **Antigravity Lab:** "Replay-Driven Agent Design — Time-Travel Debugging for Production AI Agents." Three-layer replay model: event (tool calls + LLM responses), state (context window snapshot), decision (routing choice). Documents real failure case: agent called a forbidden tool repeatedly, returned empty response. Re-running the same input produced normal behavior — the bug was non-reproducible without replay infrastructure. — [https://antigravitylab.net/en/articles/agents/antigravity-agent-replay-time-travel-debugging](https://antigravitylab.net/en/articles/agents/antigravity-agent-replay-time-travel-debugging)

## Gotchas

- **Rollback only covers what you snapshot.** If the agent sends an email, calls an external API, or modifies a database, filesystem rollback won't undo it. You need guardrails on destructive tool calls *before* the run, not rollback after.
- **Checkpoint overhead is real for large repos.** Checkpointing a 50K-file monorepo with `git stash` takes seconds to minutes. Use change-detection diffs (only snapshot what changed) instead of full repo snapshots for large repos.
- **Ghost replay caches LLM responses — but the model may not behave identically.** If the upstream call was temperature-based, the cached response is deterministic. If your fix changes a tool interface the upstream call depended on, cached responses become stale. Treat ghost replay as cost optimization, not behavioral guarantee.
- **Agent VCR's rollback is git-based — it only works for git-tracked codebases.** For agents operating on databases, cloud state, or non-git filesystems, you need a separate state snapshot mechanism (DB snapshots, disk images, cloud resource tagging).
- **Shadow branches accumulate.** Without periodic cleanup, the per-session git branches from `/rewind` pile up. Set a retention policy (e.g., auto-delete shadow branches older than 7 days, or keep only the last 3 per project).
