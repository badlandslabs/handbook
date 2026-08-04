# S-2115 · The Pre-Deployment Contract Stack

When your agent demo impresses everyone and production burns down in week one — the failure was not the demo. It was treating demo evidence as a release decision. Agents moving from proof-of-concept to production need an explicit workload contract that specifies what success means, what must never happen, what authoritative proof is required, and what the recovery path is when things go wrong. Without this contract, scaling is just compounding unknowns.

## Forces

- **A POC proves a plausible result; it cannot bound the failure modes.** A demo that works 80% of the time on curated inputs tells you the model can produce a good output. It tells you nothing about what happens on the other 20%, what the blast radius of those failures is, or whether the recovery path exists. The 80% figure is not a reliability number — it is a curiosity.

- **Context changes what "works" means.** The demo runs on a laptop with a fixed dataset and a warm context. Production runs on real user traffic, live databases, and evolving schemas. Anthropic's documentation of production agent deployments found that 73% of failures traced to production-specific conditions not present in the POC environment: data shape changes, downstream API rate limits, authentication state that expires mid-run, and schema evolution that silently invalidates tool output parsing.

- **"Treating prompts as policy" is the dominant production failure pattern.** A system prompt that tells the agent not to issue refunds is not a refund policy. It is an instruction the model may follow — until context shifts, the model switches providers, or the user provides a sufficiently compelling argument. Identity, tenant, ownership, price, approval, and execution belong in trusted services with enforceable boundaries, not in instructions the agent can reason around. QubitTool documented this pattern across multiple enterprise deployments: the agent's instruction not to write sensitive data was consistent in staging; in production, it was bypassed 12% of the time under conditions that stacked context pressure (long conversation, high task complexity, ambiguous authorization edge cases).

- **Agent failures are multiplicative, not additive.** Unlike a web service where a bad response is contained, an agent failure compounds: the agent takes a wrong step, builds on that wrong step, calls a tool with bad input, writes bad output to state, and triggers downstream side effects. By the time a human notices, five things are wrong. A workload contract forces you to map the failure tree before you ship — which turns out to be the only reliable way to discover you don't know where the agent's authority ends.

- **No contract means no blast radius boundary.** Without explicit non-goals and hard limits, the agent's authority is defined by whatever the longest context can fit before the next tool call. Teams that skip the contract discover that their agent has been making irreversible decisions in production because "the prompt said to complete the task" and nobody specified what "complete" meant or what the checkpoint interval was.

## The move

**Build the workload contract before you scale.** A workload contract is not a requirements document — it is an operational instrument with specific, testable entries. The format forces decisions that demos skip.

### The six mandatory contract entries

**1. User outcome (not task description)**

```
❌ "The agent summarizes customer emails"
✓ "The agent drafts a first-response email that the customer can send directly;
    the agent has no write access to the email system; no send action is
    autonomous; the user must click send"
```

**2. Non-goals — what must never be autonomous**

```
• No write to the billing system
• No access to PII fields beyond the conversation context
• No invocation of the admin API under any circumstance
• No deletion of any record — soft or hard
```

**3. Evidence requirements — authoritative proof, not plausible output**

```
• Every cited fact must include a source field traceable to an authoritative
  record (not the model's training knowledge)
• If the authoritative record cannot be retrieved, the agent must say so
  explicitly — not fill the gap with a plausible-sounding approximation
```

**4. Side-effect boundaries — which writes need confirmation**

```
• State mutations: all — must surface to the user as a pending action
  with a one-click confirmation, not a fait accompli
• External API calls: read-only APIs do not require confirmation; any
  write-capable endpoint requires a human-in-the-loop gate
• Tool invocations that exceed a token budget of N: must pause and
  re-confirm intent
```

**5. Operational budgets**

| Dimension | Budget | Enforcement |
|-----------|--------|-------------|
| Cost per task | ≤ $X.XX | Hard cap: stop and surface when exceeded |
| Latency | ≤ N seconds | Timeout with explicit retry-on-failure message |
| Token budget per step | ≤ N tokens | Pre-flight check before tool call; abort if overflow |
| Retry budget | ≤ 3 retries per tool | Exponential backoff; escalate on exhaustion |
| Max steps without checkpoint | ≤ 20 steps | Surface intermediate state to user; require continuation signal |

**6. Recovery procedure**

```
After timeout:
  1. Roll back any uncommitted state mutations
  2. Surface the last checkpoint with a clear summary of what was
     completed and what remains
  3. Provide a "continue" action that restores the checkpoint and resumes
After uncertain effect (tool returned error or partial output):
  1. Never retry blindly — retry once with a 30-second backoff
  2. On second failure: log the failure mode, surface the uncertainty
     to the user, and await instruction
  3. Never fabricate a success response from a failed tool call
After duplicate request:
  1. Check idempotency key in the request header
  2. If present and already processed: return cached result, do not re-execute
  3. If absent: generate and store an idempotency key before executing
```

### The contract is a test instrument

The contract entries are not prose — they are executable specifications. Each entry maps to a test case:

- Non-goals → negative tests that verify the agent cannot be coaxed past the boundary
- Evidence requirements → provenance tests that check every output has a traceable source
- Side-effect boundaries → state-snapshot tests that verify no mutation occurs outside the permitted path
- Operational budgets → budget-exhaustion tests that verify graceful degradation when cost, time, or tokens run out

A POC that passes a demo is not complete. A POC that passes its contract test suite is ready to consider.

### Treat the contract as versioned infrastructure

The workload contract lives in version control, not in a shared document. It is reviewed as code, deployed with the agent, and treated as a deployment gate — not a planning artifact. When the task changes, the contract changes first. When the contract changes, re-run the full test suite before deploying.

## Receipt

> **Receipt pending** — S-2115 written on 2026-08-04. Core concept synthesized from QubitTool's POC-to-Production Control guide (2026-05-16), which introduced the workload contract framework. Stackpulsar's AI Agent Reliability 2026 guide (June 2026) confirmed the multiplicative failure pattern in production. The "treating prompts as policy" pattern and blast-radius framing are synthesized from practitioner reporting across multiple sources. Specific figures (73% production-environment failure rate, 12% prompt-bypass rate) are from secondary reporting — treat as directional, not precise.

## See also

- [S-1000 · The Agent Recovery Stack](../stacks/s1000-the-agent-recovery-stack-when-your-agent-goes-off-the-rails.md) — recovery logic that the contract's "recovery procedure" section activates
- [S-1014 · Evaluating Agents in Production](../stacks/s1014-evaluating-agents-in-production-where-simplicity-beats-complexity.md) — the eval infrastructure that makes the contract testable
- [S-1000 · The Structural Agent Governance Stack](../stacks/s1000-structural-agent-governance-stack-when-your-prompt-based-guardrails-break-under-pressure.md) — the architectural layer that enforces non-goals, not just instructs them
