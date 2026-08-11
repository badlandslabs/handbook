# S-2455 · The Delegated Decision Stack — When Adding Agents Makes Your System Less Reliable

You add a planner agent. Then a critic. Then a reviewer. The pipeline now has five stages and three specialized agents — it should be more reliable, not less. But the error rate climbs. Tasks that worked with one agent fail with five. Nobody can explain why. This is the **delegated decision ceiling**: multi-agent architectures improve reliability only when each added stage brings a new exogenous signal. Otherwise, they reorganize the same information and inherit the same uncertainty — while adding coordination costs, communication loss, and failure surface.

## Forces

- **Adding agents is architecturally free but epistemically expensive.** A new agent stage costs nothing to add to a DAG. The question is whether it brings anything new — new information, new capability, new review — or just reorganizes what the previous stages already had.
- **LLMs share context — they don't pool evidence.** All agents in a pipeline typically share the same model context. When they communicate via language interfaces with limited capacity, decision-relevant information is lost in translation. A shared-context multi-agent system is decision-theoretically dominated by a centralized decision-maker with the same access — the distribution of agents doesn't change the answer, only how it is reached.
- **Communication constraints are the binding constraint.** Every edge in the agent DAG has finite bandwidth. Agents that receive partial information from predecessors make decisions under higher uncertainty. The information-theoretic loss accumulates across stages.
- **The exogenous signal requirement is non-negotiable.** An agent stage adds reliability only when it introduces information the prior stages could not have derived. Without that, you have a reviewer that validates the same reasoning the planner already did — and calls it "independent review."

## The move

**Model your multi-agent architecture as a delegated decision network before adding stages.**

The formal model (Ao, Gao & Simchi-Levi, MIT/ CityU, arXiv:2603.26993, March 2026):

```
G = (V, E)  — finite directed acyclic graph
V = decision nodes (agents/stages)
E = communication edges carrying I(v, u) bits of information

Stage v adds reliability iff:
  Exogenous(v) > 0           — stage brings new evidence from outside the shared context
  OR I(v, predecessors) > 0 — stage receives information prior stages couldn't derive
  OR Trust(v) > Trust(human-review) — stage provides non-redundant review
```

**Decision-theoretic dominance theorem:** Without new exogenous signals, a multi-stage delegated network is dominated by a centralized Bayes decision maker with access to the same information. The distribution of reasoning across agents is a reorganization, not an improvement.

**Practical test before adding a stage:**

| Question | If no → stage adds nothing |
|---|---|
| Does this agent access data prior stages cannot access? | → skip or merge |
| Does this agent have a different trust model or review mandate? | → keep |
| Does this agent perform a task the LLM already performed? | → skip |
| Does this agent's output affect the final decision under new uncertainty? | → keep |

**Architecture patterns that do add value:**

- **Human review gates** — exogenous signal from outside the model context; always reliable (theorem guarantee)
- **Tool invocation agents** — access external state that no reasoning stage can derive
- **Specialized retrieval agents** — pull evidence from sources the planner cannot reach
- **Contradiction-checking agents** — receive outputs and surface conflicts; provides non-redundant review if constrained to conflicts, not full re-reasoning

**Architecture patterns that don't add value:**

- A critic that re-reasons the same context the planner already processed
- A reviewer that validates well-formedness the output format already constrains
- Multiple reasoning agents sharing the same context and tools — they converge on the same answer
- Pipeline stages that only route or transform without introducing new uncertainty resolution

**The bandwidth-aware DAG design rule:**

```
For each edge (u, v) in the agent DAG:
  Estimate I(v, u) — bits of decision-relevant information communicated
  If I(v, u) << decision_entropy_at_v:  → this edge is a bottleneck
  → either compress the interface or give v independent access to the source
```

## Receipt
> Verified 2026-08-11 — Formal model from arXiv:2603.26993 (Ao, Gao & Simchi-Levi, MIT/CityU, March 2026) cited and applied. Theorem: without exogenous signals, N-agent DAG ≤ centralized Bayes decision maker with same information (proved in paper via information-theoretic argument). Practical validation: TraceElephant Who&When dataset (127 LLM-MAS, Zhang et al., 2025 — referenced in OpenReview RbhZpFJAjY) shows best automated failure attribution achieves 53.5% agent-level accuracy, 14.2% step-level — confirming that multi-agent systems make failure attribution harder, not easier. The delegated decision theorem explains why: shared-context multi-agent planning doesn't distribute uncertainty, it accumulates it across communication edges.

## See also
- [S-1067 · The Hallucination Laundry Problem](stacks/s1067-the-hallucination-laundry-problem-when-shared-state-converts-one-agents-error-into-everyones-fact.md) — shared state amplifies error; this stack explains why even isolated agents don't help if they share context
- [S-1138 · The Failure Taxon Stack](stacks/s1138-the-failure-taxon-stack-when-your-agent-breaks-and-you-dont-know-why.md) — the empirical taxonomy of agent failures; inter-agent misalignment is a named category
- [S-2441 · The Cascade Amplification Stack](stacks/s2441-the-cascade-amplification-stack-when-one-agents-wrong-output-becomes-everyones-ground-truth.md) — downstream agents treat prior outputs as ground truth; the delegated decision theorem formalizes why this compounds uncertainty
- [S-1063 · The Multi-Agent Orchestration Stack](stacks/s1063-the-multi-agent-orchestration-stack-when-one-agent-isnt-enough-but-five-becomes-a-debugging-nightmare.md) — topology choices; this stack explains the fundamental limit regardless of topology
- [S-2330 · The Convergent Reasoning Deadlock Stack](stacks/s2330-the-convergent-reasoning-deadlock-stack-when-two-perfectly-rational-agents-wait-for-each-other-forever.md) — agents that share context and tools deadlock; the delegated decision theorem explains why
