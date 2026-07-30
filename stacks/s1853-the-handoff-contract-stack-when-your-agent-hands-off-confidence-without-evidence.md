# S-1853 · The Handoff Contract Stack — When Your Agent Hands Off Confidence Without Evidence

An agent completes its work and passes the result to the next agent. The next agent trusts it. This is the problem. The upstream agent's confidence is real — it has no mechanism to distinguish "I generated this output and it looks right" from "I generated this output and it is right." The downstream agent has no way to know which. Across three handoffs, plausible-sounding wrong outputs compound until the final result is confidently wrong and no agent in the chain knows it.

## Situation

A research agent extracts 12 citations from a PDF, summarizes their findings, and hands the summary to a writer agent. The writer agent produces a polished report citing the research verbatim. Four of the citations were hallucinated by the research agent — it generated titles that matched the topic, read plausible, and were never checked. The writer agent cited them because the research agent cited them. The pipeline is wrong from step two and correct-looking all the way to delivery.

## Forces

- **Confidence transfers; evidence does not.** An LLM's output always looks confident. There is no visible signal distinguishing "verified" from "invented" except an independent check the upstream agent was never tasked to run.
- **Downstream agents default to trust.** When the upstream agent completes successfully — no error, no exception — the downstream agent treats the output as ground truth. Its own quality bar is "does this sound consistent with what I received?" not "is this independently correct?"
- **Implicit state evaporates at handoff boundaries.** What the upstream agent knew about its own uncertainty, what it didn't verify, what it assumed — none of this travels unless explicitly encoded. Handoffs that pass only the final output pass a clean surface over a murky bottom.
- **Context noise hides signal.** Passing full conversation history + all intermediate steps gives the downstream agent everything, most of which is irrelevant. The signal (the output and its provenance) is buried.

## The move

Structure every handoff as a **contract artifact** — a structured JSON/document object with five mandatory fields. This is not a logging exercise. It is a verification interface: the upstream agent fills in what it did, what it didn't, and what the downstream agent should re-verify. The downstream agent reads the contract and treats the re-verify list as a checklist, not a courtesy.

### The five fields

```python
from datetime import datetime
from typing import Optional

class HandoffContract:
    """Standard handoff artifact between agents."""

    # 1. Output — the actual deliverable
    output: dict  # The structured result being handed off

    # 2. Provenance — what the upstream agent actually did
    provenance: ProvenanceBlock

    # 3. Attestation — what the upstream agent certifies as verified
    attestation: AttestationBlock

    # 4. Gap list — what the upstream agent did NOT verify
    gap_list: list[str]  # Downstream agent's re-verification checklist

    # 5. Schema version — prevents version mismatch across agents
    schema_version: str


class ProvenanceBlock:
    """Trace of what operations produced this output."""
    input_refs: list[str]       # IDs of inputs used (file IDs, query IDs, etc.)
    tools_used: list[str]       # Tool names called
    tool_results_summary: str   # One-line digest of what tools returned
    execution_time_ms: float
    model_used: str             # Provider + model + version
    confidence_signal: str      # "high" | "medium" | "low" — self-assessed


class AttestationBlock:
    """What the upstream agent explicitly confirms is correct."""
    verified_facts: list[str]   # Specific claims this agent checked
    source_docs: list[str]      # Specific documents/URLs this agent read
    assumptions: list[str]     # What was assumed but not independently checked
    citations: list[Citation]   # Each citation: {id, title, url, verified: bool}


@dataclass
class Citation:
    id: str
    title: str
    url: Optional[str]
    verified: bool  # False = upstream generated this title without reading the source
```

### The verification loop (downstream agent)

```python
async def receive_handoff(contract: HandoffContract, agent: Agent) -> dict:
    """Downstream agent: treat every gap as a checklist item."""

    result = contract.output.copy()

    # 1. Verify citations against ground truth (spot-check)
    for citation in contract.attestation.citations:
        if not citation.verified:
            # Mark as unverified in output — don't silently pass the lie forward
            result["unverified_citations"] = result.get("unverified_citations", [])
            result["unverified_citations"].append(citation.id)
            # Optionally re-fetch and correct
            citation = await re_verify_citation(citation)

    # 2. Spot-check assumptions against independent sources
    for assumption in contract.attestation.assumptions:
        is_held = await agent.verify_assumption(assumption)
        if not is_held:
            result["assumptions_that_fAILED"] = result.get("assumptions_that_failed", [])
            result["assumptions_that_fAILED"].append(assumption)

    # 3. Log the contract for audit trail
    await log_handoff_audit(contract, agent_id=agent.id, verified=True)

    return result
```

### What this prevents

| Failure mode | Without contract | With contract |
|---|---|---|
| Hallucinated citation passes forward | Writer trusts researcher | Gap list flags unverified; downstream spot-checks |
| Assumed fact treated as proven | Pipeline compounds error | Assumptions explicitly listed for re-verification |
| Tool result error silently swallowed | Next agent uses wrong value | `provenance.tool_results_summary` surfaces the anomaly |
| Model updated, old behavior persists | Silent regression | `provenance.model_used` pins the version |
| Handoff schema mismatch | Agents speak different languages | `schema_version` enforces compatibility |

### When to use it

- Every **structured handoff** in a multi-agent pipeline: research → write → review, triage → execute → verify, plan → act → report.
- **Optional** for one-off tool calls (agent calling a search tool): the tool result is the output, not a hand-off. Only use when a second agent will take responsibility for the work.
- The contract overhead is justified when: the downstream agent will make consequential decisions based on the upstream output, the upstream agent worked with untrusted or ambiguous inputs, or more than two agents are in the chain.

## Receipt

> Verified 2026-07-30 — Research sources: Agentbrisk "Agent Handoff Patterns in 2026" (March 2026) on three handoff models and failure points; agentpatterns-ai/agent-handoff-protocols.md (June 2026) on preventing context loss at handoff boundaries; AgentBrisk production field data on citation hallucination propagating across pipeline stages. Code reflects standard contract-artifact patterns from distributed systems (Saga pattern, API contract versioning). No live execution performed.

## See also

- [S-41 · Agent Handoff Patterns](s41-agent-handoff-patterns.md) — foundational handoff mechanics; this entry extends that with the structured contract layer
- [S-1013 · The Multi-Agent Boundary Stack](s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — state disagreement at boundaries; the contract makes state explicit rather than inferred
- [S-1314 · The Pipeline Collapse Stack](s1314-the-pipeline-collapse-stack-when-your-multi-agent-pipeline-quietly-becomes-wrong-at-every-handoff.md) — handoff audit trail; the contract is the audit artifact
- [S-1851 · The Heaviside Gate Stack](s1851-the-heaviside-gate-stack-when-your-agent-proceeds-confidently-from-a-state-that-doesnt-exist.md) — verification-before-proceed; the contract's attestation block is the pre-gate evidence
- [S-1773 · The Context Hygiene Stack](s1773-the-context-hygiene-stack-when-your-agents-remember-things-that-never-happened.md) — cross-agent retrieval staleness; the contract's provenance block surfaces what was actually retrieved
