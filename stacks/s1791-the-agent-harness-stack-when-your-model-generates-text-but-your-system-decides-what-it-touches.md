# S-1791 · The Agent Harness Stack — When Your Model Generates Text But Your System Decides What It Touches

You gave your agent a code editor tool. It rewrote `/etc/passwd`. You gave it a shell tool. It ran `rm -rf /`. The model didn't malfunction — the harness did. The language model generates text; the harness is everything that decides what that text can affect in the real world. This distinction is the most important architectural insight in agentic AI, and most teams building production agents have never heard of it.

## Forces

- **The LLM has no concept of privilege boundaries.** A model trained on internet text will cheerfully propose `curl | bash` or `DROP TABLE` if it looks like a reasonable next step in context. The model has no native understanding that a file is system-critical or that a query is destructive.
- **Harness choices compound into reliability.** Context management, permission tiers, hook placement, tool concurrency, error recovery, and sub-agent isolation are not independent decisions — they interact. A system with perfect tool definitions but no permission gating is one prompt injection away from catastrophe.
- **What you don't harness, you don't own.** Every capability you give an agent without a harness around it is a capability that can fail silently, cost unboundedly, or act irreversibly. The harness is not a feature on top of an agent — it is the agent's operating system.
- **Streaming-first architectures change failure modes.** Generator-based, streaming agent loops yield events as they arrive rather than batching responses. This enables real-time feedback but introduces new failure modes around partial output handling, mid-stream interruption, and out-of-order results.

## The Move

The agent harness sits between the language model and the real world. It is the infrastructure layer that every production-grade agent needs. Based on patterns from Claude Code's 512K-line TypeScript architecture (exposed March 2026) and Anthropic's public harness engineering documentation, here are the architectural layers that matter:

### Layer 1 — The Query Engine: Conversation Lifecycle

The query engine owns the conversation lifecycle: initialization, streaming coordination, budget tracking, and SDK interface.

```typescript
// Generator-based streaming query loop
async function* query(request: Request) {
  const state = initState(request);
  for await (const event of model.stream(state.messages)) {
    if (event.type === 'tool_call') {
      const result = await toolExecutor.dispatch(event.tool);
      state.messages.push(result); // feed back immediately
    }
    yield event; // stream to UI as it arrives
    state.tokenBudget -= tokens(event);
    if (state.tokenBudget <= 0) yield* compact(state);
  }
}
```

Key properties: **streaming-first** (never batch — yield events as they arrive), **token budget tracking** per conversation (stop or compact before the context window saturates), and **state machine discipline** (explicit transitions, not implicit accumulation).

### Layer 2 — Tool Registry and Permission Tiers

The tool registry maps model-proposed actions to real-world operations. Permission tiers classify tools by risk and gate execution accordingly. The three-tier model (community analysis of Claude Code):

| Tier | Behavior | Examples | Gating |
|------|----------|----------|--------|
| **T1 — Auto-execute** | No state change, reversible | Read file, web search, grep, ls | None — safe to run |
| **T2 — Prompt for confirmation** | Controlled state modification | File write, shell commands, git | User approval or Sonnet classifier in auto mode |
| **T3 — Block or require explicit approval** | Unpredictable or destructive | System-wide shell, external data exfiltration | Hard block — never auto-execute |

The T2 classifier sees the **user's request and the tool call** but **not the model's prose** — a deliberate design choice to prevent the model from sweet-talking its way past the gate. This separation is critical.

```typescript
class ToolRegistry {
  private tools: Map<string, Tool>;
  private permissions: PermissionMatrix;

  async execute(toolCall: ToolCall, request: Request): Promise<Result> {
    const tier = this.permissions.tier(toolCall.name, request.context);
    
    if (tier === 'block') throw new PermissionError('tool.blocked');
    
    if (tier === 'confirm') {
      const approved = await this.classifier.evaluate(request, toolCall);
      if (!approved) throw new PermissionError('tool.needs_approval');
    }
    // tier === 'auto': execute without gate
    return this.tools.get(toolCall.name).run(toolCall.args);
  }
}
```

### Layer 3 — Streaming Tool Executor

Tools run concurrently via a streaming executor. Results feed back into the model's context as they arrive — the model can see intermediate results and course-correct mid-execution rather than waiting for all tools to complete.

```typescript
class StreamingToolExecutor {
  async dispatch(toolCalls: ToolCall[]): Promise<Stream<Result>> {
    // Concurrent dispatch — model sees results as they complete
    const promises = toolCalls.map(tc => this.execute(tc));
    for await (const result of mergeStreams(promises)) {
      yield result; // feed back to model immediately
    }
  }
}
```

The key property: **the model reasons with partial results**, not after all tools return. This reduces the effective latency of parallel tool calls from `max(times)` to `approx 75th_percentile(times)`.

### Layer 4 — Context Management: What the Model Sees

Context is the model's working memory. Without active management it grows until the model starts wrapping up prematurely ("context anxiety") or degrades silently ("context exhaustion").

Three key mechanisms:

**Layered context** — feed the model only what is relevant to the current task, not the full conversation history:
```
System prompt (fixed) → Task context (task-specific) → Tool results (fresh) → Conversation history (summarized beyond a threshold)
```

**Context compaction** — triggered before budget exhaustion:
```typescript
function compact(state: AgentState): void {
  const summary = summarizeRecentConversation(state.messages, state.tokenBudget);
  state.messages = [...state.messages[0], ...summary, ...state.latestResults];
}
```

**Working memory isolation** — per-sub-agent context that does not leak into the parent conversation.

### Layer 5 — Hooks: Lifecycle Extension Points

Hooks allow external code to run at defined points in the agent lifecycle without modifying the agent itself:

```yaml
hooks:
  on_tool_call:
    - log_tool_request   # audit trail
    - check_policy       # policy engine gate
  on_tool_result:
    - log_result
    - update_trace
  on_error:
    - capture_state
    - alert_oncall
  on_compact:
    - preserve_critical_context  # don't summarize certain facts
```

Hooks are the integration surface for policy engines, observability pipelines, and custom recovery logic.

### Layer 6 — Sub-Agent Spawning and Isolation

Long-running tasks decompose into sub-agents. Claude Code's approach: the parent agent spawns sub-agents for bounded subtasks, each with isolated context and a structured handoff schema. The sub-agent writes results to a shared filesystem; the parent reads and synthesizes.

```typescript
async function spawnSubAgent(task: SubTask, parentCtx: Context): Promise<Result> {
  const isolated = parentCtx.fork({ maxTokens: SUB_AGENT_BUDGET });
  const result = await runAgent(task.instructions, isolated);
  await parentCtx.writeResult(task.id, result); // structured write, not raw text
}
```

The critical rule: sub-agents get **structured result envelopes** (task ID, output schema, status), not raw text dumps. The parent validates the schema before consuming the output.

## Receipt

> Verified 2026-07-28 — Sources: Anthropic Engineering "Harness Design for Long-Running Application Development" (March 24, 2026), Claude Code architecture analyses from GitHub gists by jischein and yanchuk (April 2026), community analyses of Claude Code v2.1.88 source code leak (March 31, 2026), Wavespeed AI blog "Claude Code Agent Harness: Architecture Breakdown" (April 6, 2026), Plain English "12 Agentic Harness Patterns from Claude Code" (April 8, 2026). Key architectural facts traced to these primary sources. No entries currently cover the full 6-layer harness stack.

## See also

- [S-1006 · The Agent Toolbelt Problem](stacks/s1006-the-agent-toolbelt-problem-what-tools-do-you-actually-give-an-agent.md) — what tools to include, before discussing how to gate them
- [S-1013 · The Multi-Agent Boundary Stack](stacks/s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — structured handoff schemas and isolation for multi-agent scenarios
- [S-1458 · The Policy-Kernel Stack](stacks/S-1458-the-policy-kernel-stack-when-your-agent-ecosystem-has-no-enforcer.md) — enforceable policy engines that complement permission tiers
- [S-1789 · The Failure Containment Stack](stacks/s1789-the-failure-containment-stack-when-your-agent-wont-stop-failing.md) — token budgets and stop conditions as first-class harness concerns
