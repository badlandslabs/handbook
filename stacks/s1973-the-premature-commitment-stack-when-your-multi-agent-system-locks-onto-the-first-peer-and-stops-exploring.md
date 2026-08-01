# S-1973 · The Premature Commitment Stack

When your multi-agent system settles on the first peer it encounters and treats all subsequent evidence as confirmation — the trajectory looks coherent, nothing crashes, but the agent is defending the wrong answer.

## Forces

- LLM agents are trained to produce consistent, confident continuations — not to second-guess their own selections
- Multi-agent peer selection is a sequential, high-stakes decision with asymmetric information: you pick before you know what you don't know
- Default ReAct-style tool calling and peer routing does not enforce exploration budgets — the agent is rewarded for finishing, not for looking harder
- The failure is invisible to standard evaluation: final-answer scoring sees only the output, not the narrowing of the decision tree
- Even frontier models (GPT-4, GPT-5) exhibit the failure, suggesting it is structural rather than a capacity deficit

## The move

### The failure mode

When an LLM agent must select among N peers (agents, tools, MCP servers, or model responses), it converges on the first viable candidate within 1–2 rounds and then interprets all subsequent information through that lens. Evidence that would disconfirm the choice is either discounted or re-interpreted as supporting it.

This is **premature commitment** — distinct from hallucination or tool-call failure. The agent is doing exactly what it was designed to do: produce a coherent trajectory. The problem is that coherence emerged from a premature lock-in, not from evidence accumulation.

Two signature patterns:
- **Myopic interaction**: the agent asks the minimum number of questions before selecting
- **Polarized routing**: the agent either over-trusts or systematically avoids a peer class after one bad interaction

### Diagnosis

arXiv:2606.22936 (Mehta, June 2026) shows that hidden-state convergence at step 4 of a multi-step run predicts behavioral consistency — but **r = -0.35 with correctness on HotpotQA**, meaning agents that look most internally consistent are often most wrong. Cross-run agreement metrics amplify this: agents agree with themselves even when wrong.

Detection signals:
- Peer selection happens before ≥2 probe rounds
- Subsequent queries to alternative peers are shallow or pre-dismissed
- Agent references its own prior selection as evidence ("as agent X already confirmed…")

### MACE: Structured Peer Exploration

arXiv:2607.11250 (Choi et al., UW-Madison, July 2026) formalizes this as the **Multi-Agent Exploration problem** — modeled as a Partially Observable Stochastic Game (POSG) — and introduces **Multi-Agent Contextual Exploration (MACE)**:

```
MACE peer selection (per round):
1. Probe budget: reserve N% of total interaction budget for exploration
2. Capability estimation: track peer response quality over interaction history
3. Epsilon-explore: with probability ε, query a peer below current top-rank
4. Confidence gate: if current top peer confidence > threshold, force one alternative probe
5. Downstream regret estimation: weight future interactions by expected regret if current peer is wrong
```

Key insight from the paper: **the value of exploration increases with agent diversity**. Homogeneous agent pools mask the failure because any peer looks equally good. Diverse pools (different capabilities, different context windows) make premature commitment more costly and more likely to be wrong.

### Production intervention stack

**Layer 1 — Exploration budget enforcement**: Explicitly allocate a fraction of the total interaction budget (tokens + rounds) to non-primary peer queries. Track it like a circuit breaker: if the primary peer is selected before the exploration budget is exhausted, inject a forced probe of alternatives.

```python
class ExplorationGate:
    def __init__(self, total_budget: int, explore_fraction: float = 0.3):
        self.explore_budget = int(total_budget * explore_fraction)
        self.spent = 0
        self.primary_selected = False

    def should_explore(self, current_round: int) -> bool:
        if self.primary_selected and self.spent < self.explore_budget:
            self.spent += 1
            return True  # Force alternative peer probe
        return False

    def record_selection(self, peer_id: str, is_primary: bool):
        self.primary_selected = is_primary
```

**Layer 2 — Capability modeling**: Maintain a lightweight peer capability score updated after every interaction. Use it to detect when the agent is stuck on a degrading peer.

**Layer 3 — Commitment rollback trigger**: If a downstream task fails with the selected peer, re-run with an explicit exploration round before retrying. Treat the rollback as a first-class event, not a retry.

**Layer 4 — Diversity-aware routing**: When assembling a multi-agent pool, measure capability diversity explicitly. If all peers score similarly on capability estimation, the agent is in a high-risk homogeneous regime and the exploration budget should be increased.

### The counterintuitive truth

The standard intuition is that more capable agents explore more. The evidence shows the opposite in multi-agent settings: capable agents are *more confident* in their early selections, which causes *faster* lock-in. The fix is not to add more capable agents — it is to enforce structured exploration regardless of capability.

## Receipt

> Receipt pending — 2026-08-01
> arXiv:2607.11250 (MACE paper) code at github.com/deeplearning-wisc/mace was not yet released at time of writing. Production example drawn from the formal framework described in the paper. Validate: run a multi-agent routing experiment with 3+ peers, measure selection timing vs. correctness correlation.

## See also

- [S-05 · Multi-Agent Patterns](s05-multi-agent-patterns.md) — foundation: when to use multiple agents
- [S-06 · Model Routing](s06-model-routing.md) — single-model selection, not multi-agent
- [S-1019 · The Ghost Loop Stack](s1019-the-ghost-loop-stack-when-your-agent-decides-its-own-workflow-and-nobody-traced-it.md) — traceable workflow decisions
- [S-1972 · The Untrusted Tool Output Stack](s1972-the-untrusted-tool-output-stack-when-your-mcp-server-returns-more-than-you-bargained-for.md) — tool output gatekeeping
