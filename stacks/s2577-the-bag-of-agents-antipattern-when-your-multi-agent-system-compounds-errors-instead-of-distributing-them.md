# S-2577 · The Bag of Agents Antipattern — When Your Multi-Agent System Compounds Errors Instead of Distributing Them

Your "multi-agent" system has three agents. They share a context window. They call each other by name when they feel like it. The researcher confidently misquotes a statistic. The coder pastes it into a production file. The reviewer approves it. By the time you notice, the wrong number is in your product. This isn't a multi-agent system. It's a bag of agents.

Gartner reports 1,445% growth in multi-agent inquiries (Q1 2024 → Q2 2025). Research from Coasty.ai (July 2026) and Requesty.ai (Anthropic-sourced) consistently shows 40%+ multi-agent production failure rates — with **57% of those failures originating in orchestration design, not in individual agent capability**. The most common orchestration failure is the bag of agents pattern: throw several vaguely specialized LLMs into a shared context and let them figure it out.

## Forces

- **Uncoordinated agents don't distribute work — they distribute error.** Each agent adds a decision surface where a mistake can enter and propagate. Without a protocol governing who does what and when, errors compound multiplicatively, not additively.
- **Shared context is not shared intent.** Putting multiple agents in the same context window gives them the same information, not the same plan. The researcher and coder and reviewer each interpret the shared context differently, and those interpretations don't reconcile.
- **Vague specialization is worse than no specialization.** Calling an agent "researcher" or "reviewer" without defining the boundary of its authority, its input contract, and its output guarantee means every handoff is an implicit negotiation that can fail silently.
- **Token economics punish the bag.** Each agent in a shared-context pool pays full input cost on every message, even when only one agent needs to act. Cost compounds at O(n²) when n agents can freely reference each other's full history.
- **The failure mode looks like success.** A bag-of-agents run that completes returns HTTP 200. It looks like it worked. The wrong answer is inside.

## The move

**Replace the bag with a protocol.** The core intervention is simple: add a deterministic orchestration layer that governs *who acts next*, *what they receive*, and *what happens if they disagree*. Every agent interaction must be mediated by a protocol, not by shared context and hope.

### 1. Define explicit role contracts, not role names

"Researcher" is not a role contract. A role contract specifies:

```
Role: Researcher
Input:  One concrete question (no ambiguity)
Output:  { facts: Fact[], confidence: "high"|"medium"|"low", citations: Citation[] }
Constraint: Never state a fact without a citation. If no citation exists, say "unknown."
Exit condition: Return within 3 tool calls OR escalate.
```

Every agent in the system must have a written contract like this. If you can't write it down in three lines, the role isn't defined.

### 2. Route through a deterministic orchestrator, not shared context

```
User Input
    │
    ▼
Orchestrator (deterministic)
    │ → If task == "research"  → Agent: Researcher  (isolated context)
    │ → If task == "code"      → Agent: Coder       (isolated context)
    │ → If task == "review"    → Agent: Reviewer    (isolated context)
    │ → If task == "escalate"  → Human Loop
    ▼
Result Aggregator
```

The orchestrator is a finite state machine. It decides next state based on output quality signals, not on agents freely calling each other. Each agent operates in an *isolated context* — it receives only what the orchestrator passes it, not the full shared history.

### 3. Add a mandatory critic layer before any result is finalized

The Critic is not a peer of the other agents. It is a policy enforcement point:

```python
class CriticProtocol:
    def review(self, agent_output: AgentOutput, task: Task) -> ReviewResult:
        # Factual checks against ground truth
        factual_errors = self.check_facts(agent_output.facts)
        # Citation validation
        citation_errors = self.check_citations(agent_output.citations)
        # Constraint compliance
        constraint_violations = self.check_constraints(agent_output, task.constraints)

        if factual_errors or citation_errors or constraint_violations:
            return ReviewResult(
                status="REJECT",
                errors=[*factual_errors, *citation_errors, *constraint_violations],
                retry_agent=task.assigned_agent
            )
        return ReviewResult(status="APPROVE")

# Orchestrator enforces Critic output
result = orchestrator.delegate(task)
critic_verdict = critic.review(result, task)
if critic_verdict.status == "REJECT":
    orchestrator.retry(critic_verdict.retry_agent, task, critic_verdict.errors)
```

The Critic can only approve or reject — it cannot itself generate. It is a policy layer, not a participant.

### 4. Treat handoffs as typed data contracts, not free-form messages

Handoffs between agents must follow a schema the orchestrator validates:

```python
@dataclass
class Handoff:
    source_role: str
    target_role: str
    deliverable: dict  # schema-validated by orchestrator
    confidence: float
    open_questions: list[str]  # things the target should be aware of
    escalation_flag: bool

# Orchestrator validates handoff before delivering
orchestrator.validate_handoff(handoff)
orchestrator.deliver(handoff)
```

If the handoff doesn't match the target's input contract, the orchestrator rejects it — the source agent must fix it before proceeding.

### 5. Instrument with semantic failure signals, not just structural traces

Structural tracing (HTTP 200, token counts, step counts) stays green even when agents fail semantically. Add semantic signals:

```python
class SemanticMonitor:
    def record_step(self, agent: str, action: str, output: str, context: dict):
        # Semantic: did the agent's output match the task intent?
        intent_match = self.llm_judge.evaluate(
            output=output,
            intent=context["task_goal"],
            criteria=["factual_accuracy", "constraint_compliance", "completeness"]
        )
        # Cost: track token spend per agent per task
        cost = self.token_counter.count(output)
        # Emit to observability layer
        self.span.annotate(semantic_score=intent_match.score, cost=cost)

        if intent_match.score < 0.7:
            self.orchestrator.escalate(agent, output, intent_match.failures)
```

## When to use this

You need this stack when:
- Your multi-agent system has 3+ agents and no written protocol governing who calls whom
- Agents share a context window rather than receiving orchestrated, isolated context slices
- The failure rate in production exceeds what any single agent would produce alone
- Your observability dashboard shows green traces but customers are reporting wrong outputs
- You can no longer explain why a given output came from a given decision path

## When to skip this

Single-agent systems don't need this. If your agent is working reliably and cost-effectively alone, adding orchestration overhead is premature complexity. The bag-of-agents problem only manifests when you have *multiple agents coordinating without structure*.

## Receipt

> Verified 2026-08-13 — Research synthesis: Coasty.ai (July 2026, "bag of agents" anti-pattern, 40%+ failure rate data), Requesty.ai/Anthropic (57% orchestration design failures), Gartner multi-agent inquiry surge data via Beam.ai and RaftLabs (2026). Code patterns from standard orchestration literature. Receipt pending — not executed in live environment.

## See also

- [S-05 · Multi-Agent Patterns](stacks/s05-multi-agent-patterns.md) — the foundational taxonomy; this entry is its failure-mode counterpart
- [S-986 · The Coordination Breakdown Pattern](stacks/s986-the-coordination-breakdown-pattern-when-your-multi-agent-system-is-its-own-worst-enemy.md) — focuses on inter-agent messaging failures; this entry focuses on the pre-protocol state where failures originate
- [S-1008 · The Orchestration Pattern Match Stack](stacks/s1008-the-orchestration-pattern-match-stack-when-chains-agents-and-hierarchies-all-look-equally-right.md) — helps you choose between chain/hierarchy/swarm; this entry is the corrective for the case where no pattern is chosen
