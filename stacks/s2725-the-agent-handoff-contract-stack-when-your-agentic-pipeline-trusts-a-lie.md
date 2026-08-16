# S-2725 · The Agent Handoff Contract Stack — When Your Agentic Pipeline Trusts a Lie

You built a three-stage pipeline: Research agent → Analysis agent → Writer agent. On the happy path, it works beautifully. In production, you discover that the Research agent sometimes returns a JSON field as a string instead of an array, sometimes omits the confidence score entirely, and once returned an empty string because it couldn't find relevant data. The Analysis agent accepted all of it. The Writer agent shipped a confident report based on nothing. Nobody got an error. Nobody got the truth.

This is the handoff contract problem — and it is the invisible linchpin of every multi-agent pipeline that isn't explicitly designed around it.

## Forces

- **LLM outputs are untyped by default.** An agent that "returns a list of findings" might return a JSON array, a natural-language paragraph, a Markdown bullet list, or an apology. The consuming agent tries to parse it anyway. The failure is silent.
- **Schema mismatches propagate, not fail.** A malformed output from Agent A doesn't cause a visible error — it causes Agent B to reason from garbage and produce garbage with high confidence. By the time you see the bad output, three agents have each validated the previous agent's work against their own, equally loose, expectations.
- **Frameworks assume trust.** LangGraph, CrewAI, and AutoGen all model multi-agent pipelines as function calls — but unlike software functions, LLM outputs have no return-type guarantee. No current major framework provides a native typed-contract mechanism at agent boundaries. This is architectural debt that lives in your prompts and breaks silently in production.
- **The evaluation surface grows exponentially.** A single-agent system has one input-output contract to validate. A 3-agent pipeline has three sequential contracts plus the cross-product of how each agent might interpret the others' ambiguous outputs. At N agents, naive testing covers O(N) while the actual failure surface is O(N²).

## The move

**Define typed output envelopes for every agent handoff. Validate at the boundary, not inside the agents.**

The contract is a Pydantic model (or equivalent) that specifies the exact schema the producing agent must return. The validation gate runs immediately after the agent produces output and immediately before the consuming agent receives it. If validation fails, the pipeline halts, logs the specific violation, and retries or escalates — it does not proceed.

### Layer 1 — Output Envelope Contract

Each agent returns a typed envelope, not raw text:

```python
from pydantic import BaseModel, Field
from typing import Optional

class ResearchFindingsEnvelope(BaseModel):
    """Contract: what the Research agent MUST return."""
    findings: list[dict] = Field(
        description="List of research findings, each with 'claim', 'source', and 'confidence'"
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Overall confidence score for the research quality"
    )
    coverage: str = Field(
        description="One of: 'full', 'partial', 'insufficient'"
    )
    citations: list[str] = Field(
        description="Source URLs or references"
    )
    _schema_version: str = "1.0"  # enables schema evolution
```

The agent still produces natural language internally. The envelope wraps the output. The envelope is what gets passed to the next agent.

### Layer 2 — Validation Gate

```python
def handoff_gate(agent_output: str, contract: type[BaseModel]) -> BaseModel:
    """Validate agent output against its handoff contract."""
    try:
        parsed = json.loads(agent_output)
        return contract.model_validate(parsed)
    except json.JSONDecodeError:
        # Fallback: try to extract JSON from markdown code blocks
        import re
        match = re.search(r"```(?:json)?\n(.*?)\n```", agent_output, re.DOTALL)
        if match:
            parsed = json.loads(match.group(1))
            return contract.model_validate(parsed)
        raise HandoffContractViolation(
            f"Agent output is not valid JSON. "
            f"Cannot validate against {contract.__name__}."
        )
```

### Layer 3 — Confidence-Gated Routing

Not all failures are equal. A missing optional field is recoverable. A missing required field is not. A confidence score below threshold is worth surfacing to a human. Map violations to actions:

| Violation | Action |
|-----------|--------|
| Schema parse failure | Retry agent once, then escalate |
| Required field missing | Retry with explicit field instruction, then escalate |
| Confidence below threshold | Log + route to human review before proceeding |
| Coverage = "insufficient" | Abort pipeline, do not pass to Analysis agent |
| Schema version mismatch | Reject, pin to known-good version |

### Layer 4 — Schema Versioning

Agents evolve. The Research agent's output schema changes when you add a new field. Without versioning, a schema change silently breaks the downstream agent. Pin a schema version in every envelope. Maintain a migration path:

```python
class ResearchFindingsEnvelope(BaseModel):
    _schema_version: str = "1.1"  # bump when adding optional fields
    _migration_hint: str = "v1.0→v1.1: added 'tags' field (optional)"

    # New field with default so old consumers don't break
    tags: list[str] = Field(default_factory=list)
```

Enforce schema compatibility: additive changes (new optional fields) are backward-compatible. Breaking changes (renaming required fields, changing types) require a schema version bump and a consumer-side migration.

### Layer 5 — Observable Handoff Traces

Every handoff should emit a structured span:

```python
def trace_handoff(
    from_agent: str,
    to_agent: str,
    validated_output: BaseModel,
    validation_errors: list[str],
    attempt: int,
):
    span = {
        "type": "agent_handoff",
        "from": from_agent,
        "to": to_agent,
        "schema_version": validated_output._schema_version,
        "validation_passed": len(validation_errors) == 0,
        "violations": validation_errors,
        "attempt": attempt,
        "output_size_bytes": validated_output.model_dump_json().__len__(),
    }
    otel_tracer.emit(span)
```

This gives you the failure surface that S-05 doesn't: you can query "how many handoffs had schema violations this week?" and "which agent-pair had the highest error rate?"

## Receipt

> Receipt pending — 2026-08-16. The validation gate pattern (Pydantic contracts at agent boundaries) is demonstrated in [4mritz/multi-agent-systems-validation](https://github.com/4mritz/multi-agent-systems-validation) and [iamraghuveer.com](https://www.iamraghuveer.com/posts/agent-output-schema-validation) (both Apr 2026). The typed envelope pattern is validated in Sam Griffith's "Contract-Driven Agents" (Jun 2026) and the Vox Foundation agent-handoff-contract schema (2026). The RAND 80–90% multi-agent failure rate is cited by [Precise Impact AI](https://www.preciseimpact.ai/blog/how-to-design-ai-agent-handoff-protocols). The inter-agent error propagation example (hallucinated cost figure compounding through 3 agents) is documented in the same Precise Impact source.

## See also

[S-05 · Multi-Agent Patterns](s05-multi-agent-patterns.md) — orchestration topologies (fan-out, pipeline, supervisor)
[S-1034 · The Role Fence Stack](s1034-the-role-fence-stack-when-your-multi-agent-system-keeps-tripping-over-itself.md) — agent role isolation within shared pipelines
[S-1032 · The Dead Letter Stack](s1032-the-dead-letter-stack-when-your-agent-fails-silently-and-bills-you-loudly.md) — uncaught failures in agentic loops
[S-2603 · The Agentic Output Validation Stack](s2603-the-agentic-output-validation-stack-when-your-agent-succeeds-and-delivers-the-wrong-thing.md) — post-parse semantic validation of agent outputs
[S-04 · Structured Output](s04-structured-output.md) — extraction and JSON-mode reliability
