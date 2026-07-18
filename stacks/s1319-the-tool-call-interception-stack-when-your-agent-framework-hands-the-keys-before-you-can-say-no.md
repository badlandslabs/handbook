# S-1319 · The Tool-Call Interception Stack — When Your Agent Framework Hands the Keys Before You Can Say No

You reviewed the LangChain traces. The SQL DROP statement was in the log — not as an error, but as an *attempted execution*. The framework received the tool call from the LLM and passed it directly to the database adapter. No exception, no warning, no human-in-the-loop. The observability platform recorded the event twenty minutes later, after the table was gone.

The gap is not observability. It is a missing control point between the moment the LLM decides to call a tool and the moment that tool actually executes.

## Forces

- **The execution layer has no friction.** Most agent frameworks forward model-generated tool calls to execution with minimal mediation. The model emits `execute_sql(...)`, the framework calls the function. The only thing standing between "decided" and "done" is a JSON schema match.
- **Post-execution logging ≠ pre-execution control.** Langfuse, Arize, and Phoenix record tool calls. They do so *after* the side effect has already occurred. For destructive operations, "we logged what happened" is not a safety mechanism — it is an incident report.
- **Injection attacks exploit this gap.** A prompt injection embedded in user-supplied content causes the LLM to emit a malicious tool call. Without an interception layer, the framework passes it straight to execution. The observability layer logs the SQL injection. The table is still gone.
- **Approval gates need a harness, not a philosophy.** Everyone agrees human review is important for risky actions. But "add an approval gate" is not an implementation. The pattern needs a specific interception architecture that routes calls by risk classification, handles the decision synchronously or asynchronously, and continues or halts the agent loop based on the outcome.

## The Move

Insert a **tool-call interception layer** between the LLM's decision and the tool's execution. Every tool call passes through this layer; nothing executes without it.

```
LLM → [Interception Layer] → Tool Executor
              ↓
         Risk Classifier
         ├── LOW   → ALLOW (auto-execute)
         ├── MED   → LOG + CONTINUE
         ├── HIGH  → PENDING → Human Approval → ALLOW / DENY
         └── BLOCK → DENY + Log + Escalate
```

### Step 1 — Classify Tool Risk by Blast Radius

Not all tools are equal. Classify every tool in your catalog at registration time:

| Risk Level | Criteria | Examples |
|------------|----------|----------|
| **LOW** | Read-only, no side effects, no external blast radius | `search_kb`, `get_weather`, `calculate` |
| **MEDIUM** | Modifies internal state, reversible | `update_record`, `create_ticket`, `send_internal_slack` |
| **HIGH** | External blast, irreversible, financial or data impact | `send_email`, `execute_sql`, `deploy_code`, `move_funds` |
| **BLOCK** | Destructive by default without pre-approval | `drop_table`, `delete_bucket`, `revoke_access` |

### Step 2 — Route by Risk Class

```python
class ToolCallInterceptor:
    def __init__(self, tool_catalog, approval_queue, audit_log):
        self.catalog = tool_catalog
        self.queue = approval_queue
        self.audit = audit_log

    async def intercept(self, tool_name: str, args: dict, session_id: str) -> ToolResult:
        metadata = self.catalog.get(tool_name)
        risk = self.classify(metadata, args)

        # Always audit — before decision, not after
        await self.audit.record(session_id, tool_name, args, risk)

        if risk == Risk.LOW:
            return await self.execute(tool_name, args)

        if risk == Risk.MEDIUM:
            await self.audit.record_warning(session_id, f"MEDIUM risk: {tool_name}")
            return await self.execute(tool_name, args)

        if risk == Risk.HIGH:
            # Enqueue for human review; suspend agent loop
            approval = ApprovalRequest(
                session_id=session_id,
                tool=tool_name,
                args=args,
                risk=risk,
                context=self._build_context(tool_name, args),
            )
            result = await self.queue.enqueue_and_wait(approval, timeout=300)
            if result.status == ApprovalStatus.DENIED:
                return ToolResult(success=False, error="DENIED: human review")
            return result.execution_result

        # BLOCK — deny without enqueuing
        return ToolResult(success=False, error="BLOCKED: policy denies this tool class")

    def classify(self, metadata: ToolMetadata, args: dict) -> Risk:
        # Dynamic args inspection for context-sensitive risk
        if metadata.risk == Risk.BLOCK:
            return Risk.BLOCK
        if metadata.risk == Risk.HIGH:
            # Destructive args escalate to BLOCK
            if self._has_destructive_args(metadata, args):
                return Risk.BLOCK
        return metadata.risk
```

### Step 3 — Suspend the Agent Loop at HIGH Risk

When a HIGH-risk call is pending approval, the agent loop must pause — not abandon, not proceed. The agent holds state and resumes when approval arrives. Use a durable queue (Redis, SQS) so pending approvals survive restarts.

```python
async def agent_loop(session: AgentSession, task: str):
    while not session.done:
        decision = await session.decide(task)
        if decision.tool_call:
            result = await interceptor.intercept(
                decision.tool_name,
                decision.args,
                session.id,
            )
            if result.status == "PENDING":
                # Yield control — session persists in queue
                session.save_state()
                return  # Resume called by approval handler
            session.append(result)
        else:
            session.append(decision.response)
```

### Step 4 — Audit for Post-Incident and Pre-Incident Analysis

The interception layer's audit log is different from observability traces. It is purpose-built for governance:

- **Pre-incident**: Who approved what, when, with what context
- **Post-incident**: What was blocked, denied, or executed that should not have been
- **Compliance**: Evidence of human oversight for regulated actions

```python
audit_record = {
    "timestamp": datetime.utcnow().isoformat(),
    "session_id": session_id,
    "tool": tool_name,
    "args_hash": hash_args(args),  # redact sensitive args
    "risk_level": risk.value,
    "decision": "ALLOW|BLOCK|PENDING|DENIED",
    "approver": approver_id if risk in [Risk.HIGH] else "AUTO",
    "context_snapshot": build_safe_context(tool_name, args, session.history),
}
```

## Receipt

> Verified 2026-07-18 — AEGIS (arxiv:2603.12621, Yuan et al., USC) provides the academic foundation for this pattern: framework-agnostic interception returning ALLOW/BLOCK/PENDING. Blake Crosley (Feb 2026) documents the confabulation feedback loop (fabricated claims → memory → publication → confirmation → escalation) that makes HIGH-risk external calls especially dangerous. Neural Method's AI Control infrastructure and Microsoft Agent Framework's tool approval patterns confirm production adoption. AEGIS GitHub (justin0504/Aegis) provides open-source implementation reference. LangChain's official documentation explicitly recommends an interception layer for agentic systems with tool access.

## See also

- [S-767 · The Tool-Call Hallucination Plateau](s767-the-tool-call-hallucination-plateau.md) — wrong tool calls at the source; this entry is the enforcement layer for when they get through
- [S-964 · The Agent Failure Handling Stack](s964-the-agent-failure-handling-stack-when-your-agent-wont-quit-or-wont-start.md) — failure modes this pattern prevents from becoming incidents
- [S-1065 · The Inter-Agent Trust Escalation Stack](s1065-the-inter-agent-trust-escalation-stack-when-your-agent-takes-instructions-from-an-agent-and-bypasses-every-security-control.md) — multi-agent trust chains this pattern helps break
