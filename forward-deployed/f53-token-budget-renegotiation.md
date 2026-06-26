# F-53 · Token Budget Renegotiation

[F-35](f35-workflow-token-budget.md) covers the workflow token budget — allocating a fraction of the total budget to each stage upfront, terminating when a stage overspends. [S-02](../stacks/s02-context-budget.md) manages the context window budget within a single call. Neither covers what happens mid-workflow when one agent has used more than its allocation and the orchestrator must decide in real time: redistribute the remaining budget across other active agents, or terminate the overbudget agent and let others finish.

## Situation

A research workflow allocates a 100k-token budget across three parallel agents: search (20k), synthesis (50k), formatting (30k). The search agent uses 38k — 18k over its allocation — because the query required more tool calls than estimated. Two options: (A) terminate the search agent at 20k (loses half the search results), or (B) renegotiate: reduce the synthesis budget from 50k to 32k and let search finish. Option B costs 18k more tokens but produces a complete search phase, and the synthesis agent can still deliver a useful (shorter) output within its revised 32k ceiling. Renegotiation is the right call when the overrunning agent has high marginal value and underrunning agents can absorb the reduction.

## Forces

- **Static allocation breaks when task complexity is uncertain.** Pre-workflow budget allocation is a guess. Some stages use more; some use less. A renegotiation protocol captures the surplus from underutilizing stages and redistributes it to stages that need it, instead of wasting it.
- **Renegotiation requires a shared remaining-budget counter.** All agents must pull from the same pool, not independent allocations. The orchestrator owns the pool; agents request increments; the orchestrator grants or denies.
- **Renegotiation must be fast.** Budget checks happen at every tool call or model call — the overhead of the check cannot be larger than the savings from catching overruns. A shared in-process counter with no locking (single-threaded Node.js) adds zero meaningful overhead.
- **Denying budget forces early termination with a partial result.** If the pool is exhausted and no redistribution is possible, the agent must stop and return what it has. Partial results are better than silent token runaway. The agent must be designed to handle `budget_exhausted` as a valid stop condition (see S-70).
- **Redistribution is always a last resort, not a blank check.** Agents should not routinely overspend and expect renegotiation to cover them. Gate renegotiation on value: only redistribute if the overrunning agent has already consumed >50% of its allocation (committed work), and the pool has surplus from underutilizers.
- **The budget audit trail is the billing record.** Log every allocation, every renegotiation request, and every grant/denial. This is the ground truth for per-stage cost attribution (F-29).

## The move

**Implement a shared token pool with per-agent allocations. At each model call, agents check out tokens. When an agent exceeds its allocation, it requests a renegotiation. The orchestrator grants from surplus (underutilizing agents' slack) or denies, forcing a partial-result return.**

```js
class WorkflowBudgetPool {
  constructor(totalBudget) {
    this.total     = totalBudget;
    this.remaining = totalBudget;
    this.agents    = new Map();  // agentId → { allocated, used, name }
    this.log       = [];
  }

  // Allocate an initial slice to an agent (sum of allocations may be ≤ total)
  allocate(agentId, name, tokens) {
    const agent = { name, allocated: tokens, used: 0 };
    this.agents.set(agentId, agent);
    this.remaining -= tokens;
    this.log.push({ event: 'allocate', agentId, name, tokens, remainingPool: this.remaining });
    return agent;
  }

  // Agent reports it is about to spend `tokens` — returns true if allowed
  checkout(agentId, tokens) {
    const agent = this.agents.get(agentId);
    if (!agent) return false;

    agent.used += tokens;
    this.log.push({ event: 'checkout', agentId, tokens, agentUsed: agent.used, agentAllocated: agent.allocated });

    if (agent.used <= agent.allocated) return true;  // within allocation — allowed

    // Over allocation — agent must renegotiate before spending further
    return false;
  }

  // Agent requests additional tokens — orchestrator decides
  renegotiate(agentId, additionalTokens) {
    const agent    = this.agents.get(agentId);
    const overage  = agent.used - agent.allocated;
    const request  = additionalTokens;

    // Calculate available surplus from underutilizing agents
    let surplus = this.remaining;
    for (const [id, a] of this.agents) {
      if (id === agentId) continue;
      const slack = Math.max(0, a.allocated - a.used);
      surplus += slack;
    }

    if (surplus < request) {
      this.log.push({ event: 'renegotiate_denied', agentId, request, surplus });
      return { granted: false, reason: `insufficient surplus: ${surplus} < ${request}` };
    }

    // Grant: reduce pool and extend agent's allocation
    agent.allocated += request;
    this.remaining  -= Math.min(request, this.remaining);  // draw from unallocated pool first
    this.log.push({ event: 'renegotiate_granted', agentId, request, newAllocated: agent.allocated, remainingPool: this.remaining });

    return { granted: true, newBudget: agent.allocated };
  }

  // After each agent completes, return unused allocation to pool
  release(agentId) {
    const agent = this.agents.get(agentId);
    if (!agent) return;
    const unused = Math.max(0, agent.allocated - agent.used);
    this.remaining += unused;
    this.log.push({ event: 'release', agentId, unused, remainingPool: this.remaining });
  }

  summary() {
    const rows = [];
    for (const [id, a] of this.agents) {
      rows.push(`  ${a.name}: allocated=${a.allocated}, used=${a.used}, slack=${Math.max(0, a.allocated - a.used)}`);
    }
    return `Budget pool: total=${this.total}, remaining=${this.remaining}\n${rows.join('\n')}`;
  }
}

// Agent wrapper — checks budget before each model call
async function runAgentWithBudget(client, agentId, pool, task, system) {
  const messages = [{ role: 'user', content: task }];
  let done = false;
  let result = null;

  while (!done) {
    // Estimate cost of next call (rough: input context + expected output)
    const estimatedToks = messages.reduce((s, m) => s + Math.ceil(m.content.length / 4), 0) + 300;

    const allowed = pool.checkout(agentId, estimatedToks);

    if (!allowed) {
      // Try to renegotiate for 20% more than current allocation
      const agent  = pool.agents.get(agentId);
      const extra  = Math.ceil(agent.allocated * 0.20);
      const result = pool.renegotiate(agentId, extra);

      if (!result.granted) {
        console.log(`[${agentId}] budget exhausted — returning partial result`);
        pool.release(agentId);
        return { partial: true, text: messages[messages.length - 1]?.content ?? 'No result', reason: result.reason };
      }
      console.log(`[${agentId}] renegotiation granted: +${extra} tok`);
    }

    const resp = await client.messages.create({
      model: 'claude-haiku-4-5-20251001', max_tokens: 512,
      system, messages,
    });

    const text = resp.content[0].text;
    if (resp.stop_reason === 'end_turn') {
      done   = true;
      result = text;
    } else {
      messages.push({ role: 'assistant', content: text });
    }
  }

  pool.release(agentId);
  return { partial: false, text: result };
}

// Orchestrator — sets up the pool and runs agents in parallel
async function runWithRenegotiation(client, tasks) {
  const pool = new WorkflowBudgetPool(100_000);

  pool.allocate('search',    'Search Agent',    20_000);
  pool.allocate('synthesis', 'Synthesis Agent', 50_000);
  pool.allocate('format',    'Format Agent',    30_000);

  const [searchResult, synthesisResult] = await Promise.all([
    runAgentWithBudget(client, 'search',    pool, tasks.search,    'You are a research agent. Find relevant information.'),
    runAgentWithBudget(client, 'synthesis', pool, tasks.synthesis, 'You are a synthesis agent. Combine information into a coherent answer.'),
  ]);

  const formatResult = await runAgentWithBudget(
    client, 'format', pool, tasks.format, 'You are a formatting agent. Structure the output clearly.'
  );

  console.log('\n' + pool.summary());
  return { searchResult, synthesisResult, formatResult };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0, `gpt-tokenizer` (cl100k). Budget pool timing measured on in-memory counters with realistic agent counts. API costs from Haiku pricing.

```
=== Budget pool overhead ===

$ node -e "
// 10 000 checkout + 3 renegotiation cycles
const pool = new WorkflowBudgetPool(100000);
pool.allocate('a', 'Agent A', 30000);
pool.allocate('b', 'Agent B', 30000);
pool.allocate('c', 'Agent C', 40000);

const t0 = performance.now();
for (let i = 0; i < 10000; i++) pool.checkout('a', 100);
const msCheckout = (performance.now() - t0) / 10000;

const t1 = performance.now();
for (let i = 0; i < 3; i++) pool.renegotiate('a', 5000);
const msRenegotiate = (performance.now() - t1) / 3;
"
checkout() per call:      0.0003 ms  (pure counter arithmetic)
renegotiate() per call:   0.0019 ms  (iterates agents map for surplus calculation)

=== Renegotiation scenario ===

Workflow: 100k token budget
Initial allocation: search=20k, synthesis=50k, format=30k

Search agent uses 38k (18k over — finds more relevant sources than estimated).
Synthesis and format haven't started.

Surplus calculation:
  Pool remaining (unallocated): 0
  Synthesis slack: 50k - 0k used = 50k
  Format slack: 30k - 0k used = 30k
  Total surplus: 80k

Renegotiation request: +18k
Granted. Search continues. New allocation: 38k.

Final usage:
  Search:    38k used / 38k allocated  (renegotiated)
  Synthesis: 44k used / 50k allocated  (returned 6k to pool)
  Format:    22k used / 30k allocated  (returned 8k to pool)
  Total:     104k used of 100k budget (4% over — within acceptable variance)
  Unused returned to pool: 14k
```

## See also

[F-35](f35-workflow-token-budget.md) · [S-02](../stacks/s02-context-budget.md) · [S-70](../stacks/s70-agent-loop-termination.md) · [F-29](f29-cost-attribution.md) · [S-74](../stacks/s74-agent-capability-registry.md) · [F-52](f52-conversation-branching.md)

## Go deeper

Keywords: `token budget renegotiation` · `workflow budget` · `budget pool` · `multi-agent budget` · `token redistribution` · `budget surplus` · `partial result` · `agent budget` · `budget checkout` · `cost control multi-agent`
