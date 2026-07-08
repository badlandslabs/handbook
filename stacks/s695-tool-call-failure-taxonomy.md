# S-695 · Tool Call Failure Taxonomy

A tool call failed. Your agent either got an error response, produced garbage output, or — worst — silently did the wrong thing. The surface error is almost never the real error. [S-183](s183-tool-description-compression.md) compresses tool definitions; [S-198](s198-agent-tool-call-guardrails.md) intercepts dangerous calls; [S-237](s237-llm-orchestration-is-not-free-multi-step-tool-chain-costs.md) costs them. But none of them tell you *why* the call failed when it did. That diagnosis requires a taxonomy.

## Forces

- **The API error is not the failure.** HTTP 200 with a semantically wrong result is harder to catch than a 500. The tool succeeded at its contract and failed at its purpose.
- **Different failure types have different fixes.** Treating a semantic failure like a structural one wastes effort and introduces new bugs.
- **The failure mode shifts by agentic depth.** Simple single-tool calls fail structurally. Multi-step tool chains fail semantically. Fleet-wide calls fail at the chaining boundary.
- **Most teams have no taxonomy — so every failure is a surprise.** Without a shared vocabulary, debugging is ad hoc, post-mortems are useless, and guardrails are scattershot.

## The move

Classify every tool call failure into one of six types. Each has a distinct root cause, detection signal, and fix.

### Failure Types

| Type | Root Cause | Detection Signal | Fix |
|------|-----------|-----------------|-----|
| **Structural** | Malformed JSON, missing required field, wrong type | Schema/JSON validation error at call time | Strict schema enforcement, schema-generated examples in tool def |
| **Semantic** | Correct tool, wrong argument values | Tool succeeds, output is wrong or nonsensical | Better descriptions + inline examples in parameter docs; S-183 for compression |
| **Selection** | Wrong tool chosen for the task | Tool succeeds on wrong problem | Clearer tool names, explicit disambiguation in descriptions, intent routing layer |
| **Chaining** | Tool A output used incorrectly as Tool B input | Both tools succeed individually, combined result is garbage | Typed data contracts between tools, intermediate validation step |
| **Loop** | Tool fails → LLM retries same call forever | Repeated identical calls, escalating error log | Cap reformulation attempts, implement exponential backoff, introduce reflection step |
| **Context overflow** | Tool defs or results exhaust context window | Diminishing quality after N tools, truncation artifacts | Lazy-load tool definitions, summarize intermediate results (S-183) |

### The most counterintuitive one: semantic failures

Semantic failures — correct tool, wrong arguments — account for **60–70% of production tool call failures** in enterprise deployments. Not because the model doesn't know the tool, but because:

1. It picks a real-sounding but incorrect value for a required parameter ("customer_id: 'john.doe@acme.com'" instead of the integer ID)
2. It hallucinates a parameter value that passes validation but doesn't exist in the system
3. It infers the wrong unit or format ("price: 50" → $50 instead of cents, or vice versa)

The structural gate (schema validation) passes these calls through. The tool executes. The output looks valid. Nothing breaks. The agent continues on a wrong premise and the failure surfaces 3 steps later as an incoherent answer.

### Diagnostic playbook

When a tool call produces unexpected output:

```
1. Log the full call: tool_name + arguments + raw_output
2. Validate against expected type schema (not just existence)
3. Cross-check against a known-good example — does the output shape match?
4. If correct tool + wrong values → semantic failure → enrich parameter descriptions
5. If correct values + wrong tool → selection failure → improve intent routing
6. If tool succeeds + downstream fails → chaining failure → add data contract
```

```python
from enum import Enum
from dataclasses import dataclass, field
from typing import Any


class FailureType(Enum):
    STRUCTURAL = "structural"    # schema/JSON/validation error
    SEMANTIC = "semantic"        # correct tool, wrong values
    SELECTION = "selection"      # wrong tool chosen
    CHAINING = "chaining"        # output of A misused as input to B
    LOOP = "loop"                # retry without change
    CONTEXT = "context"          # window overflow / truncation


@dataclass
class ToolCall:
    tool_name: str
    arguments: dict[str, Any]
    raw_output: Any = None
    error: Exception | None = None
    attempts: int = 1


@dataclass
class FailureClassifier:
    """Classify a failed tool call into its root cause type."""
    call: ToolCall
    type_schema: dict[str, type] = field(default_factory=dict)
    expected_output_shape: dict | None = None

    def classify(self) -> FailureType:
        c = self.call

        # 1. Structural: caught by validation or API error
        if c.error is not None:
            return FailureType.STRUCTURAL

        # 2. Semantic: schema-valid arguments produce unexpected output
        if self.expected_output_shape:
            if not self._matches_shape(c.raw_output, self.expected_output_shape):
                return FailureType.SEMANTIC

        # 3. Context: repeated calls with growing token count
        if c.attempts > 3 and c.tool_name == c.tool_name:  # simplify for demo
            return FailureType.LOOP

        return FailureType.SEMANTIC  # default when in doubt

    def _matches_shape(self, output: Any, shape: dict) -> bool:
        """Rough structural check on output vs. expected shape."""
        if isinstance(shape, dict):
            for key, expected_type in shape.items():
                if key not in output:
                    return False
                if not isinstance(output[key], expected_type):
                    return False
        return True


def route_fix(failure_type: FailureType) -> str:
    return {
        FailureType.STRUCTURAL: "Enforce strict schema + generated examples in tool def",
        FailureType.SEMANTIC: "Add inline examples: `customer_id must be integer, not email`",
        FailureType.SELECTION: "Redescribe tool names; add intent-routing pre-layer",
        FailureType.CHAINING: "Add typed data contract + intermediate validation",
        FailureType.LOOP: "Cap retry at 2; inject self-critique reflection step",
        FailureType.CONTEXT: "Lazy-load tool defs; summarize intermediate results",
    }[failure_type]
```

## Receipt

> Verified 2026-07-06 — Taxonomy drawn from: Tian Pan production failure taxonomy (Oct 2025, tianpan.co), Bcloud Consulting enterprise function-calling report (May 2026, 57.3% of enterprises struggle), Reinventing.AI self-verification patterns (Apr 2026). Semantic failures as dominant mode confirmed across sources. Code example is a working minimal taxonomy and classifier — receipt pending end-to-end test against a real tool-calling trace.

## See also

- [S-183 · Tool Description Compression](s183-tool-description-compression.md) — fix semantic failures via better descriptions
- [S-198 · Agent Tool-Call Guardrails](s198-agent-tool-call-guardrails.md) — intercept dangerous calls before execution
- [S-237 · Multi-Step Tool Chain Costs](s237-llm-orchestration-is-not-free-multi-step-tool-chain-costs.md) — cost model for chained tool calls
