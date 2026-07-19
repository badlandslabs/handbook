# S-1358 · The Stochastic-Deterministic Boundary — When Your Agent Proposes the Wrong Action and the System Runs It Anyway

When you reach for it: You have a production agent that works well in eval, passes all tests, and still sends a 90% discount to the wrong customer, writes an incorrect database record, or escalates a ticket to the wrong queue. The LLM did exactly what it was asked. The system did exactly what the LLM output. The failure is not in the model or the infrastructure — it is in the seam between them.

## Forces

- **LLM output is a proposal, not a commitment.** An LLM generates text. That text becomes a function call, a database write, a message send — only because a deterministic layer chose to interpret it that way. Every real-world action requires crossing from the probabilistic world (LLM) to the deterministic world (your system). That crossing has no guard by default.
- **Infrastructure treats LLM output as trusted input.** Most agent runtimes pipe LLM output directly into tool calls. The LLM is the authority; the system is the actuator. This assignment is backwards for anything that matters. The LLM is right often enough to pass QA; it is wrong often enough to cause incidents.
- **The composition is load-bearing, but unnamed.** Per-call model capability has improved substantially with each generation, and per-call variance has compressed. As that compression continues, the architectural surface shifts to what surrounds the model — the seam, its contracts, and the patterns that govern it. This seam is where production agents fail, and it has no canonical name.
- **Ad-hoc validation is the default.** Teams discover the gap through incidents, not through design. The fix is usually scattered: a manual review step here, a Pydantic guard there, an if-statement checking a parameter elsewhere. No coherent model.

## The move

Name and structure the seam: the **Stochastic-Deterministic Boundary (SDB)**. The SDB is the four-part contract between a probabilistic LLM and the deterministic systems it drives:

| Component | Role | Example |
|-----------|------|---------|
| **Proposer** | LLM generates the action proposal | `llm.generate("Sell 50 NVDA at market")` → JSON `{symbol, qty, order_type}` |
| **Verifier** | Deterministic check before execution | Cash sufficient? Within risk limits? Market hours open? Within position limit? |
| **Commit** | Execute the verified action | `broker.submit_order(verified_payload)` |
| **Reject** | Typed, structured rejection with recovery hint | `{reason: "limit_exceeded", retry_with: {qty: 25}, escalate: false}` |

The **Verifier** is the critical new element. It is not the LLM checking itself. It is code. It is deterministic. It runs before the commit and decides whether the proposal becomes an action.

```python
class StochasticDeterministicBoundary:
    def __init__(self, llm, tools, verifier_policies: list[VerifierPolicy]):
        self.proposer = llm          # stochastic: generates proposals
        self.verifier_policies = verifier_policies  # deterministic: approves/rejects
        self.tools = tools           # deterministic: executes commits

    async def run(self, task: str, context: dict) -> ExecutionResult:
        # 1. PROPOSE — LLM generates an action
        proposal = await self.proposer.generate(task, context)

        # 2. VERIFY — deterministic gate before anything runs
        violations = []
        for policy in self.verifier_policies:
            result = policy.check(proposal, context)
            if not result.approved:
                violations.append(result)

        if violations:
            return ExecutionResult(
                status="rejected",
                proposal=proposal,
                violations=violations,
                recovery_hint=self._derive_hint(violations)
            )

        # 3. COMMIT — execute only after all verifiers pass
        tool_name = proposal["tool"]
        tool_args = proposal["args"]
        result = await self.tools[tool_name].execute(**tool_args)

        # 4. LOG — proposal → verdict → outcome for audit
        await self.audit_log.append({
            "proposal": proposal,
            "verdict": "approved",
            "commit_result": result,
            "timestamp": now()
        })

        return ExecutionResult(status="committed", result=result)


class RiskLimitVerifier(VerifierPolicy):
    """Example verifier: reject orders exceeding risk limits."""
    def check(self, proposal: dict, context: dict) -> VerificationResult:
        if proposal.get("tool") != "submit_order":
            return VerificationResult(approved=True)
        qty = proposal["args"].get("quantity", 0)
        if qty > context["max_position_size"]:
            return VerificationResult(
                approved=False,
                reason="position_limit_exceeded",
                detail=f"{qty} exceeds max {context['max_position_size']}",
                retry_with={"quantity": context["max_position_size"]},
                escalate=False
            )
        return VerificationResult(approved=True)
```

### Choosing what gets an SDB

Not every action needs the full four-part contract. Rate the cost of each action along two axes:

| | Reversible | Irreversible |
|---|---|---|
| **Low cost** | No SDB needed. Let the agent run. | Light SDB (Verifier only, auto-retry on reject) |
| **High cost** | SDB with Commit gate and audit log | Full SDB: Verifier + Commit + Reject + audit + HITL option |

### Composing SDBs into patterns

**Sequential chain:** Proposal → Verifier → Commit → Proposal → Verifier → Commit. Each step is gated. An order that fails the verifier skips the commit and produces a structured rejection that feeds back into the next proposal. The LLM reads the rejection and tries a compliant alternative.

**Parallel exploration:** Multiple proposals generated simultaneously, each fed through its own Verifier, results merged. Used for tree-search or multi-option evaluation. DeltaBox (Dong et al., SJTU/Huawei, arXiv:2605.22781, 2026) provides millisecond-scale OS-level checkpoint/rollback to support this at production speed — a natural complement to the SDB pattern for high-frequency state exploration.

**Supervisor-reviewer:** One agent proposes; a separate verifier-agent reviews the proposal's rationale (not just the output) before the commit fires. Catches semantic errors that deterministic policy checks miss.

## Receipt

> Verified 2026-07-19 — SDB pattern derived from Vasundra Srinivasan, "A Methodology for Selecting and Composing Runtime Architecture Patterns for Production LLM Agents" (arXiv:2605.20173, May 2026). Four-part Proposer/Verifier/Commit/Reject contract validated against published examples: trading agent risk gate, discount authorization threshold, and ticket routing escalation. Companion repository: github.com/vasundras/agent-runtime-patterns. DeltaBox (arXiv:2605.22781, Dong et al., June 2026) identified as complementary OS-level mechanism for high-frequency SDB enforcement in tree-search/RL workloads.

## See also

- [S-1016 · The Agent Failure Intervention Stack](s1016-the-agent-failure-intervention-stack-when-your-agent-works-but-wrong.md) — failure intervention taxonomy; the SDB is the architectural prerequisite for reliable intervention
- [S-1013 · The Multi-Agent Boundary Stack](s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — the agent-to-agent boundary; complementary to the LLM-to-system seam
- [S-1239 · The Runtime Verification Loop](s1239-the-runtime-verification-loop-when-your-agent-scores-97-percent-and-walks-straight-into-the-wrong-answer.md) — inline step verification; SDB provides the structural contract that verification gates operate within
