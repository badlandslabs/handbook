# S-1675 · The Behavior Tree Agent Stack — When Your Agent Loop Is Uncharted Water and Nobody Can Trace It

When your agent needs to handle failures gracefully, try multiple strategies, run sub-tasks in parallel, and still produce a predictable result — and you can't tell whether it will hit the fallback, the retry, or the dead end until you're already in production.

## Forces

- **Free-form loops are uncharted territory.** A ReAct-style `while not done: think → act → check` loop has no explicit branches, no defined failure paths, and no way to enumerate what the agent *should* do when a tool call fails. The model decides at runtime — and you trace it after the fact or not at all.
- **Orchestration frameworks solve the problem they were built for, not yours.** LangGraph gives you a state graph but requires you to define every edge and condition. A behavior tree gives you composable, named patterns (try this, then that, or that) that encode failure logic as structure, not code.
- **The escalation-from-chain gap is real but narrow.** S-1673 covers graduating from chains to state graphs. This covers what to reach for *inside* the state graph: the hierarchical, composable control-flow pattern that makes agent logic testable without running the agent.
- **Testability and reliability are the same problem.** An agent you can't test in isolation is an agent that will fail silently in production. Behavior trees decompose into nodes that can be unit-tested independently.

## The move

Model your agent's decision logic as a **behavior tree** — a hierarchical structure of composable nodes that execute in a defined order, with explicit fallback paths and named traversal.

### Node types

| Node | Symbol | What it does |
|---|---|---|
| **Sequence** | `→` | Run children left-to-right; succeed if all succeed |
| **Selector** | `?` | Run children left-to-right; succeed on first success |
| **Fallback** | `↺` | Run children left-to-right; succeed on first success; used for recovery |
| **Parallel** | `∥` | Run children concurrently; merge results |
| **Decorator** | `◻` | Wrap a child with a condition (retry N times, invert result, cap depth) |

### Minimal implementation

```python
from enum import Enum
from dataclasses import dataclass, field
from typing import Callable, Optional

class Status(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    RUNNING = "running"

@dataclass
class BehaviorNode:
    name: str
    run: Callable[[], Status]
    children: list["BehaviorNode"] = field(default_factory=list)
    max_retries: int = 0

    def execute(self, depth: int = 0) -> Status:
        indent = "  " * depth
        print(f"{indent}{self.name}...")
        result = self._execute(depth)
        print(f"{indent}{self.name} → {result.value}")
        return result

    def _execute(self, depth: int) -> Status:
        raise NotImplementedError


class SequenceNode(BehaviorNode):
    def _execute(self, depth: int) -> Status:
        for child in self.children:
            status = child.execute(depth + 1)
            if status == Status.FAILURE:
                return Status.FAILURE
        return Status.SUCCESS


class SelectorNode(BehaviorNode):
    def _execute(self, depth: int) -> Status:
        for child in self.children:
            status = child.execute(depth + 1)
            if status == Status.SUCCESS:
                return Status.SUCCESS
        return Status.FAILURE


class FallbackNode(BehaviorNode):
    """Fallback: try children until one succeeds. Use for recovery strategies."""
    def _execute(self, depth: int) -> Status:
        for child in self.children:
            status = child.execute(depth + 1)
            if status == Status.SUCCESS:
                return Status.SUCCESS
        return Status.FAILURE


class DecoratorRetry(BehaviorNode):
    child: BehaviorNode = field(default_factory=BehaviorNode)

    def _execute(self, depth: int) -> Status:
        for attempt in range(self.max_retries + 1):
            result = self.child.execute(depth + 1)
            if result == Status.SUCCESS:
                return Status.SUCCESS
            print(f"{'  ' * (depth+1)}retry {attempt+1}/{self.max_retries}")
        return Status.FAILURE


class ToolCallNode(BehaviorNode):
    """Leaf node: run a tool and return success/failure based on response."""
    tool_fn: Callable = field(default=None)
    args: dict = field(default_factory=dict)

    def _execute(self, depth: int) -> Status:
        try:
            result = self.tool_fn(**self.args) if self.tool_fn else Status.SUCCESS
            return Status.SUCCESS if result else Status.FAILURE
        except Exception:
            return Status.FAILURE
```

### Assembling a task agent

```python
# Define leaf nodes (tools)
fetch = ToolCallNode(name="fetch_context", tool_fn=retrieve_context)
search = ToolCallNode(name="web_search", tool_fn=do_search)
draft = ToolCallNode(name="draft_response", tool_fn=generate_draft)
validate = ToolCallNode(name="validate_output", tool_fn=check_schema)

# Recovery fallback: try search, fall back to cached
search_fallback = FallbackNode(name="knowledge_source", children=[
    search,
    ToolCallNode(name="use_cache", tool_fn=retrieve_from_cache),
])

# Retry the full fetch step up to 2 times
fetch_with_retry = DecoratorRetry(
    name="fetch_retry",
    max_retries=2,
    child=search_fallback,
)

# Main sequence: fetch → draft → validate
task_tree = SequenceNode(name="task", children=[
    fetch_with_retry,
    draft,
    DecoratorRetry(
        name="validate_retry",
        max_retries=1,
        child=validate,
    ),
])

# Execute
result = task_tree.execute()
```

### What you get

- **Named nodes, not raw code.** Every decision point has a label. Traversal output reads like a structured log: `task → fetch_retry → knowledge_source → web_search → FAILURE → use_cache → SUCCESS → draft_response → SUCCESS → validate_retry → validate_output → SUCCESS`.
- **Composable failure paths.** Add a new fallback strategy by inserting a child node. No rewiring.
- **Unit-testable leaves.** Each tool call node mocks its `tool_fn` and asserts on status, without running the LLM.
- **Depth and retry caps.** Decorator nodes prevent runaway loops without adding branching logic to every node.
- **Explicit over implicit.** The tree structure *is* the documentation of what the agent tries and in what order.

### Comparison with alternatives

| Pattern | Testability | Failure explicitness | Complexity |
|---|---|---|---|
| ReAct loop | None | Runtime inference only | Low |
| Behavior tree | Node-level | Named fallback paths | Low–medium |
| State machine (LangGraph) | State-level | Conditional edges | Medium |
| Full orchestrator (CrewAI) | Task-level | Built-in | Medium–high |

Behavior trees sit between ReAct (too implicit) and a full state machine (too much upfront design). They encode the "what to try next" logic that ReAct delegates to the model, making it explicit, named, and testable.

## See also

- [S-1673 · Orchestration Graduation](s1673-the-orchestration-graduation-stack-when-to-escalate-from-prompt-chains-to-state-graphs.md) — when to escalate from chains to structured graphs
- [S-1033 · Behavioral Version](s1033-the-behavioral-version-stack-when-your-git-log-is-clean-but-your-agent-is-broken.md) — tracking which tree revision shipped
- [S-1046 · Agent Dead End](s1046-the-agent-dead-end-stack-when-your-agent-fails-and-cant-recover.md) — the terminal failure node pattern
- [F-65 · Prompt Regression Testing](forward-deployed/f65-prompt-regression-testing.md) — testing tree traversal outcomes

## Sources

- StateFlow (COLM 2024): FSM-based agent paradigm, 13–28% task success improvement vs. ReAct, 3–5× cost reduction
- AgentMarketCap (Apr 2026): "Agent State Machine Design Pattern" — FSMs outperform free-form LLM planning in production
- Zylos Research (Apr 2026): "Finite State Machines and Statecharts for AI Agent Orchestration" — prompts as first-class state machine components
- NVIDIA 2026 State of AI Report: "state consistency during failures" cited as top operational challenge ahead of model accuracy and cost
- SkillGen (Jun 2026): BT vs FSM comparison for agent state management with production implementation patterns
- Microsoft AutoGen / StateFlow research: quantified error amplification problem in free-form multi-step agents
