# S-2614 · The Harness Engineering Loop Stack — When the Model Is Not Your Problem and You Change Everything Anyway

Your agent scores 52.8% on the benchmark. You upgrade to a better model — it scores 53.1%. You hire a prompt engineer — 53.4%. Then someone rewrites the harness: the same model scores 66.5% and lands in the top 5 on the leaderboard. The model never changed. The harness did everything.

This is the core empirical finding of 2026's harness engineering discipline: **the model is rarely the bottleneck**. The execution environment, tooling surface, verification logic, and state management around the model — the harness — is where most of the action is. And it is optimizable in ways that model upgrades are not: deterministically, iteratively, and with measurable signal.

## Forces

- **Agent quality is harness-defined, not model-defined.** A coding agent on Terminal Bench 2.0 gained 13.7 points (52.8 → 66.5%) by harness changes alone, with the model held constant. The harness shapes how the model's capability maps to task outcomes.
- **Harness improvements compound.** Unlike model upgrades (one-time discrete gains), a well-designed harness feeds improvements forward: better traces from the improved agent become better eval seeds, which reveal more harness gaps, which produce better traces. This is a flywheel, not a one-shot.
- **You cannot hill-climb without a signal.** Harness engineering without evals is guesswork. Evals without harness iteration is theater. The loop requires both: eval failures as the signal, harness changes as the action.
- **Trace data is the training set you already have.** Production runs generate millions of tokens of trajectory data. This is the richest eval seed source available — more representative than hand-crafted test cases, and it surfaces failure modes that nobody would think to invent.
- **Self-verification closes the loop inside the agent.** Adding a self-check step to the harness (verify this plan before executing it) is the single highest-leverage harness modification for coding agents on tool-use benchmarks.

## The Move

The harness is the structured runtime that turns a language model into an agent: system prompt, tool definitions, execution flow, verification logic, state management, and observability hooks. **Harness engineering** is the iterative discipline of modifying these components to improve agent behavior, using evals as the learning signal.

The canonical loop:

```
Production traces → eval seed extraction → eval case authoring
     ↑                                              ↓
improved harness ← harness modification ← eval failures
```

### Move 1: Self-Verification as a Harness Primitive

Add a verification step inside the harness before the agent acts. Before executing a tool call sequence, the agent evaluates its own plan against a checklist:

```python
class HarnessWithSelfVerification:
    def __init__(self, model, tools, max_retries=2):
        self.model = model
        self.tools = tools
        self.max_retries = max_retries

    def execute(self, task):
        plan = self.model.think(f"Plan: {task}\nTools: {self.tools}")
        
        # Self-verification loop — the harness modification
        for attempt in range(self.max_retries):
            check = self.model.judge(
                f"Does this plan accomplish the task correctly?\n{plan}\n\n"
                f"Task: {task}\n"
                f"Tool set: {self.tools}"
            )
            if check.approved:
                break
            plan = self.model.revise(f"Revise: {plan}\nFeedback: {check.feedback}")
        
        return self._execute_plan(plan)

# On SWE-bench Lite: ~15% absolute improvement from self-verification alone
# Source: LangChain Deep Agents, Feb 2026
```

This is not prompt engineering — it is execution flow modification. The verification happens inside the harness loop, with its own LLM call, independent of the planning call.

### Move 2: Traces as the Eval Seed Bank

Production traces are the highest-signal data for generating new eval cases. The pattern:

1. **Mine production traces** for failures (tool-call errors, plan revisions, retry loops)
2. **Convert failures to eval seeds** — each failure is a concrete scenario with known inputs, expected behavior, and a reason it broke
3. **Expand seeds** — generate N variants per seed (change the domain context, not the failure mode) to create distributional coverage
4. **Gate with current agent** — only add to the pinned eval set if the expanded variants still fail against the current agent; passing cases aren't gaps

```python
from traces import TraceStore

store = TraceStore()  # LangSmith, Phoenix, custom — any OTEL-compatible store

def mine_eval_seeds(store: TraceStore, min_failure_score=0.3) -> list[EvalCase]:
    """Convert production failures into eval seed bank."""
    traces = store.query(
        filter="has_tool_error == true OR revision_count > 3",
        lookback="30d",
        limit=1000
    )
    seeds = []
    for trace in traces:
        failure_type = classify_failure(trace)
        variants = generate_variants(trace, n=5, preserve_failure_mode=True)
        
        # Gate: only add if current agent still fails
        if not agent.passes(trace.as_eval_case()):
            seeds.append(trace.as_eval_case())
            seeds.extend(variants)
    
    return seeds
```

### Move 3: The Compound Harness System

LangChain's arXiv:2604.25850 frames this as compound systems: layers of tooling that amplify each other. The most effective compound harness combines:

| Component | Purpose | Leverage |
|---|---|---|
| System prompt | Task framing, output format | Low–medium (diminishing returns) |
| Tool definitions | What the agent can do | High (wrong tool = wrong trajectory) |
| Execution flow | Loop structure, branching logic | High (controls path shape) |
| Self-verification | Pre-execution plan check | Very high on coding tasks |
| Trace instrumentation | Feedback signal | Required for iterative improvement |
| Eval harness | Regression gate | Required for safe deployment |

The insight: **each component has a different leverage multiplier**. Teams that optimize system prompts exhaust their gains quickly. Teams that design execution flows and add self-verification to tool-calling loops are still finding gains.

## Receipt

> Verified 2026-08-14 — Core findings from three independently documented sources: (1) LangChain Deep Agents Feb 2026: coding agent went from 52.8% → 66.5% on Terminal Bench 2.0 (Top 30 → Top 5) with harness changes only, model held constant. (2) arXiv:2604.25850 J Lin "Agentic Harness Engineering" — formalizes observability-driven harness evolution for coding agents; 29 citations as of 2026. (3) LangChain Better-Harness recipe (Apr 2026) and Trace-as-Training-Data post (Jul 2026) — concrete implementation patterns with 6-step harness hill-climbing recipe. Real tradeoffs: self-verification adds latency (1 extra LLM call per attempt, ~500ms–2s per step), which matters for real-time use cases; compound harness systems increase debugging complexity; eval seed extraction requires trace instrumentation to be present from the start — retrofitting is expensive.

## See also

- [S-2565 · The Regression Test Flywheel](stacks/s2565-the-regression-test-flywheel-stack-when-your-agent-ships-fine-but-you-cannot-prove-it.md) — the CI/regression side of the same loop
- [S-2561 · The ETCLOVG Harness Layering](stacks/s2561-the-etclovg-harness-layering-stack-when-your-trace-says-failed-but-you-cannot-find-where.md) — anatomy of the seven harness layers
- [S-2589 · The Trajectory Eval Stack](stacks/s2589-the-trajectory-eval-stack-when-your-agent-succeeds-at-the-wrong-thing.md) — why trajectory-level eval is needed to drive harness improvements
- [S-2605 · The Tool Description Engineering Stack](stacks/s2605-the-tool-description-engineering-stack-when-your-system-prompt-is-not-where-your-tool-selection-decisions-get-made.md) — tool definitions as the highest-leverage harness surface
