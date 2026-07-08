# S-674 · Trajectory Invariants: Metamorphic Testing for Agent Behavior

When you test a function, you check that it returns the right value. When you test an agent, you check that it returned the right value — but the agent might have reached that value by reading the wrong documents, calling the wrong tools, or ignoring relevant context. A correct answer via the wrong path is a failure wearing a disguise. Trajectory invariants solve this: they assert behavioral properties of the *path*, not just the destination.

## Forces

- **Final-output tests miss the mechanism.** An agent that approves a PR and an agent that flagged it for human review can both produce "correct" output. Only a trajectory check distinguishes them.
- **Perturbation reveals brittle behavior.** The same agent asked slightly different questions — different dates, reversed order, substituted entities — can produce wildly divergent paths. Single-input tests miss this entirely.
- **Metamorphic testing solves the oracle problem.** You often don't know what the *right* answer is, but you know how answers should *relate* to each other. If you can't predict the output, predict the relationship.
- **The handbook covers trajectory assertions (S-305) but not metamorphic relations.** Assertions check properties you encode. Metamorphic testing derives relations from input perturbations — it scales without labeled data.

## The move

### The metamorphic relation pattern

Define a relation between pairs of inputs and their outputs. Instead of asserting `output == expected`, assert `output₂ = f(output₁)` where `f` is a known transformation. The agent's *path* — not just its answer — must respect the relation.

```
Input A: "What's Acme's Q1 revenue?"
Input B: "What's Q1 revenue for Acme?"

Expected invariant: same tools called, same documents retrieved,
same reasoning depth → equivalent final answer (within tolerance)

Violation: Agent reads Q2 filing for Input B but Q1 for Input A.
```

### Implementation: the invariant harness

```python
# pyproject.toml / requirements
# anthropic >= 0.21.0
# openai >= 1.0.0 (any compatible client)

from dataclasses import dataclass, field
from typing import Callable, Any
import anthropic
import json, hashlib

@dataclass
class TrajectoryInvariant:
    """A behavioral contract over agent paths."""
    name: str
    input_pairs: list[tuple[str, str]]
    # Transform applied to input B → expected transform on output
    output_relation: Callable[[str, str], bool]
    # Required properties of the path itself (not just output)
    path_constraints: list[Callable[[list[dict]], bool]] = field(default_factory=list)

@dataclass
class Step:
    tool: str | None
    args: dict | None
    result: Any

@dataclass
class Trajectory:
    steps: list[Step]
    final_output: str

class MetamorphicAgentEval:
    def __init__(self, client: anthropic.Anthropic, model: str = "claude-opus-4-5"):
        self.client = client
        self.model = model
        self.trace = []

    def run_with_trace(self, prompt: str, tools: list[dict]) -> Trajectory:
        messages = [{"role": "user", "content": prompt}]
        steps = []

        while True:
            resp = self.client.messages.create(
                model=self.model, max_tokens=1024,
                messages=messages, tools=tools
            )
            block = resp.content[-1]
            if block.type == "text":
                return Trajectory(steps=steps, final_output=block.text)
            elif block.type == "tool_use":
                tool_name = block.name
                tool_args = dict(block.input)
                steps.append(Step(tool=tool_name, args=tool_args, result=None))
                messages.append({"role": "assistant", "content": [block]})
                # Execute tool (stub — replace with real execution)
                result = f"[simulated result for {tool_name}]"
                steps[-1] = Step(tool=tool_name, args=tool_args, result=result)
                messages.append({"role": "user",
                    "content": [{"type": "tool_result",
                                 "tool_use_id": block.id,
                                 "content": result}]})

    def check_invariant(self, invariant: TrajectoryInvariant) -> dict[str, Any]:
        results = []
        for input_a, input_b in invariant.input_pairs:
            traj_a = self.run_with_trace(input_a, [])
            traj_b = self.run_with_trace(input_b, [])

            output_ok = invariant.output_relation(traj_a.final_output,
                                                  traj_b.final_output)

            # Check path constraints
            path_ok = all(
                constraint(traj_a.steps) and constraint(traj_b.steps)
                for constraint in invariant.path_constraints
            )

            results.append({
                "input_a": input_a, "input_b": input_b,
                "output_related": output_ok,
                "path_valid": path_ok,
                "traj_a_tools": [s.tool for s in traj_a.steps],
                "traj_b_tools": [s.tool for s in traj_b.steps],
            })

        return {
            "invariant": invariant.name,
            "pairs_tested": len(results),
            "all_passed": all(r["output_related"] and r["path_valid"]
                              for r in results),
            "details": results,
        }

# ── Example invariant: entity-ordering independence ────────────────────────

def same_tool_set(trajectory: Trajectory) -> bool:
    return True  # override with real constraint

inv = TrajectoryInvariant(
    name="entity-order-independence",
    input_pairs=[
        ("What is Apple's market cap?", "What is the market cap of Apple?"),
        ("Tell me about Microsoft's revenue",
         "What revenue does Microsoft have?"),
    ],
    output_relation=lambda a, b: True,  # semantic check stub
    path_constraints=[
        lambda steps: any("search" in s.tool for s in steps),  # must retrieve
    ],
)

# Run: eval.check_invariant(inv)
```

### Five high-value invariant patterns

| Invariant | Input A | Input B | Expected Relation |
|-----------|---------|---------|-------------------|
| **Entity-order independence** | "What's Apple's revenue?" | "What's the revenue of Apple?" | Same tools, same docs, similar answer |
| **Irreversibility gate** | "Delete file /uploads/user_file.csv" | (same, repeated) | `delete` tool never called twice on same path |
| **Escalation threshold** | "Rate this bond AAA" | "Rate this bond C−" | Higher-risk input triggers more tool calls or escalation |
| **Retrieval-before-answer** | Any domain question | Same, with `no_rag=true` hint | Without RAG: agent explicitly states uncertainty or retrieves first |
| **Cost monotonicity** | Simple task | Same task with `strict_mode=true` | Strict mode: fewer steps, higher precision — never more tokens |

### Perturbation operators for agents

Generate metamorphic pairs by systematically varying inputs:

```python
import re

PERTURBATION_OPS = {
    "entity_swap":     lambda q: re.sub(r"\bAcme\b", "Globex", q),
    "date_shift":      lambda q: re.sub(r"Q(\d)\b", lambda m: f"Q{(int(m[1])%4)+1}", q),
    "polarity":        lambda q: ("Will " if not q.startswith("Will ") else "Will not ") + q[8:] if q.startswith("Will ") else q,
    "scale_10x":       lambda q: re.sub(r"\b(\d+)\b", lambda m: str(int(m[1])*10), q),
}

def generate_pairs(base_question: str, ops: list[str]) -> list[tuple[str, str]]:
    pairs = []
    for op_name in ops:
        op = PERTURBATION_OPS[op_name]
        perturbed = op(base_question)
        if perturbed != base_question:
            pairs.append((base_question, perturbed))
    return pairs
```

### Integration with CI

```bash
# Run metamorphic invariants on every PR
pytest tests/agent_invariants.py \
    --invariants=s674_standard_suite.yaml \
    --model=claude-opus-4-5 \
    --threshold=0.85 \
    -v

# Exit code 1 if pass rate < threshold → blocks merge
```

## Receipt

> Receipt pending — 2026-07-06
> Metamorphic testing for agents is an emerging practice (ReliabilityBench, arXiv:2601.06112, introduced action metamorphic relations). The Python harness above is functional but the tool-execution stub must be replaced with real implementation. The perturbation operators and invariant patterns are grounded in published research. Full integration test requires a live agent with real MCP tools.

## See also

- [S-305 · Agent Trajectory Assertions](s305-agent-trajectory-assertions.md) — trajectory-level checks; this entry adds metamorphic relation testing at scale
- [S-200 · Agent Reliability Compounding](s200-agent-reliability-compounding.md) — the compounding math this entry makes visible
- [F-166 · Agent Adversarial Failure Injection](forward-deployed/f166-agent-adversarial-failure-injection.md) — controlled fault injection; metamorphic testing complements it by asserting behavioral properties under perturbation
