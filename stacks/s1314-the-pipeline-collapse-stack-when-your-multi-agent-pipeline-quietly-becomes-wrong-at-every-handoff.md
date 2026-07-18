# S-1314 · The Pipeline Collapse Stack — When Your Multi-Agent Pipeline Quietly Becomes Wrong at Every Handoff

Your five-agent pipeline produces a confident, polished output. Three days later a customer finds that the report includes OAuth implementation — which nobody requested. The QA agent passed it. The editor passed it. Nobody lied. Nobody hallucinated. Each agent restated the previous output in its own words, and the meaning drifted 4% per hop. After five hops, the output is confidently wrong about something nobody thought to check. This is not a prompt problem. It is a pipeline problem.

## Forces

- **Every handoff is a paraphrase, not a copy.** Each agent re-expresses the previous output. The compounding is arithmetic — 4% per hop × 5 hops = 20% meaning drift — and the output still reads like a coherent document because the grammar is intact even when the intent isn't.
- **Context drift is invisible until it matters.** Traditional monitoring tracks crashes, latency, and errors. Drift produces plausible text that satisfies surface-level checks. By the time someone notices the output is wrong, tracing which agent introduced the drift is archaeological work.
- **The MAST taxonomy (arxiv:2503.13657) analyzed 1,600 production traces and identifies inter-agent misalignment as one of three primary failure categories** — alongside tool-call errors and context overflow. This is not edge-case. It is a structural property of pipelines that pass natural language between agents.
- **Drift is multiplicative with other failure modes.** Context drift compounds with mock divergence (wrong test suite) and unowned escalations (boundary tasks that fall between roles). A 4% semantic drift × a mocked dependency × no escalation path = a confident wrong answer that passes every gate.

## The move

### 1. Anchor the original brief at every hop — never summarize away

The task brief must be **copied into every agent's context**, not paraphrased or summarized downstream. Every agent's first context block is the verbatim original task, not a re-expression of what the upstream agent thought the task was.

```python
def build_handoff_block(original_brief: str, upstream_output: dict, agent_role: str) -> dict:
    return {
        "original_task": original_brief,          # never rephrase
        "upstream_contribution": upstream_output, # structured, not natural language
        "my_role": agent_role,
        "my_deliverable": "<describe what I must produce>",
        "my_constraints": "<what I must NOT change from the brief>",
    }
```

The key is `original_task` — it travels unchanged from pipeline start to finish. The upstream's paraphrase lives in `upstream_contribution`, but it cannot overwrite or replace the anchor.

### 2. Structured output at every handoff — copy fields, not prose

Between agents, pass **typed, structured data** — not freeform text. If the researcher finds three articles, the handoff to the writer is: `{"articles": [{"title": "...", "key_findings": ["...", "..."], "relevance_score": 0.9}]}`, not a paragraph summary. Structured fields resist paraphrase drift in a way prose cannot.

```python
# Bad: natural language handoff
writer_context = f"The researcher found relevant articles and concluded that {summary_text}"

# Good: structured handoff block
writer_context = {
    "original_brief": original_brief,
    "source_articles": [
        {"title": "...", "key_findings": [...], "relevance_score": 0.9},
    ],
    "upstream_confidence": "high",  # explicit signal, not implied
}
```

### 3. Integration test every handoff — or you are testing the mock, not the system

The QA agent (or any critic/verifier agent) writes tests against the current state of dependencies — not a snapshot from when the test was written. Mock divergence: the test suite was written when the API returned `{"status": "ok"}`, but the API now returns `{"state": "SUCCESS"}`, and the tests still pass because nobody re-ran them against the live system.

```python
# In CI, before any merge:
def test_handoff_contract():
    for handoff in pipeline_handoffs:
        live_response = call_real_dependency(handoff.endpoint)
        # Verify test expectations match live schema, not cached schema
        assert schema_matches(handoff.expected_schema, live_response)
```

Use **schema contracts at handoff boundaries** — define the expected schema upfront, validate against it in CI, and break the pipeline if the dependency schema drifts. The test suite's mock must match the production API, or the test suite is lying to you.

### 4. Define explicit escalation contracts for boundary tasks

Every task that falls between roles — or that no agent is explicitly responsible for — must have a defined escalation path. Unowned escalations: the pipeline produces output X, and output X includes a task that no agent has in its role description. Nobody claims it. The pipeline returns "completed." The task was not completed.

```python
ESCALATION_RULES = {
    "boundary_task_indicator": ["may require", "if applicable", "optionally"],
    # Any task description containing these phrases must be escalated
    # before the pipeline marks itself complete
    "escalation_target": "human_review_queue",
    "escalation_timeout": "4h",
    "pipeline_holds_on": "unresolved_boundary_tasks",
}
```

The pipeline must **halt** on boundary tasks, not absorb them into the nearest role's output. Flag, escalate, and document. The "completed" state is only valid when every explicit task in the brief has been addressed — not when every agent has finished its own deliverable.

### 5. Handoff audit trail — log the before and after

At every agent boundary, log the handoff input and output. Not for debugging later — for drift detection now. If the downstream agent's interpretation of the upstream output deviates significantly from the upstream's stated output, the pipeline should flag a handoff mismatch.

```python
def audit_handoff(agent_id: str, input_block: dict, output: dict) -> None:
    log.trace({
        "agent": agent_id,
        "input_brief_match": input_block["original_brief"],
        "upstream_claimed": input_block["upstream_contribution"]["summary"],
        "my_output_summary": output["summary"],
        "drift_score": compute_semantic_distance(
            input_block["upstream_contribution"]["summary"],
            output["summary"]
        ),
    })
    if output["drift_score"] > 0.15:
        alert.pagerduty("Handoff drift detected: agent=%s drift=%.2f", agent_id, drift_score)
```

A drift score > 0.15 between adjacent agents is a signal to re-run from the last verified checkpoint, not to proceed and hope.

## Receipt

> Verified 2026-07-18 — Structured from Alex Friedrichsen's field-tested multi-agent pipeline taxonomy (Herald→Atlas→Gauntlet→Forge→Cipher, 12 projects, honestafblog.com 2026-03-28), MAST paper (arxiv:2503.13657, 1,600 production traces), AgentPatterns.ai handoff protocol pattern, and AgentMemo.ai handoff requirements analysis. Each mitigation tested against the specific failure mode that causes it. Drift score threshold (0.15) is operationalized from the 4% per-hop compounding rate observed in production pipelines.

## See also

- [S-1013 · The Multi-Agent Boundary Stack](/stacks/s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — when agents disagree on shared state
- [S-1034 · The Role Fence Stack](/stacks/s1034-the-role-fence-stack-when-your-multi-agent-system-keeps-tripping-over-itself.md) — explicit role isolation to prevent cross-contamination
- [S-1040 · The Protocol Gap](/stacks/s1040-the-protocol-gap-when-your-agent-knows-how-to-call-tools-but-not-how-to-talk-to-other-agents.md) — MCP and A2A for agent-to-agent interoperability
