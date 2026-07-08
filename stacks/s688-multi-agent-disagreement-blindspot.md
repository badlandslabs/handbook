# S-688 · The Multi-Agent Disagreement Blindspot

Parallel agents working the same task disagree 20–40% of the time — and most production systems make the disagreement invisible by design. The final answer gets logged; the disagreement doesn't.

## Forces

- **Same task, different tools = divergent outputs.** Two agents reading the same PR via `git diff` vs GitHub API produce different severity assessments. Both are correct from their own evidence. The system picks one and discards the other.
- **Logs hide the conflict.** Structured logs show only the winning output. Debugging the failure requires replaying both agents — which you can't do if you didn't capture the divergence.
- **Downstream failures are cryptic.** A downstream system receives "high severity" and acts on it. When it fails, the failure looks like a bad call on the output, not a silent disagreement between two agents with different tool access.
- **Detectors don't fire.** Standard error rates, loop counters, and schema validators all pass — the system succeeded at producing a well-formed output. The problem is which output was chosen and why.

## The move

**Detect, log, and resolve inter-agent output disagreement as a first-class event.**

```
┌─────────────┐  ┌─────────────┐
│  Agent A    │  │  Agent B    │
│ (tool: git) │  │ (tool: API) │
└──────┬──────┘  └──────┬──────┘
       │                │
       └───────┬────────┘
               ▼
      ┌────────────────┐
      │ Disagreement    │
      │ Detector        │
      │ (output diff + │
      │  confidence     │
      │  comparison)    │
      └────────┬───────┘
               │
    ┌──────────┼──────────┐
    ▼          ▼          ▼
  LOG      ROUTE TO    CONSENSUS
  divergence  judge      re-run
  event       agent      (if format
                              match)
```

**Mode 1 — Log divergence (async / latency-tolerant):**
```python
import hashlib, structlog

async def detect_divergence(agent_outputs: list[AgentResult]) -> DivergenceReport:
    """Run after all parallel agents complete, before routing to consumer."""
    if len(agent_outputs) < 2:
        return DivergenceReport(disagreement=False)
    
    # Structural diff: do outputs agree on key fields?
    field_agreement = {
        field: len(set(o.fields.get(field) for o in agent_outputs)) == 1
        for field in shared_schema(agent_outputs)
    }
    
    disagreements = {f: v for f, v in field_agreement.items() if not v}
    
    if disagreements:
        # Emit as first-class structured event — NOT buried in a log line
        structlog.get_logger().warning(
            "agent_output_disagreement",
            task_id=agent_outputs[0].task_id,
            diverging_fields=list(disagreements.keys()),
            agent_ids=[o.agent_id for o in agent_outputs],
            agent_tools=[o.tool_source for o in agent_outputs],
            # Store full outputs for replay — don't drop them
            outputs={o.agent_id: o.raw for o in agent_outputs},
        )
    
    return DivergenceReport(
        disagreement=bool(disagreements),
        diverging_fields=disagreements,
        winning_output=agent_outputs[0],  # preserve ordering signal
    )
```

**Mode 2 — Judge agent (sync / high-stakes):**
```python
async def resolve_via_judge(disagreement: DivergenceReport) -> ResolvedOutput:
    """Route to a third agent with both outputs + evidence."""
    judge_prompt = f"""
Task: {disagreement.task_description}
Evidence from Agent A (git diff): {disagreement.outputs["agent_a"]}
Evidence from Agent B (GitHub API): {disagreement.outputs["agent_b"]}

Which agent has more complete evidence for this specific task?
Return: {{"winner": "agent_a" | "agent_b", "reason": "...", "confidence": 0.0-1.0}}
"""
    # Pass both outputs and their evidence chains — not just the final text
    verdict = await judge_agent.run(judge_prompt, context=[
        *disagreement.outputs.values()
    ])
    return ResolvedOutput(verdict=verdict, disagreement_logged=True)
```

**Mode 3 — Consensus re-run (compatible outputs only):**
```python
async def resolve_via_consensus(disagreement: DivergenceReport) -> ResolvedOutput:
    """Both agents can re-run with the other's evidence as additional context."""
    if not all(o.supports_feedback for o in disagreement.agent_results):
        return await resolve_via_judge(disagreement)
    
    # Feed each agent the other's key evidence, ask for re-assessment
    results = await asyncio.gather(*[
        agent.reassess(with_evidence=other.output)
        for agent, other in pairwise(disagreement.agent_results)
    ])
    return merge_with_confidence_weighting(results)
```

**Key invariant:** The disagreement event is always emitted, regardless of resolution mode. Even if you resolve immediately, you have an audit trail.

## Receipt

> Verified 2026-07-06 — Pattern validated against tianpan.co research (May 2026): parallel agents disagree 20–40% of the time on software engineering tasks; silent pick is the dominant production behavior. Three-mode taxonomy (log / judge / consensus) corresponds to production latency and stakes tolerance gradients observed in multi-agent orchestration literature. Reference: LangGraph checkpoint patterns (s195) provide the durable state infrastructure for disagreement event capture.

> Receipt pending — needs live example from a parallel agent system with divergent tool access.

## See also

- [S-12 · Structured Output](s12-structured-output.md) — shared schema is the prerequisite for field-level disagreement detection
- [S-125 · Multi-Source Claim Conflict Detection](s125-multi-source-claim-conflict.md) — same problem, different domain (sources vs agents)
- [S-195 · Agent Checkpoint Resume](s195-agent-checkpoint-resume.md) — durable state enables replay of divergent agent runs
- [S-439 · Confident False Success](s439-confident-false-success-the-self-assessment-failure-mode.md) — disagreement is a form of silent false success
