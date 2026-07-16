# S-1147 · The Hook-Injection Pattern — When Your Agent Learns from Every Failure and Never Makes the Same Mistake Twice

The first time your agent deletes the wrong file, you fix it. The fifth time, you should have a hook. The Hook-Injection Pattern makes every agent failure a permanent, enforceable improvement to the harness — not a retry, not a note in Slack, not a ticket you'll forget to triage.

## Forces

- **Failures are harness failures, not model failures.** The default move after an agent mistake is to blame the model and wait for a new version. The harness engineering discipline rejects this: if the agent did the wrong thing with the tools it was given, the harness failed to prevent it.
- **AGENTS.md accumulates rot.** Documenting conventions in a markdown file doesn't prevent recurrence — the next agent run reads the same prompt and makes the same mistake. Writing "don't run destructive commands without user confirmation" in a file doesn't enforce it in code.
- **Tool-call interception is the most underutilized leverage point.** The moment between "agent decides to call a tool" and "tool actually executes" is the cleanest place to inject safety, logging, cost control, and correction — and most teams don't wire it at all.
- **Hooks must be composable and ordered.** A naive hook implementation blocks you from adding a second concern. Real hook systems need a chain-of-responsibility with explicit ordering (before-tools, after-tools, around-tools) so that cost hooks, security hooks, and logging hooks can coexist independently.
- **Claude Code proved this at scale.** Anthropic's Claude Code (512K lines of TypeScript) exposes every capability through discrete, permission-gated tools with hook interception baked into the execution path. The permission prompt is not UI chrome — it is a mandatory gate between model intent and tool execution. 1,906 files of discipline built around the simple insight that the harness is where you enforce.

## The Move

Three concrete places to inject hooks, ordered from lowest to highest leverage:

### 1. Before-Tool Hooks (guard intercept)

Run before every tool call. This is where you block dangerous actions, enforce permission boundaries, check budgets, and validate arguments.

```python
# Hook: block shell commands that contain destructive flags
def before_bash(tool_name: str, args: dict, context: AgentContext) -> HookResult:
    if tool_name == "bash" and any(d in args.get("command", "") for d in ["rm -rf", "dropdb", "DROP TABLE"]):
        return HookResult(blocked=True, reason="Destructive command blocked by before-hook")
    return HookResult(allowed=True)

# Hook: enforce token budget per step
def before_llm(tool_name: str, args: dict, context: AgentContext) -> HookResult:
    if context.total_spent_tokens > context.token_budget:
        return HookResult(blocked=True, reason="Token budget exceeded")
    return HookResult(allowed=True)
```

### 2. After-Tool Hooks (post-execution validation)

Run after every tool call, regardless of success or failure. This is where you detect semantic failures (the tool succeeded but the result is wrong), record trajectories for evals, and trigger recovery paths.

```python
# Hook: detect silent failures via output shape validation
def after_tool(tool_name: str, result: Any, context: AgentContext) -> HookResult:
    # The tool returned 200 OK but empty data — suspicious
    if tool_name == "db_query" and result.get("rows") == [] and not context.user_asked_for_empty():
        logger.warning(f"Silent failure detected on {tool_name}, flagging for review")
        context.flags.append(("silent_empty_result", tool_name))
    # Record trajectory for eval harness
    context.trajectory.record(tool_name, args, result)
    return HookResult(allowed=True)
```

### 3. The Ratchet Principle (durable convention)

Every recurring failure should become a durable hook, not a retry. Add it to the hook chain — not to the prompt.

```python
# Anti-pattern: fix in the prompt
system_prompt += "\n- Never delete files in /prod without confirmation."

# Ratchet pattern: fix in the hook
class ProductionGuardHook:
    def before_bash(self, command: str, context: AgentContext) -> HookResult:
        if "/prod" in command and any(d in command for d in ["rm", "delete", "drop"]):
            return HookResult(blocked=True, reason="Prod deletion requires human confirmation")
        return HookResult(allowed=True)

# Hook chain composes — order matters
HOOK_CHAIN = [
    CostBudgetHook(),      # runs first — cheapest to fail fast
    ProductionGuardHook(), # runs second — enforces business policy
    SemanticValidatorHook(), # runs third — checks output shape
    TrajectoryRecorderHook(), # runs last — always records
]
```

The ratchet principle: every time an agent slips through a hook and causes a problem, the fix is a new hook entry in the chain, not a model swap or a prompt patch. Hooks are the production-grade way to encode institutional knowledge about what agents should and shouldn't do.

### 4. Around-Tool Hooks (retry + fallback injection)

Wraps a tool call in retry logic, circuit breaking, and fallback selection — all outside the model's control.

```python
def around_tool(tool_name: str, args: dict, context: AgentContext) -> HookResult:
    for attempt in range(3):
        result = execute_tool(tool_name, args)
        if result.success:
            return HookResult(allowed=True, result=result)
        if is_transient_error(result):
            continue
        if is_permanent_error(result):
            # Fall back to safer alternative
            fallback = get_fallback_tool(tool_name, args)
            return HookResult(allowed=True, result=execute_tool(fallback, args))
    return HookResult(blocked=True, reason=f"All {attempt} attempts failed")
```

## Receipt

> Verified 2026-07-15 — The hook-injection pattern is documented across three independent sources: Viv Trivedy's "Anatomy of an Agent Harness" (LangChain, March 2026), Addy Osmani's "Agent Harness Engineering" (Google, April/May 2026), and Claude Code's leaked architecture (Anthropic, March 2026). Claude Code's 512K-line codebase implements before/after/around hooks as first-class execution gates — not optional middleware. Real-world adoption confirmed via LangChain's open-source hooks API, Microsoft MAF hook system (BUILD 2026), and Databricks Omnigent hook registration. Production impact: LangChain reported 13.7 benchmark point improvement from harness-only changes (zero model changes).

## See also

- [S-366 · Harness Engineering: The Discipline Around the Model](stacks/s366-harness-engineering-the-discipline-around-the-model.md) — The broader discipline that makes hooks necessary
- [S-1145 · The Two-Layer Guard Stack](stacks/s1145-the-two-layer-guard-stack-when-your-prompt-guardrail-cant-see-the-tool-call-that-breaks-you.md) — Why prompt-level guards alone aren't enough; hooks fill the gap
- [S-1006 · The Agent Toolbelt Problem](stacks/s1006-the-agent-toolbelt-problem-what-tools-do-you-actually-give-an-agent.md) — Hooks are the mechanism for managing tool permissions at scale
- [S-1101 · The Execution Plane Stack](stacks/s1101-the-execution-plane-stack-when-your-agent-has-hands-but-theyre-unreliable.md) — Hooks live in the execution plane, not the reasoning layer
