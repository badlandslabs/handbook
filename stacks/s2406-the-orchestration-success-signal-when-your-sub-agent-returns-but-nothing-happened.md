# S-2405 · The Orchestration Success Signal — When Your Sub-Agent Returns But Nothing Happened

Your multi-agent pipeline completes without errors. Every sub-agent call returned 200. The trace shows a clean execution graph. Three hours later, a user reports the support ticket was never created. The researcher agent did the research. The writer agent wrote the summary. The executor agent — which was supposed to call the CRM API — returned successfully. But the ticket doesn't exist.

The orchestrator marks steps complete when sub-agents return. That is the wrong unit of success.

## Forces

- **The orchestrator's success criterion is the wrong abstraction.** "The call returned without error" means the LLM produced a response. It does not mean the intended side effect happened. A sub-agent can complete its model call, decide not to run the tool, and still satisfy the orchestrator's success condition perfectly.
- **Span-level tracing tells the truth about each span, not about the execution graph.** Every span in the trace accurately reports what it did. None of them report what the graph needed but didn't get. The missing write is invisible at the span level.
- **This failure is structurally invisible by design.** Most orchestration frameworks use `try/catch` around sub-agent calls. If the call returns, the exception block doesn't fire. The framework has no mechanism to detect that the intended action didn't happen.
- **The problem compounds with parallelism.** In a fan-out pattern, one sub-agent silently skipping its write leaves a gap the orchestrator doesn't know to compensate. Downstream agents receive partial context and proceed confidently with missing data.

## The move

**Step 1: Define success at the action level, not the call level.**

```python
# WRONG: orchestrator success = sub-agent returned
async def run_step(agent, task):
    try:
        result = await agent.run(task)
        return result  # marks complete even if result.effects_missing
    except Exception as e:
        handle_error(e)

# RIGHT: orchestrator success = intended effect confirmed
async def run_step(agent, task):
    result = await agent.run(task)
    expected_effects = task.effects_required  # e.g. ["ticket_created"]
    confirmed = await verify_effects(expected_effects)
    if not confirmed:
        raise EffectNotConfirmedError(f"Task {task.id}: expected {expected_effects}, missing")
    return result
```

**Step 2: Treat effects as first-class citizens, not as implementation details.**

For each sub-agent task, declare the required effects explicitly:

```python
@dataclass
class AgentTask:
    instruction: str
    effects_required: list[Effect]  # not just "did it return?"

@dataclass
class Effect:
    type: str  # "api_call", "file_write", "state_update"
    params: dict  # enough to re-verify without re-executing
    verify: Callable[[], Awaitable[bool]]  # side-effect-specific check
```

**Step 3: Verify effects, not just responses.**

```python
async def verify_effects(effects: list[Effect]) -> bool:
    results = await asyncio.gather(*[e.verify() for e in effects], return_exceptions=True)
    return all(r is True for r in results)

# Example effect definitions:
Effect(
    type="api_call",
    params={"method": "POST", "path": "/tickets", "id_field": "ticket_id"},
    verify=lambda: ticket_exists(ticket_id)  # poll the CRM, not the trace
)
Effect(
    type="file_write",
    params={"path": "/tmp/report.md"},
    verify=lambda: Path("/tmp/report.md").exists()
)
```

**Step 4: The orchestrator compensates, not just detects.**

When an effect is missing, the orchestrator must either retry, escalate, or invoke a compensating agent — not just log and continue:

```python
async def run_with_effect_guarantee(agent, task):
    for attempt in range(task.max_retries):
        result = await run_step(agent, task)
        confirmed = await verify_effects(task.effects_required)
        if confirmed:
            return result
        logger.warning(f"Effect gap on task {task.id}, attempt {attempt+1}")
        await task.compensate()  # cleanup partial state before retry
    raise EffectUnrecoverableError(f"Failed after {task.max_retries} attempts")
```

**Step 5: Instrument the gap, not just the call.**

Add a semantic gap metric to your observability layer — count steps where the model returned but the expected effects list was empty or incomplete. This metric lives above span level and must be computed by the orchestrator:

```python
# In the orchestrator's post-step hook:
if len(result.tool_calls) == 0 and task.effects_required:
    metrics.increment("orchestration.effect_gap")
    trace.annotate("effect_gap", {"required": task.effects_required, "got": []})
```

## Receipt

> Verified 2026-08-10 — Tessary.ai (June 21, 2026, updated July 31, 2026) documents the orchestrator success signal problem with data from the MAST taxonomy (1,642 annotated traces, 7 open-source frameworks). IBM Research ICPE '26 paper (DOI: 10.1145/3777911.3801104) provides the first systematic study of silent failure detection in multi-agentic AI trajectories. The pattern is confirmed across frameworks: orchestrators that use call-return as success produce silent failures at 14–31% of sub-agent steps in production traces.

## See also

- [S-1023 · The Recovery Ladder](s1023-the-recovery-ladder-when-your-agent-thinks-it-succeeded-but-didnt.md) — semantic gap between what the agent reports and what actually happened
- [S-1066 · The Invisible Failure Stack](s1066-the-invisible-failure-stack-when-your-agent-succeeds-and-burns-47k-instead.md) — failures invisible to deterministic monitoring
- [S-1325 · The Agent Handoff Stack](s1325-the-agent-handoff-stack-when-your-agents-pass-bad-batons.md) — coordination failures between agents (36.9% of multi-agent failures per MAST)
- [S-1082 · The Five-Layer Harness](s1082-the-error-taxonomy-and-the-five-layer-harness-stopping-agents-from-hurting-themselves-and-everything-else.md) — harness architecture for agent execution
